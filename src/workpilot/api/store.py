"""任务元数据与执行日志的 SQLite 持久化（独立于 LangGraph checkpoint）。"""

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# 任务状态
PENDING = "pending"
RUNNING = "running"
WAITING_APPROVAL = "waiting_approval"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"

TERMINAL_STATUSES = {SUCCEEDED, FAILED, CANCELLED}


class TaskNotFoundError(KeyError):
    """任务不存在。"""


class TaskStore:
    """任务表：对外查询的状态、结果、日志。工作流恢复走 LangGraph checkpoint。"""

    def __init__(self, db_path: str | Path):
        self._db_path = str(db_path)
        self._lock = threading.Lock()
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ---- 底层连接管理 ----
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _write(self, fn: Callable[[sqlite3.Connection], Any]) -> Any:
        with self._lock:
            conn = self._connect()
            try:
                result = fn(conn)
                conn.commit()
                return result
            finally:
                conn.close()

    def _read(self, fn: Callable[[sqlite3.Connection], Any]) -> Any:
        with self._lock:
            conn = self._connect()
            try:
                return fn(conn)
            finally:
                conn.close()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _init_schema(self) -> None:
        def _init(conn: sqlite3.Connection) -> None:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    input TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result_json TEXT,
                    error TEXT,
                    approval_requested INTEGER DEFAULT 0,
                    approval_decision INTEGER,
                    cancel_requested INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    level TEXT DEFAULT 'info',
                    message TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_task_logs_task ON task_logs(task_id)")

        self._write(_init)

    # ---- 任务 CRUD ----
    def create_task(self, task_input: str, task_id: str | None = None) -> str:
        task_id = task_id or uuid.uuid4().hex
        now = self._now()

        def _create(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO tasks (task_id, input, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (task_id, task_input, PENDING, now, now),
            )
            conn.execute(
                "INSERT INTO task_logs (task_id, level, message, created_at) VALUES (?, ?, ?, ?)",
                (task_id, "info", "任务已创建", now),
            )

        self._write(_create)
        return task_id

    def get_task(self, task_id: str) -> dict:
        row = self._read(lambda conn: conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)).fetchone())
        if row is None:
            raise TaskNotFoundError(task_id)
        return dict(row)

    def update_status(
        self,
        task_id: str,
        status: str,
        *,
        result: dict | None = None,
        error: str | None = None,
        approval_requested: bool | None = None,
        approval_decision: bool | None = None,
    ) -> None:
        now = self._now()
        fields = ["status = ?", "updated_at = ?"]
        params: list[Any] = [status, now]
        if result is not None:
            fields.append("result_json = ?")
            params.append(json.dumps(result, ensure_ascii=False, default=str))
        if error is not None:
            fields.append("error = ?")
            params.append(error)
        if approval_requested is not None:
            fields.append("approval_requested = ?")
            params.append(1 if approval_requested else 0)
        if approval_decision is not None:
            fields.append("approval_decision = ?")
            params.append(1 if approval_decision else 0)
        params.append(task_id)

        def _update(conn: sqlite3.Connection) -> None:
            conn.execute(f"UPDATE tasks SET {', '.join(fields)} WHERE task_id = ?", params)

        self._write(_update)

    def set_cancel_requested(self, task_id: str) -> None:
        now = self._now()
        self._write(
            lambda conn: conn.execute(
                "UPDATE tasks SET cancel_requested = 1, updated_at = ? WHERE task_id = ?",
                (now, task_id),
            )
        )

    def is_cancel_requested(self, task_id: str) -> bool:
        row = self._read(
            lambda conn: conn.execute("SELECT cancel_requested FROM tasks WHERE task_id = ?", (task_id,)).fetchone()
        )
        return bool(row and row["cancel_requested"])

    def set_approval(self, task_id: str, approved: bool) -> None:
        now = self._now()
        self._write(
            lambda conn: conn.execute(
                "UPDATE tasks SET approval_decision = ?, updated_at = ? WHERE task_id = ?",
                (1 if approved else 0, now, task_id),
            )
        )

    # ---- 日志与结果 ----
    def add_log(self, task_id: str, level: str, message: str) -> None:
        now = self._now()
        self._write(
            lambda conn: conn.execute(
                "INSERT INTO task_logs (task_id, level, message, created_at) VALUES (?, ?, ?, ?)",
                (task_id, level, message, now),
            )
        )

    def get_logs(self, task_id: str) -> list[dict]:
        rows = self._read(
            lambda conn: conn.execute(
                "SELECT level, message, created_at FROM task_logs WHERE task_id = ? ORDER BY id",
                (task_id,),
            ).fetchall()
        )
        return [dict(r) for r in rows]

    def get_result(self, task_id: str) -> dict | None:
        task = self.get_task(task_id)
        raw = task.get("result_json")
        return json.loads(raw) if raw else None

    # ---- worker 轮询 ----
    def poll_due_tasks(self) -> list[tuple[str, str]]:
        """返回需要 worker 处理的任务：``(task_id, action)``，action ∈ ``run``/``resume``。"""

        def _poll(conn: sqlite3.Connection) -> list[tuple[str, str]]:
            run_rows = conn.execute(
                "SELECT task_id FROM tasks WHERE status = ? AND cancel_requested = 0 ORDER BY created_at",
                (PENDING,),
            ).fetchall()
            resume_rows = conn.execute(
                "SELECT task_id FROM tasks WHERE status = ? AND approval_decision IS NOT NULL "
                "AND cancel_requested = 0 ORDER BY created_at",
                (WAITING_APPROVAL,),
            ).fetchall()
            return [(r["task_id"], "run") for r in run_rows] + [
                (r["task_id"], "resume") for r in resume_rows
            ]

        return self._read(_poll)
