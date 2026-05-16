"""
构建 ChromaDB 知识库索引。
- 本地手动运行：python rag/build_index.py
- 部署时：由 app.py 在启动时自动调用（仅当索引不存在时）
"""
import os
import sys
from pathlib import Path

# 设置 HuggingFace 镜像（解决国内/Cloud网络问题）
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

sys.path.insert(0, str(Path(__file__).parent.parent))

from rag.retriever import build_index

if __name__ == "__main__":
    print("开始构建知识库索引...")
    build_index()
    print("完成！")
