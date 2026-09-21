#!/usr/bin/env python3
"""第 09 章：把重要信息保存到 .memory，并在下一次任务中召回。"""

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
WORKDIR = Path(__file__).resolve().parents[2]
MEMORY_DIR = WORKDIR / ".memory"
MEMORY_INDEX = MEMORY_DIR / "MEMORY.md"


def slugify(name: str) -> str:
    slug = re.sub(r"[^\w-]+", "-", name.lower(), flags=re.UNICODE).strip("-")
    return slug or "memory"


def memory_document(name: str, memory_type: str, description: str, body: str) -> str:
    return (
        "---\n"
        f"name: {name}\n"
        f"type: {memory_type}\n"
        f"description: {description}\n"
        "---\n\n"
        f"{body.strip()}\n"
    )


def rebuild_index() -> str:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# Memory Index", ""]
    for path in sorted(MEMORY_DIR.glob("*.md")):
        if path.name == MEMORY_INDEX.name:
            continue
        text = path.read_text(encoding="utf-8")
        description = next(
            (line.split(":", 1)[1].strip() for line in text.splitlines() if line.startswith("description:")),
            "",
        )
        lines.append(f"- [{path.stem}]({path.name}): {description}")
    MEMORY_INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(MEMORY_INDEX.relative_to(WORKDIR))


def remember(name: str, memory_type: str, description: str, body: str) -> str:
    """写入一条持久化记忆，并重建索引。"""
    allowed_types = {"user", "project", "feedback", "reference"}
    if memory_type not in allowed_types:
        return f"Error: type 必须是 {sorted(allowed_types)} 之一"
    path = MEMORY_DIR / f"{slugify(name)}.md"
    path.write_text(
        memory_document(name, memory_type, description, body),
        encoding="utf-8",
    )
    index_path = rebuild_index()
    return f"已保存记忆：{path.relative_to(WORKDIR)}\n索引：{index_path}"


def recall_memory(query: str, limit: int = 3) -> str:
    """先按关键词筛选，再读取相关记忆正文。"""
    query_words = {
        word.lower()
        for word in re.findall(r"[a-zA-Z0-9]+|[\u4e00-\u9fff]", query)
    }
    candidates = []
    for path in MEMORY_DIR.glob("*.md"):
        if path.name == MEMORY_INDEX.name:
            continue
        text = path.read_text(encoding="utf-8")
        haystack = text.lower()
        score = sum(word in haystack for word in query_words)
        if score:
            candidates.append((score, path, text))

    candidates.sort(key=lambda item: (-item[0], item[1].name))
    selected = candidates[: max(1, min(limit, 5))]
    if not selected:
        return "(没有找到相关记忆)"
    return "\n\n".join(
        f"[Memory: {path.name}]\n{text}" for _, path, text in selected
    )


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "保存一条以后可能复用的长期信息。不要保存只对当前任务有效的临时指令。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "memory_type": {"type": "string", "enum": ["user", "project", "feedback", "reference"]},
                    "description": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["name", "memory_type", "description", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recall_memory",
            "description": "根据当前问题召回相关的持久化记忆。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["query"],
            },
        },
    },
]

TOOL_HANDLERS = {"remember": remember, "recall_memory": recall_memory}


def agent_loop(user_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个简洁的中文助手。Memory 只是背景知识，当前用户请求优先。"
                "用户明确要求记住长期信息时使用 remember；需要背景时使用 recall_memory。"
            ),
        },
        {"role": "user", "content": user_text},
    ]

    while True:
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


if __name__ == "__main__":
    query = input("请输入任务（例如：请记住项目默认模型）：\n> ")
    print(agent_loop(query))
