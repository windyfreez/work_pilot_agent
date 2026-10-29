"""Agent 组装、模型客户端与运行器的测试（不连接真实模型）。"""

import time
from pathlib import Path

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from workpilot.agent import AgentRunner, AgentTimeoutError, build_agent, get_chat_model
from workpilot.agent.builder import build_system_prompt
from workpilot.config import Settings
from workpilot.schemas.tools import (
    CreateDocumentInput,
    ListFilesInput,
    ReadDocumentInput,
)
from workpilot.tools.registry import build_tools


class ToolCapableFakeChatModel(GenericFakeChatModel):
    """支持 ``bind_tools`` 的假模型：``create_agent`` 需要调用 ``bind_tools``。"""

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


class SlowFakeChatModel(ToolCapableFakeChatModel):
    """每次生成前休眠一段时间的假模型，用于测试超时。"""

    delay: float = 1.0

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        time.sleep(self.delay)
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def _tool_call(name: str, args: dict, call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def test_get_chat_model_config():
    settings = Settings(
        llm_model="deepseek-chat",
        llm_base_url="https://api.deepseek.com",
        llm_api_key="sk-test-placeholder",
        llm_temperature=0.3,
        llm_request_timeout=30.0,
    )
    model = get_chat_model(settings)
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "deepseek-chat"
    assert model.openai_api_base == "https://api.deepseek.com"
    assert model.temperature == 0.3
    assert model.request_timeout == 30.0
    assert model.openai_api_key is not None  # 密钥已从配置传入，非硬编码


def test_build_tools_registers_three_tools():
    tools = build_tools(Settings(allowed_dirs=[Path(".")]))
    assert sorted(t.name for t in tools) == ["create_document", "list_files", "read_document"]


def test_build_tools_args_schemas():
    tools = {t.name: t for t in build_tools(Settings(allowed_dirs=[Path(".")]))}
    assert tools["list_files"].args_schema is ListFilesInput
    assert tools["read_document"].args_schema is ReadDocumentInput
    assert tools["create_document"].args_schema is CreateDocumentInput


def test_build_agent_runs_single_tool_loop(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    fake = ToolCapableFakeChatModel(
        messages=iter(
            [
                _tool_call("list_files", {"directory": "."}, "c1"),
                AIMessage(content="文件已列出"),
            ]
        )
    )
    agent = build_agent(settings=Settings(allowed_dirs=[tmp_path]), model=fake)
    result = agent.invoke({"messages": [{"role": "user", "content": "列出文件"}]})
    messages = result["messages"]
    assert any(getattr(m, "type", None) == "tool" for m in messages)
    assert messages[-1].content == "文件已列出"


def test_multi_step_tool_loop(tmp_path: Path):
    """完整循环：模型依次调用两个工具，工具结果回传模型后再给最终回答。"""
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    fake = ToolCapableFakeChatModel(
        messages=iter(
            [
                _tool_call("list_files", {"directory": "."}, "c1"),
                _tool_call("read_document", {"path": "a.txt"}, "c2"),
                AIMessage(content="完成"),
            ]
        )
    )
    agent = build_agent(settings=Settings(allowed_dirs=[tmp_path]), model=fake)
    result = agent.invoke({"messages": [{"role": "user", "content": "处理文件"}]})
    messages = result["messages"]
    ok_calls = [
        m
        for m in messages
        if getattr(m, "type", None) == "tool" and getattr(m, "status", None) != "error"
    ]
    assert len(ok_calls) == 2
    assert messages[-1].content == "完成"


def test_tool_error_captured_and_returned_to_model(tmp_path: Path):
    """工具抛 PathError 时被捕获为 error ToolMessage 返回模型，运行不中断。"""
    fake = ToolCapableFakeChatModel(
        messages=iter(
            [
                _tool_call("read_document", {"path": "missing.txt"}, "c1"),
                AIMessage(content="读取失败，文件不存在"),
            ]
        )
    )
    agent = build_agent(settings=Settings(allowed_dirs=[tmp_path]), model=fake)
    result = agent.invoke({"messages": [{"role": "user", "content": "读文件"}]})
    messages = result["messages"]
    assert any(
        getattr(m, "type", None) == "tool" and getattr(m, "status", None) == "error"
        for m in messages
    )
    assert messages[-1].content == "读取失败，文件不存在"


def test_tool_call_limit_stops_gracefully(tmp_path: Path):
    """工具调用次数达到上限后优雅结束，不再执行超限调用。"""
    fake = ToolCapableFakeChatModel(
        messages=iter(
            [
                _tool_call("list_files", {"directory": "."}, "c1"),
                _tool_call("list_files", {"directory": "."}, "c2"),
                _tool_call("list_files", {"directory": "."}, "c3"),
            ]
        )
    )
    agent = build_agent(
        settings=Settings(allowed_dirs=[tmp_path]), model=fake, max_tool_calls=2
    )
    result = agent.invoke({"messages": [{"role": "user", "content": "x"}]})
    messages = result["messages"]
    ok_calls = [
        m
        for m in messages
        if getattr(m, "type", None) == "tool" and getattr(m, "status", None) != "error"
    ]
    assert len(ok_calls) == 2
    assert "limit" in (messages[-1].content or "").lower()


def test_runner_returns_structured_result(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")
    fake = ToolCapableFakeChatModel(
        messages=iter(
            [
                _tool_call("list_files", {"directory": "."}, "c1"),
                AIMessage(content="done"),
            ]
        )
    )
    runner = AgentRunner(settings=Settings(allowed_dirs=[tmp_path]), model=fake)
    result = runner.run("列出文件")
    assert result.output == "done"
    assert result.tool_calls == 1


def test_runner_timeout(tmp_path: Path):
    slow = SlowFakeChatModel(delay=0.5, messages=iter([AIMessage(content="done")]))
    runner = AgentRunner(
        settings=Settings(allowed_dirs=[tmp_path], agent_timeout_seconds=0.1),
        model=slow,
    )
    with pytest.raises(AgentTimeoutError):
        runner.run("hi")


def test_system_prompt_includes_allowed_dirs(tmp_path: Path):
    prompt = build_system_prompt([tmp_path / "data"])
    assert str(tmp_path / "data") in prompt
    assert "相对路径" in prompt
