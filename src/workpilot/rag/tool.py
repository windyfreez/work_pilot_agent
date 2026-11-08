"""把知识库检索封装为 LangChain 工具。"""

from langchain_core.tools import BaseTool, tool

from .store import KnowledgeStore


def build_retrieval_tool(store: KnowledgeStore) -> BaseTool:
    """返回一个语义检索工具，供 Agent / 工作流调用。"""

    @tool
    def search_knowledge_base(query: str) -> str:
        """在知识库中语义检索与 query 最相关的片段，返回带来源（文件名/片段号）的内容。"""
        chunks = store.retrieve(query)
        if not chunks:
            return "知识库中没有找到足够依据。"
        return "\n\n".join(
            f"[{c.filename}#片段{c.chunk_index}] {c.content}" for c in chunks
        )

    return search_knowledge_base
