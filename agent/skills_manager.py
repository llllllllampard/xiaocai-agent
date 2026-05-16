"""
Skill 系统核心模块
- 加载 Skill 并注入 prompt
- 记录每次使用，更新 use_count / satisfaction_rate
- 负反馈触发 meta-reflection，生成优化建议写入 optimization_log
"""

import json
from datetime import datetime
from pathlib import Path

SKILLS_DIR = Path(__file__).parent.parent / "skills"
REGISTRY_PATH = SKILLS_DIR / "registry.json"

# Skill ID → 场景路由 Intent 的映射
INTENT_TO_SKILL = {
    "onboarding":      "onboarding_guide",
    "knowledge_qa":    "explain_financial_concept",
    "expense_review":  "expense_review",
    "emotion_support": "emotion_support",
    "general":         None,
    "goal_check":      None,
    "image_analysis":  None,
}


# ── 注册表读写 ────────────────────────────────────────────────
def _load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        return {"skills": []}
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def _save_registry(registry: dict):
    REGISTRY_PATH.write_text(
        json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _load_skill_file(file_rel: str) -> dict | None:
    path = SKILLS_DIR / file_rel
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _save_skill_file(file_rel: str, data: dict):
    path = SKILLS_DIR / file_rel
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ── 核心接口 ──────────────────────────────────────────────────
def get_skill_prompt_addon(intent: str) -> str:
    """
    根据当前场景 intent 找到对应 Skill，
    返回需要追加到 system prompt 末尾的指令片段。
    """
    skill_id = INTENT_TO_SKILL.get(intent)
    if not skill_id:
        return ""

    registry = _load_registry()
    entry = next((s for s in registry["skills"] if s["skill_id"] == skill_id), None)
    if not entry:
        return ""

    skill = _load_skill_file(entry["file"])
    if not skill:
        return ""

    template = skill.get("template", "")
    params = skill.get("default_params", {})

    # 把 default_params 里的值填入模板占位符（简单字符串替换）
    addon = template
    for k, v in params.items():
        addon = addon.replace(f"{{{k}}}", str(v))

    return f"\n\n### Skill 指令（{skill.get('name', skill_id)} v{skill.get('version', 1)}）\n{addon}"


def record_skill_usage(intent: str):
    """每次调用 handler 后记录 use_count。"""
    skill_id = INTENT_TO_SKILL.get(intent)
    if not skill_id:
        return
    registry = _load_registry()
    for entry in registry["skills"]:
        if entry["skill_id"] == skill_id:
            entry["use_count"] = entry.get("use_count", 0) + 1
            break
    _save_registry(registry)


def record_skill_feedback(intent: str, is_positive: bool, last_output: str = "", feedback_text: str = ""):
    """记录用户反馈，更新 satisfaction_rate，负反馈触发进化。"""
    skill_id = INTENT_TO_SKILL.get(intent)
    if not skill_id:
        return

    registry = _load_registry()
    entry = next((s for s in registry["skills"] if s["skill_id"] == skill_id), None)
    if not entry:
        return

    if is_positive:
        entry["positive_feedback"] = entry.get("positive_feedback", 0) + 1
    else:
        entry["negative_feedback"] = entry.get("negative_feedback", 0) + 1

    pos = entry.get("positive_feedback", 0)
    neg = entry.get("negative_feedback", 0)
    total = pos + neg
    entry["satisfaction_rate"] = round(pos / total, 3) if total else None
    _save_registry(registry)

    # 负反馈 → 触发 meta-reflection
    if not is_positive:
        _trigger_meta_reflection(skill_id, entry.get("file", ""), last_output, feedback_text)


def get_skills_summary() -> list[dict]:
    """返回所有 Skill 的展示数据，用于界面渲染。"""
    registry = _load_registry()
    result = []
    for entry in registry["skills"]:
        skill = _load_skill_file(entry.get("file", "")) or {}
        log = skill.get("optimization_log", [])
        result.append({
            "skill_id":        entry["skill_id"],
            "name":            entry.get("name", entry["skill_id"]),
            "version":         skill.get("version", 1),
            "use_count":       entry.get("use_count", 0),
            "satisfaction_rate": entry.get("satisfaction_rate"),
            "status":          entry.get("status", "initial"),
            "latest_change":   log[-1].get("change", "初始版本") if log else "初始版本",
        })
    return result


# ── meta-reflection（负反馈驱动进化）────────────────────────
def _trigger_meta_reflection(skill_id: str, file_rel: str, last_output: str, feedback_text: str):
    """
    调用 LLM 分析失败原因，生成优化建议，写入 optimization_log，版本号+1。
    """
    skill = _load_skill_file(file_rel)
    if not skill:
        return

    meta_skill_path = SKILLS_DIR / "prompt_skills" / "skill_meta_reflection.json"
    if not meta_skill_path.exists():
        return
    meta_skill = json.loads(meta_skill_path.read_text(encoding="utf-8"))

    # 构造 meta-reflection 输入
    prompt = meta_skill.get("template", "").replace(
        "{skill_name}", skill.get("name", skill_id)
    ).replace(
        "{version}", str(skill.get("version", 1))
    ).replace(
        "{skill_template}", skill.get("template", "")[:500]
    ).replace(
        "{input_params}", json.dumps(skill.get("default_params", {}), ensure_ascii=False)
    ).replace(
        "{output}", last_output[:300]
    ).replace(
        "{user_feedback_text}", feedback_text or "（用户未填写说明）"
    ).replace(
        "{current_satisfaction_rate}", str(skill.get("satisfaction_rate", "未知"))
    ).replace(
        "{today}", datetime.now().strftime("%Y-%m-%d")
    )

    try:
        import os
        from openai import OpenAI
        api_key = os.environ.get("DASHSCOPE_API_KEY")
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        resp = client.chat.completions.create(
            model="qwen3.5-plus",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
        )
        suggestion = resp.choices[0].message.content or ""
        # 过滤 <think> 标签
        import re
        suggestion = re.sub(r"<think>.*?</think>", "", suggestion, flags=re.DOTALL).strip()
    except Exception as e:
        suggestion = f"自动分析失败：{e}"

    # 写入 optimization_log，版本号+1
    old_version = skill.get("version", 1)
    new_version = old_version + 1
    skill["version"] = new_version
    skill.setdefault("optimization_log", []).append({
        "version":            new_version,
        "date":               datetime.now().strftime("%Y-%m-%d"),
        "change":             suggestion[:200],
        "trigger":            "negative_feedback",
        "satisfaction_before": skill.get("satisfaction_rate"),
    })
    _save_skill_file(file_rel, skill)

    # 同步更新注册表版本号
    registry = _load_registry()
    for entry in registry["skills"]:
        if entry["skill_id"] == skill_id:
            entry["version"] = new_version
            break
    _save_registry(registry)
