# Remove Streamlit Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除所有 Streamlit 前端代码，保留 agent 核心逻辑完整不变。

**Architecture:** 直接删除 `app.py` 和 `.streamlit/` 目录，修改 `requirements.txt` 移除 `streamlit` 依赖。`agent/memory.py` 无需改动（经核查无 streamlit 引用）。

**Tech Stack:** Python, Git

---

### Task 1: 移除 `streamlit` 依赖

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 读取当前 requirements.txt 内容**

查看文件确认 `streamlit>=1.35.0` 所在行。

- [ ] **Step 2: 删除 streamlit 行**

将 `requirements.txt` 中的 `streamlit>=1.35.0` 这一行删除，其余行保持不变。

最终文件内容应为：
```
openai>=1.30.0
sentence-transformers>=3.0.0
numpy>=1.26.0
python-dotenv>=1.0.0
```

- [ ] **Step 3: 验证文件**

确认文件中不再包含 `streamlit` 字样：
```bash
grep -i streamlit requirements.txt
```
Expected: 无输出

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: remove streamlit dependency"
```

---

### Task 2: 删除 `.streamlit/` 目录

**Files:**
- Delete: `.streamlit/config.toml`
- Delete: `.streamlit/secrets.toml`
- Delete: `.streamlit/` 目录

- [ ] **Step 1: 确认目录内容**

```bash
ls .streamlit/
```
Expected: `config.toml  secrets.toml`

- [ ] **Step 2: 删除整个 .streamlit 目录**

```bash
rm -rf .streamlit/
```

- [ ] **Step 3: 验证删除**

```bash
ls .streamlit/ 2>&1
```
Expected: `ls: cannot access '.streamlit/': No such file or directory`（或 Windows 等价错误）

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore: remove .streamlit config directory"
```

---

### Task 3: 删除 `app.py`

**Files:**
- Delete: `app.py`

- [ ] **Step 1: 确认文件存在**

```bash
ls app.py
```
Expected: `app.py`

- [ ] **Step 2: 删除 app.py**

```bash
rm app.py
```

- [ ] **Step 3: 验证删除**

```bash
ls app.py 2>&1
```
Expected: `ls: cannot access 'app.py': No such file or directory`（或 Windows 等价错误）

- [ ] **Step 4: 验证 agent 核心文件完整**

```bash
ls agent/
```
Expected: `__init__.py  handlers.py  learning.py  memory.py  router.py  skills_manager.py  tools.py`

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove Streamlit app.py frontend"
```

---

### Task 4: 验证 agent 核心无 streamlit 残留引用

**Files:**
- 只读检查，无修改

- [ ] **Step 1: 扫描所有 Python 文件中的 streamlit 引用**

```bash
grep -r "streamlit" agent/ rag/ skills/ prompts/ --include="*.py" --include="*.json" --include="*.md"
```
Expected: 无输出

- [ ] **Step 2: 确认 agent 可导入（无 streamlit 依赖）**

```bash
python -c "from agent.router import detect_intent; from agent.handlers import dispatch; from agent.memory import UserProfile; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit（若步骤1/2均通过，无需额外改动，直接记录）**

如果步骤 1 发现残留引用，手动删除相关 import 行后再执行：
```bash
git add -A
git commit -m "chore: clean up remaining streamlit references"
```
如果无残留，跳过此步骤。
