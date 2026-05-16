# 移除 Streamlit 前端 — 设计文档

**日期:** 2026-05-16  
**范围:** 仅清理前端文件，保留 agent 核心逻辑完整不变

---

## 目标

删除所有 Streamlit 前端代码，留下一个纯 Python agent 核心，供后续接入任意前端。

---

## 要删除的文件

| 文件/目录 | 原因 |
|---|---|
| `app.py` | Streamlit 主入口（1076行），全部是 UI 代码 |
| `.streamlit/config.toml` | Streamlit 主题配置，无 agent 逻辑 |
| `.streamlit/secrets.toml` | Streamlit secrets，API key 已由 `.env` 承载 |
| `.streamlit/`（整个目录） | 同上 |

---

## 要修改的文件

### `requirements.txt`
- 移除 `streamlit>=1.35.0` 一行
- 其余依赖不动

### `agent/memory.py`
- **无需修改。** 经核查，`memory.py` 中没有任何 `streamlit` import。
- L2 层（会话状态）完全由 `app.py` 的 `st.session_state` 管理，随 `app.py` 一起删除即可。
- L1/L3/L4 层逻辑完整保留。

---

## 不动的文件（完整保留）

- `agent/router.py` — 意图路由
- `agent/handlers.py` — LLM 调用与合规检查
- `agent/learning.py` — 自适应学习引擎
- `agent/skills_manager.py` — Skill 注入
- `agent/tools.py` — 金融计算工具
- `agent/memory.py` — 四层记忆系统
- `rag/` — RAG 检索
- `skills/` — Skill 注册表与 prompt
- `data/` — 持久化用户数据
- `prompts/system_base.md` — 基础系统 prompt

---

## 删除后的状态

agent 核心完整可用，但没有运行入口。调用方式：

```python
from agent.router import detect_intent
from agent.handlers import dispatch
from agent.memory import UserProfile

profile = UserProfile().load()
intent = detect_intent(user_message, profile)
reply, updated_profile = dispatch(intent, user_message, profile, rag_context=[])
```

后续可接入任意前端（FastAPI、React、微信小程序等）。
