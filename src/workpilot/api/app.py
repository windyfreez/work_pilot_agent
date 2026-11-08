"""FastAPI 应用与路由。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from workpilot.agent.llm import get_chat_model
from workpilot.config import Settings
from workpilot.rag.store import KnowledgeStore, get_embedding_model
from workpilot.workflow.runner import WorkflowRunner

from .schemas import (
    ApprovalRequest,
    DocumentImportRequest,
    KnowledgeSearchRequest,
    TaskCreateRequest,
)
from .store import (
    CANCELLED,
    PENDING,
    TERMINAL_STATUSES,
    WAITING_APPROVAL,
    TaskNotFoundError,
    TaskStore,
)
from .worker import TaskWorker


def create_app(
    settings: Settings | None = None,
    model=None,
    store: TaskStore | None = None,
    checkpointer=None,
    embedding=None,
    rag_client=None,
    start_worker: bool = True,
) -> FastAPI:
    """构建 FastAPI 应用（依赖可注入，便于测试）。"""
    settings = settings or Settings()
    model = model or get_chat_model(settings)
    store = store or TaskStore(settings.tasks_db_path)

    runner = WorkflowRunner(
        settings,
        model,
        checkpointer=checkpointer,
        should_cancel=lambda task_id: store.is_cancel_requested(task_id),
    )
    rag_store = KnowledgeStore(
        settings,
        embedding=embedding or get_embedding_model(settings),
        client=rag_client,
    )
    worker = TaskWorker(store, runner, settings.worker_poll_interval)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        if start_worker:
            worker.start()
        yield
        worker.stop()

    app = FastAPI(title="WorkPilot Agent API", lifespan=lifespan)
    app.state.store = store
    app.state.runner = runner
    app.state.rag_store = rag_store
    app.state.worker = worker

    @app.post("/api/tasks", status_code=202)
    def create_task(req: TaskCreateRequest):
        task_id = store.create_task(req.input)
        return {"task_id": task_id, "status": PENDING}

    @app.get("/api/tasks/{task_id}")
    def get_task(task_id: str):
        task = _get_task_or_404(store, task_id)
        return {
            "task_id": task["task_id"],
            "status": task["status"],
            "input": task["input"],
            "error": task["error"],
            "approval_requested": bool(task["approval_requested"]),
            "created_at": task["created_at"],
            "updated_at": task["updated_at"],
        }

    @app.get("/api/tasks/{task_id}/logs")
    def get_logs(task_id: str):
        _get_task_or_404(store, task_id)
        return {"task_id": task_id, "logs": store.get_logs(task_id)}

    @app.get("/api/tasks/{task_id}/result")
    def get_result(task_id: str):
        task = _get_task_or_404(store, task_id)
        if task["status"] not in TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail="任务尚未完成")
        return {
            "task_id": task_id,
            "status": task["status"],
            "result": store.get_result(task_id),
        }

    @app.post("/api/tasks/{task_id}/approve")
    def approve(task_id: str, req: ApprovalRequest):
        task = _get_task_or_404(store, task_id)
        if task["status"] != WAITING_APPROVAL:
            raise HTTPException(status_code=409, detail=f"任务当前状态为 {task['status']}，无法审批")
        store.set_approval(task_id, req.approved)
        store.add_log(task_id, "info", "已提交审批决定")
        return {"task_id": task_id, "status": WAITING_APPROVAL}

    @app.post("/api/tasks/{task_id}/cancel")
    def cancel(task_id: str):
        task = _get_task_or_404(store, task_id)
        if task["status"] in TERMINAL_STATUSES:
            raise HTTPException(status_code=409, detail="任务已结束，无法取消")
        if task["status"] in (PENDING, WAITING_APPROVAL):
            store.update_status(task_id, CANCELLED)
            store.add_log(task_id, "info", "任务已取消")
        else:  # running
            store.set_cancel_requested(task_id)
            store.add_log(task_id, "info", "已请求取消，将在下一个步骤生效")
        return {"task_id": task_id, "status": store.get_task(task_id)["status"]}

    @app.post("/api/knowledge/documents")
    def import_documents(req: DocumentImportRequest):
        try:
            n = rag_store.ingest(req.paths)
        except Exception as exc:  # noqa: BLE001 - 转为 4xx 返回
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"imported_chunks": n}

    @app.post("/api/knowledge/search")
    def search_knowledge(req: KnowledgeSearchRequest):
        chunks = rag_store.retrieve(req.query, top_k=req.top_k)
        return {
            "results": [
                {
                    "content": c.content,
                    "filename": c.filename,
                    "source": c.source,
                    "chunk_index": c.chunk_index,
                    "score": c.score,
                }
                for c in chunks
            ]
        }

    return app


def _get_task_or_404(store: TaskStore, task_id: str) -> dict:
    try:
        return store.get_task(task_id)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="任务不存在")
