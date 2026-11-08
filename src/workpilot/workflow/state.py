"""任务工作流的状态与结构化模型。"""

from enum import Enum
from typing import TypedDict

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """单个执行步骤。"""

    step: int = Field(description="步骤序号，从 1 开始")
    tool: str = Field(description="工具名：list_files / read_document / create_document")
    args: dict = Field(description="工具参数")
    description: str = Field(default="", description="步骤说明")


class Plan(BaseModel):
    """结构化任务计划。"""

    steps: list[PlanStep] = Field(description="按顺序执行的步骤列表")


class VerificationResult(BaseModel):
    """验证结果。"""

    ok: bool
    message: str = ""


class TaskStatus(str, Enum):
    """任务状态。"""

    PENDING = "pending"
    PLANNED = "planned"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class TaskState(TypedDict, total=False):
    """任务工作流的统一状态。"""

    task_id: str
    task_input: str
    plan: list[PlanStep]
    current_step: int
    results: list[str]
    verification: VerificationResult | None
    status: str
    error: str | None
    retries: int
