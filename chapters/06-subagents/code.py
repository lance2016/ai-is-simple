#!/usr/bin/env python3
"""第 06 章：让 task 工具启动一个拥有独立 messages 的 Subagent。"""

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


BASE_TOOLS = [
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

BASE_HANDLERS = {
    "list_files": list_files,
    "read_file": read_file,
}


def run_tool(tool_call, handlers: dict) -> str:
    name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments or "{}")
    handler = handlers.get(name)
    if handler is None:
        return f"Error: 未注册的工具 {name}"
    try:
        return str(handler(**arguments))
    except Exception as exc:
        return f"Error: 工具 {name} 执行失败：{exc}"


def run_subagent(prompt: str) -> str:
    """用全新的 messages 运行子 Agent，只返回最后的文本。"""
    print("[Subagent started]")
    sub_messages = [
        {
            "role": "system",
            "content": (
                "你是一个专注的子 Agent。完成用户交给你的子任务，"
                "可以读取项目文件，最后只返回简短、清晰的总结。"
            ),
        },
        {"role": "user", "content": prompt},
    ]

    for _ in range(8):
        response = client.chat.completions.create(
            model=MODEL,
            messages=sub_messages,
            tools=BASE_TOOLS,
            tool_choice="auto",
        )
        message = response.choices[0].message
        sub_messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            print("[Subagent done]")
            return message.content or "(子 Agent 没有返回总结)"

        for tool_call in message.tool_calls:
            result = run_tool(tool_call, BASE_HANDLERS)
            print(f"  [sub] {tool_call.function.name}: {result[:80]}")
            sub_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    return "Subagent 达到最大轮数，未能返回最终总结。"


TASK_TOOL = {
    "type": "function",
    "function": {
        "name": "task",
        "description": "使用新的对话上下文完成一个聚焦的子任务，并返回最终总结。",
        "parameters": {
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    },
}

TOOLS = [*BASE_TOOLS, TASK_TOOL]
TOOL_HANDLERS = {**BASE_HANDLERS, "task": run_subagent}


def agent_loop(user_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是主 Agent。需要深入阅读或调查时，"
                "使用 task 把聚焦子任务交给 Subagent，再根据总结回答。"
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
            result = run_tool(tool_call, TOOL_HANDLERS)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    return "达到最大轮数，循环停止；请检查主任务和子任务的结果。"


if __name__ == "__main__":
    query = input("请输入一个适合委派的任务：\n> ")
    print(agent_loop(query))
