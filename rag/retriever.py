"""
RAG 检索模块：查询改写 → ChromaDB 语义检索 → 相关度过滤 → 返回上下文片段。
"""

import json
from pathlib import Path

import os
import chromadb
from chromadb.utils import embedding_functions

# 使用 HuggingFace 镜像站，解决国内网络访问问题
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

KB_DIR = Path(__file__).parent / "knowledge_base"
CHROMA_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "xiaocai_knowledge"
SIMILARITY_THRESHOLD = 0.70   # 低于此相似度不注入
TOP_K = 3


def _get_collection():
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="paraphrase-multilingual-MiniLM-L12-v2"
    )
    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


def build_index():
    """读取知识库所有 JSON 文档，建立 ChromaDB 索引。只需运行一次。"""
    collection = _get_collection()
    docs, ids, metas = [], [], []

    for json_file in KB_DIR.rglob("*.json"):
        try:
            doc = json.loads(json_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        doc_id = doc.get("doc_id", json_file.stem)
        # 用 summary + title + tags 拼成检索文本，content 作为返回内容
        search_text = f"{doc.get('title', '')} {doc.get('summary', '')} {' '.join(doc.get('tags', []))}"
        docs.append(search_text)
        ids.append(doc_id)
        metas.append({
            "title": doc.get("title", ""),
            "category": doc.get("category", ""),
            "difficulty": doc.get("difficulty", ""),
            "content": doc.get("content", ""),
            "summary": doc.get("summary", ""),
        })

    if not docs:
        print("知识库为空，跳过索引构建。")
        return

    # 分批 upsert，避免一次太大
    batch = 50
    for i in range(0, len(docs), batch):
        collection.upsert(
            documents=docs[i:i+batch],
            ids=ids[i:i+batch],
            metadatas=metas[i:i+batch],
        )
    print(f"索引构建完成，共 {len(docs)} 篇文档。")


def retrieve(query: str, difficulty_filter: str = None) -> str:
    """
    检索与 query 相关的知识片段。
    返回拼接好的字符串，可直接注入 system prompt；无结果时返回空字符串。
    """
    try:
        collection = _get_collection()
    except Exception:
        return ""

    where = {"difficulty": difficulty_filter} if difficulty_filter else None
    try:
        results = collection.query(
            query_texts=[query],
            n_results=TOP_K,
            where=where,
            include=["metadatas", "distances"],
        )
    except Exception:
        return ""

    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    snippets = []
    for meta, dist in zip(metadatas, distances):
        similarity = 1 - dist   # cosine distance → similarity
        if similarity < SIMILARITY_THRESHOLD:
            continue
        title = meta.get("title", "")
        content = meta.get("content", "")
        snippets.append(f"【{title}】\n{content}")

    if not snippets:
        return ""

    return "以下是相关知识库内容，请基于此回答用户问题（如与用户实际情况不符可灵活调整）：\n\n" + \
           "\n\n---\n\n".join(snippets)
