"""
小财 · 大学生理财陪伴AI搭子
Streamlit 主程序
"""

import base64
import json
from datetime import date, datetime
from pathlib import Path

import streamlit as st

# ── 启动时自动构建 RAG 索引（仅当 index.pkl 不存在时）──────────
import os
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
_index_file = Path(__file__).parent / "rag" / "index.pkl"
if not _index_file.exists():
    try:
        from rag.retriever import build_index
        build_index()
    except Exception:
        pass  # 索引构建失败不影响主程序启动，RAG 降级为空

from agent.memory import UserProfile, EpisodicMemory, ConversationHistory
from agent.router import route, INTENT_KNOWLEDGE_QA, INTENT_GENERAL, INTENT_IMAGE_ANALYSIS
from agent.handlers import dispatch
from agent.tools import analyze_expense_distribution, forecast_month_end_spending
from agent.skills_manager import record_skill_feedback, get_skills_summary
from rag.retriever import retrieve

# ── 页面配置 ──────────────────────────────────────────────────
st.set_page_config(
    page_title="小财 · 理财搭子",
    page_icon="🌱",
    layout="centered",
)

# ── 全局 UI 样式（frontend-design: 竹纸·温暖编辑风）──────────
st.markdown("""
<style>
/* ── 字体引入 ── */
@import url('https://fonts.googleapis.com/css2?family=ZCOOL+XiaoWei&family=Noto+Sans+SC:wght@300;400;500;600&display=swap');

/* ── CSS 变量 ── */
:root {
    --c-paper:   #F7F4EE;   /* 竹纸米白 */
    --c-ink:     #2A2118;   /* 深墨色 */
    --c-moss:    #3E7B58;   /* 苔绿主色 */
    --c-sage:    #6FAE8A;   /* 浅苔绿 */
    --c-mist:    #E8F0E3;   /* 薄雾绿（边框/背景） */
    --c-warm:    #F0EBE0;   /* 温暖米色（侧边栏/卡片） */
    --c-amber:   #C87A3A;   /* 琥珀色强调 */
    --c-user-bg: #EBF4EF;   /* 用户气泡背景 */
    --r-card:    14px;
    --r-bubble:  18px;
    --shadow-soft: 0 2px 12px rgba(42,33,24,0.07);
    --shadow-card: 0 4px 20px rgba(42,33,24,0.10);
}

/* ── 全局底色与字体 ── */
html, body, [class*="css"], .stApp {
    background-color: var(--c-paper) !important;
    font-family: 'Noto Sans SC', 'PingFang SC', sans-serif !important;
    color: var(--c-ink) !important;
}

/* ── 主容器：底部留足空间给固定聊天框 ── */
.main .block-container {
    max-width: 780px !important;
    padding: 0 1.8rem 140px !important;
    background: var(--c-paper) !important;
}

/* ── 标题字体 ── */
h1, h2, h3 {
    font-family: 'ZCOOL XiaoWei', 'Noto Serif SC', serif !important;
    color: var(--c-ink) !important;
    letter-spacing: 0.04em !important;
}

/* ── 顶部横幅 ── */
.xiaocai-banner {
    background: linear-gradient(135deg, var(--c-moss) 0%, #2D5E43 60%, #1E4530 100%);
    border-radius: var(--r-card);
    padding: 22px 28px 20px;
    color: #fff;
    margin: 16px 0 12px;
    position: relative;
    overflow: hidden;
    box-shadow: var(--shadow-card);
}
.xiaocai-banner::before {
    content: '';
    position: absolute;
    top: -30px; right: -30px;
    width: 140px; height: 140px;
    background: rgba(255,255,255,0.06);
    border-radius: 50%;
}
.xiaocai-banner::after {
    content: '';
    position: absolute;
    bottom: -50px; right: 60px;
    width: 180px; height: 180px;
    background: rgba(255,255,255,0.04);
    border-radius: 50%;
}
.xiaocai-banner h2 {
    font-family: 'ZCOOL XiaoWei', serif !important;
    color: #fff !important;
    margin: 0 0 5px !important;
    font-size: 1.7rem !important;
    letter-spacing: 0.08em !important;
    text-shadow: 0 1px 4px rgba(0,0,0,0.2);
}
.xiaocai-banner p {
    color: rgba(255,255,255,0.82) !important;
    margin: 0 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0.03em;
}

/* ── 聊天消息区域整体背景 ── */
[data-testid="stChatMessage"] {
    padding: 12px 16px !important;
    margin: 8px 0 !important;
    border-radius: var(--r-bubble) !important;
    animation: fadeSlideUp 0.25s ease both;
}
@keyframes fadeSlideUp {
    from { opacity: 0; transform: translateY(8px); }
    to   { opacity: 1; transform: translateY(0); }
}

/* ── assistant 气泡 ── */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarContainer"]) {
    background: #FFFFFF !important;
    border: 1px solid var(--c-mist) !important;
    border-radius: var(--r-bubble) var(--r-bubble) var(--r-bubble) 4px !important;
    box-shadow: var(--shadow-soft) !important;
}

/* ── 进度条 ── */
[data-testid="stProgress"] {
    height: 8px !important;
    border-radius: 99px !important;
    background: var(--c-mist) !important;
}
[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, var(--c-moss), var(--c-sage)) !important;
    border-radius: 99px !important;
    transition: width 0.6s cubic-bezier(.4,0,.2,1) !important;
}

/* ── 侧边栏 ── */
[data-testid="stSidebar"] {
    background: var(--c-warm) !important;
    border-right: 1px solid #DDD6C8 !important;
}
[data-testid="stSidebar"] > div { padding: 1rem 0.8rem !important; }
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    font-family: 'ZCOOL XiaoWei', serif !important;
    font-size: 1rem !important;
    color: var(--c-moss) !important;
    margin-bottom: 10px !important;
    letter-spacing: 0.06em !important;
}

/* ── 按钮统一基础（font + 过渡，不干扰尺寸）── */
[data-testid="stButton"] > button {
    font-family: 'Noto Sans SC', sans-serif !important;
    font-size: 0.88rem !important;
    font-weight: 400 !important;
    border-radius: 9px !important;
    transition: all 0.18s ease !important;
    letter-spacing: 0.02em !important;
    /* 不在这里设置 padding，让 Streamlit 自己控制尺寸 */
}

/* ── 主要按钮（kind=primary）── */
button[kind="primary"] {
    background: var(--c-moss) !important;
    color: #fff !important;
    border: none !important;
    font-weight: 500 !important;
    box-shadow: 0 2px 8px rgba(62,123,88,0.30) !important;
}
button[kind="primary"]:hover {
    background: #2D5E43 !important;
    box-shadow: 0 4px 14px rgba(62,123,88,0.4) !important;
    transform: translateY(-1px) !important;
}

/* ── 次要按钮（kind=secondary / 默认）── */
button[kind="secondary"],
[data-testid="stButton"] > button:not([kind="primary"]) {
    background: transparent !important;
    border: 1.5px solid #C8D8C2 !important;
    color: var(--c-moss) !important;
}
button[kind="secondary"]:hover,
[data-testid="stButton"] > button:not([kind="primary"]):hover {
    background: var(--c-mist) !important;
    border-color: var(--c-sage) !important;
}

/* ── 侧边栏快捷按钮：全宽、左对齐、无边框 ── */
[data-testid="stSidebar"] [data-testid="stButton"] > button {
    width: 100% !important;
    text-align: left !important;
    border: none !important;
    background: rgba(62,123,88,0.07) !important;
    color: var(--c-ink) !important;
    padding: 8px 12px !important;
    margin-bottom: 3px !important;
    font-size: 0.87rem !important;
}
[data-testid="stSidebar"] [data-testid="stButton"] > button:hover {
    background: rgba(62,123,88,0.15) !important;
    color: var(--c-moss) !important;
    transform: none !important;
    box-shadow: none !important;
}

/* ── 输入框 ── */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stSelectbox"] select {
    background: #FDFBF7 !important;
    border: 1.5px solid #D8D0C4 !important;
    border-radius: 10px !important;
    color: var(--c-ink) !important;
    font-family: 'Noto Sans SC', sans-serif !important;
    padding: 9px 13px !important;
    transition: border-color 0.2s, box-shadow 0.2s !important;
}
[data-testid="stTextInput"] input:focus,
[data-testid="stNumberInput"] input:focus {
    border-color: var(--c-moss) !important;
    box-shadow: 0 0 0 3px rgba(62,123,88,0.12) !important;
    outline: none !important;
}

/* ── 聊天输入框 ── */
[data-testid="stChatInput"] {
    border-radius: 14px !important;
    border: 1.5px solid #D8D0C4 !important;
    background: #FDFBF7 !important;
    box-shadow: var(--shadow-soft) !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: var(--c-moss) !important;
    box-shadow: 0 0 0 3px rgba(62,123,88,0.1) !important;
}
[data-testid="stChatInput"] textarea {
    font-family: 'Noto Sans SC', sans-serif !important;
    font-size: 0.93rem !important;
    color: var(--c-ink) !important;
    background: transparent !important;
}

/* ── 提示框 ── */
[data-testid="stAlert"] {
    border-radius: 12px !important;
    border-left-width: 3px !important;
    font-size: 0.88rem !important;
}

/* ── expander ── */
[data-testid="stExpander"] {
    background: #FDFBF7 !important;
    border: 1px solid #DDD6C8 !important;
    border-radius: var(--r-card) !important;
    box-shadow: none !important;
}
[data-testid="stExpander"] summary {
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    color: var(--c-moss) !important;
    padding: 10px 14px !important;
}

/* ── 表单卡片 ── */
[data-testid="stForm"] {
    background: #FDFBF7 !important;
    border: 1px solid #DDD6C8 !important;
    border-radius: var(--r-card) !important;
    padding: 18px !important;
    box-shadow: var(--shadow-soft) !important;
}

/* ── 图表 ── */
[data-testid="stBarChart"] svg { border-radius: 10px !important; }

/* ── 分割线 ── */
hr {
    border: none !important;
    border-top: 1px solid #E0D8CC !important;
    margin: 14px 0 !important;
}

/* ── 标题行工具按钮（历史/新对话）── */
.top-toolbar [data-testid="stButton"] > button {
    font-size: 0.80rem !important;
    padding: 5px 11px !important;
    border-radius: 8px !important;
    border-color: #C8D8C2 !important;
}

/* ── 容器卡片 ── */
[data-testid="stVerticalBlock"] > [data-testid="stVerticalBlock"] {
    background: #FDFBF7 !important;
}
div[data-testid="stHorizontalBlock"] { align-items: flex-end !important; }

/* ── 图片上传按钮 ── */
div[data-testid="column"]:has(> div > [data-testid="stFileUploaderDropzone"]) {
    display: flex; align-items: flex-end; padding-bottom: 4px;
}
[data-testid="stFileUploaderDropzoneInstructions"] { display: none !important; }
[data-testid="stFileUploaderDropzone"] {
    padding: 0 !important; border: none !important;
    background: transparent !important; min-height: unset !important;
}
[data-testid="stFileUploaderDropzone"] button {
    height: 44px !important; width: 44px !important;
    padding: 0 !important; font-size: 17px !important;
    border-radius: 11px !important;
    border: 1.5px solid #C8D8C2 !important;
    background: #FDFBF7 !important;
    color: var(--c-moss) !important;
    transition: all 0.18s !important;
}
[data-testid="stFileUploaderDropzone"] button:hover {
    background: var(--c-mist) !important;
    border-color: var(--c-moss) !important;
    transform: scale(1.05) !important;
}

/* ── 滚动条美化 ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: var(--c-paper); }
::-webkit-scrollbar-thumb {
    background: #C8D8C2;
    border-radius: 99px;
}
::-webkit-scrollbar-thumb:hover { background: var(--c-sage); }

/* ── 隐藏默认 footer/menu，保留 header（含侧边栏收缩按钮）── */
#MainMenu { visibility: hidden !important; }
footer    { visibility: hidden !important; }
/* 仅隐藏 header 里的 Streamlit 标题文字，保留侧边栏展开按钮 */
header [data-testid="stDecoration"] { display: none !important; }
header [data-testid="stHeader"] > div:first-child { display: none !important; }

/* ── 👍👎 反馈按钮细化 ── */
[data-key="fb_pos"] button, [data-key="fb_neg"] button {
    font-size: 1rem !important;
    padding: 4px 10px !important;
    border-radius: 99px !important;
    min-width: 36px !important;
}
</style>
""", unsafe_allow_html=True)

# ── 持久化实例 ────────────────────────────────────────────────
profile_store = UserProfile()
episodic = EpisodicMemory()
conversation_history = ConversationHistory()

# ── Session State 初始化 ──────────────────────────────────────
if "profile" not in st.session_state:
    st.session_state.profile = profile_store.load()
if "history" not in st.session_state:
    st.session_state.history = []
if "expenses" not in st.session_state:
    st.session_state.expenses = [
        e["content"] for e in episodic.get_recent("expense", days=30)
    ]
if "pending_feedback" not in st.session_state:
    st.session_state.pending_feedback = None
if "last_intent" not in st.session_state:
    st.session_state.last_intent = "general"
if "onboarding_step" not in st.session_state:
    st.session_state.onboarding_step = "goal"
if "session_id" not in st.session_state:
    st.session_state.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
if "confirm_clear_history" not in st.session_state:
    st.session_state.confirm_clear_history = False
if "viewing_session_id" not in st.session_state:
    st.session_state.viewing_session_id = None
# 快捷按钮触发的待处理消息（修复快捷按钮不触发回答的bug）
if "pending_user_msg" not in st.session_state:
    st.session_state.pending_user_msg = None
# 待处理的图片
if "pending_image_b64" not in st.session_state:
    st.session_state.pending_image_b64 = None


# ── 工具函数 ──────────────────────────────────────────────────
def add_message(role: str, content: str):
    st.session_state.history.append({"role": role, "content": content})


def get_context_window(n: int = 15) -> list:
    from agent.learning import compress_context_if_needed
    return compress_context_if_needed(st.session_state.history, threshold=20)[-n:]


def save_feedback(is_positive: bool):
    last_output = st.session_state.pending_feedback or ""
    episodic.record("feedback", {"is_positive": is_positive, "last_assistant_msg": last_output})
    record_skill_feedback(
        intent=st.session_state.last_intent,
        is_positive=is_positive,
        last_output=last_output,
    )
    st.session_state.pending_feedback = None


def trigger_shortcut(msg: str):
    """快捷按钮触发：写入history并标记待处理消息，rerun后由主流程处理。"""
    add_message("user", msg)
    st.session_state.pending_user_msg = msg
    st.rerun()


def run_dispatch(user_msg: str, profile: dict, image_b64: str = ""):
    """统一的dispatch入口，处理文字或图片消息，渲染回复并保存。"""
    if image_b64:
        intent = INTENT_IMAGE_ANALYSIS
    else:
        intent = route(user_msg, profile)

    st.session_state.last_intent = intent
    rag_ctx = ""
    if intent in (INTENT_KNOWLEDGE_QA, INTENT_GENERAL):
        rag_ctx = retrieve(user_msg)

    with st.chat_message("assistant", avatar="🌱"):
        with st.spinner("小财思考中..."):
            reply, updated_profile = dispatch(
                intent=intent,
                user_msg=user_msg,
                history=get_context_window(),
                profile=profile,
                expenses=st.session_state.expenses,
                rag_context=rag_ctx,
                image_base64=image_b64,
            )
        st.markdown(reply)

    add_message("assistant", reply)
    st.session_state.profile = updated_profile
    st.session_state.pending_feedback = reply
    profile_store.save(updated_profile)
    conversation_history.save_session(st.session_state.session_id, st.session_state.history)


def render_goal_card():
    goals = st.session_state.profile.get("financial_goals", [])
    if not goals:
        return
    for g in goals:
        target = g.get("target_amount", 1)
        current = g.get("current_amount", 0)
        pct = min(current / target, 1.0) if target else 0
        st.progress(pct, text=f"🎯 {g['name']}  {current:.0f} / {target:.0f} 元  ({pct*100:.0f}%)")

    if st.button("+ 新增目标", key="add_goal_btn"):
        st.session_state["_show_add_goal_form"] = True

    if st.session_state.get("_show_add_goal_form"):
        with st.form("add_goal_form"):
            new_goal_name = st.text_input("目标名称", placeholder="比如：旅行基金、考研备用金……")
            col1, col2 = st.columns(2)
            with col1:
                new_target = st.number_input("目标金额（元）", min_value=100.0, value=3000.0, step=100.0, key="ng_target")
            with col2:
                new_monthly = st.number_input("每月计划存入（元）", min_value=50.0, value=500.0, step=50.0, key="ng_monthly")
            col_ok, col_cancel = st.columns(2)
            with col_ok:
                form_ok = st.form_submit_button("确认添加")
            with col_cancel:
                form_cancel = st.form_submit_button("取消")
            if form_ok and new_goal_name:
                profile = st.session_state.profile
                profile.setdefault("financial_goals", []).append({
                    "name": new_goal_name, "target_amount": new_target,
                    "monthly_saving": new_monthly, "deadline": "", "current_amount": 0,
                })
                profile_store.save(profile)
                st.session_state.profile = profile
                st.session_state["_show_add_goal_form"] = False
                st.rerun()
            if form_cancel:
                st.session_state["_show_add_goal_form"] = False
                st.rerun()


def render_expense_chart():
    if not st.session_state.expenses:
        st.caption("还没有消费记录")
        return
    result = analyze_expense_distribution(st.session_state.expenses, "本月")
    if "error" in result:
        return
    breakdown = result["breakdown"]
    st.caption(f"本月已录入 {result['count']} 笔 · 共 {result['total']:.0f} 元")
    chart_data = {k: v["amount"] for k, v in breakdown.items()}
    st.bar_chart(chart_data, use_container_width=True, height=160)
    top = result["top_category"]
    st.caption(f"最大支出：{top} {breakdown[top]['pct']}%")


def expense_instant_feedback(record: dict):
    result = analyze_expense_distribution(st.session_state.expenses, "本月")
    if "error" in result:
        return
    forecast = forecast_month_end_spending(st.session_state.expenses)
    cat = record["category"]
    cat_amt = result["breakdown"].get(cat, {}).get("amount", record["amount"])
    cat_pct = result["breakdown"].get(cat, {}).get("pct", 100)
    msg = f"✅ **{cat}** 已录入 {cat_amt:.0f} 元（本月占比 {cat_pct}%）"
    if "forecast_month_end" in forecast:
        msg += f"　· 预计月底总支出 **{forecast['forecast_month_end']:.0f} 元**"
    st.info(msg)


# ── 冷启动结构化流程 ──────────────────────────────────────────
RISK_QUESTIONS = [
    {"q": "如果你存了1000元，第二天它变成950元了，你的第一反应是？",
     "opts": ["A. 赶紧取出来，亏了50块太难受", "B. 有点担心，先观望几天", "C. 正常波动，继续持有"],
     "key": "r1"},
    {"q": "你存的这笔钱，多久之内可能要用到？",
     "opts": ["A. 3个月内可能要用", "B. 半年到一年后", "C. 1年以上，暂时用不到"],
     "key": "r2"},
    {"q": "你对理财的期望是？",
     "opts": ["A. 不亏就行，安全第一", "B. 稳健增值，小风险可以接受", "C. 争取高收益，愿意承担一定风险"],
     "key": "r3"},
]
SCORE_MAP = {"A": 1, "B": 2, "C": 3}
ADVICE = {
    "保守型": "① 每月先把存款放进货币基金（余额宝类），年化约2%，随存随取\n② 攒够3个月备用金后，我们再聊下一步",
    "稳健型": "① 每月先把存款放进货币基金，保证流动性\n② 攒到1000元后，可以考虑指数基金定投，我到时候再教你 ✨",
    "积极型": "① 留够1个月生活费的应急金放货币基金\n② 剩余部分每月定投宽基指数基金（沪深300）\n③ 先从小额开始，感受市场节奏",
}


def render_onboarding():
    profile = st.session_state.profile
    step = st.session_state.onboarding_step

    if step == "goal":
        st.info("👋 欢迎！先帮我了解一下你的理财目标～")
        with st.form("goal_form"):
            goal_name = st.text_input("你最想实现什么目标？", placeholder="比如：旅行基金、考研备用金、应急金……")
            col1, col2 = st.columns(2)
            with col1:
                target_amount = st.number_input("目标金额（元）", min_value=100.0, value=3000.0, step=100.0)
            with col2:
                monthly_saving = st.number_input("每月计划存入（元）", min_value=50.0, value=500.0, step=50.0)
            monthly_income = st.number_input(
                "月均可支配收入（元，可选填）", min_value=0.0, value=0.0, step=100.0,
                help="填写后小财可以判断每月存入金额是否在合理范围（建议月收入的10%-30%）",
            )
            submitted = st.form_submit_button("确认目标 →")
            if submitted and goal_name:
                from agent.tools import calculate_investment_timeline
                result = calculate_investment_timeline(target_amount, monthly_saving)
                months = result.get("months", "?")
                profile["financial_goals"] = [{
                    "name": goal_name, "target_amount": target_amount,
                    "monthly_saving": monthly_saving, "deadline": "", "current_amount": 0,
                }]
                profile_store.save(profile)
                st.session_state.profile = profile

                if monthly_saving > target_amount * 0.8:
                    st.warning(f"存入比例过高：每月存入 {monthly_saving:.0f} 元已超过目标金额的 80%，建议调整。")
                if monthly_income > 0 and monthly_saving / monthly_income > 0.5:
                    st.warning(f"每月存入比例为月收入的 {monthly_saving/monthly_income*100:.0f}%，建议控制在10%-30%。")

                reply = (
                    f"好的！目标设定为：**{goal_name} {target_amount:.0f} 元**，"
                    f"每月存 {monthly_saving:.0f} 元，预计约 **{months} 个月**达成 🎯\n\n"
                    "接下来做个小测评，帮我了解你的风险偏好，就3个问题～"
                )
                add_message("assistant", reply)
                st.session_state.onboarding_step = "risk_q0"
                st.rerun()

    elif step.startswith("risk_q"):
        idx = int(step[-1])
        if idx >= len(RISK_QUESTIONS):
            score = sum(SCORE_MAP.get(profile.get(q["key"], "B"), 2) for q in RISK_QUESTIONS)
            risk_level = "稳健型"
            for r, label in [(range(3, 5), "保守型"), (range(5, 8), "稳健型"), (range(8, 10), "积极型")]:
                if score in r:
                    risk_level = label
                    break
            profile["risk_level"] = risk_level
            profile["onboarding_done"] = True
            profile_store.save(profile)
            st.session_state.profile = profile
            episodic.record("risk_test_completed", {"result": risk_level, "score": score})
            advice = ADVICE.get(risk_level, "")
            reply = (
                f"测评完成！你是 **{risk_level}** 投资者 🎉\n\n"
                f"根据你的情况，建议这样开始：\n{advice}\n\n"
                "有什么问题随时问我，接下来我们可以聊聊理财知识，或者帮你分析消费～"
            )
            add_message("assistant", reply)
            st.session_state.onboarding_step = "done"
            st.rerun()
        else:
            qdata = RISK_QUESTIONS[idx]
            st.info(f"**问题 {idx+1}/3**：{qdata['q']}")
            for opt in qdata["opts"]:
                if st.button(opt, key=f"risk_{idx}_{opt[0]}"):
                    profile[qdata["key"]] = opt[0]
                    profile_store.save(profile)
                    st.session_state.profile = profile
                    add_message("user", opt)
                    st.session_state.onboarding_step = f"risk_q{idx+1}"
                    st.rerun()


# ── 侧边栏 ────────────────────────────────────────────────────
with st.sidebar:
    st.title("📊 消费录入")
    with st.form("expense_form", clear_on_submit=True):
        amount = st.number_input("金额（元）", min_value=0.1, step=0.5)
        category = st.selectbox("类别", ["餐饮", "娱乐", "学习", "生活", "交通", "其他"])
        note = st.text_input("备注（可选）")
        submitted = st.form_submit_button("✓ 确认录入")
        if submitted and amount > 0:
            record = {"amount": amount, "category": category,
                      "note": note, "date": date.today().isoformat()}
            episodic.record("expense", record)
            st.session_state.expenses.append(record)
            expense_instant_feedback(record)

    st.divider()
    render_expense_chart()

    st.divider()
    st.markdown("**⚡ 快捷入口**")
    if st.button("📚 学一个新知识"):
        trigger_shortcut("帮我学一个适合我当前水平的理财知识")
    if st.button("🎯 查看我的目标"):
        goals = st.session_state.profile.get("financial_goals", [])
        if len(goals) > 1:
            names = "、".join(g["name"] for g in goals)
            trigger_shortcut(f"帮我看看我所有的攒钱目标进度，我有 {len(goals)} 个目标：{names}")
        else:
            trigger_shortcut("帮我看看我的攒钱目标进度")
    if st.button("📈 分析我的消费"):
        trigger_shortcut("帮我分析一下最近的消费情况")
    if st.button("💡 今日理财小知识"):
        trigger_shortcut("给我讲一个理财小知识")

    st.divider()
    with st.expander("📈 小财的成长记录", expanded=False):
        skills = get_skills_summary()
        for s in skills:
            sat = s["satisfaction_rate"]
            sat_str = f"{sat*100:.0f}%" if sat is not None else "暂无数据"
            st.markdown(
                f"**{s['name']}** "
                f"<span style='color:gray'>v{s['version']} · 使用{s['use_count']}次 · 满意度{sat_str}</span>",
                unsafe_allow_html=True,
            )
            st.caption(f"最近优化：{s['latest_change'][:60]}")


# ── 固定顶栏（纯 HTML，position:fixed）────────────────────────
# 按钮用表单+隐藏提交模拟点击，避免 Streamlit rerun 问题
# 用 st.query_params 传递顶栏点击信号
_qp = st.query_params
if _qp.get("_action") == "new_chat":
    st.session_state.history = []
    st.session_state.session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    st.session_state.pending_feedback = None
    st.session_state.pending_user_msg = None
    st.session_state.viewing_session_id = None
    st.query_params.clear()
    st.rerun()
if _qp.get("_action") == "toggle_history":
    st.session_state["_show_history_panel"] = not st.session_state.get("_show_history_panel", False)
    st.query_params.clear()
    st.rerun()

# ── 把自定义顶栏注入 Streamlit 原生 header ──────────────────
# 原理：覆盖 Streamlit header 的内容区，用 sticky 定位
# 天然跟随 sidebar 宽度，无需 JavaScript 手动调整
st.markdown("""
<style>
/* 1. 让 Streamlit 原生 header 变成我们的容器 */
header[data-testid="stHeader"] {
    background: linear-gradient(135deg, #3E7B58 0%, #2D5E43 60%, #1E4530 100%) !important;
    height: 52px !important;
    min-height: 52px !important;
    padding: 0 20px !important;
    display: flex !important;
    align-items: center !important;
    box-shadow: 0 2px 12px rgba(0,0,0,0.15) !important;
    z-index: 999990 !important;
}
/* 2. 隐藏 header 内 Streamlit 原有的按钮/菜单（保留 sidebar 展开按钮） */
header[data-testid="stHeader"] > div:not([data-testid="stDecoration"]) {
    display: none !important;
}
/* 3. 自定义顶栏内容覆盖在 header 上 */
.xiaocai-topbar-inner {
    position: fixed;
    top: 0;
    /* left/right 跟随 Streamlit header，天然随 sidebar 变化 */
    left: var(--sidebar-width, 0px);
    right: 0;
    height: 52px;
    z-index: 999991;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    pointer-events: none; /* 让 sidebar 按钮可以被点击 */
}
.xiaocai-topbar-inner > * { pointer-events: all; }
.xiaocai-topbar-left {
    display: flex;
    align-items: center;
    gap: 6px;
    overflow: hidden;
    flex: 1;
}
.xiaocai-topbar-title {
    font-family: 'ZCOOL XiaoWei', serif;
    font-size: 1.2rem;
    color: #fff;
    white-space: nowrap;
    letter-spacing: 0.06em;
}
.xiaocai-topbar-sep { color: rgba(255,255,255,0.4); margin: 0 3px; font-size: 0.9rem; }
.xiaocai-topbar-sub {
    font-size: 0.78rem;
    color: rgba(255,255,255,0.72);
    white-space: nowrap;
}
.xiaocai-topbar-btns { display: flex; gap: 8px; flex-shrink: 0; }
.topbar-btn {
    background: rgba(255,255,255,0.14);
    border: 1px solid rgba(255,255,255,0.28);
    color: #fff !important;
    border-radius: 8px;
    padding: 5px 13px;
    font-size: 0.80rem;
    cursor: pointer;
    text-decoration: none !important;
    white-space: nowrap;
    font-family: 'Noto Sans SC', sans-serif;
    transition: background 0.15s;
}
.topbar-btn:hover { background: rgba(255,255,255,0.26); }

/* 4. 主内容区顶部留出 header 高度 */
.main .block-container {
    padding-top: 12px !important;
    padding-bottom: 90px !important;
}
</style>

<!-- 顶栏内容层：叠在 Streamlit header 上 -->
<div class="xiaocai-topbar-inner" id="xiaocai-topbar-inner">
  <div class="xiaocai-topbar-left">
    <span class="xiaocai-topbar-title">🌱 小财</span>
    <span class="xiaocai-topbar-sep">·</span>
    <span class="xiaocai-topbar-sub">你的理财搭子 · 从第一步开始，陪你把钱管好</span>
  </div>
  <div class="xiaocai-topbar-btns">
    <a class="topbar-btn" href="?_action=toggle_history">📖 历史对话</a>
    <a class="topbar-btn" href="?_action=new_chat">🆕 新对话</a>
  </div>
</div>

<script>
(function() {
  function sync() {
    var header = document.querySelector('header[data-testid="stHeader"]');
    var bar    = document.getElementById('xiaocai-topbar-inner');
    var chat   = document.querySelector('[data-testid="stChatInput"]');
    if (!header || !bar) return;

    // Streamlit 原生 header 自己会随 sidebar 动态调整 left
    // 我们直接读 header 的当前 left 值，跟随它即可
    var headerLeft = header.getBoundingClientRect().left;
    bar.style.left  = headerLeft + 'px';
    if (chat) chat.style.left = headerLeft + 'px';
  }

  // 用 requestAnimationFrame 在每帧都同步，动画过程中不会错位
  function loop() {
    sync();
    requestAnimationFrame(loop);
  }
  loop();
})();
</script>
""", unsafe_allow_html=True)

# 历史对话面板（折叠展开）
if st.session_state.get("_show_history_panel"):
    with st.container(border=True):
        st.markdown("**📖 历史对话记录**")
        sessions = conversation_history.get_sessions(limit=10)
        if not sessions:
            st.caption("暂无历史对话记录")
        else:
            for sess in sessions:
                ts = sess["timestamp"][:16].replace("T", " ")
                preview = sess.get("first_user_msg", "") or "（无用户消息）"
                count = sess["message_count"]
                c1, c2 = st.columns([5, 1])
                with c1:
                    st.markdown(
                        f"<small style='color:gray'>{ts} · 共{count}条</small><br>"
                        f"<span style='font-size:0.9em'>{preview[:40]}…</span>",
                        unsafe_allow_html=True,
                    )
                with c2:
                    if st.button("查看", key=f"view_{sess['session_id']}"):
                        st.session_state.viewing_session_id = sess["session_id"]
                        st.session_state["_show_history_panel"] = False
                        st.rerun()
            st.divider()
            if not st.session_state.confirm_clear_history:
                if st.button("🗑️ 清空历史", key="clear_history_btn"):
                    st.session_state.confirm_clear_history = True
                    st.rerun()
            else:
                st.warning("确认清空所有历史对话记录？此操作不可恢复。")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("确认清空", key="confirm_yes"):
                        conversation_history.clear_all()
                        st.session_state.confirm_clear_history = False
                        st.toast("历史对话已清空")
                        st.rerun()
                with cc2:
                    if st.button("取消", key="confirm_no"):
                        st.session_state.confirm_clear_history = False
                        st.rerun()

render_goal_card()
st.divider()

# 历史对话回放
if st.session_state.viewing_session_id:
    view_id = st.session_state.viewing_session_id
    view_msgs = conversation_history.get_session_messages(view_id)
    ts_label = view_id.replace("session_", "").replace("_", " ")
    with st.expander(f"📖 {ts_label}（共{len(view_msgs)}条）", expanded=True):
        for msg in view_msgs:
            with st.chat_message(msg["role"], avatar="🌱" if msg["role"] == "assistant" else "👤"):
                st.markdown(msg["content"])
        if st.button("关闭", key="close_view"):
            st.session_state.viewing_session_id = None
            st.rerun()
    st.divider()

# 渲染当前对话历史
for msg in st.session_state.history:
    with st.chat_message(msg["role"], avatar="🌱" if msg["role"] == "assistant" else "👤"):
        st.markdown(msg["content"])

# 👍👎 反馈按钮
if st.session_state.pending_feedback and st.session_state.history:
    if st.session_state.history[-1]["role"] == "assistant":
        col1, col2, col3 = st.columns([1, 1, 8])
        with col1:
            if st.button("👍", key="fb_pos"):
                save_feedback(True)
                st.toast("谢谢！我会继续保持～")
        with col2:
            if st.button("👎", key="fb_neg"):
                save_feedback(False)
                st.toast("收到，我会改进！")

# ── 冷启动阶段 ────────────────────────────────────────────────
profile = st.session_state.profile
if not profile.get("onboarding_done"):
    if st.session_state.onboarding_step == "goal" and not st.session_state.history:
        with st.chat_message("assistant", avatar="🌱"):
            welcome = "你好！我是**小财**，你的理财搭子 🌱\n\n我可以帮你：**攒钱规划** · **消费复盘** · **入门理财**\n\n先来了解一下你的目标～"
            st.markdown(welcome)
        add_message("assistant", welcome)
    render_onboarding()
    st.stop()

# ── 正常对话阶段 ──────────────────────────────────────────────

# 处理快捷按钮触发的待处理消息（修复快捷按钮不回答bug）
pending_msg = st.session_state.pop("pending_user_msg", None) if "pending_user_msg" in st.session_state else None
# 用 get 后置 None 避免 KeyError
if st.session_state.get("pending_user_msg"):
    pending_msg = st.session_state.pending_user_msg
    st.session_state.pending_user_msg = None

if pending_msg:
    with st.chat_message("user", avatar="👤"):
        st.markdown(pending_msg)
    run_dispatch(pending_msg, profile)
    st.rerun()

# ── 附件上传区（在聊天框上方，紧凑显示已选附件）─────────────
# 支持图片 + 文档，上传后暂存，随下一条文字消息一起发送
st.markdown("""
<style>
/* ── Streamlit 原生 chat_input 容器：隐藏它本身，我们自己控制位置 ── */
/* chat_input 已经是 fixed bottom，我们只需要调整 left 随 sidebar 变化 */
[data-testid="stChatInput"] {
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
    z-index: 1001 !important;
    transition: left 0.3s ease !important;
    background: #F7F4EE !important;
    border-top: 1px solid #E0D8CC !important;
    box-shadow: 0 -3px 16px rgba(42,33,24,0.08) !important;
    padding: 8px 16px 10px !important;
}

/* ── 附件按钮容器：固定在底部，紧贴 chat_input 右侧 ── */
#xiaocai-bottombar {
    position: fixed;
    bottom: 8px;
    right: 16px;
    z-index: 1002;
    display: flex;
    align-items: center;
    gap: 6px;
    transition: left 0.3s ease;
    pointer-events: none; /* 让底下的 chat_input 仍可点击 */
}
#xiaocai-bottombar > * { pointer-events: all; }

/* 附件上传器：压成图标按钮 */
[data-testid="stFileUploaderDropzoneInstructions"] { display: none !important; }
[data-testid="stFileUploaderDropzone"] {
    padding: 0 !important; border: none !important;
    background: transparent !important; min-height: unset !important;
}
[data-testid="stFileUploaderDropzone"] button {
    height: 38px !important; width: 38px !important;
    padding: 0 !important; border-radius: 9px !important;
    border: 1.5px solid #C8D8C2 !important;
    background: #FDFBF7 !important;
}
[data-testid="stFileUploaderDropzone"] button span { display: none !important; }
[data-testid="stFileUploaderDropzone"] button::before { content: "📎"; font-size: 15px; }

/* 附件徽章（显示在输入框上方） */
.attach-badge {
    position: fixed;
    bottom: 62px;
    right: 70px;
    background: #EAF5ED;
    border: 1px solid #B8D8C4;
    border-radius: 16px;
    padding: 3px 10px;
    font-size: 0.8rem;
    color: #2D5A3D;
    z-index: 1003;
    max-width: 260px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
</style>

<!-- 底栏容器（仅放附件按钮，JS 同步 left） -->
<div id="xiaocai-bottombar"></div>

<script>
(function() {
  function syncLeft() {
    var sidebar  = document.querySelector('[data-testid="stSidebar"]');
    var topbar   = document.getElementById('xiaocai-topbar');
    var bottombar= document.getElementById('xiaocai-bottombar');
    var chatInput= document.querySelector('[data-testid="stChatInput"]');
    if (!sidebar) return;

    var rect = sidebar.getBoundingClientRect();
    var sidebarW = (rect.width > 10 && rect.right > 0) ? rect.right : 0;

    if (topbar)    topbar.style.left    = sidebarW + 'px';
    if (chatInput) chatInput.style.left = sidebarW + 'px';
    // bottombar 右侧对齐不变，left 不需要改
  }
  syncLeft();
  var ro = new ResizeObserver(syncLeft);
  var sb = document.querySelector('[data-testid="stSidebar"]');
  if (sb) ro.observe(sb);
  var mo = new MutationObserver(syncLeft);
  mo.observe(document.body, { childList: true, subtree: true, attributes: true,
                               attributeFilter: ['style', 'class'] });
  setInterval(syncLeft, 300);
})();
</script>
""", unsafe_allow_html=True)

# 附件上传控件（Streamlit 渲染后 JS 会把它移入 bottombar）
uploader_key = f"attach_{st.session_state.get('_uploader_key', 0)}"
uploaded_file = st.file_uploader(
    "📎",
    type=["jpg", "jpeg", "png", "webp", "pdf", "txt", "csv", "xlsx", "docx", "md"],
    key=uploader_key,
    label_visibility="collapsed",
)

# 有附件时显示悬浮徽章 + 暂存
if uploaded_file is not None:
    fname = uploaded_file.name
    st.markdown(f'<div class="attach-badge">📎 {fname}</div>', unsafe_allow_html=True)
    st.session_state["_pending_file_name"] = fname
    st.session_state["_pending_file_b64"] = base64.b64encode(uploaded_file.getvalue()).decode()
    st.session_state["_pending_file_type"] = uploaded_file.type or ""

# 聊天输入框
user_input = st.chat_input("和小财聊聊吧～")

# ── 处理带附件的发送 ─────────────────────────────────────────
if user_input:
    pending_file_b64 = st.session_state.pop("_pending_file_b64", None)
    pending_file_name = st.session_state.pop("_pending_file_name", None)
    pending_file_type = st.session_state.pop("_pending_file_type", "")

    if pending_file_b64:
        # 重置 uploader key 清空控件
        st.session_state["_uploader_key"] = st.session_state.get("_uploader_key", 0) + 1
        display_msg = f"📎 {pending_file_name}\n\n{user_input}"
        add_message("user", display_msg)
        with st.chat_message("user", avatar="👤"):
            st.markdown(display_msg)
        # 判断是图片还是文档
        is_image = pending_file_type.startswith("image/")
        if is_image:
            run_dispatch(user_input, profile, image_b64=pending_file_b64)
        else:
            # 文档：把文件名和内容作为文字上下文传给 LLM
            import base64 as _b64
            try:
                file_text = _b64.b64decode(pending_file_b64).decode("utf-8", errors="replace")[:3000]
                doc_context = f"用户上传了文件【{pending_file_name}】，内容如下：\n{file_text}\n\n用户问题：{user_input}"
            except Exception:
                doc_context = f"用户上传了文件【{pending_file_name}】，请根据用户问题回答：{user_input}"
            run_dispatch(doc_context, profile)
    else:
        add_message("user", user_input)
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)
        run_dispatch(user_input, profile)
    st.rerun()
