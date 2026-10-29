"""模型客户端封装：基于 OpenAI 兼容协议构建 ChatOpenAI。"""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from workpilot.config import Settings


def get_chat_model(settings: Settings | None = None) -> BaseChatModel:
    """根据配置返回一个 LangChain 聊天模型（OpenAI 兼容协议）。

    密钥仅从配置/环境变量读取，绝不硬编码；未配置 base_url 时使用官方端点。
    """
    settings = settings or Settings()

    kwargs: dict = {
        "model_name": settings.llm_model,
        "temperature": settings.llm_temperature,
    }
    if settings.llm_base_url:
        kwargs["openai_api_base"] = settings.llm_base_url
    if settings.llm_api_key:
        kwargs["openai_api_key"] = settings.llm_api_key
    return ChatOpenAI(**kwargs)
