"""任务工作流运行器：checkpoint 持久化 + run/resume + 超时。"""

import queue
import sqlite3
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command

from workpilot.agent.llm import get_chat_model
from workpilot.config import Settings

from .graph import build_graph
from .state import VerificationResult


class TaskTimeoutError(RuntimeError):
    """任务工作流单次运行超时。"""


@dataclass
class TaskOutcome:
    """任务工作流的运行结果。"""

    task_id: str
    status: str
    output: str = ""
    plan: list = field(default_factory=list)
    results: list = field(default_factory=list)
    verification: VerificationResult | None = None
    confirmation: str | None = None
    error: str | None = None


def _invoke_with_timeout(graph, payload, config: dict, timeout: float) -> dict:
    """在守护线程中执行 ``graph.invoke``，超时则抛出 ``TaskTimeoutError``。"""
    q: queue.Queue = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            q.put(("ok", graph.invoke(payload, config=config)))
        except Exception as exc:  # noqa: BLE001 - 转发给调用方线程
            q.put(("err", exc))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        status, value = q.get(timeout=timeout)
    except queue.Empty:
        raise TaskTimeoutError(f"任务执行超过 {timeout} 秒") from None
    if status == "err":
        raise value
    return value


class WorkflowRunner:
    """可控任务工作流：规划 → 执行 → 验证，支持 checkpoint 持久化与人工确认。"""

    def __init__(
        self,
        settings: Settings | None = None,
        model: BaseChatModel | None = None,
        checkpointer=None,
        should_cancel=None,
    ):
        self._settings = settings or Settings()
        self._model = model or get_chat_model(self._settings)
        self._should_cancel = should_cancel or (lambda task_id: False)

        if checkpointer is not None:
            self._checkpointer = checkpointer
            self._owns_checkpointer = False
        else:
            self._checkpointer = self._build_sqlite_checkpointer()
            self._owns_checkpointer = True

        self._graph = build_graph(
            self._settings,
            self._model,
            self._checkpointer,
            should_cancel=self._should_cancel,
        )

    def _build_sqlite_checkpointer(self) -> SqliteSaver:
        db_path = Path(self._settings.checkpoint_db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        return SqliteSaver(conn)

    def run(self, task_input: str, task_id: str | None = None) -> TaskOutcome:
        """启动一个任务；若遇人工确认会暂停并返回 awaiting_confirmation。"""
        task_id = task_id or uuid4().hex
        config = {"configurable": {"thread_id": task_id}}
        payload = {"task_id": task_id, "task_input": task_input}
        state = self._invoke(payload, config)
        return self._to_outcome(task_id, state)

    def resume(self, task_id: str, approve: bool) -> TaskOutcome:
        """对暂停中的人工确认做出决定并继续执行。"""
        config = {"configurable": {"thread_id": task_id}}
        state = self._invoke(Command(resume=approve), config)
        return self._to_outcome(task_id, state)

    def _invoke(self, payload, config: dict) -> dict:
        timeout = self._settings.task_timeout_seconds
        if timeout is None:
            return self._graph.invoke(payload, config=config)
        return _invoke_with_timeout(self._graph, payload, config, timeout)

    def _to_outcome(self, task_id: str, state: dict) -> TaskOutcome:
        interrupts = state.get("__interrupt__")
        if interrupts:
            payload = interrupts[0].value
            description = payload.get("description") if isinstance(payload, dict) else str(payload)
            return TaskOutcome(
                task_id=task_id,
                status="awaiting_confirmation",
                confirmation=description or str(payload),
            )

        results = list(state.get("results", []))
        return TaskOutcome(
            task_id=task_id,
            status=state.get("status", "unknown"),
            output=results[-1] if results else "",
            plan=[s.model_dump() for s in state.get("plan", [])],
            results=results,
            verification=state.get("verification"),
            error=state.get("error"),
        )

    def close(self) -> None:
        """关闭自建的 SQLite 连接。"""
        if self._owns_checkpointer and hasattr(self._checkpointer, "conn"):
            self._checkpointer.conn.close()
