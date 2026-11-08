"""基于检索结果生成带来源引用的回答。"""

from langchain_core.language_models.chat_models import BaseChatModel

from .store import RetrievedChunk

NO_ANSWER_TEXT = "知识库中没有找到足够依据来回答该问题。"


def answer_with_sources(
    query: str,
    retrieved: list[RetrievedChunk],
    llm: BaseChatModel,
) -> str:
    """用检索到的片段生成带来源引用的回答；无相关资料时返回明确提示。"""
    if not retrieved:
        return NO_ANSWER_TEXT

    context = "\n\n".join(
        f"[来源{i + 1}：{c.filename}（片段 {c.chunk_index}）]\n{c.content}"
        for i, c in enumerate(retrieved)
    )
    prompt = (
        "根据以下资料回答用户问题，并在答案中标注来源编号（如 [来源1]）。"
        "若资料不足以回答，请说明依据不足。\n\n"
        f"资料：\n{context}\n\n"
        f"问题：{query}\n\n回答："
    )
    return llm.invoke(prompt).content
