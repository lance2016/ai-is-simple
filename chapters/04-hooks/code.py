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
            "description": "删除文件。示例程序禁止执行。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
]


# Hard boundaries live inside the tool functions: every call passes through them,
# whether or not any hook is registered. They are the same limits as chapter 03.
SENSITIVE_FILES = {".env", ".env.local", ".env.production", ".env.development"}
ROOT_READABLE_FILES = {"README.md", "Agents.md", "SOURCES.md", "STYLE_GUIDE.md"}


def safe_path(relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("path 必须是非空字符串")
    path = (WORKDIR / relative_path).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError("路径不能跳出项目目录")
    return path


def safe_read_path(relative_path: str) -> Path:
    path = safe_path(relative_path)
    if path.name in SENSITIVE_FILES or any(part.startswith(".git") for part in path.parts):
        raise ValueError("出于安全考虑，不能读取 .env 或 .git 等敏感路径")
    is_root_doc = path.parent == WORKDIR and path.name in ROOT_READABLE_FILES
    if not (is_root_doc or (WORKDIR / "chapters") in path.parents):
        raise ValueError("示例只允许读取根目录教学文档或 chapters/ 下的文件")
    return path


def safe_write_path(relative_path: str) -> Path:
    path = safe_path(relative_path)
    if (WORKDIR / "notes") not in path.parents:
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
    """按注册顺序运行所有回调，返回第一个不为 None 的结果。

    是否用这个结果改变流程，由触发 Hook 的调用位置决定。
    """
    blocked = None
    for callback in HOOKS[event]:
        result = callback(*args)
        if result is not None and blocked is None:
            blocked = result
    return blocked


def prompt_log_hook(user_text: str):
    print(f"[hook] 收到用户问题：{user_text[:40]}")


def permission_hook(name: str, arguments: dict):
    """可插拔的策略：这一步要不要先问用户。路径范围不归它管，那是工具函数自己的硬边界。"""
    if name == "delete_file":
        return "Permission denied：示例程序不允许删除文件"

    if name == "write_note":
        try:
            safe_write_path(arguments.get("path"))
        except ValueError as exc:
            # No point asking the user to confirm a write that the tool will refuse anyway.
            return f"Permission denied：{exc}"
        try:
            choice = input(
                f"准备写入 {arguments['path']}，完整内容如下：\n"
                f"{arguments.get('content', '')}\n允许吗？[y/N] "
            ).strip().lower()
        except EOFError:
            # Nobody can confirm in a non-interactive run, so refuse.
            return "Permission denied：用户没有确认写入"
        if choice not in {"y", "yes"}:
            return "Permission denied：用户没有确认写入"
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


def parse_arguments(tool_call) -> dict | None:
    try:
        arguments = json.loads(tool_call.function.arguments or "{}")
    except (json.JSONDecodeError, TypeError):
        return None
    return arguments if isinstance(arguments, dict) else None


def run_tool(name: str, arguments: dict) -> str:
    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return f"未知工具：{name}"
    try:
        return str(handler(**arguments))
    except Exception as exc:
        return f"工具执行失败：{exc}"


def agent_loop(user_text: str) -> str:
    # 这个示例只用它记录输入，忽略 Hook 的返回值。
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

    for _ in range(MAX_TURNS):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        choice = response.choices[0]
        message = choice.message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            # Stop 在这里用于收尾记录；本示例不支持 Hook 要求继续运行。
            trigger_hooks("Stop", messages)
            if choice.finish_reason != "stop":
                return f"模型未正常结束：{choice.finish_reason}"
            return message.content or ""

        # Same rule as chapter 01: never run arguments that may have been cut off.
        if choice.finish_reason != "tool_calls":
            return f"工具调用未正常结束：{choice.finish_reason}"

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            arguments = parse_arguments(tool_call)
            if arguments is None:
                blocked = "工具参数必须是合法的 JSON 对象"
            else:
                # 本示例只有 PreToolUse 的返回值会决定是否执行工具。
                blocked = trigger_hooks("PreToolUse", name, arguments)

            if blocked:
                result = str(blocked)
            else:
                result = run_tool(name, arguments)
                # 当前 PostToolUse 用于观察结果，不能改变已完成的工具调用。
                trigger_hooks("PostToolUse", name, result)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    trigger_hooks("Stop", messages)
    return "达到最大轮数，循环停止；请检查任务是否真的完成。"


if __name__ == "__main__":
    query = input("请输入任务（例如：请读取 README.md）：\n> ")
    print(agent_loop(query))
