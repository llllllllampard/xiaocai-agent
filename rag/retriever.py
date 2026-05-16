"""
RAG 检索模块：纯 sentence-transformers + numpy 实现，无需 chromadb。
索引在内存中构建，首次启动时加载一次，后续检索直接用向量余弦相似度。
"""

import json
import os
import pickle
from pathlib import Path

import numpy as np

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

KB_DIR = Path(__file__).parent / "knowledge_base"
INDEX_PATH = Path(__file__).parent / "index.pkl"   # 持久化向量索引
SIMILARITY_THRESHOLD = 0.35
TOP_K = 3
MODEL_NAME = "paraphrase-multilingual-MiniLM-L12-v2"

# 模块级缓存：避免每次检索都重新加载模型
_model = None
_index: dict | None = None   # {"embeddings": np.ndarray, "docs": list[dict]}


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(MODEL_NAME)
    return _model


def build_index():
    """读取所有知识库 JSON，计算 embedding，保存到 index.pkl。"""
    model = _get_model()
    docs = []

    for json_file in KB_DIR.rglob("*.json"):
        try:
            doc = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        search_text = (
            f"{doc.get('title', '')} "
            f"{doc.get('summary', '')} "
            f"{' '.join(doc.get('tags', []))}"
        )
        docs.append({
            "search_text": search_text,
            "title":   doc.get("title", ""),
            "content": doc.get("content", ""),
            "summary": doc.get("summary", ""),
        })

    if not docs:
        print("知识库为空，跳过索引构建。")
        return

    texts = [d["search_text"] for d in docs]
    embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    index = {"embeddings": embeddings, "docs": docs}
    with open(INDEX_PATH, "wb") as f:
        pickle.dump(index, f)
    print(f"索引构建完成，共 {len(docs)} 篇文档。")

    global _index
    _index = index


def _load_index() -> dict | None:
    global _index
    if _index is not None:
        return _index
    if INDEX_PATH.exists():
        try:
            with open(INDEX_PATH, "rb") as f:
                _index = pickle.load(f)
            return _index
        except Exception:
            pass
    # 索引不存在则动态构建
    try:
        build_index()
    except Exception:
        pass
    return _index


def retrieve(query: str, difficulty_filter: str = None) -> str:
    """
    检索与 query 最相关的知识片段，返回可注入 system prompt 的字符串。
    无结果或出错时返回空字符串（不影响主流程）。
    """
    try:
        index = _load_index()
        if not index:
            return ""

        model = _get_model()
        query_emb = model.encode([query], normalize_embeddings=True)[0]

        embeddings = index["embeddings"]   # shape: (n_docs, dim)
        scores = embeddings @ query_emb    # 余弦相似度（已归一化）

        top_indices = np.argsort(scores)[::-1][:TOP_K]
        snippets = []
        for idx in top_indices:
            if scores[idx] < SIMILARITY_THRESHOLD:
                continue
            doc = index["docs"][idx]
            snippets.append(f"【{doc['title']}】\n{doc['content']}")

        if not snippets:
            return ""

        return (
            "以下是相关知识库内容，请基于此回答用户问题"
            "（如与用户实际情况不符可灵活调整）：\n\n"
            + "\n\n---\n\n".join(snippets)
        )
    except Exception:
        return ""
