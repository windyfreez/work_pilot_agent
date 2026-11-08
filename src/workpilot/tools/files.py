"""文件工具的核心实现（纯函数，便于单元测试）。"""

import os
import uuid
from pathlib import Path

from ._paths import PathError, PathResolver


def read_text_or_none(path: Path) -> str | None:
    """读取文本内容；失败（二进制 / IO 错误）返回 None。"""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


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


def is_overwrite(resolver: PathResolver, path: str, content: str) -> bool:
    """判断 create_document 是否会覆盖一个内容不同的已存在文件（高风险操作）。"""
    target = resolver.resolve(path)
    if not (target.exists() and target.is_file()):
        return False
    return read_text_or_none(target) != content


def create_document(resolver: PathResolver, path: str, content: str) -> str:
    """在授权目录内创建（或覆盖）文本文件，返回其绝对路径。

    幂等策略：已存在且内容相同时为 no-op；写入采用「临时文件 + 原子 rename」，
    失败不会留下半截文件。
    """
    target = resolver.resolve(path)
    if target.exists() and target.is_file():
        if read_text_or_none(target) == content:
            return str(target)  # 内容相同，幂等 no-op

    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / f".{target.name}.{uuid.uuid4().hex}.tmp"
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, target)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
    return str(target)
