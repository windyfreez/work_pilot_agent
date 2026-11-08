"""Agent 组装、模型客户端与运行器的测试（不连接真实模型）。"""

import time
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
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


class ReflectiveToolModel(BaseChatModel):
    """第一轮发起固定工具调用；第二轮读取真实 ``ToolMessage`` 内容作答。

    用于证明「真实执行闭环」：最终回答由真实工具结果驱动，而非脚本硬编码。
    """

    tool_name: str
    tool_args: dict
    answer_template: str = "工具结果：{result}"

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        if not tool_msgs:
            return ChatResult(
                generations=[
                    ChatGeneration(
                        message=AIMessage(
                            content="",
                            tool_calls=[
                                {"name": self.tool_name, "args": self.tool_args, "id": "call_1"}
                            ],
                        )
                    )
                ]
            )
        real_result = tool_msgs[-1].content
        return ChatResult(
            generations=[
                ChatGeneration(
                    message=AIMessage(content=self.answer_template.format(result=real_result))
                )
            ]
        )

    @property
    def _llm_type(self) -> str:
        return "reflective-tool-model"


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


def test_read_loop_uses_real_file_content(tmp_path: Path):
    """真实闭环：模型发起工具调用 → 程序真实读文件 → 模型基于真实内容作答。"""
    (tmp_path / "doc.txt").write_text("真实内容ABC", encoding="utf-8")
    model = ReflectiveToolModel(
        tool_name="read_document",
        tool_args={"path": "doc.txt"},
        answer_template="读取到的内容：{result}",
    )
    agent = build_agent(settings=Settings(allowed_dirs=[tmp_path]), model=model)
    result = agent.invoke({"messages": [{"role": "user", "content": "读取 doc.txt"}]})
    messages = result["messages"]

    # 1) 模型确实发起了工具调用
    assert any(
        getattr(m, "type", None) == "ai" and getattr(m, "tool_calls", None)
        for m in messages
    )
    # 2) 工具真实执行，ToolMessage 内容就是磁盘上的真实内容
    tool_msgs = [
        m
        for m in messages
        if getattr(m, "type", None) == "tool" and getattr(m, "status", None) == "success"
    ]
    assert len(tool_msgs) == 1
    assert tool_msgs[0].content == "真实内容ABC"
    # 3) 最终回答由真实结果驱动（包含真实内容，而非硬编码）
    assert "真实内容ABC" in messages[-1].content


def test_create_loop_actually_writes_file(tmp_path: Path):
    """真实闭环（写路径）：模型发起 create_document → 磁盘真实落盘 → 模型引用真实返回路径。"""
    model = ReflectiveToolModel(
        tool_name="create_document",
        tool_args={"path": "out.txt", "content": "写入的内容XYZ"},
        answer_template="已创建：{result}",
    )
    agent = build_agent(settings=Settings(allowed_dirs=[tmp_path]), model=model)
    result = agent.invoke({"messages": [{"role": "user", "content": "创建 out.txt"}]})
    messages = result["messages"]

    # 1) 工具真实执行（成功 ToolMessage）
    tool_msgs = [
        m
        for m in messages
        if getattr(m, "type", None) == "tool" and getattr(m, "status", None) == "success"
    ]
    assert len(tool_msgs) == 1
    # 2) 磁盘上真实出现了文件，且内容正确
    assert (tmp_path / "out.txt").read_text(encoding="utf-8") == "写入的内容XYZ"
    # 3) 最终回答引用了真实的返回路径
    assert str(tmp_path / "out.txt") in messages[-1].content
