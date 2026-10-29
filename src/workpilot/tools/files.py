"""文件工具的核心实现（纯函数，便于单元测试）。"""

from pathlib import Path

from ._paths import PathError, PathResolver


def list_files(resolver: PathResolver, directory: str, recursive: bool = False) -> list[str]:
    """列出授权目录内指定目录下的文件，返回相对该目录的相对路径列表（已排序）。"""
    target = resolver.resolve(directory)
    if not target.exists():
        raise PathError(f"目录不存在：'{directory}'")
    if not target.is_dir():
        raise PathError(f"不是目录：'{directory}'")

    entries = sorted(target.rglob("*")) if recursive else sorted(target.iterdir())
    files = [e for e in entries if e.is_file()]
    return [str(e.relative_to(target)).replace("\\", "/") for e in files]


def read_document(resolver: PathResolver, path: str, max_bytes: int = 1_000_000) -> str:
    """读取授权目录内文本文件的 UTF-8 内容；拒绝越界、过大与二进制文件。"""
    target = resolver.resolve(path)
    if not target.exists():
        raise PathError(f"文件不存在：'{path}'")
    if not target.is_file():
        raise PathError(f"不是文件：'{path}'")
    if target.stat().st_size > max_bytes:
        raise PathError(f"文件过大（超过 {max_bytes} 字节）：'{path}'")

    data = target.read_bytes()
    if b"\x00" in data:
        raise PathError(f"文件为二进制或含空字节，拒绝读取：'{path}'")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PathError(f"文件不是有效的 UTF-8 文本：'{path}'") from exc


def create_document(resolver: PathResolver, path: str, content: str) -> str:
    """在授权目录内创建（或覆盖）文本文件，返回其绝对路径。"""
    target = resolver.resolve(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)
