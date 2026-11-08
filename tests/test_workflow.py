"""任务工作流（阶段二）的端到端测试（不连真实模型）。"""

import sqlite3
from pathlib import Path

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.sqlite import SqliteSaver

from workpilot.config import Settings
from workpilot.workflow import Plan, PlanStep, WorkflowRunner


class FakePlanningModel(BaseChatModel):
    """返回脚本化计划的假模型：规划节点直接拿到计划。"""

    plan: Plan

    def with_structured_output(self, schema, **kwargs):
        plan = self.plan

        class Planner:
            def invoke(self, *args, **kwargs):
                return plan

        return Planner()

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise NotImplementedError("规划测试中不会调用 _generate")

    @property
    def _llm_type(self) -> str:
        return "fake-planning-model"


@pytest.fixture
def checkpointer(tmp_path: Path):
    conn = sqlite3.connect(str(tmp_path / "ckpt.sqlite"), check_same_thread=False)
    yield SqliteSaver(conn)
    conn.close()


def _runner(tmp_path: Path, plan: Plan, checkpointer, **settings_kwargs) -> WorkflowRunner:
    model = FakePlanningModel(plan=plan)
    settings = Settings(allowed_dirs=[tmp_path], **settings_kwargs)
    return WorkflowRunner(settings=settings, model=model, checkpointer=checkpointer)


def test_create_task_succeeds(tmp_path: Path, checkpointer):
    plan = Plan(steps=[PlanStep(step=1, tool="create_document", args={"path": "report.md", "content": "# 报告"})])
    outcome = _runner(tmp_path, plan, checkpointer).run("创建 report.md")
    assert outcome.status == "succeeded"
    assert outcome.verification.ok is True
    # 磁盘真实落盘
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == "# 报告"


def test_read_task_uses_real_content(tmp_path: Path, checkpointer):
    (tmp_path / "doc.txt").write_text("真实内容ABC", encoding="utf-8")
    plan = Plan(steps=[PlanStep(step=1, tool="read_document", args={"path": "doc.txt"})])
    outcome = _runner(tmp_path, plan, checkpointer).run("读 doc.txt")
    assert outcome.status == "succeeded"
    assert outcome.output == "真实内容ABC"  # 真实读取到的内容


def test_multi_step_plan(tmp_path: Path, checkpointer):
    plan = Plan(
        steps=[
            PlanStep(step=1, tool="create_document", args={"path": "a.md", "content": "AAA"}),
            PlanStep(step=2, tool="read_document", args={"path": "a.md"}),
        ]
    )
    outcome = _runner(tmp_path, plan, checkpointer).run("先写再读")
    assert outcome.status == "succeeded"
    assert outcome.results[-1] == "AAA"
    assert (tmp_path / "a.md").read_text(encoding="utf-8") == "AAA"


def test_overwrite_requires_confirmation_then_approve(tmp_path: Path, checkpointer):
    (tmp_path / "report.md").write_text("旧内容", encoding="utf-8")
    plan = Plan(steps=[PlanStep(step=1, tool="create_document", args={"path": "report.md", "content": "新内容"})])
    runner = _runner(tmp_path, plan, checkpointer)

    outcome = runner.run("覆盖 report.md")
    assert outcome.status == "awaiting_confirmation"
    assert outcome.confirmation
    # 暂停在确认处，磁盘尚未改动
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == "旧内容"

    resumed = runner.resume(outcome.task_id, approve=True)
    assert resumed.status == "succeeded"
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == "新内容"


def test_overwrite_confirmation_reject(tmp_path: Path, checkpointer):
    (tmp_path / "report.md").write_text("旧内容", encoding="utf-8")
    plan = Plan(steps=[PlanStep(step=1, tool="create_document", args={"path": "report.md", "content": "新内容"})])
    runner = _runner(tmp_path, plan, checkpointer)

    outcome = runner.run("覆盖 report.md")
    assert outcome.status == "awaiting_confirmation"

    resumed = runner.resume(outcome.task_id, approve=False)
    assert resumed.status == "failed"
    assert resumed.error == "用户拒绝覆盖文件"
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == "旧内容"  # 未被改动


def test_plan_truncated_to_max_steps(tmp_path: Path, checkpointer):
    plan = Plan(
        steps=[
            PlanStep(step=1, tool="create_document", args={"path": "a.md", "content": "A"}),
            PlanStep(step=2, tool="create_document", args={"path": "b.md", "content": "B"}),
            PlanStep(step=3, tool="create_document", args={"path": "c.md", "content": "C"}),
        ]
    )
    runner = _runner(tmp_path, plan, checkpointer, task_max_steps=2)
    outcome = runner.run("创建三个文件")
    assert outcome.status == "succeeded"
    assert len(outcome.plan) == 2  # 计划被截断到最大步数
    assert (tmp_path / "a.md").exists() and (tmp_path / "b.md").exists()
    assert not (tmp_path / "c.md").exists()  # 超出的步骤未执行


def test_read_empty_file_retries_then_fails(tmp_path: Path, checkpointer):
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    plan = Plan(steps=[PlanStep(step=1, tool="read_document", args={"path": "empty.txt"})])
    runner = _runner(tmp_path, plan, checkpointer, task_max_retries=2)
    outcome = runner.run("读空文件")
    assert outcome.status == "failed"
    assert outcome.error == "读取结果为空"
    # 初始执行 + 2 次重试 = 3 次执行
    assert len(outcome.results) == 3
