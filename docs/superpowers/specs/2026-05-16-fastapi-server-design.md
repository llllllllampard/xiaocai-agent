# FastAPI HTTP Server 设计文档

**日期:** 2026-05-16  
**范围:** 为小财 agent 新增 FastAPI HTTP 服务，支持 SSE 流式输出，可部署至 Railway/Render

---

## 目标

为现有 agent 核心包一层 FastAPI HTTP 服务，暴露聊天 API，使任意网页前端（React/Vue）可通过 HTTP 调用小财，并能部署到 Railway/Render 获得公网地址。

---

## 新增文件

```
api/
├── __init__.py          # 空文件，使 api 成为 Python 包
└── main.py              # FastAPI 应用，所有路由在此定义
Procfile                 # Railway/Render 启动命令
```

不修改任何 `agent/` 文件。

---

## API 端点

### `POST /chat`

主聊天接口，SSE 流式输出。

**请求体（JSON）：**
```json
{
  "message": "什么是货币基金？",
  "session_id": "user-abc-123"
}
```
- `message`：用户消息，必填
- `session_id`：会话标识，可选，默认 `"default"`

**响应：** `Content-Type: text/event-stream`

每个 SSE event：
```
data: {"token": "货"}
data: {"token": "币"}
data: {"token": "基"}
data: {"token": "金"}
...
data: {"done": true, "intent": "knowledge_qa"}
```

**数据流：**
1. 加载 `UserProfile`
2. 调用 `detect_intent(message, profile)` 获取意图
3. 调用 `dispatch(intent, message, profile, rag_context=[])` 获取完整回复字符串
4. 按字符逐个 yield SSE event（模拟流式，因 Qwen 当前未开放流式接口）
5. 最终 yield `{"done": true, "intent": intent}`

**错误响应（非 SSE）：**
- `422 Unprocessable Entity`：请求体格式错误（FastAPI 自动处理）
- `500 Internal Server Error`：`{"error": "..."}`

---

### `GET /health`

健康检查。

**响应：**
```json
{"status": "ok"}
```

---

### `GET /docs`

FastAPI 自动生成的 Swagger UI 文档（无需手动实现）。

---

## CORS 配置

允许所有来源，方便前端本地开发直接调用：
```python
allow_origins=["*"]
allow_methods=["*"]
allow_headers=["*"]
```

---

## 新增依赖

`requirements.txt` 追加：
```
fastapi>=0.110.0
uvicorn>=0.29.0
python-multipart>=0.0.9
```

---

## 部署配置

### `Procfile`（Railway/Render 启动命令）

```
web: uvicorn api.main:app --host 0.0.0.0 --port $PORT
```

`$PORT` 由平台自动注入。

### 环境变量

在 Railway/Render 控制台设置：

| 变量名 | 说明 |
|---|---|
| `DASHSCOPE_API_KEY` | 阿里云 DashScope API Key |

### 部署步骤（Railway）

1. 打开 [railway.app](https://railway.app)，用 GitHub 账号登录
2. New Project → Deploy from GitHub repo → 选择此仓库
3. 在 Variables 面板添加 `DASHSCOPE_API_KEY`
4. 推送代码后自动构建并上线
5. 在 Settings → Domains 生成公网地址，如 `https://xiaocai-xxx.railway.app`

### 本地运行

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload --port 8000
```

访问 `http://localhost:8000/docs` 可直接测试接口。

---

## 会话与用户 profile

当前 `data/user_profile.json` 是单用户文件，所有 `session_id` 共用同一个 profile。对于比赛 demo 足够。后续可按 `session_id` 分文件存储扩展多用户支持。

---

## 不改动的文件

`agent/`、`rag/`、`skills/`、`data/`、`prompts/` 全部零改动。
