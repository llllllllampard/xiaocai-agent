# FastAPI HTTP Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为小财 agent 新增 FastAPI HTTP 服务，暴露 SSE 流式聊天 API，可部署至 Railway/Render 获得公网地址。

**Architecture:** 新建 `api/main.py` 包含所有路由，不修改任何 `agent/` 代码。`POST /chat` 调用现有 `route()` + `dispatch()`，把完整回复按字符逐个 yield 为 SSE event。新增 `Procfile` 供 Railway/Render 使用。

**Tech Stack:** FastAPI 0.110+, uvicorn 0.29+, Python SSE (StreamingResponse), python-dotenv

---

## 文件结构

| 文件 | 操作 | 职责 |
|---|---|---|
| `api/__init__.py` | 新建（空） | 使 api 成为 Python 包 |
| `api/main.py` | 新建 | FastAPI 应用，所有路由 |
| `Procfile` | 新建 | Railway/Render 启动命令 |
| `requirements.txt` | 修改 | 追加 fastapi, uvicorn, python-multipart |

---

### Task 1: 添加 FastAPI 依赖

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 追加依赖**

将 `requirements.txt` 改为：
```
openai>=1.30.0
sentence-transformers>=3.0.0
numpy>=1.26.0
python-dotenv>=1.0.0
fastapi>=0.110.0
uvicorn>=0.29.0
python-multipart>=0.0.9
```

- [ ] **Step 2: 安装依赖**

```bash
pip install fastapi>=0.110.0 uvicorn>=0.29.0 python-multipart>=0.0.9
```

Expected: 安装成功，无报错

- [ ] **Step 3: 验证 FastAPI 可导入**

```bash
python -c "import fastapi; import uvicorn; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: add fastapi and uvicorn dependencies"
```

---

### Task 2: 创建 api 包和 FastAPI 应用骨架

**Files:**
- Create: `api/__init__.py`
- Create: `api/main.py`

- [ ] **Step 1: 写测试（健康检查端点）**

新建文件 `tests/test_api.py`：

```python
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_api.py::test_health -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'api'`

- [ ] **Step 3: 创建 api/__init__.py（空文件）**

创建空文件 `api/__init__.py`（内容为空即可）。

- [ ] **Step 4: 创建 api/main.py 骨架**

```python
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

app = FastAPI(title="小财 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
python -m pytest tests/test_api.py::test_health -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add api/__init__.py api/main.py tests/test_api.py
git commit -m "feat: add FastAPI app skeleton with health endpoint"
```

---

### Task 3: 实现 POST /chat SSE 流式端点

**Files:**
- Modify: `api/main.py`
- Modify: `tests/test_api.py`

**背景知识：**
- `agent/router.py` 的 `route(user_message, profile)` 返回意图字符串
- `agent/handlers.py` 的 `dispatch(intent, user_msg, history, profile, expenses, rag_context, image_base64)` 返回 `(reply: str, updated_profile: dict)`
- `agent/memory.py` 的 `UserProfile().load()` 返回用户画像 dict

- [ ] **Step 1: 写测试**

在 `tests/test_api.py` 末尾追加：

```python
def test_chat_returns_sse():
    response = client.post(
        "/chat",
        json={"message": "你好", "session_id": "test-session"},
        headers={"Accept": "text/event-stream"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]
    # 响应体包含 SSE data 行
    assert b"data:" in response.content


def test_chat_missing_message_returns_422():
    response = client.post("/chat", json={"session_id": "test"})
    assert response.status_code == 422


def test_chat_empty_message_returns_422():
    response = client.post("/chat", json={"message": "", "session_id": "test"})
    assert response.status_code == 422
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
python -m pytest tests/test_api.py -v
```

Expected: `test_health` PASS，其余 FAIL — `404 Not Found`

- [ ] **Step 3: 实现 /chat 端点**

将 `api/main.py` 改为完整版：

```python
import json
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, field_validator

load_dotenv()

app = FastAPI(title="小财 API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

    @field_validator("message")
    @classmethod
    def message_must_not_be_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("message must not be empty")
        return v


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _stream_reply(reply: str, intent: str):
    for char in reply:
        yield _sse_event({"token": char})
    yield _sse_event({"done": True, "intent": intent})


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    from agent.router import route
    from agent.handlers import dispatch
    from agent.memory import UserProfile

    profile = UserProfile().load()
    intent = route(req.message, profile)
    reply, _ = dispatch(
        intent=intent,
        user_msg=req.message,
        history=[],
        profile=profile,
        rag_context="",
    )

    return StreamingResponse(
        _stream_reply(reply, intent),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
```

- [ ] **Step 4: 运行测试，确认通过**

```bash
python -m pytest tests/test_api.py -v
```

Expected: 全部 PASS（注意：`test_chat_returns_sse` 会真正调用 LLM，需要 `DASHSCOPE_API_KEY` 环境变量有效）

如果没有有效 API Key，跳过该测试用例，手动验证：
```bash
python -m pytest tests/test_api.py::test_chat_missing_message_returns_422 tests/test_api.py::test_chat_empty_message_returns_422 tests/test_api.py::test_health -v
```

Expected: 3 个非 LLM 测试全部 PASS

- [ ] **Step 5: 手动验证流式输出**

```bash
uvicorn api.main:app --reload --port 8000
```

另开终端：
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"你好，小财","session_id":"test"}' \
  --no-buffer
```

Expected: 看到逐行输出 `data: {"token": "你"}` 等 SSE event，最后 `data: {"done": true, ...}`

- [ ] **Step 6: Commit**

```bash
git add api/main.py tests/test_api.py
git commit -m "feat: implement POST /chat SSE streaming endpoint"
```

---

### Task 4: 新增 Procfile 供 Railway/Render 部署

**Files:**
- Create: `Procfile`

- [ ] **Step 1: 创建 Procfile**

新建文件 `Procfile`，内容：
```
web: uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

- [ ] **Step 2: 验证文件内容**

```bash
cat Procfile
```

Expected: `web: uvicorn api.main:app --host 0.0.0.0 --port $PORT`

- [ ] **Step 3: Commit**

```bash
git add Procfile
git commit -m "chore: add Procfile for Railway/Render deployment"
```

---

### Task 5: 部署到 Railway

**Files:** 无代码变更，仅操作 Railway 控制台

- [ ] **Step 1: 推送代码到 GitHub**

```bash
git push origin master
```

确认 GitHub 仓库已有最新代码。

- [ ] **Step 2: 在 Railway 创建项目**

1. 打开 [https://railway.app](https://railway.app)，用 GitHub 登录
2. 点击 **New Project** → **Deploy from GitHub repo**
3. 选择 `ZSYH-PM-competiton` 仓库
4. Railway 自动检测 `Procfile` 并开始构建

- [ ] **Step 3: 设置环境变量**

在 Railway 项目页面：
1. 点击服务 → **Variables** 标签
2. 添加变量：`DASHSCOPE_API_KEY` = 你的阿里云 DashScope API Key

- [ ] **Step 4: 生成公网域名**

在 Railway 项目页面：
1. 点击服务 → **Settings** → **Networking**
2. 点击 **Generate Domain**，得到形如 `https://xiaocai-xxx.railway.app` 的地址

- [ ] **Step 5: 验证部署成功**

```bash
curl https://你的域名.railway.app/health
```

Expected: `{"status":"ok"}`

```bash
curl -X POST https://你的域名.railway.app/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"你好小财","session_id":"test"}' \
  --no-buffer
```

Expected: SSE 流式回复正常输出
