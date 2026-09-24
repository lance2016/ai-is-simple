#!/usr/bin/env python3
"""实战篇 02：长期记忆

项目规则每次新对话带入；具体经验按任务需要，用现有 read 工具打开。

启动：
  uv run python labs/01-mini-coding-agent/server.py --lab 02
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01-mini-coding-agent"))

from agent import Extension, Workspace  # noqa: E402

# 用 --lab 02 启动时，默认切到这个目录，里面有代码和记忆示例。
DEMO = "demo"
# 页面空白时显示的示例任务，点一下就填进输入框。
SAMPLES = (
    "修复 stats.py 里 median 对偶数长度列表的处理问题。",
    "stats.py 里的 median 以前发现过什么问题？",
    "记住：统计函数收到空列表时，要给出清楚的错误。",
)

MEMORY_FILE = ".agent/MEMORY.md"
MEMORIES_DIR = ".agent/memories"
# 常驻记忆每次都会发给模型，限制长度，避免慢慢变成项目百科。
MAX_CORE_MEMORY_CHARS = 1600


class MemoryExtension(Extension):
    name = "memory"

    def system_prompt(self, workspace: Workspace) -> str:
        # 常驻规则和按需读取的经验目录分开，避免每次请求都注入所有历史。
        parts = (
            self._core_memory(workspace),
            self._memory_catalog(workspace),
            self._memory_rules(),
        )
        return "\n\n".join(part for part in parts if part)

    def _core_memory(self, workspace: Workspace) -> str:
        path = workspace.resolve(MEMORY_FILE)
        content = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
        if len(content) > MAX_CORE_MEMORY_CHARS:
            content = content[:MAX_CORE_MEMORY_CHARS] + "\n（常驻记忆太长，后面被截断了，请提醒用户整理。）"
        return (
            f"## 常驻项目记忆（{MEMORY_FILE}）\n\n"
            f"{content or '（还没有记忆）'}"
        )

    def _memory_catalog(self, workspace: Workspace) -> str:
        lines = []
        directory = workspace.resolve(MEMORIES_DIR)
        for path in sorted(directory.glob("*.md")):
            fields = read_front_matter(path)
            name = fields.get("name", path.stem)
            kind = fields.get("type", "未分类")
            scope = fields.get("scope", "project")
            description = fields.get("description", "（没有简介）")
            source = fields.get("source", "")
            source_text = f"；来源：{source}" if source else ""
            lines.append(f"- [{scope}/{kind}] {name}：{description}{source_text}（全文：{workspace.label(path)}）")
        catalog = "\n".join(lines) or "（还没有经验记录）"
        return (
            "## 过往经验目录\n\n"
            f"{catalog}\n\n"
            "这里只列记录简介。问题和某条简介相关时，再用 read 读取那一条的全文。"
        )

    @staticmethod
    def _memory_rules() -> str:
        return (
            "## 记忆使用规则\n\n"
            "- 每次任务都适用的稳定项目规则，才放进常驻的 MEMORY.md；\n"
            "- 某次故障、决定或解决办法，单独写入 memories/ 下的 Markdown，"
            "开头标明 name、type、scope、source、description；\n"
            "- 用户明确说“记住”才保存新信息，用现有 write / edit，等待授权；\n"
            "- 新信息与旧记录冲突时保留变化线索，不能静默覆盖；应用前核对当前文件；\n"
            "- 当前用户要求优先；\n"
            "- 不要保存密钥、临时要求或没有依据的猜测。"
        )


def read_front_matter(path: Path) -> dict[str, str]:
    """读取记忆条目前面的简单 YAML 元数据。"""
    fields: dict[str, str] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if lines and lines[0] == "---":
        for line in lines[1:]:
            if line == "---":
                break
            key, separator, value = line.partition(":")
            if separator:
                fields[key.strip()] = value.strip()
    return fields


def create(workspace: Workspace) -> Extension:
    return MemoryExtension()
