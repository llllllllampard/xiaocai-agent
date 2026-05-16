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
