"""
四层记忆系统
L1 上下文记忆：由调用方管理（conversation_history list）
L2 会话记忆：Streamlit session_state（由 app.py 管理）
L3 情节记忆：episodes.jsonl，追加写入，带时间戳
L4 语义记忆：semantics.json，从情节记忆中提炼的用户模式
"""

import json
from datetime import datetime, timedelta
from pathlib import Path


DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


# ── 默认用户画像 ─────────────────────────────────────────────
DEFAULT_PROFILE = {
    "onboarding_done": False,
    "risk_level": None,           # 保守型 / 稳健型 / 积极型
    "financial_goals": [],        # [{name, target_amount, monthly_saving, deadline, current_amount}]
    "learned_concepts": [],       # ["货币基金", "复利", ...]
    "interaction_count": 0,       # 累计对话轮次
}

DEFAULT_SEMANTICS = {
    "inferred_risk_profile": None,    # {profile, confidence}
    "learning_style": "unknown",      # concise / balanced / detailed
    "avg_weekly_spending": None,
    "top_spending_category": None,
    "concept_maturity": {},           # {"货币基金": 0.9, ...}
    "engagement_score": 0.5,
}


# ── L3 情节记忆 ───────────────────────────────────────────────
class EpisodicMemory:
    def __init__(self):
        self.path = DATA_DIR / "episodes.jsonl"

    def record(self, episode_type: str, content: dict):
        episode = {
            "timestamp": datetime.now().isoformat(),
            "type": episode_type,
            "content": content,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(episode, ensure_ascii=False) + "\n")

    def get_recent(self, episode_type: str, days: int = 30) -> list:
        if not self.path.exists():
            return []
        # days=0 表示获取所有记录，不做时间过滤
        if days == 0:
            return self.get_all(episode_type)
        cutoff = datetime.now() - timedelta(days=days)
        results = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                ep = json.loads(line)
                if ep["type"] == episode_type:
                    if datetime.fromisoformat(ep["timestamp"]) > cutoff:
                        results.append(ep)
        return results

    def get_all(self, episode_type: str) -> list:
        return self.get_recent(episode_type, days=3650)


# ── L4 语义记忆 ───────────────────────────────────────────────
class SemanticMemory:
    def __init__(self):
        self.path = DATA_DIR / "semantics.json"

    def load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return DEFAULT_SEMANTICS.copy()

    def save(self, data: dict):
        self.path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def update(self, key: str, value, ema_weight: float = 0.8):
        """数值型字段用指数移动平均更新，其他直接覆盖。"""
        data = self.load()
        if isinstance(value, (int, float)) and isinstance(data.get(key), (int, float)):
            data[key] = ema_weight * value + (1 - ema_weight) * data[key]
        else:
            data[key] = value
        self.save(data)

    def mark_concept_learned(self, concept: str, maturity: float = 0.6):
        data = self.load()
        maturity_map = data.get("concept_maturity", {})
        old = maturity_map.get(concept, 0.0)
        maturity_map[concept] = max(old, maturity)
        data["concept_maturity"] = maturity_map
        self.save(data)


# ── 用户画像（L2/L3 基础） ────────────────────────────────────
class UserProfile:
    def __init__(self):
        self.path = DATA_DIR / "user_profile.json"

    def load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return DEFAULT_PROFILE.copy()

    def save(self, profile: dict):
        self.path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def update(self, **kwargs):
        profile = self.load()
        profile.update(kwargs)
        self.save(profile)

    def add_goal(self, name: str, target_amount: float, monthly_saving: float,
                 deadline: str, current_amount: float = 0.0):
        profile = self.load()
        profile["financial_goals"].append({
            "name": name,
            "target_amount": target_amount,
            "monthly_saving": monthly_saving,
            "deadline": deadline,
            "current_amount": current_amount,
        })
        self.save(profile)

    def add_learned_concept(self, concept: str):
        profile = self.load()
        if concept not in profile["learned_concepts"]:
            profile["learned_concepts"].append(concept)
            self.save(profile)


# ── 对话历史持久化 ────────────────────────────────────────────
class ConversationHistory:
    """持久化对话历史，按session分组存储"""

    def __init__(self):
        self.path = DATA_DIR / "conversations.jsonl"

    def save_session(self, session_id: str, messages: list):
        """保存一次完整的对话session（upsert逻辑：同id则替换，否则追加）"""
        existing = []
        if self.path.exists():
            with open(self.path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        existing.append(json.loads(line))

        timestamp = datetime.now().isoformat()
        updated = False
        for i, record in enumerate(existing):
            if record.get("session_id") == session_id:
                existing[i] = {
                    "session_id": session_id,
                    "timestamp": record.get("timestamp", timestamp),  # 保留首次时间
                    "messages": messages,
                }
                updated = True
                break

        if not updated:
            existing.append({
                "session_id": session_id,
                "timestamp": timestamp,
                "messages": messages,
            })

        with open(self.path, "w", encoding="utf-8") as f:
            for record in existing:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def get_sessions(self, limit: int = 10) -> list:
        """获取最近的N个对话session摘要（session_id, 时间, 第一条用户消息, 消息数）"""
        if not self.path.exists():
            return []
        sessions = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                messages = record.get("messages", [])
                first_user_msg = ""
                for msg in messages:
                    if msg.get("role") == "user":
                        first_user_msg = msg.get("content", "")[:50]
                        break
                sessions.append({
                    "session_id": record["session_id"],
                    "timestamp": record.get("timestamp", ""),
                    "first_user_msg": first_user_msg,
                    "message_count": len(messages),
                })
        # 按时间倒序，取最近N条
        sessions.sort(key=lambda x: x["timestamp"], reverse=True)
        return sessions[:limit]

    def get_session_messages(self, session_id: str) -> list:
        """获取某个session的完整消息列表"""
        if not self.path.exists():
            return []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                if record.get("session_id") == session_id:
                    return record.get("messages", [])
        return []

    def clear_all(self):
        """清空所有对话历史"""
        if self.path.exists():
            self.path.write_text("", encoding="utf-8")
