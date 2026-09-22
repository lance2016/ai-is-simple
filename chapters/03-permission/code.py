#!/usr/bin/env python3
"""第 03 章：在工具执行前增加一个简单的 Permission 检查。"""

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

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取项目内允许访问的文本文件，不读取 .env 等敏感文件。",
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
            "description": "向 notes/ 目录写入一条笔记。执行前需要用户确认。",
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
            "description": "删除项目内的文件。教学示例中禁止使用。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
]


def safe_path(relative_path: str) -> Path:
    """只允许访问项目目录内的路径。"""
    path = (WORKDIR / relative_path).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError("路径不能跳出项目目录")
    return path


SENSITIVE_FILES = {".env", ".env.local", ".env.production", ".env.development"}
ROOT_READABLE_FILES = {"README.md", "Agents.md", "SOURCES.md", "STYLE_GUIDE.md"}


def safe_read_path(relative_path: str) -> Path:
    """把读取范围限制在教学文档和章节目录，并拒绝敏感文件。"""
    path = safe_path(relative_path)
    if path.name in SENSITIVE_FILES or any(part.startswith(".git") for part in path.parts):
        raise ValueError("出于安全考虑，不能读取 .env 或 .git 等敏感路径")

    is_root_doc = path.parent == WORKDIR and path.name in ROOT_READABLE_FILES
    is_chapter_file = (WORKDIR / "chapters") in path.parents
    if not (is_root_doc or is_chapter_file):
        raise ValueError("示例只允许读取根目录教学文档或 chapters/ 下的文件")
    return path


def safe_write_path(relative_path: str) -> Path:
    """写入只允许落在 notes/，避免把示例变成任意文件覆盖器。"""
    path = safe_path(relative_path)
    notes_dir = WORKDIR / "notes"
    if notes_dir not in path.parents:
        raise ValueError("写入范围仅限 notes/ 目录")
    return path


def read_file(path: str) -> str:
    return safe_read_path(path).read_text(encoding="utf-8")[:8000]


def write_note(path: str, content: str) -> str:
    file_path = safe_write_path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(content, encoding="utf-8")
    return f"已写入 {path}"


TOOL_HANDLERS = {
    "read_file": read_file,
    "write_note": write_note,
}

# 永久禁止的工具不进入 TOOL_HANDLERS，因此不会有执行机会。
DENY_LIST = {"delete_file": "示例程序不允许删除文件"}


def check_permission(name: str, arguments: dict) -> tuple[bool, str]:
    """在真正调用处理函数前，判断这次操作能否继续。"""
    if name in DENY_LIST:
        return False, DENY_LIST[name]

    try:
        if name == "read_file":
            safe_read_path(arguments.get("path", ""))
        elif name == "write_note":
            safe_write_path(arguments.get("path", ""))
        else:
            safe_path(arguments.get("path", ""))
    except ValueError as exc:
        return False, str(exc)

    if name == "write_note":
        content = str(arguments.get("content", ""))
        choice = input(
            f"准备写入 {arguments['path']}，完整内容如下：\n{content}\n允许吗？[y/N] "
        ).strip().lower()
        if choice not in {"y", "yes"}:
            return False, "用户没有确认写入"

    if name not in TOOL_HANDLERS:
        return False, f"未知工具：{name}"

    return True, ""


def run_tool(tool_call) -> str:
    name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments or "{}")
    allowed, reason = check_permission(name, arguments)

    if not allowed:
        return f"Permission denied: {reason}"

    try:
        return str(TOOL_HANDLERS[name](**arguments))
    except Exception as exc:
        return f"工具执行失败：{exc}"


def agent_loop(user_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个简洁的中文助手。"
                "读取文件使用 read_file，写笔记使用 write_note，"
                "删除文件可以提出 delete_file，但程序可能拒绝。"
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
            result = run_tool(tool_call)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    return "达到最大轮数，循环停止；请检查任务是否真的完成。"


if __name__ == "__main__":
    query = input("请输入任务（例如：请读取 README.md）：\n> ")
    print(agent_loop(query))
