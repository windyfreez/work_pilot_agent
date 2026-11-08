"""RAG 清洗 / 分块 / 向量化 / 检索 / 工具 / 回答 / 评测的测试（不连真实 API）。"""

import hashlib
import importlib.util
import json
from pathlib import Path

import chromadb
import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from workpilot.config import Settings
from workpilot.rag import (
    NO_ANSWER_TEXT,
    KnowledgeStore,
    RetrievedChunk,
    answer_with_sources,
    build_retrieval_tool,
    clean_text,
    split_text,
)


class CharNGramEmbeddings:
    """字符 n-gram 哈希嵌入：离线、确定性，捕获一定词面相似度。"""

    def __init__(self, dim: int = 4096, n: int = 3):
        self.dim = dim
        self.n = n

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        t = text.lower()
        for i in range(len(t) - self.n + 1):
            h = int(hashlib.md5(t[i : i + self.n].encode()).hexdigest(), 16) % self.dim
            vec[h] += 1.0
        norm = sum(v * v for v in vec) ** 0.5
        return [v / norm for v in vec] if norm else vec

    def embed_documents(self, texts):
        return [self._embed(t) for t in texts]

    def embed_query(self, text):
        return self._embed(text)


class RecordingLLM(BaseChatModel):
    """记录 prompt 并返回固定回答的假 LLM。"""

    last_prompt: str = ""

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.last_prompt = messages[-1].content if messages else ""
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="回答：配置项是 WORKPILOT_ALLOWED_DIRS"))]
        )

    @property
    def _llm_type(self) -> str:
        return "recording-llm"


@pytest.fixture
def store(tmp_path: Path) -> KnowledgeStore:
    settings = Settings(chroma_dir=str(tmp_path / "chroma"))
    client = chromadb.PersistentClient(path=str(tmp_path / "cdb"))
    return KnowledgeStore(settings=settings, embedding=CharNGramEmbeddings(), client=client)


def test_clean_text():
    assert clean_text("a\tb\r\n\r\n\r\nc") == "a b\n\nc"
    assert clean_text("\x00foo\x1fbar") == "foobar"


def test_split_text():
    text = "para one\n\npara two\n\npara three"
    chunks = split_text(text, chunk_size=20, chunk_overlap=5)
    assert chunks
    assert all(len(c) <= 20 for c in chunks)


def test_split_empty():
    assert split_text("") == []


def test_ingest_and_retrieve_with_metadata(store: KnowledgeStore, tmp_path: Path):
    (tmp_path / "doc_a.md").write_text("WorkPilot 的授权目录由 WORKPILOT_ALLOWED_DIRS 配置", encoding="utf-8")
    (tmp_path / "doc_b.md").write_text("Chroma 是本地向量数据库", encoding="utf-8")
    n = store.ingest([tmp_path / "doc_a.md", tmp_path / "doc_b.md"])
    assert n >= 2

    chunks = store.retrieve("授权目录环境变量", top_k=3)
    assert chunks
    for c in chunks:
        assert c.filename in ("doc_a.md", "doc_b.md")
        assert c.source.endswith(c.filename)
        assert c.chunk_index >= 0


def test_retrieve_ranks_relevant_doc_first(store: KnowledgeStore, tmp_path: Path):
    (tmp_path / "config.md").write_text("授权目录由 WORKPILOT_ALLOWED_DIRS 环境变量配置", encoding="utf-8")
    (tmp_path / "unrelated.md").write_text("今天天气很好，适合去公园散步", encoding="utf-8")
    store.ingest([tmp_path])

    chunks = store.retrieve("WORKPILOT_ALLOWED_DIRS 是什么", top_k=2)
    assert chunks[0].filename == "config.md"


def test_retrieve_threshold_filters_out_irrelevant(tmp_path: Path):
    (tmp_path / "config.md").write_text("授权目录由 WORKPILOT_ALLOWED_DIRS 配置", encoding="utf-8")
    settings = Settings(chroma_dir=str(tmp_path / "chroma"), rag_score_threshold=0.5)
    client = chromadb.PersistentClient(path=str(tmp_path / "cdb"))
    store = KnowledgeStore(settings=settings, embedding=CharNGramEmbeddings(), client=client)
    store.ingest([tmp_path])

    chunks = store.retrieve("完全无关的问题 火星上有没有水", top_k=3)
    assert chunks == []  # 低相关度被阈值过滤


def test_retrieval_tool(store: KnowledgeStore, tmp_path: Path):
    (tmp_path / "config.md").write_text("授权目录由 WORKPILOT_ALLOWED_DIRS 配置", encoding="utf-8")
    store.ingest([tmp_path])
    tool = build_retrieval_tool(store)
    result = tool.invoke({"query": "授权目录"})
    assert "config.md" in result


def test_retrieval_tool_no_material(store: KnowledgeStore):
    tool = build_retrieval_tool(store)  # 空库
    result = tool.invoke({"query": "任意问题"})
    assert "没有找到足够依据" in result


def test_answer_no_material():
    llm = RecordingLLM()
    assert answer_with_sources("问题", [], llm) == NO_ANSWER_TEXT


def test_answer_with_sources_includes_context():
    retrieved = [
        RetrievedChunk(
            content="WORKPILOT_ALLOWED_DIRS 配置授权目录",
            source="/x/config.md",
            filename="config.md",
            format="md",
            chunk_index=0,
            score=0.9,
        )
    ]
    llm = RecordingLLM()
    result = answer_with_sources("授权目录是什么", retrieved, llm)
    assert result == "回答：配置项是 WORKPILOT_ALLOWED_DIRS"
    assert "config.md" in llm.last_prompt  # prompt 中携带了来源


def test_eval_harness_runs(tmp_path: Path):
    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("eval_rag", root / "eval" / "eval_rag.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    eval_set = json.loads((root / "eval" / "eval_set.json").read_text(encoding="utf-8"))
    result = mod.run_eval(
        str(root / "eval" / "corpus"),
        eval_set,
        mod.CharNGramEmbeddings(),
        mod.FakeLLM(),
        score_threshold=0.1,
        client=chromadb.PersistentClient(path=str(tmp_path / "eval_cdb")),
    )
    assert set(result["summary"].keys()) == {"recall@k", "keyword_hit", "citation_hit"}
    assert len(result["details"]) == len(eval_set["questions"])
    # q5（无相关资料）应明确回答“没有找到足够依据”
    q5 = next(d for d in result["details"] if d["id"] == "q5")
    assert q5["no_answer_ok"] is True
