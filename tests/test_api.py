"""API 端点端到端测试（TestClient + 假模型 + 手动触发 worker）。"""

import hashlib
from pathlib import Path

import chromadb
import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.memory import InMemorySaver

from workpilot.api import create_app
from workpilot.api.store import CANCELLED, FAILED, PENDING, SUCCEEDED, WAITING_APPROVAL, TaskStore
from workpilot.config import Settings
from workpilot.workflow import Plan, PlanStep


class FakePlanningModel(BaseChatModel):
    """返回脚本化计划的假模型。"""

    plan: Plan

    def with_structured_output(self, schema, **kwargs):
        plan = self.plan

        class Planner:
            def invoke(self, *args, **kwargs):
                return plan

        return Planner()

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError

    @property
    def _llm_type(self) -> str:
        return "fake-planning-model"


class CharNGramEmbeddings:
    """字符 n-gram 哈希嵌入（离线、确定性）。"""

    def __init__(self, dim: int = 4096, n: int = 3):
        self.dim = dim
        self.n = n

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        t = text.lower()
        for i in range(len(t) - self.n + 1):
            h = int(hashlib.md5(t[i : i + self.n].encode()).hexdigest(), 16) % self.dim
            vec[h] += 1.0
        norm = sum(v * v for v in vec) ** 0.5
        return [v / norm for v in vec] if norm else vec

    def embed_documents(self, texts):
        return [self._embed(t) for t in texts]

    def embed_query(self, text):
        return self._embed(text)


def _make_client(tmp_path: Path, plan: Plan):
    settings = Settings(
        allowed_dirs=[tmp_path / "data"],
        tasks_db_path=str(tmp_path / "tasks.sqlite"),
        checkpoint_db_path=str(tmp_path / "checkpoints.sqlite"),
    )
    (tmp_path / "data").mkdir(parents=True)
    store = TaskStore(settings.tasks_db_path)
    model = FakePlanningModel(plan=plan)
    app = create_app(
        settings=settings,
        model=model,
        store=store,
        checkpointer=InMemorySaver(),
        embedding=CharNGramEmbeddings(),
        rag_client=chromadb.PersistentClient(path=str(tmp_path / "cdb")),
        start_worker=False,
    )
    return TestClient(app), app


def _create_plan(path: str = "report.md", content: str = "# 报告") -> Plan:
    return Plan(steps=[PlanStep(step=1, tool="create_document", args={"path": path, "content": content})])


def test_create_task_returns_pending(tmp_path: Path):
    client, _ = _make_client(tmp_path, _create_plan())
    resp = client.post("/api/tasks", json={"input": "创建报告"})
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == PENDING
    assert body["task_id"]

    # 创建即返回 pending，尚未执行（解耦）
    got = client.get(f"/api/tasks/{body['task_id']}").json()
    assert got["status"] == PENDING


def test_task_succeeds_via_worker(tmp_path: Path):
    client, app = _make_client(tmp_path, _create_plan())
    tid = client.post("/api/tasks", json={"input": "创建报告"}).json()["task_id"]

    app.state.worker.process_once()
    got = client.get(f"/api/tasks/{tid}").json()
    assert got["status"] == SUCCEEDED

    result = client.get(f"/api/tasks/{tid}/result").json()
    assert result["status"] == SUCCEEDED
    assert result["result"]["output"].endswith("report.md")


def test_task_waiting_approval_then_approve(tmp_path: Path):
    client, app = _make_client(tmp_path, _create_plan("report.md", "新内容"))
    (tmp_path / "data" / "report.md").write_text("旧内容", encoding="utf-8")
    tid = client.post("/api/tasks", json={"input": "覆盖 report.md"}).json()["task_id"]

    app.state.worker.process_once()
    assert client.get(f"/api/tasks/{tid}").json()["status"] == WAITING_APPROVAL

    # 审批通过
    resp = client.post(f"/api/tasks/{tid}/approve", json={"approved": True})
    assert resp.status_code == 200
    app.state.worker.process_once()
    assert client.get(f"/api/tasks/{tid}").json()["status"] == SUCCEEDED
    assert (tmp_path / "data" / "report.md").read_text(encoding="utf-8") == "新内容"


def test_task_waiting_approval_then_reject(tmp_path: Path):
    client, app = _make_client(tmp_path, _create_plan("report.md", "新内容"))
    (tmp_path / "data" / "report.md").write_text("旧内容", encoding="utf-8")
    tid = client.post("/api/tasks", json={"input": "覆盖 report.md"}).json()["task_id"]

    app.state.worker.process_once()
    client.post(f"/api/tasks/{tid}/approve", json={"approved": False})
    app.state.worker.process_once()
    assert client.get(f"/api/tasks/{tid}").json()["status"] == FAILED
    assert (tmp_path / "data" / "report.md").read_text(encoding="utf-8") == "旧内容"


def test_cancel_pending_task(tmp_path: Path):
    client, app = _make_client(tmp_path, _create_plan())
    tid = client.post("/api/tasks", json={"input": "创建报告"}).json()["task_id"]

    resp = client.post(f"/api/tasks/{tid}/cancel")
    assert resp.status_code == 200
    assert resp.json()["status"] == CANCELLED

    # worker 不应再执行已取消任务
    app.state.worker.process_once()
    assert client.get(f"/api/tasks/{tid}").json()["status"] == CANCELLED


def test_logs(tmp_path: Path):
    client, app = _make_client(tmp_path, _create_plan())
    tid = client.post("/api/tasks", json={"input": "创建报告"}).json()["task_id"]
    app.state.worker.process_once()

    logs = client.get(f"/api/tasks/{tid}/logs").json()["logs"]
    messages = [l["message"] for l in logs]
    assert "任务已创建" in messages
    assert any("工作流" in m or "成功" in m for m in messages)


def test_knowledge_import_and_search(tmp_path: Path):
    (tmp_path / "doc.md").write_text("WorkPilot 的授权目录由 WORKPILOT_ALLOWED_DIRS 配置", encoding="utf-8")
    client, _ = _make_client(tmp_path, _create_plan())

    resp = client.post("/api/knowledge/documents", json={"paths": [str(tmp_path / "doc.md")]})
    assert resp.status_code == 200
    assert resp.json()["imported_chunks"] >= 1

    resp = client.post("/api/knowledge/search", json={"query": "授权目录环境变量", "top_k": 3})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert results
    assert results[0]["filename"] == "doc.md"


def test_get_unknown_task_404(tmp_path: Path):
    client, _ = _make_client(tmp_path, _create_plan())
    assert client.get("/api/tasks/nonexistent").status_code == 404
