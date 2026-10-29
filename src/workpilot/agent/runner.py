"""Agent 运行器：完整工具调用循环 + 超时 + 结构化结果。"""

import queue
import threading
from dataclasses import dataclass, field
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from workpilot.config import Settings

from .builder import build_agent


class AgentTimeoutError(RuntimeError):
    """Agent 单次运行超时。"""


@dataclass
class AgentRunResult:
    """Agent 运行结果。"""

    output: str
    messages: list[Any] = field(default_factory=list)
    tool_calls: int = 0


def _invoke_with_timeout(agent, payload: dict, timeout: float) -> dict:
    """在独立守护线程中执行 ``agent.invoke``，超时则抛出 ``AgentTimeoutError``。

    说明：超时后守护线程仍在后台继续，不会阻塞进程退出；这是无第三方依赖的
    跨平台超时实现（Windows 无 SIGALRM）。
    """
    q: queue.Queue = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            q.put(("ok", agent.invoke(payload)))
        except Exception as exc:  # noqa: BLE001 - 转发给调用方线程
            q.put(("err", exc))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        status, value = q.get(timeout=timeout)
    except queue.Empty:
        raise AgentTimeoutError(f"Agent 运行超过 {timeout} 秒") from None
    if status == "err":
        raise value
    return value


class AgentRunner:
    """对 LangChain Agent 的高层封装：提供整体超时与结构化结果。"""

    def __init__(self, settings: Settings | None = None, model: BaseChatModel | None = None):
        self._settings = settings or Settings()
        self._agent = build_agent(self._settings, model)

    def run(self, user_input: str) -> AgentRunResult:
        """运行一次 Agent 任务，返回结构化结果。"""
        payload = {"messages": [{"role": "user", "content": user_input}]}
        timeout = self._settings.agent_timeout_seconds

        if timeout is None:
            result = self._agent.invoke(payload)
        else:
            result = _invoke_with_timeout(self._agent, payload, timeout)

        messages = list(result.get("messages", []))
        last = messages[-1] if messages else None
        output = getattr(last, "content", "") or ""
        tool_calls = sum(1 for m in messages if getattr(m, "type", None) == "tool")
        return AgentRunResult(output=output, messages=messages, tool_calls=tool_calls)
