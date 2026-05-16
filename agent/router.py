"""
场景路由器：根据用户消息和当前状态，判断应进入哪个 Handler。
"""

from .learning import detect_emotion, detect_confusion
from .memory import UserProfile

INTENT_ONBOARDING = "onboarding"
INTENT_KNOWLEDGE_QA = "knowledge_qa"
INTENT_EXPENSE_REVIEW = "expense_review"
INTENT_EMOTION_SUPPORT = "emotion_support"
INTENT_GOAL_CHECK = "goal_check"
INTENT_GENERAL = "general"
INTENT_IMAGE_ANALYSIS = "image_analysis"

KNOWLEDGE_KEYWORDS = [
    "什么是", "怎么理解", "能解释", "是什么意思", "基金", "股票", "ETF",
    "债券", "定投", "复利", "风险", "收益", "净值", "仓位", "货币基金",
    "指数基金", "年化", "分散", "资产配置", "保险", "利率",
]

EXPENSE_KEYWORDS = [
    "消费", "复盘", "钱花哪", "花了多少", "支出", "账单", "记录",
    "帮我看看", "分析一下", "录入", "记一笔",
]

GOAL_KEYWORDS = [
    "目标", "进度", "攒了多少", "还差多少", "计划", "旅行基金",
    "备用金", "存款", "攒钱",
]


def route(user_message: str, profile: dict) -> str:
    """返回意图常量，由 handlers.py 根据意图分发处理。"""

    # 新用户强制冷启动
    if not profile.get("onboarding_done"):
        return INTENT_ONBOARDING

    # 情绪陪伴优先级最高（需要立刻响应）
    if detect_emotion(user_message):
        return INTENT_EMOTION_SUPPORT

    msg = user_message.lower()

    if any(kw in msg for kw in EXPENSE_KEYWORDS):
        return INTENT_EXPENSE_REVIEW

    if any(kw in msg for kw in GOAL_KEYWORDS):
        return INTENT_GOAL_CHECK

    if any(kw in msg for kw in KNOWLEDGE_KEYWORDS):
        return INTENT_KNOWLEDGE_QA

    return INTENT_GENERAL
