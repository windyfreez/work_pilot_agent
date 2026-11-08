"""工作流验证与幂等工具的单元测试。"""

from pathlib import Path

import pytest

from workpilot.tools import files
from workpilot.tools._paths import PathResolver
from workpilot.workflow import PlanStep
from workpilot.workflow.verify import verify_step


@pytest.fixture
def resolver(tmp_path: Path) -> PathResolver:
    return PathResolver([tmp_path])


def test_verify_create_ok(resolver: PathResolver, tmp_path: Path):
    (tmp_path / "a.md").write_text("AAA", encoding="utf-8")
    step = PlanStep(step=1, tool="create_document", args={"path": "a.md", "content": "AAA"})
    assert verify_step(step, str(tmp_path / "a.md"), resolver).ok is True


def test_verify_create_missing(resolver: PathResolver):
    step = PlanStep(step=1, tool="create_document", args={"path": "a.md", "content": "AAA"})
    assert verify_step(step, "", resolver).ok is False


def test_verify_create_content_mismatch(resolver: PathResolver, tmp_path: Path):
    (tmp_path / "a.md").write_text("BBB", encoding="utf-8")
    step = PlanStep(step=1, tool="create_document", args={"path": "a.md", "content": "AAA"})
    assert verify_step(step, str(tmp_path / "a.md"), resolver).ok is False


def test_verify_read(resolver: PathResolver):
    step = PlanStep(step=1, tool="read_document", args={"path": "a.md"})
    assert verify_step(step, "内容", resolver).ok is True
    assert verify_step(step, "", resolver).ok is False


def test_verify_list_files(resolver: PathResolver):
    step = PlanStep(step=1, tool="list_files", args={"directory": "."})
    assert verify_step(step, "['a.txt']", resolver).ok is True


def test_is_overwrite(resolver: PathResolver, tmp_path: Path):
    (tmp_path / "a.md").write_text("AAA", encoding="utf-8")
    assert files.is_overwrite(resolver, "a.md", "BBB") is True  # 内容不同 → 覆盖
    assert files.is_overwrite(resolver, "a.md", "AAA") is False  # 内容相同 → no-op
    assert files.is_overwrite(resolver, "b.md", "AAA") is False  # 不存在


def test_create_document_idempotent(resolver: PathResolver, tmp_path: Path):
    f = tmp_path / "a.md"
    files.create_document(resolver, "a.md", "AAA")
    mtime1 = f.stat().st_mtime_ns
    files.create_document(resolver, "a.md", "AAA")  # 相同内容 → no-op
    assert f.stat().st_mtime_ns == mtime1  # 未重新写入
    assert f.read_text(encoding="utf-8") == "AAA"
