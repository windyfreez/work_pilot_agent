"""后台任务执行线程：解耦「创建任务」与「实际执行」。"""

import threading

from .store import (
    CANCELLED,
    FAILED,
    PENDING,
    RUNNING,
    SUCCEEDED,
    WAITING_APPROVAL,
    TaskStore,
)


class TaskWorker:
    """轮询 SQLite 中待办任务，调用工作流执行；长任务不因 HTTP 超时丢失状态。"""

    def __init__(self, store: TaskStore, runner, poll_interval: float = 0.5):
        self._store = store
        self._runner = runner
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, daemon=True, name="task-worker")
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def process_once(self) -> None:
        """处理一轮待办任务（测试/手动触发用）。"""
        for task_id, action in self._store.poll_due_tasks():
            try:
                if action == "run":
                    self._run(task_id)
                else:
                    self._resume(task_id)
            except Exception as exc:  # noqa: BLE001 - 记录后继续处理下一个
                self._store.add_log(task_id, "error", f"处理异常：{exc}")

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.process_once()
            except Exception:  # noqa: BLE001 - 轮询循环不能因异常退出
                pass
            self._stop.wait(self._poll_interval)

    def _run(self, task_id: str) -> None:
        task = self._store.get_task(task_id)
        if task["cancel_requested"]:
            self._store.update_status(task_id, CANCELLED)
            self._store.add_log(task_id, "info", "任务已取消")
            return

        self._store.update_status(task_id, RUNNING)
        self._store.add_log(task_id, "info", "开始执行工作流")
        try:
            outcome = self._runner.run(task["input"], task_id)
            self._handle_outcome(task_id, outcome)
        except Exception as exc:  # noqa: BLE001
            self._store.update_status(task_id, FAILED, error=str(exc))
            self._store.add_log(task_id, "error", f"执行失败：{exc}")

    def _resume(self, task_id: str) -> None:
        task = self._store.get_task(task_id)
        decision = bool(task["approval_decision"])
        self._store.update_status(task_id, RUNNING, approval_decision=decision)
        self._store.add_log(task_id, "info", "审批通过，继续执行" if decision else "审批拒绝，终止任务")
        try:
            outcome = self._runner.resume(task_id, decision)
            self._handle_outcome(task_id, outcome)
        except Exception as exc:  # noqa: BLE001
            self._store.update_status(task_id, FAILED, error=str(exc))
            self._store.add_log(task_id, "error", f"执行失败：{exc}")

    def _handle_outcome(self, task_id: str, outcome) -> None:
        if outcome.status == "awaiting_confirmation":
            self._store.update_status(task_id, WAITING_APPROVAL, approval_requested=True)
            self._store.add_log(task_id, "warn", f"等待人工确认：{outcome.confirmation}")
        elif outcome.status == "succeeded":
            self._store.update_status(task_id, SUCCEEDED, result=self._outcome_to_dict(outcome))
            self._store.add_log(task_id, "info", "任务成功")
        elif outcome.status == "cancelled":
            self._store.update_status(task_id, CANCELLED)
            self._store.add_log(task_id, "info", "任务已取消")
        else:
            self._store.update_status(task_id, FAILED, error=outcome.error)
            self._store.add_log(task_id, "error", f"任务失败：{outcome.error}")

    @staticmethod
    def _outcome_to_dict(outcome) -> dict:
        verification = outcome.verification.model_dump() if outcome.verification else None
        return {
            "output": outcome.output,
            "plan": outcome.plan,
            "results": outcome.results,
            "verification": verification,
            "error": outcome.error,
        }
