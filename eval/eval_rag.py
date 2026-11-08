"""RAG 评测脚本（可重复运行）。

用法：
    python eval/eval_rag.py                                # 默认离线（fake embedding + fake LLM）
    python eval/eval_rag.py --embedding real --llm real    # 真实 embedding + LLM（需 .env 密钥）

指标：
    - recall@k        检索结果命中预期来源文档的比例
    - keyword_hit     回答是否包含标准答案关键词
    - citation_hit    回答是否引用了预期来源文档
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from workpilot.config import Settings  # noqa: E402
from workpilot.rag import KnowledgeStore, answer_with_sources  # noqa: E402
from workpilot.rag.answer import NO_ANSWER_TEXT  # noqa: E402


class CharNGramEmbeddings:
    """字符 n-gram 哈希嵌入：离线、确定性，仅用于验证评测流程。"""

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


class FakeLLM:
    """离线假 LLM：回答里引用检索到的来源。"""

    def invoke(self, prompt):
        from langchain_core.messages import AIMessage

        return AIMessage(content="根据提供的资料回答（含来源引用）。")


def build_embedding(mode: str):
    if mode == "real":
        from workpilot.rag.store import get_embedding_model

        return get_embedding_model(Settings())
    return CharNGramEmbeddings()


def build_llm(mode: str):
    if mode == "real":
        from workpilot.agent.llm import get_chat_model

        return get_chat_model(Settings())
    return FakeLLM()


def run_eval(corpus_dir: str, eval_set: dict, embedding, llm, score_threshold: float | None = None, client=None) -> dict:
    """运行评测，返回汇总指标与逐题明细。"""
    import chromadb

    settings = Settings(rag_score_threshold=score_threshold)
    client = client or chromadb.EphemeralClient()  # 默认内存库；测试可传入隔离的 client
    store = KnowledgeStore(settings=settings, embedding=embedding, client=client)

    n = store.ingest([corpus_dir])
    print(f"已导入 {n} 个片段")

    details = []
    for q in eval_set["questions"]:
        retrieved = store.retrieve(q["question"])
        ret_filenames = [c.filename for c in retrieved]
        answer = answer_with_sources(q["question"], retrieved, llm)

        expected = q.get("expected_sources", [])
        recall = len(set(ret_filenames) & set(expected)) / len(expected) if expected else 1.0
        keywords = q.get("answer_keywords", [])
        keyword_hit = all(k in answer for k in keywords) if keywords else 1.0
        cited = sum(1 for s in expected if s in answer)
        citation_hit = cited / len(expected) if expected else 1.0
        no_answer_ok = (NO_ANSWER_TEXT in answer) if not expected else None

        details.append(
            {
                "id": q["id"],
                "recall": recall,
                "keyword_hit": keyword_hit,
                "citation_hit": citation_hit,
                "no_answer_ok": no_answer_ok,
                "retrieved": ret_filenames,
                "answer": answer,
            }
        )

    n_q = len(details) or 1
    summary = {
        "recall@k": sum(d["recall"] for d in details) / n_q,
        "keyword_hit": sum(d["keyword_hit"] for d in details) / n_q,
        "citation_hit": sum(d["citation_hit"] for d in details) / n_q,
    }
    return {"summary": summary, "details": details}


def main() -> int:
    parser = argparse.ArgumentParser(description="RAG 评测")
    parser.add_argument("--embedding", choices=["fake", "real"], default="fake")
    parser.add_argument("--llm", choices=["fake", "real"], default="fake")
    parser.add_argument("--score-threshold", type=float, default=None)
    parser.add_argument("--corpus-dir", default=str(ROOT / "eval" / "corpus"))
    parser.add_argument("--eval-file", default=str(ROOT / "eval" / "eval_set.json"))
    args = parser.parse_args()

    eval_set = json.loads(Path(args.eval_file).read_text(encoding="utf-8"))
    embedding = build_embedding(args.embedding)
    llm = build_llm(args.llm)

    result = run_eval(args.corpus_dir, eval_set, embedding, llm, score_threshold=args.score_threshold)

    print("\n=== 汇总 ===")
    for k, v in result["summary"].items():
        print(f"{k}: {v:.3f}")
    print("\n=== 明细 ===")
    for d in result["details"]:
        print(
            f"[{d['id']}] recall={d['recall']:.2f} keyword={d['keyword_hit']} "
            f"cite={d['citation_hit']} no_answer_ok={d['no_answer_ok']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
