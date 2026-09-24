#!/usr/bin/env python3
"""实战篇 02：让 Agent 记住项目里的约定

不加任何新工具，只往系统提示里补一段话：
  .agent/MEMORY.md          全文放进系统提示（第 09 章 Memory）
  .agent/skills/*/SKILL.md  只放名字和简介，要用时模型自己 read 全文（第 07 章 Skill Loading）

模型想记东西，就用现有的 edit / write 去改 MEMORY.md，照样要你点头。

启动：
  uv run python labs/01-mini-coding-agent/server.py --lab 02
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01-mini-coding-agent"))

from agent import Extension, Workspace  # noqa: E402

# 用 --lab 02 启动时，默认切到这个目录，里面是给这个实战准备的练习项目。
DEMO = "demo"
# 页面空白时显示的示例任务，点一下就填进输入框。
SAMPLES = (
    "审查一下 stats.py",
    "记住：以后审查结果只列“必须改”的问题",
)

MEMORY_FILE = ".agent/MEMORY.md"
SKILLS_DIR = ".agent/skills"
# 记忆每一轮都跟着系统提示发出去，太长就是在白白烧上下文。
MAX_MEMORY_CHARS = 4000


class MemoryExtension(Extension):
    name = "memory"

    def system_prompt(self, workspace: Workspace) -> str:
        # 每次新对话都会重新读一遍，所以对话里改过的记忆，要到下一次新对话才出现在这里。
        return "\n\n".join(part for part in (self._memory(workspace), self._skills(workspace)) if part)

    def _memory(self, workspace: Workspace) -> str:
        path = workspace.root / MEMORY_FILE
        content = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
        if len(content) > MAX_MEMORY_CHARS:
            content = content[:MAX_MEMORY_CHARS] + "\n（记忆太长，后面被截断了，请提醒用户整理。）"
        return (
            f"## 项目记忆（{MEMORY_FILE}）\n\n"
            f"{content or '（还没有记忆）'}\n\n"
            "记忆规则：\n"
            f"- 用户明确说“记住”，或者是以后每次都会用到的稳定约定，才用 edit / write 更新 {MEMORY_FILE}；\n"
            "- 只对这一次任务有效的要求，不要记；\n"
            "- 记忆和用户当前的要求冲突时，听当前的，并提醒用户要不要更新记忆。"
        )

    def _skills(self, workspace: Workspace) -> str:
        lines = []
        for path in sorted((workspace.root / SKILLS_DIR).glob("*/SKILL.md")):
            name, description = read_front_matter(path)
            lines.append(f"- {name}：{description}（全文：{workspace.label(path)}）")
        if not lines:
            return ""
        return (
            "## 可用技能\n\n" + "\n".join(lines) + "\n\n"
            "这里只有简介。任务用得上某个技能时，先用 read 读它的全文，再按里面的要求做；用不上就别读。"
        )


def read_front_matter(path: Path) -> tuple[str, str]:
    """从 SKILL.md 开头的 --- 块里取 name 和 description，格式和第 07 章一样。"""
    fields = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0] == "---":
        for line in lines[1:]:
            if line == "---":
                break
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
    return fields.get("name", path.parent.name), fields.get("description", "（没有简介）")


def create(workspace: Workspace) -> Extension:
    return MemoryExtension()
