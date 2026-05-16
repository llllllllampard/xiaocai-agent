"""
工具层：注册供 Claude tool_use 调用的 Python 函数。
每个工具对应 TOOL_DEFINITIONS 中的一条 schema。
"""

import json
from datetime import datetime, date, timedelta
from calendar import monthrange


# ── Tool Schemas（传给 Claude API 的 tools 参数）─────────────
TOOL_DEFINITIONS = [
    {
        "name": "calculate_investment_timeline",
        "description": "计算用户达成储蓄/理财目标所需的时间（月数），并给出每月需要存多少钱。",
        "input_schema": {
            "type": "object",
            "properties": {
                "target_amount": {"type": "number", "description": "目标金额（元）"},
                "monthly_saving": {"type": "number", "description": "每月计划存入金额（元）"},
                "current_amount": {"type": "number", "description": "当前已有存款（元），默认0"},
                "annual_return_rate": {"type": "number", "description": "预期年化收益率，如0.02代表2%，默认0.02"},
            },
            "required": ["target_amount", "monthly_saving"],
        },
    },
    {
        "name": "calculate_compound_interest",
        "description": "计算复利增长，展示坚持定投X年后的资产规模。",
        "input_schema": {
            "type": "object",
            "properties": {
                "principal": {"type": "number", "description": "初始本金（元）"},
                "monthly_investment": {"type": "number", "description": "每月定投金额（元）"},
                "annual_rate": {"type": "number", "description": "年化收益率，如0.06代表6%"},
                "years": {"type": "number", "description": "投资年限"},
            },
            "required": ["principal", "monthly_investment", "annual_rate", "years"],
        },
    },
    {
        "name": "analyze_expense_distribution",
        "description": "分析用户近期消费结构，返回各类别占比、最大支出类别、环比变化。",
        "input_schema": {
            "type": "object",
            "properties": {
                "expenses": {
                    "type": "array",
                    "description": "消费记录列表，每条包含 category、amount、date",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "amount": {"type": "number"},
                            "date": {"type": "string"},
                        },
                    },
                },
                "period_label": {"type": "string", "description": "统计周期描述，如'上周'或'本月'"},
            },
            "required": ["expenses"],
        },
    },
    {
        "name": "forecast_month_end_spending",
        "description": "根据当月已有消费，预测月底总支出。",
        "input_schema": {
            "type": "object",
            "properties": {
                "expenses_this_month": {
                    "type": "array",
                    "description": "本月已录入消费",
                    "items": {
                        "type": "object",
                        "properties": {
                            "amount": {"type": "number"},
                            "date": {"type": "string"},
                        },
                    },
                },
            },
            "required": ["expenses_this_month"],
        },
    },
    {
        "name": "score_risk_tolerance",
        "description": "根据风险测评三题的答案，计算用户风险等级。",
        "input_schema": {
            "type": "object",
            "properties": {
                "q1": {"type": "string", "description": "第1题答案：A/B/C"},
                "q2": {"type": "string", "description": "第2题答案：A/B/C"},
                "q3": {"type": "string", "description": "第3题答案：A/B/C"},
            },
            "required": ["q1", "q2", "q3"],
        },
    },
    {
        "name": "analyze_expense_trend",
        "description": "分析用户近N周的消费长期趋势，按周分组统计，返回每周总额、趋势方向（上升/下降/平稳）、平均值、最高最低周。",
        "input_schema": {
            "type": "object",
            "properties": {
                "weeks": {"type": "integer", "description": "统计最近几周的数据，默认8周"},
            },
            "required": [],
        },
    },
]

SCORE_MAP = {"A": 1, "B": 2, "C": 3}


# ── Tool 实现 ─────────────────────────────────────────────────
def calculate_investment_timeline(
    target_amount: float,
    monthly_saving: float,
    current_amount: float = 0.0,
    annual_return_rate: float = 0.02,
) -> dict:
    monthly_rate = annual_return_rate / 12
    current = current_amount
    months = 0
    while current < target_amount and months < 600:
        current = current * (1 + monthly_rate) + monthly_saving
        months += 1
    if months >= 600:
        return {"error": "目标金额过大或月存金额过少，无法在合理时间内达成"}
    total_invested = current_amount + monthly_saving * months
    total_growth = current - total_invested
    return {
        "months": months,
        "years": round(months / 12, 1),
        "total_invested": round(total_invested, 2),
        "total_growth": round(total_growth, 2),
        "final_amount": round(current, 2),
    }


def calculate_compound_interest(
    principal: float,
    monthly_investment: float,
    annual_rate: float,
    years: float,
) -> dict:
    monthly_rate = annual_rate / 12
    months = int(years * 12)
    balance = principal
    for _ in range(months):
        balance = balance * (1 + monthly_rate) + monthly_investment
    total_invested = principal + monthly_investment * months
    total_growth = balance - total_invested
    return {
        "final_amount": round(balance, 2),
        "total_invested": round(total_invested, 2),
        "total_growth": round(total_growth, 2),
        "growth_rate": round(total_growth / total_invested * 100, 1),
    }


def analyze_expense_distribution(expenses: list, period_label: str = "近期") -> dict:
    if not expenses:
        return {"error": "暂无消费记录"}
    by_cat: dict[str, float] = {}
    for e in expenses:
        cat = e.get("category", "其他")
        by_cat[cat] = by_cat.get(cat, 0) + e.get("amount", 0)
    total = sum(by_cat.values())
    breakdown = {k: {"amount": round(v, 2), "pct": round(v / total * 100, 1)}
                 for k, v in by_cat.items()}
    top_cat = max(by_cat, key=by_cat.get)
    return {
        "period": period_label,
        "total": round(total, 2),
        "count": len(expenses),
        "breakdown": breakdown,
        "top_category": top_cat,
        "top_category_pct": round(by_cat[top_cat] / total * 100, 1),
    }


def forecast_month_end_spending(expenses_this_month: list) -> dict:
    if not expenses_this_month:
        return {"error": "本月暂无消费记录"}
    today = date.today()
    days_in_month = monthrange(today.year, today.month)[1]
    days_elapsed = today.day
    total_so_far = sum(e.get("amount", 0) for e in expenses_this_month)
    daily_avg = total_so_far / days_elapsed
    forecast = daily_avg * days_in_month
    return {
        "total_so_far": round(total_so_far, 2),
        "days_elapsed": days_elapsed,
        "days_remaining": days_in_month - days_elapsed,
        "daily_avg": round(daily_avg, 2),
        "forecast_month_end": round(forecast, 2),
    }


def score_risk_tolerance(q1: str, q2: str, q3: str) -> dict:
    score = SCORE_MAP.get(q1.upper(), 2) + SCORE_MAP.get(q2.upper(), 2) + SCORE_MAP.get(q3.upper(), 2)
    if score <= 4:
        level = "保守型"
        desc = "你更看重资金安全，建议从货币基金开始，保证本金不受损失。"
    elif score <= 7:
        level = "稳健型"
        desc = "你能接受小幅波动，指数基金定投是适合你的入门方式。"
    else:
        level = "积极型"
        desc = "你愿意承担一定风险换取更高收益，可以考虑股票型基金，但要注意分散投资。"
    return {"risk_level": level, "score": score, "description": desc}


def analyze_expense_trend(weeks: int = 8) -> dict:
    """读取最近 weeks 周的消费记录，按周分组，计算每周总额，返回趋势数据。"""
    from .memory import EpisodicMemory
    episodic = EpisodicMemory()

    days = weeks * 7
    episodes = episodic.get_recent("expense", days=days)
    if not episodes:
        return {"error": "暂无消费记录"}

    # 按自然周（ISO week）分组
    weekly: dict[str, float] = {}
    for ep in episodes:
        try:
            ts = datetime.fromisoformat(ep["timestamp"])
        except Exception:
            continue
        # ISO year-week 作为分组 key，如 "2025-W03"
        week_key = ts.strftime("%G-W%V")
        amount = ep["content"].get("amount", 0)
        weekly[week_key] = weekly.get(week_key, 0) + amount

    if not weekly:
        return {"error": "没有可统计的消费记录"}

    sorted_weeks = sorted(weekly.items())  # 按时间升序
    week_labels = [w for w, _ in sorted_weeks]
    week_totals = [round(v, 2) for _, v in sorted_weeks]

    avg = round(sum(week_totals) / len(week_totals), 2)
    max_week = week_labels[week_totals.index(max(week_totals))]
    min_week = week_labels[week_totals.index(min(week_totals))]

    # 趋势判断：比较前半段均值与后半段均值
    mid = len(week_totals) // 2
    if mid > 0:
        first_half_avg = sum(week_totals[:mid]) / mid
        second_half_avg = sum(week_totals[mid:]) / (len(week_totals) - mid)
        if second_half_avg > first_half_avg * 1.05:
            trend = "上升"
        elif second_half_avg < first_half_avg * 0.95:
            trend = "下降"
        else:
            trend = "平稳"
    else:
        trend = "数据不足"

    return {
        "weeks_analyzed": len(sorted_weeks),
        "weekly_totals": dict(zip(week_labels, week_totals)),
        "average_weekly": avg,
        "trend": trend,
        "highest_week": {"week": max_week, "amount": max(week_totals)},
        "lowest_week": {"week": min_week, "amount": min(week_totals)},
    }


# ── 工具分发器 ────────────────────────────────────────────────
TOOL_FUNCTIONS = {
    "calculate_investment_timeline": calculate_investment_timeline,
    "calculate_compound_interest": calculate_compound_interest,
    "analyze_expense_distribution": analyze_expense_distribution,
    "forecast_month_end_spending": forecast_month_end_spending,
    "score_risk_tolerance": score_risk_tolerance,
    "analyze_expense_trend": analyze_expense_trend,
}


def dispatch_tool(name: str, inputs: dict) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return json.dumps({"error": f"未知工具: {name}"}, ensure_ascii=False)
    try:
        result = fn(**inputs)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
