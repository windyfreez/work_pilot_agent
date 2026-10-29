"""路径校验单元测试。"""

from pathlib import Path

import pytest

from workpilot.tools._paths import PathError, PathResolver


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "root"


@pytest.fixture
def resolver(root: Path) -> PathResolver:
    root.mkdir(parents=True)
    return PathResolver([root])


def test_empty_allowed_dirs_rejected():
    with pytest.raises(ValueError):
        PathResolver([])


def test_relative_path_resolves_within_allowed(resolver: PathResolver, root: Path):
    assert resolver.resolve("a.txt") == (root / "a.txt").resolve()
    assert resolver.resolve("sub/b.txt") == (root / "sub" / "b.txt").resolve()


def test_dot_resolves_to_allowed_dir(resolver: PathResolver, root: Path):
    assert resolver.resolve(".") == root.resolve()


def test_traversal_rejected(resolver: PathResolver):
    with pytest.raises(PathError):
        resolver.resolve("../outside.txt")


def test_absolute_inside_allowed(resolver: PathResolver, root: Path):
    target = root / "x.txt"
    assert resolver.resolve(str(target)) == target.resolve()


def test_absolute_outside_rejected(resolver: PathResolver, tmp_path: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(PathError):
        resolver.resolve(str(outside / "x.txt"))


def test_symlink_escape_rejected(tmp_path: Path, root: Path):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("当前环境不允许创建符号链接")
    resolver = PathResolver([root])
    with pytest.raises(PathError):
        resolver.resolve("link/x.txt")
