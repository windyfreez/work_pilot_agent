"""阶段 0 冒烟测试。

验证：Python 版本满足要求、包可导入、包版本与 pyproject.toml 一致。
"""

import sys
import tomllib
from pathlib import Path

import workpilot

ROOT = Path(__file__).resolve().parent.parent


def test_python_version_satisfies_requirement():
    assert sys.version_info >= (3, 11), "pyproject.toml 声明 requires-python >= 3.11"


def test_package_imports_and_has_version():
    assert workpilot.__version__ == "0.1.0"


def test_package_version_matches_pyproject():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["version"] == workpilot.__version__
