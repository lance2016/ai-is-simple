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
        for manifest in sorted(self.skills_dir.glob("*/SKILL.md")):
            text = manifest.read_text(encoding="utf-8")
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
                "path": str(manifest),
            }

    @staticmethod
    def _field(text: str, field: str) -> str:
        match = re.search(rf"^\s*{re.escape(field)}:\s*[\"']?(.+?)[\"']?\s*$", text, re.MULTILINE)
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
        return Path(skill["path"]).read_text(encoding="utf-8")


SKILL_LOADER = SkillLoader(SKILLS_DIR)


def list_skills() -> str:
    return SKILL_LOADER.catalog()


def load_skill(name: str) -> str:
    return SKILL_LOADER.load(name)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "列出当前可用技能的名称和简介。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "load_skill",
            "description": "按技能名称加载完整 SKILL.md。",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "list_skills": list_skills,
    "load_skill": load_skill,
}


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
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")
            handler = TOOL_HANDLERS.get(name)
            result = handler(**arguments) if handler else f"未知工具：{name}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                }
            )

    return "达到最大轮数，循环停止；请检查技能是否真的被正确使用。"


if __name__ == "__main__":
    query = input("请输入任务（例如：请加载 code-review）：\n> ")
    print(agent_loop(query))
