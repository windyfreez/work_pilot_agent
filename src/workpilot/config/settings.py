"""应用配置：从环境变量 / .env 读取，密钥不硬编码。"""

import os
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """WorkPilot 全局配置。

    通过环境变量（前缀 ``WORKPILOT_``）或项目根目录的 ``.env`` 注入。
    密钥只从环境读取，代码中绝不出现真实密钥。
    """

    model_config = SettingsConfigDict(
        env_prefix="WORKPILOT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- LLM（OpenAI 兼容协议：OpenAI / DeepSeek / Ollama 通用）----
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None  # 为空时使用官方端点
    llm_api_key: str | None = None  # 从环境变量 WORKPILOT_LLM_API_KEY 读取
    llm_temperature: float = 0.0

    # ---- 文件工具 ----
    # 授权目录：字符串可用平台分隔符（Windows ';'，POSIX ':'）或逗号分隔。
    allowed_dirs: list[Path] = Field(default_factory=lambda: [Path("data")])
    read_max_bytes: int = 1_000_000  # read_document 读取上限（默认 1 MB）

    @field_validator("allowed_dirs", mode="before")
    @classmethod
    def _parse_allowed_dirs(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.replace(",", os.pathsep)
            parts = [p.strip() for p in normalized.split(os.pathsep) if p.strip()]
            return [Path(p) for p in parts] if parts else [Path("data")]
        return value

    @field_validator("allowed_dirs", mode="after")
    @classmethod
    def _resolve_allowed_dirs(cls, value: list[Path]) -> list[Path]:
        return [p.expanduser().resolve() for p in value]
