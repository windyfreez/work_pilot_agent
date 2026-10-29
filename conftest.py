"""pytest 全局配置（仅测试环境生效）。

本沙盒下，Python 在 Windows 上用 ``mode=0o700`` 创建目录时会设置受限 ACL，
导致测试进程后续无法访问该目录——pytest 的 ``tmp_path`` 与 ``tempfile`` 均受影响。

这里做两件事：
1. 把临时目录重定向到工作区内（系统临时目录 ``C:\\Users\\...\\Temp\\dsh-*`` 不可读写）；
2. 把测试进程内的 ``os.mkdir`` / ``os.makedirs`` 统一放宽为 ``0o777``（继承父目录 ACL），
   避免 ``0o700`` 触发受限 ACL。
"""

import os
import tempfile
from pathlib import Path

# 1) 临时目录重定向到工作区
_WORK_TMP = Path(__file__).resolve().parent / ".pytest-tmp"
_WORK_TMP.mkdir(parents=True, exist_ok=True)
os.environ["TEMP"] = str(_WORK_TMP)
os.environ["TMP"] = str(_WORK_TMP)
tempfile.tempdir = str(_WORK_TMP)

# 2) 放宽目录创建 mode
if os.name == "nt":
    _real_mkdir = os.mkdir
    _real_makedirs = os.makedirs

    def _mkdir(path, mode=0o777, *, dir_fd=None):
        return _real_mkdir(path, 0o777, dir_fd=dir_fd)

    def _makedirs(name, mode=0o777, exist_ok=False):
        return _real_makedirs(name, 0o777, exist_ok=exist_ok)

    os.mkdir = _mkdir
    os.makedirs = _makedirs
