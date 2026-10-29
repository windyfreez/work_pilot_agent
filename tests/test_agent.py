"""Agent 组装与模型客户端的测试（不连接真实模型）。"""

from pathlib import Path

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from workpilot.agent import build_agent, get_chat_model
from workpilot.config import Settings
from workpilot.schemas.tools import (
    CreateDocumentInput,
    ListFilesInput,
    ReadDocumentInput,
)
from workpilot.tools.registry import build_tools


class ToolCapableFakeChatModel(GenericFakeChatModel):
    """支持 ``bind_tools`` 的假模型。

    ``create_agent`` 内部会调用 ``model.bind_tools(tools)`` 把工具绑定到模型，
    而 ``GenericFakeChatModel`` 未实现该方法，这里直接返回自身。
    """

    def bind_tools(self, tools, *, tool_choice=None, **kwargs):
        return self


def test_get_chat_model_config():
    settings = Settings(
        llm_model="deepseek-chat",
        llm_base_url="https://api.deepseek.com",
        llm_api_key="sk-test-placeholder",
        llm_temperature=0.3,
    )
    model = get_chat_model(settings)
    assert isinstance(model, ChatOpenAI)
    assert model.model_name == "deepseek-chat"
    assert model.openai_api_base == "https://api.deepseek.com"
    assert model.temperature == 0.3
    assert model.openai_api_key is not None  # 密钥已从配置传入，非硬编码


def test_build_tools_registers_three_tools():
    tools = build_tools(Settings(allowed_dirs=[Path(".")]))
    assert sorted(t.name for t in tools) == ["create_document", "list_files", "read_document"]


def test_build_tools_args_schemas():
    tools = {t.name: t for t in build_tools(Settings(allowed_dirs=[Path(".")]))}
    assert tools["list_files"].args_schema is ListFilesInput
    assert tools["read_document"].args_schema is ReadDocumentInput
    assert tools["create_document"].args_schema is CreateDocumentInput


def test_build_agent_runs_tool_loop(tmp_path: Path):
    (tmp_path / "a.txt").write_text("hi", encoding="utf-8")

    fake_model = ToolCapableFakeChatModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": "list_files", "args": {"directory": "."}, "id": "call_1"}
                    ],
                ),
                AIMessage(content="文件已列出"),
            ]
        )
    )

    agent = build_agent(settings=Settings(allowed_dirs=[tmp_path]), model=fake_model)
    result = agent.invoke({"messages": [{"role": "user", "content": "列出文件"}]})

    messages = result["messages"]
    # 至少发生了一次工具调用，且最终回答来自模型的第二次回复
    assert any(getattr(m, "type", None) == "tool" for m in messages)
    assert messages[-1].content == "文件已列出"
