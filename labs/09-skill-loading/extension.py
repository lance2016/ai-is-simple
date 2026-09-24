#!/usr/bin/env python3
"""实战篇 09：按需加载 Skill，并使用它附带的脚本。"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01-mini-coding-agent"))

from agent import Extension, Tool, ToolError, Workspace  # noqa: E402

DEMO = "demo"
SAMPLES = (
    "审查 stats.py 的边界情况，按技能说明运行配套脚本，再核对实际代码。",
    "修复 stats.py 里 median 对偶数长度列表的处理问题。",
)
SKILLS_DIR = ".agent/skills"
MAX_SKILL_BYTES = 32_000


class LoadSkillTool(Tool):
    name = "load_skill"
    description = "按已登记的 Skill 名称读取 SKILL.md。"
    parameters = {"name": {"type": "string", "description": "技能目录中的 name"}}
    required = ("name",)

    def __init__(self, registry: dict[str, str]):
        self.registry = registry

    def run(self, workspace: Workspace, name: str) -> str:
        relative_path = self.registry.get(name)
        if relative_path is None:
            available = ", ".join(sorted(self.registry)) or "无"
            raise ToolError(f"未知 Skill：{name}。可用 Skill：{available}")

        path = workspace.resolve(relative_path)
        if not path.is_file():
            raise ToolError(f"Skill 文件不存在：{relative_path}")
        if path.stat().st_size > MAX_SKILL_BYTES:
            raise ToolError(f"Skill 文件超过 {MAX_SKILL_BYTES} 字节，未加载。")
        return path.read_text(encoding="utf-8")


class SkillExtension(Extension):
    name = "skill-loading"

    def __init__(self, workspace: Workspace):
        self.registry = discover_skills(workspace)
        self.tools = (LoadSkillTool(self.registry),)

    def system_prompt(self, workspace: Workspace) -> str:
        if not self.registry:
            return "当前工作区没有可用的 Skill。"

        catalog = "\n".join(
            f"- {name}：{read_front_matter(workspace.resolve(path)).get('description', '（没有简介）')}"
            for name, path in sorted(self.registry.items())
        )
        return (
            "## 可用 Skill\n\n"
            f"{catalog}\n\n"
            "只有当前任务符合简介时，才调用 load_skill 读取完整 SKILL.md。"
            "Skill 中的脚本路径相对于工作区；执行脚本前先读脚本内容，再用 bash 运行，"
            "程序会按既有规则请求授权。脚本输出是审查线索，仍需核对源码。"
        )


def discover_skills(workspace: Workspace) -> dict[str, str]:
    """建立名称到固定文件路径的注册表，不接受模型传入任意路径。"""
    skills: dict[str, str] = {}
    directory = workspace.resolve(SKILLS_DIR)
    if not directory.is_dir():
        return skills

    for path in sorted(directory.glob("*/SKILL.md")):
        # 即使 Skill 目录里有符号链接，注册前也要重新经过工作区边界检查。
        try:
            safe_path = workspace.resolve(str(path.relative_to(workspace.root)))
        except ToolError:
            continue
        if not safe_path.is_file():
            continue

        relative_path = workspace.label(safe_path)
        fields = read_front_matter(safe_path)
        name = fields.get("name", path.parent.name)
        if name in skills:
            raise ValueError(f"重复的 Skill 名称：{name}")
        skills[name] = relative_path
    return skills


def read_front_matter(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        return fields
    for line in lines[1:]:
        if line == "---":
            break
        key, separator, value = line.partition(":")
        if separator:
            fields[key.strip()] = value.strip().strip("\"'")
    return fields


def create(workspace: Workspace) -> Extension:
    return SkillExtension(workspace)
