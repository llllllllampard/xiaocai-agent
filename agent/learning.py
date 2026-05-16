"""
持续学习引擎：从用户行为中提取信号，动态更新语义记忆，生成自适应 Prompt 片段。
B1: 基于对话轮次分阶段激活自适应能力
B3: 上下文超长时摘要压缩
B4: 情绪词汇补全（市场波动 + 攒钱受挫）
C4: 学习路径推荐
C7: 风险推断不覆盖测评结果
"""

import os
import re
from openai import OpenAI
from .memory import EpisodicMemory, SemanticMemory, UserProfile

episodic = EpisodicMemory()
semantic = SemanticMemory()


LEARNING_PATH = {
    "货币基金": ["基金", "债券"],
    "基金":     ["指数基金", "ETF", "定投"],
    "债券":     ["资产配置"],
    "指数基金": ["资产配置", "市盈率"],
    "ETF":      ["指数基金", "资产配置"],
    "定投":     ["复利", "止损"],
    "复利":     ["资产配置"],
    "风险":     ["资产配置", "止损"],
    "收益":     ["年化", "复利"],
    "年化":     ["复利", "资产配置"],
}

# B4：市场波动焦虑 + 攒钱受挫两类情绪全覆盖
ANXIETY_WORDS = [
    # 市场波动类
    "亏", "跌", "慌", "要不要卖", "割肉", "后悔", "怕", "焦虑", "暴跌", "赔",
    "血亏", "绿了", "套牢", "腰斩", "崩了",
    # 攒钱受挫类（B4新增）
    "坚持不下去", "攒不住", "又花完了", "没毅力", "控制不住", "月光",
    "存不下来", "花钱停不下来", "没存到", "计划失败", "又超支了",
]
CONSERVATIVE_WORDS = ["安全", "稳健", "保本", "不亏", "低风险", "稳", "保守", "存款"]
AGGRESSIVE_WORDS = ["高收益", "赚钱", "暴富", "翻倍", "高回报", "激进", "冒险", "炒"]
CONFUSED_WORDS = ["什么意思", "能再解释", "不懂", "看不懂", "说人话", "搞不懂", "没听懂", "能详细"]
SATISFIED_WORDS = ["懂了", "明白了", "好的", "清楚了", "原来如此", "谢谢", "get到", "学会了"]


def detect_emotion(text: str) -> bool:
    return any(w in text for w in ANXIETY_WORDS)


def detect_satisfaction(text: str) -> bool:
    return any(w in text for w in SATISFIED_WORDS)


def detect_confusion(text: str) -> bool:
    return any(w in text for w in CONFUSED_WORDS)


def update_risk_signal(text: str):
    """从用户提问关键词推断风险偏好倾向，更新语义记忆。"""
    data = semantic.load()
    profile_data = data.get("inferred_risk_profile") or {"conservative": 0, "aggressive": 0, "balanced": 0}
    if not isinstance(profile_data, dict) or "conservative" not in profile_data:
        profile_data = {"conservative": 0, "aggressive": 0, "balanced": 0}

    if any(w in text for w in CONSERVATIVE_WORDS):
        profile_data["conservative"] = profile_data.get("conservative", 0) + 1
    elif any(w in text for w in AGGRESSIVE_WORDS):
        profile_data["aggressive"] = profile_data.get("aggressive", 0) + 1
    else:
        profile_data["balanced"] = profile_data.get("balanced", 0) + 1

    total = sum(profile_data.values()) or 1
    top = max(profile_data, key=profile_data.get)
    confidence = profile_data[top] / total

    semantic.update("inferred_risk_profile", {
        "profile": top,
        "confidence": round(confidence, 2),
        "counts": profile_data,
    })


def update_learning_style(response_length: int):
    """根据 agent 回复长度的历史均值推断用户偏好。"""
    data = semantic.load()
    old = data.get("avg_response_length", response_length)
    new_avg = 0.8 * response_length + 0.2 * old
    semantic.update("avg_response_length", new_avg)

    if new_avg < 180:
        style = "concise"
    elif new_avg < 380:
        style = "balanced"
    else:
        style = "detailed"
    semantic.update("learning_style", style)


def generate_adaptive_prompt_addon(profile: dict) -> str:
    """
    根据语义记忆生成追加到 system prompt 末尾的自适应规则。
    返回一段文字，由 handlers 拼接到 system prompt 中。
    """
    sem = semantic.load()
    lines = []

    # 学习风格
    style = sem.get("learning_style", "unknown")
    if style == "concise":
        lines.append("用户偏好简洁回答：请用 bullet points，每次回复不超过 150 字。")
    elif style == "detailed":
        lines.append("用户喜欢详细解释：可以展开讲，包含例子和细节，不必刻意压缩篇幅。")

    # 已掌握概念
    learned = profile.get("learned_concepts", [])
    if learned:
        lines.append(f"用户已掌握的概念（请跳过基础介绍，直接进阶）：{'、'.join(learned)}。")

    # 风险偏好：优先使用测评结果，行为推断仅作补充观察
    inferred = sem.get("inferred_risk_profile")
    assessed_risk = profile.get("risk_level")  # 测评结果（冷启动三题）
    if inferred and isinstance(inferred, dict) and inferred.get("confidence", 0) > 0.80:
        mapping = {"conservative": "保守型", "aggressive": "积极型", "balanced": "稳健型"}
        label = mapping.get(inferred["profile"], inferred["profile"])
        if assessed_risk:
            # 已有测评结果：推断仅作补充，不覆盖
            lines.append(
                f"用户测评风险偏好为 {assessed_risk}，行为观察（补充参考）：偏向 {label}"
                f"（置信度 {inferred['confidence']:.0%}）。以测评结果为主要依据。"
            )
        else:
            # 无测评结果：使用推断值
            lines.append(f"行为推断：用户偏向 {label}（置信度 {inferred['confidence']:.0%}），给建议时请参考。")
    elif assessed_risk:
        # 有测评结果但推断置信度不足：仅展示测评结果
        lines.append(f"用户测评风险偏好为 {assessed_risk}，请以此为主要依据给出建议。")

    # 消费特征
    top_cat = sem.get("top_spending_category")
    if top_cat:
        lines.append(f"消费特征：用户最大支出类别是「{top_cat}」，复盘时可重点关注。")

    # B1：第7轮+才启用学习风格（否则样本太少不准）
    interaction_count = profile.get("interaction_count", 0)
    if interaction_count < 7:
        # 移除刚才已写入的学习风格行（样本不足时不注入）
        lines = [l for l in lines if "偏好简洁" not in l and "喜欢详细" not in l]

    # C4：学习路径推荐（第15轮+才主动推送进阶）
    concept_maturity = sem.get("concept_maturity", {})
    recommended = []
    for concept, maturity in concept_maturity.items():
        if maturity > 0.7:
            for next_concept in LEARNING_PATH.get(concept, []):
                if concept_maturity.get(next_concept, 0) <= 0.7 and next_concept not in recommended:
                    recommended.append(next_concept)
    if recommended and interaction_count >= 15:
        lines.append(f"根据用户学习进度，建议在合适时机引导学习：{'、'.join(recommended[:3])}。")
    elif recommended:
        # 15轮以内：只做隐性准备，不强推
        lines.append(f"用户已掌握基础，待熟练后可引导学习：{'、'.join(recommended[:2])}（暂勿主动提及）。")

    # B1：第30轮+注入个性化消费模式建议
    if interaction_count >= 30:
        avg_weekly = sem.get("avg_weekly_spending")
        if avg_weekly:
            lines.append(
                f"用户周均消费约 {avg_weekly:.0f} 元，消费模式已相对稳定，"
                f"可提供更个性化的储蓄优化建议。"
            )

    if not lines:
        return ""
    return "\n### 动态自适应规则\n" + "\n".join(f"- {l}" for l in lines)


# ── B3：上下文摘要压缩 ────────────────────────────────────────
def compress_context_if_needed(history: list, threshold: int = 20) -> list:
    """
    B3：对话超过 threshold 轮时，将旧对话用轻量模型压缩为摘要，保留最近10轮完整。
    失败时静默降级为滑动窗口，不影响主流程。
    """
    if len(history) <= threshold:
        return history

    keep_recent = 10
    old_messages = history[:-keep_recent]
    recent_messages = history[-keep_recent:]

    try:
        api_key = os.environ.get("DASHSCOPE_API_KEY")
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets.get("DASHSCOPE_API_KEY")
            except Exception:
                pass
        if not api_key:
            return history[-keep_recent:]

        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        conv_text = "\n".join(
            f"{'用户' if m['role']=='user' else '小财'}: {str(m.get('content',''))[:200]}"
            for m in old_messages
        )
        resp = client.chat.completions.create(
            model="qwen-turbo",
            messages=[{"role": "user", "content":
                f"请用100字以内总结以下对话的关键信息，保留：用户财务状况、目标、已学概念、主要问题：\n{conv_text}"
            }],
            max_tokens=200,
        )
        summary = resp.choices[0].message.content or ""
        summary = re.sub(r"<think>.*?</think>", "", summary, flags=re.DOTALL).strip()
        return [{"role": "assistant", "content": f"[早期对话摘要] {summary}"}] + recent_messages

    except Exception:
        return history[-keep_recent:]
