#!/usr/bin/env python3
"""第 07 章：先展示技能目录，需要时再加载完整 SKILL.md。"""

import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not API_KEY:
    raise SystemExit("请先在 .env 中填写 DEEPSEEK_API_KEY。")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
SKILLS_DIR = Path(__file__).parent / "skills"
MAX_TURNS = 8


class SkillLoader:
    """启动时建立技能目录，之后按名称读取完整内容。"""

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills: dict[str, dict[str, str]] = {}
        self.scan()

    def scan(self) -> None:
        self.skills.clear()
        skills_root = self.skills_dir.resolve()
        for manifest in sorted(self.skills_dir.glob("*/SKILL.md")):
            try:
                # 登记时也检查真实路径，避免技能目录里的符号链接指向外部文件。
                manifest_path = manifest.resolve()
                if not manifest_path.is_relative_to(skills_root) or not manifest_path.is_file():
                    continue
                text = manifest_path.read_text(encoding="utf-8")
            except (OSError, RuntimeError, UnicodeError):
                continue
            name = self._field(text, "name") or manifest.parent.name
            description = self._field(text, "description")
            if not description:
                description = next(
                    (line.lstrip("# ").strip() for line in text.splitlines() if line.strip()),
                    "",
                )
            self.skills[name] = {
                "name": name,
                "description": description,
                "path": str(manifest_path),
            }

    @staticmethod
    def _field(text: str, field: str) -> str:
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return ""
        try:
            closing = lines.index("---", 1)
        except ValueError:
            return ""

        frontmatter = "\n".join(lines[1:closing])
        match = re.search(
            rf"^\s*{re.escape(field)}:\s*[\"']?(.+?)[\"']?\s*$",
            frontmatter,
            re.MULTILINE,
        )
        return match.group(1).strip() if match else ""

    def catalog(self) -> str:
        if not self.skills:
            return "(没有找到技能)"
        return "\n".join(
            f"- {item['name']}: {item['description']}"
            for item in self.skills.values()
        )

    def load(self, name: str) -> str:
        skill = self.skills.get(name)
        if skill is None:
            available = ", ".join(self.skills) or "none"
            return f"Error: 未知技能 {name}。可用技能：{available}"
        try:
            path = Path(skill["path"]).resolve()
            if not path.is_relative_to(self.skills_dir.resolve()):
                return "Error: 技能文件不在技能目录中"
            return path.read_text(encoding="utf-8")
        except (OSError, RuntimeError, UnicodeError):
            return "Error: 技能文件无法读取"


SKILL_LOADER = SkillLoader(SKILLS_DIR)


def load_skill(name: str) -> str:
    return SKILL_LOADER.load(name)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "按技能名称加载完整 SKILL.md。",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
]

TOOL_HANDLERS = {"load_skill": load_skill}


def run_tool_call(tool_call) -> str:
    """检查模型生成的参数，再调用应用登记的工具。"""
    name = tool_call.function.name
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return f"Error: 未知工具 {name}"

    try:
        arguments = json.loads(tool_call.function.arguments or "{}")
    except (json.JSONDecodeError, TypeError):
        return "Error: 工具参数不是合法 JSON"

    # JSON Schema 会引导模型，但 Harness 仍要检查它实际发来的数据。
    if (
        not isinstance(arguments, dict)
        or set(arguments) != {"name"}
        or not isinstance(arguments["name"], str)
    ):
        return "Error: load_skill 需要且只接受一个字符串参数 name"

    return handler(**arguments)


def agent_loop(user_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个简洁的中文助手。\n"
                "当前可用技能目录如下：\n"
                f"{SKILL_LOADER.catalog()}\n\n"
                "只有任务需要时，才调用 load_skill 读取完整说明。"
            ),
        },
        {"role": "user", "content": user_text},
    ]

    for _ in range(MAX_TURNS):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            return message.content or ""

        for tool_call in message.tool_calls:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": run_tool_call(tool_call),
                }
            )

    return "达到最大轮数，循环停止；请检查技能是否真的被正确使用。"


if __name__ == "__main__":
    query = input("请输入任务（例如：请加载 code-review）：\n> ")
    print(agent_loop(query))
