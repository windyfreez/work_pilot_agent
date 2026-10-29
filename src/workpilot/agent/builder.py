"""组装 LangChain 工具调用 Agent。"""

from pathlib import Path

from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware, ToolErrorMiddleware
from langchain_core.language_models.chat_models import BaseChatModel

from workpilot.config import Settings
from workpilot.tools._paths import PathError
from workpilot.tools.registry import build_tools

from .llm import get_chat_model

def build_system_prompt(allowed_dirs: list[Path]) -> str:
    """根据授权目录构造系统提示词，明确告知模型可操作的具体路径。"""
    dirs = "\n".join(f"- {p}" for p in allowed_dirs)
    return (
        "你是 WorkPilot 办公助手，负责执行文档读写类办公任务。\n\n"
        f"授权目录（你只能读写这些目录内的文件，绝对路径如下）：\n{dirs}\n\n"
        "规则：\n"
        "1. 操作文件前先用 list_files 查看目录，再按需 read_document / create_document。\n"
        "2. 工具的 path / directory 参数可用相对路径（相对于第一个授权目录）或上述绝对路径。\n"
        "3. 不要尝试授权目录之外的路径（如 ../、/ 等）。"
    )


def _on_tool_error(exc: Exception, request) -> str | None:
    """把可安全暴露的工具异常转成错误消息返回给模型；其余异常照常抛出。"""
    if isinstance(exc, (PathError, OSError)):
        tool_call = getattr(request, "tool_call", None)
        name = tool_call.get("name", "未知工具") if tool_call else "未知工具"
        return f"工具 `{name}` 执行失败：{type(exc).__name__}: {exc}"
    return None


def build_agent(
    settings: Settings | None = None,
    model: BaseChatModel | None = None,
    *,
    max_tool_calls: int | None = None,
):
    """构建一个已注册文件工具的 LangChain Agent。

    - 工具异常经 ``ToolErrorMiddleware`` 捕获后作为错误消息返回模型（不中断运行）。
    - 工具调用次数经 ``ToolCallLimitMiddleware`` 限制，达到上限后优雅结束。

    返回的 Agent 可用如下方式调用：
        result = agent.invoke({"messages": [{"role": "user", "content": "..."}]})
    """
    settings = settings or Settings()
    chat_model = model or get_chat_model(settings)
    tools = build_tools(settings)

    limit = max_tool_calls if max_tool_calls is not None else settings.agent_max_tool_calls
    middleware = [
        ToolErrorMiddleware(on_error=_on_tool_error),
        ToolCallLimitMiddleware(run_limit=limit, exit_behavior="end"),
    ]
    return create_agent(
        model=chat_model,
        tools=tools,
        system_prompt=build_system_prompt(settings.allowed_dirs),
        middleware=middleware,
    )
