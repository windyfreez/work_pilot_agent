"""知识库：文档导入 → 清洗 → 分块 → 向量化写 Chroma → 语义检索。"""

from dataclasses import dataclass
from pathlib import Path

from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

from workpilot.config import Settings

from .cleaner import clean_text
from .loader import parse_directory, parse_file
from .splitter import split_text


@dataclass
class RetrievedChunk:
    """检索到的片段（含来源元数据）。"""

    content: str
    source: str
    filename: str
    format: str
    chunk_index: int
    score: float


def get_embedding_model(settings: Settings) -> Embeddings:
    """根据配置返回 OpenAI 兼容的 embedding 模型。"""
    kwargs: dict = {"model": settings.embedding_model}
    if settings.llm_base_url:
        kwargs["openai_api_base"] = settings.llm_base_url
    if settings.llm_api_key:
        kwargs["openai_api_key"] = settings.llm_api_key
    return OpenAIEmbeddings(**kwargs)


class KnowledgeStore:
    """知识库封装：负责向量化、持久化与语义检索。"""

    def __init__(
        self,
        settings: Settings | None = None,
        embedding: Embeddings | None = None,
        client=None,
    ):
        self._settings = settings or Settings()
        self._embedding = embedding or get_embedding_model(self._settings)
        self._vectorstore = Chroma(
            collection_name="workpilot_kb",
            embedding_function=self._embedding,
            persist_directory=self._settings.chroma_dir,
            client=client,
            collection_metadata={"hnsw:space": "cosine"},
        )

    def ingest(self, paths: list[str | Path]) -> int:
        """导入并向量化一批文档（文件或目录），返回写入的 chunk 总数。"""
        documents = self._build_documents(paths)
        if not documents:
            return 0
        self._vectorstore.add_documents(documents)
        return len(documents)

    def retrieve(self, query: str, top_k: int | None = None) -> list[RetrievedChunk]:
        """语义检索 Top-K 片段（按相关度排序）。"""
        top_k = top_k or self._settings.rag_top_k
        results = self._vectorstore.similarity_search_with_relevance_scores(query, k=top_k)

        chunks: list[RetrievedChunk] = []
        threshold = self._settings.rag_score_threshold
        for doc, score in results:
            if threshold is not None and score < threshold:
                continue
            meta = doc.metadata
            chunks.append(
                RetrievedChunk(
                    content=doc.page_content,
                    source=meta.get("source", ""),
                    filename=meta.get("filename", ""),
                    format=meta.get("format", ""),
                    chunk_index=meta.get("chunk_index", 0),
                    score=score,
                )
            )
        return chunks

    def _build_documents(self, paths: list[str | Path]) -> list[Document]:
        parsed = []
        for p in paths:
            path = Path(p)
            if path.is_dir():
                parsed.extend(parse_directory(path))
            else:
                parsed.append(parse_file(path))

        documents: list[Document] = []
        for doc in parsed:
            text = clean_text(doc.text)
            for i, chunk in enumerate(
                split_text(text, self._settings.rag_chunk_size, self._settings.rag_chunk_overlap)
            ):
                documents.append(
                    Document(
                        page_content=chunk,
                        metadata={
                            "source": doc.source,
                            "filename": doc.filename,
                            "format": doc.format,
                            "chunk_index": i,
                        },
                    )
                )
        return documents
