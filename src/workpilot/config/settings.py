"""应用配置：从环境变量 / .env 读取，密钥不硬编码。"""

import os
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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
    llm_request_timeout: float | None = None  # 单次模型请求超时（秒）

    # ---- Agent ----
    agent_timeout_seconds: float | None = None  # 单次运行整体超时（秒），None=不限制
    agent_max_tool_calls: int = 10  # 单次运行最多工具调用次数

    # ---- 文件工具 ----
    # 授权目录：字符串可用平台分隔符（Windows ';'，POSIX ':'）或逗号分隔。
    # NoDecode：阻止 pydantic-settings 把该字段当 JSON 解析，交给 _parse_allowed_dirs 处理普通字符串。
    allowed_dirs: Annotated[list[Path], NoDecode] = Field(default_factory=lambda: [Path("data")])
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

    @field_validator("llm_request_timeout", "agent_timeout_seconds", mode="before")
    @classmethod
    def _empty_str_to_none(cls, value: object) -> object:
        # .env 里留空（如 `WORKPILOT_LLM_REQUEST_TIMEOUT=`）会得到空字符串，需转为 None。
        if isinstance(value, str) and value.strip() == "":
            return None
        return value
