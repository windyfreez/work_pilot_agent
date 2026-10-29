"""文件工具核心实现的单元测试。"""

from pathlib import Path

import pytest

from workpilot.tools import files
from workpilot.tools._paths import PathError, PathResolver


@pytest.fixture
def resolver(tmp_path: Path) -> PathResolver:
    return PathResolver([tmp_path])


def test_list_files_non_recursive(resolver: PathResolver, tmp_path: Path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "b.md").write_text("b", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.txt").write_text("c", encoding="utf-8")

    assert files.list_files(resolver, ".") == ["a.txt", "b.md"]


def test_list_files_recursive(resolver: PathResolver, tmp_path: Path):
    (tmp_path / "a.txt").write_text("a", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.txt").write_text("c", encoding="utf-8")

    assert files.list_files(resolver, ".", recursive=True) == ["a.txt", "sub/c.txt"]


def test_list_files_empty_dir(resolver: PathResolver, tmp_path: Path):
    assert files.list_files(resolver, ".") == []


def test_list_files_missing_dir(resolver: PathResolver):
    with pytest.raises(PathError):
        files.list_files(resolver, "nope")


def test_list_files_path_is_file(resolver: PathResolver, tmp_path: Path):
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    with pytest.raises(PathError):
        files.list_files(resolver, "a.txt")


def test_read_document_ok(resolver: PathResolver, tmp_path: Path):
    (tmp_path / "doc.md").write_text("你好，世界", encoding="utf-8")
    assert files.read_document(resolver, "doc.md") == "你好，世界"


def test_read_document_missing(resolver: PathResolver):
    with pytest.raises(PathError):
        files.read_document(resolver, "nope.txt")


def test_read_document_too_large(resolver: PathResolver, tmp_path: Path):
    (tmp_path / "big.txt").write_bytes(b"x" * 100)
    with pytest.raises(PathError):
        files.read_document(resolver, "big.txt", max_bytes=10)


def test_read_document_binary(resolver: PathResolver, tmp_path: Path):
    (tmp_path / "bin.txt").write_bytes(b"\x00\x01\x02")
    with pytest.raises(PathError):
        files.read_document(resolver, "bin.txt")


def test_read_document_not_utf8(resolver: PathResolver, tmp_path: Path):
    (tmp_path / "latin.txt").write_bytes(b"\xff\xfe\xfa")
    with pytest.raises(PathError):
        files.read_document(resolver, "latin.txt")


def test_create_document_creates_parents(resolver: PathResolver, tmp_path: Path):
    target = files.create_document(resolver, "out/report.md", "# 报告")
    assert Path(target) == (tmp_path / "out" / "report.md").resolve()
    assert (tmp_path / "out" / "report.md").read_text(encoding="utf-8") == "# 报告"


def test_create_document_overwrites(resolver: PathResolver, tmp_path: Path):
    f = tmp_path / "x.md"
    f.write_text("旧内容", encoding="utf-8")
    files.create_document(resolver, "x.md", "新内容")
    assert f.read_text(encoding="utf-8") == "新内容"


def test_create_document_traversal_rejected(resolver: PathResolver):
    with pytest.raises(PathError):
        files.create_document(resolver, "../evil.md", "x")
