"""任务步骤的结果验证。"""

from workpilot.tools._paths import PathResolver
from workpilot.tools.files import read_text_or_none

from .state import PlanStep, VerificationResult


def verify_step(step: PlanStep, result: str, resolver: PathResolver) -> VerificationResult:
    """验证单个步骤的执行结果是否满足要求。"""
    tool = step.tool

    if tool == "create_document":
        target = resolver.resolve(step.args.get("path", ""))
        if not target.is_file():
            return VerificationResult(ok=False, message=f"文件未创建：{target}")
        actual = read_text_or_none(target)
        expected = step.args.get("content", "")
        if actual != expected:
            return VerificationResult(ok=False, message="文件内容与预期不符")
        return VerificationResult(ok=True, message="文件已创建且内容正确")

    if tool == "read_document":
        if not result or not result.strip():
            return VerificationResult(ok=False, message="读取结果为空")
        return VerificationResult(ok=True, message="读取成功")

    if tool == "list_files":
        return VerificationResult(ok=True, message="列出目录成功")

    return VerificationResult(ok=False, message=f"未知工具：{tool}")
