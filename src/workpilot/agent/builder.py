"""组装 LangChain 工具调用 Agent。"""

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel

from workpilot.config import Settings
from workpilot.tools.registry import build_tools

from .llm import get_chat_model

SYSTEM_PROMPT = (
    "你是 WorkPilot 办公助手，负责执行文档读写类办公任务。"
    "操作文件前先用 list_files 查看目录，再按需调用 read_document 或 create_document。"
    "所有文件操作都被限制在授权目录内，请勿尝试越界路径。"
)


def build_agent(settings: Settings | None = None, model: BaseChatModel | None = None):
    """构建一个已注册文件工具的 LangChain Agent。

    返回的 Agent 可用如下方式调用：
        result = agent.invoke({"messages": [{"role": "user", "content": "..."}]})
    """
    settings = settings or Settings()
    chat_model = model or get_chat_model(settings)
    tools = build_tools(settings)
    return create_agent(model=chat_model, tools=tools, system_prompt=SYSTEM_PROMPT)
