"""Settings 配置解析测试。"""

import os
from pathlib import Path

from workpilot.config import Settings


def test_allowed_dirs_from_env_pathsep_string(monkeypatch, tmp_path: Path):
    """回归：WORKPILOT_ALLOWED_DIRS 传普通字符串（平台分隔符）应能正确解析，而非按 JSON。"""
    a = tmp_path / "a"
    b = tmp_path / "b"
    monkeypatch.setenv("WORKPILOT_ALLOWED_DIRS", f"{a}{os.pathsep}{b}")
    settings = Settings()
    assert settings.allowed_dirs == [a.resolve(), b.resolve()]


def test_allowed_dirs_from_comma_string(monkeypatch, tmp_path: Path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    monkeypatch.setenv("WORKPILOT_ALLOWED_DIRS", f"{a},{b}")
    settings = Settings()
    assert settings.allowed_dirs == [a.resolve(), b.resolve()]


def test_allowed_dirs_single_string(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("WORKPILOT_ALLOWED_DIRS", str(tmp_path / "data"))
    settings = Settings()
    assert settings.allowed_dirs == [(tmp_path / "data").resolve()]


def test_empty_timeout_env_becomes_none(monkeypatch):
    """回归：.env 里超时字段留空（空字符串）时应解析为 None，而不是报错。"""
    monkeypatch.setenv("WORKPILOT_LLM_REQUEST_TIMEOUT", "")
    monkeypatch.setenv("WORKPILOT_AGENT_TIMEOUT_SECONDS", "")
    settings = Settings()
    assert settings.llm_request_timeout is None
    assert settings.agent_timeout_seconds is None
