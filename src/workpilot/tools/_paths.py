"""路径安全校验：所有文件操作必须落在授权目录内。"""

from pathlib import Path


class PathError(ValueError):
    """路径非法（越界、不存在、类型错误等）。"""


class PathResolver:
    """把用户输入路径解析为授权目录内的绝对路径，并拒绝越界。

    规则：
    - 相对路径相对第一个授权目录解析；
    - 绝对路径必须落在某个授权目录内；
    - 使用 ``resolve()`` 归一化 ``..`` 与符号链接后再做前缀校验。
    """

    def __init__(self, allowed_dirs: list[Path]):
        if not allowed_dirs:
            raise ValueError("至少需要配置一个授权目录")
        self._allowed = [Path(p).resolve() for p in allowed_dirs]

    @property
    def allowed_dirs(self) -> list[Path]:
        return list(self._allowed)

    def resolve(self, path: str) -> Path:
        """解析并校验路径，返回授权目录内的绝对路径；越界时抛出 PathError。"""
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = self._allowed[0] / p
        resolved = p.resolve()

        if not any(resolved == d or d in resolved.parents for d in self._allowed):
            raise PathError(f"路径越界：'{path}' 不在任何授权目录内")
        return resolved
