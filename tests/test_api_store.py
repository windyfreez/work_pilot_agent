"""TaskStore 单元测试。"""

import pytest

from workpilot.api.store import (
    CANCELLED,
    PENDING,
    SUCCEEDED,
    WAITING_APPROVAL,
    TaskNotFoundError,
    TaskStore,
)


@pytest.fixture
def store(tmp_path) -> TaskStore:
    return TaskStore(str(tmp_path / "tasks.sqlite"))


def test_create_and_get(store: TaskStore):
    tid = store.create_task("创建报告")
    task = store.get_task(tid)
    assert task["status"] == PENDING
    assert task["input"] == "创建报告"


def test_task_not_found(store: TaskStore):
    with pytest.raises(TaskNotFoundError):
        store.get_task("nonexistent")


def test_update_status_and_result(store: TaskStore):
    tid = store.create_task("x")
    store.update_status(tid, SUCCEEDED, result={"output": "ok"})
    assert store.get_task(tid)["status"] == SUCCEEDED
    assert store.get_result(tid) == {"output": "ok"}


def test_logs(store: TaskStore):
    tid = store.create_task("x")
    store.add_log(tid, "info", "开始")
    store.add_log(tid, "error", "失败")
    logs = store.get_logs(tid)
    assert [l["message"] for l in logs] == ["任务已创建", "开始", "失败"]


def test_cancel_flag(store: TaskStore):
    tid = store.create_task("x")
    assert store.is_cancel_requested(tid) is False
    store.set_cancel_requested(tid)
    assert store.is_cancel_requested(tid) is True


def test_poll_due_tasks(store: TaskStore):
    tid1 = store.create_task("a")
    tid2 = store.create_task("b")
    assert set(store.poll_due_tasks()) == {(tid1, "run"), (tid2, "run")}

    store.update_status(tid1, WAITING_APPROVAL)
    store.set_approval(tid1, True)
    assert set(store.poll_due_tasks()) == {(tid2, "run"), (tid1, "resume")}
