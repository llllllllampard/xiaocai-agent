"""
对话 Handler 层：每个场景的完整对话处理逻辑。
使用 OpenAI 兼容接口对接阿里云百炼。
所有 Handler 返回 (assistant_reply: str, updated_profile: dict)。
"""

import json
import os
import re
from pathlib import Path

from openai import OpenAI

from .memory import EpisodicMemory, SemanticMemory, UserProfile
from .tools import TOOL_DEFINITIONS, dispatch_tool
from .learning import generate_adaptive_prompt_addon, update_risk_signal, update_learning_style
from .skills_manager import get_skill_prompt_addon, record_skill_usage
from .router import (
    INTENT_ONBOARDING, INTENT_KNOWLEDGE_QA, INTENT_EXPENSE_REVIEW,
    INTENT_EMOTION_SUPPORT, INTENT_GOAL_CHECK, INTENT_GENERAL,
    INTENT_IMAGE_ANALYSIS,
)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
BASE_SYSTEM = (PROMPTS_DIR / "system_base.md").read_text(encoding="utf-8")

episodic = EpisodicMemory()
semantic = SemanticMemory()
user_profile_store = UserProfile()

BAILIAN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
MODEL = "qwen3.5-plus"

# ── C2：违规内容检测正则（预编译提升效率）────────────────────────
_VIOLATION_PATTERNS = [
    re.compile(p) for p in [
        r"推荐.*股票代码",
        r"买入.*代码",
        r"保证.*收益",
        r"稳赚",
        r"无风险.*%",
    ]
]
_DISCLAIMER = (
    "\n\n⚠️ 温馨提示：以上为通用知识分享，不构成具体投资建议，"
    "投资有风险，请谨慎决策。"
)


def _get_client() -> OpenAI:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    return OpenAI(api_key=api_key, base_url=BAILIAN_BASE_URL)


# ── Tool schema 转换（Anthropic格式 → OpenAI格式）─────────────
def _to_openai_tools(tool_defs: list) -> list:
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tool_defs
    ]


OPENAI_TOOLS = _to_openai_tools(TOOL_DEFINITIONS)


def _build_system_prompt(profile: dict, extra: str = "", rag_context: str = "", intent: str = "") -> str:
    """构造完整 system prompt 字符串。"""
    parts = [BASE_SYSTEM]

    dynamic_parts = []
    if profile.get("risk_level"):
        dynamic_parts.append(f"用户风险偏好：{profile['risk_level']}")
    goals = profile.get("financial_goals", [])
    if goals:
        g = goals[0]
        dynamic_parts.append(
            f"当前目标：{g['name']} {g['current_amount']}/{g['target_amount']} 元，"
            f"每月存 {g['monthly_saving']} 元"
        )
    learned = profile.get("learned_concepts", [])
    if learned:
        dynamic_parts.append(f"已掌握概念：{'、'.join(learned)}")

    if dynamic_parts:
        parts.append("\n### 当前用户画像\n" + "\n".join(f"- {p}" for p in dynamic_parts))

    adaptive = generate_adaptive_prompt_addon(profile)
    if adaptive:
        parts.append(adaptive)

    if extra:
        parts.append(f"\n### 当前场景指令\n{extra}")

    skill_addon = get_skill_prompt_addon(intent) if intent else ""
    if skill_addon:
        parts.append(skill_addon)

    if rag_context:
        parts.append(f"\n{rag_context}")

    return "\n".join(parts)


def _call_llm(system_prompt: str, history: list, user_msg: str, use_tools: bool = False) -> str:
    """调用百炼 LLM，处理 tool_call 循环，返回最终文本回复。"""
    # C3：API 调用失败时返回友好提示，不崩溃
    try:
        client = _get_client()

        messages = [{"role": "system", "content": system_prompt}]
        messages += history
        messages.append({"role": "user", "content": user_msg})

        kwargs = dict(model=MODEL, messages=messages, max_tokens=800)
        if use_tools:
            kwargs["tools"] = OPENAI_TOOLS
            kwargs["tool_choice"] = "auto"

        response = client.chat.completions.create(**kwargs)
        msg = response.choices[0].message

        # Tool call 循环
        while msg.tool_calls:
            messages.append(msg)
            for tc in msg.tool_calls:
                try:
                    inputs = json.loads(tc.function.arguments)
                except Exception:
                    inputs = {}
                result = dispatch_tool(tc.function.name, inputs)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
            response = client.chat.completions.create(**kwargs | {"messages": messages})
            msg = response.choices[0].message

        reply = _strip_think(msg.content or "")
    except Exception:
        return "小财现在有点忙，稍后再试试吧～"

    # C2：违规内容后置检查，命中则追加免责声明
    if any(p.search(reply) for p in _VIOLATION_PATTERNS):
        reply += _DISCLAIMER

    return reply


def _strip_think(text: str) -> str:
    """过滤 qwen3 系列模型输出的 <think>...</think> 思考过程。"""
    import re
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


# ── 各场景 Handler ────────────────────────────────────────────

def handle_onboarding(user_msg: str, history: list, profile: dict) -> tuple[str, dict]:
    """冷启动：理财目标 → 风险测评 → 第一步建议。"""
    extra = (PROMPTS_DIR / "onboarding.md").read_text(encoding="utf-8") if (PROMPTS_DIR / "onboarding.md").exists() else ""
    system = _build_system_prompt(profile, extra=extra, intent="onboarding")
    reply = _call_llm(system, history, user_msg, use_tools=True)

    for level in ["保守型", "稳健型", "积极型"]:
        if level in reply:
            profile["risk_level"] = level
            profile["onboarding_done"] = True
            user_profile_store.save(profile)
            episodic.record("risk_test_completed", {"result": level})
            break

    update_risk_signal(user_msg)
    return reply, profile


def handle_knowledge_qa(user_msg: str, history: list, profile: dict, rag_context: str = "") -> tuple[str, dict]:
    """知识问答：自适应难度 + RAG 增强。"""
    extra = (PROMPTS_DIR / "knowledge_qa.md").read_text(encoding="utf-8") if (PROMPTS_DIR / "knowledge_qa.md").exists() else ""
    system = _build_system_prompt(profile, extra=extra, rag_context=rag_context, intent="knowledge_qa")
    reply = _call_llm(system, history, user_msg, use_tools=False)

    episodic.record("question_asked", {"text": user_msg})
    concept = _extract_concept(user_msg)
    semantic.mark_concept_learned(concept, maturity=0.6)
    update_learning_style(len(reply))
    # 把语义记忆同步回 profile
    profile["learned_concepts"] = list(semantic.load().get("concept_maturity", {}).keys())
    user_profile_store.save(profile)
    return reply, profile


def handle_expense_review(user_msg: str, history: list, profile: dict, expenses: list) -> tuple[str, dict]:
    """消费复盘：分析结构 + 发起对话。"""
    extra = f"""当前场景：消费复盘。
用户近期消费数据：
{json.dumps(expenses, ensure_ascii=False, indent=2)}
请按三步骤发起复盘：数据呈现→一个关注点→开放询问。"""
    system = _build_system_prompt(profile, extra=extra, intent="expense_review")
    reply = _call_llm(system, history, user_msg, use_tools=True)

    if expenses:
        from .tools import analyze_expense_distribution
        result = analyze_expense_distribution(expenses)
        if "top_category" in result:
            semantic.update("top_spending_category", result["top_category"])
            semantic.update("avg_weekly_spending", result.get("total", 0) / 4)

    return reply, profile


def handle_emotion_support(user_msg: str, history: list, profile: dict) -> tuple[str, dict]:
    """情绪陪伴：共情 → 认知引导 → 决策框架。"""
    extra = """当前场景：情绪陪伴。
用户出现焦虑/恐慌信号。严格按三步骤回应：
1. 先共情（1-2句，不评判）
2. 引导认知（1个反常识视角）
3. 给3个自问问题（不直接说买或卖）
绝对不得给出应该卖或应该持有的直接操作建议。"""
    system = _build_system_prompt(profile, extra=extra, intent="emotion_support")
    reply = _call_llm(system, history, user_msg, use_tools=False)
    episodic.record("emotion_event", {"text": user_msg, "type": "anxiety"})
    return reply, profile


def handle_goal_check(user_msg: str, history: list, profile: dict) -> tuple[str, dict]:
    """目标进度查询。"""
    system = _build_system_prompt(profile)
    reply = _call_llm(system, history, user_msg, use_tools=True)
    return reply, profile


def handle_general(user_msg: str, history: list, profile: dict, rag_context: str = "") -> tuple[str, dict]:
    """通用对话兜底。"""
    system = _build_system_prompt(profile, rag_context=rag_context)
    reply = _call_llm(system, history, user_msg, use_tools=True)
    update_risk_signal(user_msg)
    return reply, profile


def handle_image_analysis(image_base64: str, user_msg: str, history: list, profile: dict) -> tuple[str, dict]:
    """处理包含图片的消息，支持账单分析、K线图解读等。"""
    system = _build_system_prompt(profile, extra="""
    用户上传了一张图片，请仔细分析图片内容，结合用户的问题给出专业建议。
    常见场景：
    1. 账单/消费截图：分析消费结构，给出建议
    2. 基金/股票K线图：解读走势，注意不要直接建议买卖
    3. 理财产品截图：解读产品信息，说明风险
    4. 其他金融相关图片：专业解读
    重要：分析图片时保持小财的温柔导师风格，不推荐具体产品代码。
    """, intent="image_analysis")

    client = _get_client()
    messages_with_image = history + [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
            {"type": "text", "text": user_msg or "请帮我分析这张图片"},
        ],
    }]

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "system", "content": system}] + messages_with_image,
            max_tokens=800,
        )
        reply = _strip_think(response.choices[0].message.content or "")
    except Exception:
        reply = "图片收到啦！不过我现在暂时无法直接识别图片内容，你可以描述一下图片里的内容，我来帮你分析～"

    return reply, profile


def dispatch(intent: str, user_msg: str, history: list, profile: dict,
             expenses: list = None, rag_context: str = "",
             image_base64: str = "") -> tuple[str, dict]:
    if intent == INTENT_IMAGE_ANALYSIS:
        result = handle_image_analysis(image_base64, user_msg, history, profile)
    elif intent == INTENT_ONBOARDING:
        result = handle_onboarding(user_msg, history, profile)
    elif intent == INTENT_KNOWLEDGE_QA:
        result = handle_knowledge_qa(user_msg, history, profile, rag_context)
    elif intent == INTENT_EXPENSE_REVIEW:
        result = handle_expense_review(user_msg, history, profile, expenses or [])
    elif intent == INTENT_EMOTION_SUPPORT:
        result = handle_emotion_support(user_msg, history, profile)
    elif intent == INTENT_GOAL_CHECK:
        result = handle_goal_check(user_msg, history, profile)
    else:
        result = handle_general(user_msg, history, profile, rag_context)

    record_skill_usage(intent)

    # C6：更新对话轮次计数器
    updated = result[1]
    updated["interaction_count"] = updated.get("interaction_count", 0) + 1
    user_profile_store.save(updated)
    return result[0], updated


def _extract_concept(text: str) -> str:
    concepts = ["货币基金", "基金", "股票", "ETF", "债券", "定投", "复利",
                "风险", "收益", "指数基金", "资产配置", "年化", "净值"]
    for c in concepts:
        if c in text:
            return c
    return "理财概念"
