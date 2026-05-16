from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_missing_message_returns_422():
    response = client.post("/chat", json={"session_id": "test"})
    assert response.status_code == 422


def test_chat_empty_message_returns_422():
    response = client.post("/chat", json={"message": "", "session_id": "test"})
    assert response.status_code == 422
