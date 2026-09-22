#!/usr/bin/env python3
"""第 02 章：用多个工具和一个分发 map 扩展 Agent。"""

import json
import os
from datetime import datetime
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


# 工具定义：告诉模型“我有哪些能力，以及每个能力需要什么参数”。
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出项目中符合 pattern 的文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "例如 chapters/**/*.md",
                    }
                },
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
    {
        "type": "function",
        "function": {
            "name": "get_today",
            "description": "获取今天的日期。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def safe_path(relative_path: str) -> Path:
    """只允许访问项目目录内的文件。"""
    path = (WORKDIR / relative_path).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError("路径不能跳出项目目录")
    return path


def list_files(pattern: str) -> str:
    """列出项目内的文件，不接受绝对路径或 ..。"""
    pattern_path = Path(pattern)
    if pattern_path.is_absolute() or ".." in pattern_path.parts:
        return "Error: pattern 只能在项目目录内使用"

    matches = sorted(
        str(path.relative_to(WORKDIR))
        for path in WORKDIR.glob(pattern)
        if path.is_file()
    )
    return "\n".join(matches[:100]) or "(没有找到文件)"


def read_file(path: str, limit: int = 80) -> str:
    """读取项目内的文本文件，并限制返回行数。"""
    try:
        lines = safe_path(path).read_text(encoding="utf-8").splitlines()
        if len(lines) > limit:
            lines = lines[:limit] + [f"...（还有 {len(lines) - limit} 行）"]
        return "\n".join(lines)
    except Exception as exc:
        return f"Error: {exc}"


def get_today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


# 分发 map：模型说出工具名称，程序就能找到对应的 Python 函数。
TOOL_HANDLERS = {
    "list_files": list_files,
    "read_file": read_file,
    "get_today": get_today,
}


def run_tool(tool_call) -> str:
    """解析参数，找到处理函数，执行后返回结果。"""
    name = tool_call.function.name
    try:
        arguments = json.loads(tool_call.function.arguments or "{}")
        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            return f"Error: 未注册的工具 {name}"
        return str(handler(**arguments))
    except Exception as exc:
        return f"Error: 工具 {name} 执行失败：{exc}"


def agent_loop(user_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个简洁的中文学习助手。"
                "需要列文件时使用 list_files，需要阅读文件时使用 read_file，"
                "需要日期时使用 get_today；其他问题直接回答。"
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

        # 没有工具调用，说明模型已经可以直接回答。
        if not message.tool_calls:
            return message.content or ""

        # 多个工具调用按返回顺序执行，并逐个把结果送回模型。
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
    query = "列出 chapters 目录下的 Markdown 文件，并告诉我第 01 章是什么主题。"
    print(agent_loop(query))
