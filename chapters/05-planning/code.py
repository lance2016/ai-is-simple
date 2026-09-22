#!/usr/bin/env python3
"""第 05 章：给 Agent 增加一个可更新的任务清单。"""

import json
import os
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
MAX_TURNS = 8


class TodoManager:
    """保存计划状态，并在写入前做最基本的校验。"""

    def __init__(self):
        self.items: list[dict] = []

    def update(self, todos: list) -> str:
        if not isinstance(todos, list):
            raise ValueError("todos 必须是列表")
        if len(todos) > 10:
            raise ValueError("一次最多保存 10 个任务")

        validated = []
        in_progress_count = 0
        for index, todo in enumerate(todos):
            content = str(todo.get("content", "")).strip()
            status = str(todo.get("status", "pending")).lower()
            if not content:
                raise ValueError(f"第 {index + 1} 个任务没有内容")
            if status not in {"pending", "in_progress", "completed"}:
                raise ValueError(f"不支持的状态：{status}")
            if status == "in_progress":
                in_progress_count += 1
            validated.append({"content": content, "status": status})

        if in_progress_count > 1:
            raise ValueError("同时只能有一个 in_progress 任务")

        self.items = validated
        return self.render()

    def render(self) -> str:
        markers = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}
        if not self.items:
            return "(任务清单为空)"
        done = sum(item["status"] == "completed" for item in self.items)
        lines = [f"{markers[item['status']]} {item['content']}" for item in self.items]
        lines.append(f"\n进度：{done}/{len(self.items)} 已完成")
        return "\n".join(lines)


TODO = TodoManager()


def safe_path(relative_path: str) -> Path:
    path = (WORKDIR / relative_path).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError("路径不能跳出项目目录")
    return path


def list_files(pattern: str) -> str:
    if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
        return "Error: pattern 只能在项目目录内使用"
    matches = sorted(
        str(path.relative_to(WORKDIR))
        for path in WORKDIR.glob(pattern)
        if path.is_file()
    )
    return "\n".join(matches[:100]) or "(没有找到文件)"


def read_file(path: str, limit: int = 60) -> str:
    lines = safe_path(path).read_text(encoding="utf-8").splitlines()
    if len(lines) > limit:
        lines = lines[:limit] + [f"...（还有 {len(lines) - limit} 行）"]
    return "\n".join(lines)


def todo_write(todos: list) -> str:
    try:
        output = TODO.update(todos)
    except (AttributeError, TypeError, ValueError) as exc:
        return f"Error: {exc}"
    print(f"\n[计划已更新]\n{output}")
    return output


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "todo_write",
            "description": "创建或更新当前任务的计划清单。复杂任务应先调用它。",
            "parameters": {
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "maxItems": 10,
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "status": {
                                    "type": "string",
                                    "enum": ["pending", "in_progress", "completed"],
                                },
                            },
                            "required": ["content", "status"],
                        },
                    }
                },
                "required": ["todos"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出项目内符合 pattern 的文件。",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取项目内的文本文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "todo_write": todo_write,
    "list_files": list_files,
    "read_file": read_file,
}


def run_tool(tool_call) -> str:
    name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments or "{}")
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return f"Error: 未注册的工具 {name}"
    try:
        return str(handler(**arguments))
    except Exception as exc:
        return f"Error: 工具 {name} 执行失败：{exc}"


def agent_loop(user_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个简洁的中文助手。面对多步骤任务时，"
                "先用 todo_write 列出计划；执行过程中及时更新状态。"
            ),
        },
        {"role": "user", "content": user_text},
    ]
    rounds_since_todo = 0

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

        used_todo = False
        for tool_call in message.tool_calls:
            if tool_call.function.name == "todo_write":
                used_todo = True
            result = run_tool(tool_call)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

        rounds_since_todo = 0 if used_todo else rounds_since_todo + 1
        if rounds_since_todo >= 3:
            messages.append(
                {
                    "role": "user",
                    "content": "提醒：如果任务仍有多个步骤，请检查并更新 todo_write。",
                }
            )
            rounds_since_todo = 0

    return "达到最大轮数，循环停止；请检查计划和实际结果。"


if __name__ == "__main__":
    query = input("请输入一个多步骤任务：\n> ")
    print(agent_loop(query))
