#!/usr/bin/env python3
"""第 04 章：用 Hook Registry 给 Agent Loop 增加扩展点。"""

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

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取项目内的文本文件。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_note",
            "description": "向项目内写入一条笔记。执行前需要用户确认。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_file",
            "description": "删除文件。示例程序禁止执行。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
]


def safe_path(relative_path: str) -> Path:
    path = (WORKDIR / relative_path).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError("路径不能跳出项目目录")
    return path


def read_file(path: str) -> str:
    return safe_path(path).read_text(encoding="utf-8")[:8000]


def write_note(path: str, content: str) -> str:
    file_path = safe_path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"已写入 {path}"


TOOL_HANDLERS = {
    "read_file": read_file,
    "write_note": write_note,
}


# Hook Registry：事件名对应一组按顺序执行的回调函数。
HOOKS = {
    "UserPromptSubmit": [],
    "PreToolUse": [],
    "PostToolUse": [],
    "Stop": [],
}


def register_hook(event: str, callback) -> None:
    HOOKS[event].append(callback)


def trigger_hooks(event: str, *args):
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None:
            return result
    return None


def prompt_log_hook(user_text: str):
    print(f"[hook] 收到用户问题：{user_text[:40]}")


def permission_hook(name: str, arguments: dict):
    """Permission 从循环里搬到了 PreToolUse Hook。"""
    if name == "delete_file":
        return "Permission denied：示例程序不允许删除文件"

    try:
        safe_path(arguments.get("path", ""))
    except ValueError as exc:
        return f"Permission denied：{exc}"

    if name == "write_note":
        choice = input(f"准备写入 {arguments['path']}，允许吗？[y/N] ").strip().lower()
        if choice not in {"y", "yes"}:
            return "Permission denied：用户没有确认写入"

    if name not in TOOL_HANDLERS:
        return f"Permission denied：未知工具 {name}"
    return None


def log_tool_hook(name: str, arguments: dict):
    print(f"[hook] PreToolUse: {name}({arguments})")


def large_output_hook(name: str, output: str):
    if len(output) > 4000:
        print(f"[hook] PostToolUse：{name} 返回内容较长")


def summary_hook(messages: list):
    print(f"[hook] Stop：本次上下文共有 {len(messages)} 条消息")


register_hook("UserPromptSubmit", prompt_log_hook)
register_hook("PreToolUse", permission_hook)
register_hook("PreToolUse", log_tool_hook)
register_hook("PostToolUse", large_output_hook)
register_hook("Stop", summary_hook)


def run_tool(tool_call) -> str:
    name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments or "{}")
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return f"未知工具：{name}"
    try:
        return str(handler(**arguments))
    except Exception as exc:
        return f"工具执行失败：{exc}"


def agent_loop(user_text: str) -> str:
    trigger_hooks("UserPromptSubmit", user_text)
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个简洁的中文助手。"
                "读取文件使用 read_file，写笔记使用 write_note，"
                "删除文件可以提出 delete_file，但程序会拒绝。"
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
            trigger_hooks("Stop", messages)
            return message.content or ""

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")
            blocked = trigger_hooks("PreToolUse", name, arguments)

            if blocked:
                result = str(blocked)
            else:
                result = run_tool(tool_call)
                trigger_hooks("PostToolUse", name, result)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )


if __name__ == "__main__":
    query = input("请输入任务（例如：请读取 README.md）：\n> ")
    print(agent_loop(query))
