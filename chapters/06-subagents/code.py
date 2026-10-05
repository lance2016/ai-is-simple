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
MAX_SUBAGENT_RUNS = 3


def safe_path(relative_path: str) -> Path:
    candidate = Path(relative_path)
    if (
        candidate.is_absolute()
        or ".." in candidate.parts
        or any(part.startswith(".") for part in candidate.parts)
    ):
        raise ValueError("只允许读取项目内的非隐藏路径")

    path = (WORKDIR / candidate).resolve()
    if not path.is_relative_to(WORKDIR) or any(
        part.startswith(".") for part in path.relative_to(WORKDIR).parts
    ):
        raise ValueError("路径不在允许范围内")
    return path


def list_files(pattern: str) -> str:
    candidate = Path(pattern)
    if (
        not pattern.strip()
        or candidate.is_absolute()
        or ".." in candidate.parts
        or any(part.startswith(".") for part in candidate.parts)
    ):
        return "Error: pattern 只能匹配项目内的非隐藏路径"
    matches = sorted(
        str(path.relative_to(WORKDIR))
        for path in WORKDIR.glob(pattern)
        if path.is_file()
        and not any(
            part.startswith(".") for part in path.relative_to(WORKDIR).parts
        )
    )
    return "\n".join(matches[:100]) or "(没有找到文件)"


def read_file(path: str, limit: int = 60) -> str:
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 200
    ):
        raise ValueError("limit 必须是 1 到 200 之间的整数")
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
    try:
        arguments = json.loads(tool_call.function.arguments or "{}")
    except (json.JSONDecodeError, TypeError):
        return "Error: 工具参数不是有效 JSON"
    if not isinstance(arguments, dict):
        return "Error: 工具参数必须是 JSON 对象"

    handler = handlers.get(name)
    if handler is None:
        return f"Error: 未注册的工具 {name}"
    try:
        return str(handler(**arguments))
    except Exception as exc:
        # 避免把本机绝对路径等异常细节回传给模型。
        return f"Error: 工具 {name} 执行失败（{type(exc).__name__}）"


def run_subagent(prompt: str) -> str:
    """用全新的 messages 运行子 Agent，只返回最后的文本。"""
    if not isinstance(prompt, str) or not prompt.strip():
        return "Error: 子任务描述不能为空"

    print("[Subagent started]")
    sub_messages = [
        {
            "role": "system",
            "content": (
                "你是一个只读调查子 Agent。完成用户交给你的聚焦子任务，"
                "结论附上项目内文件路径和简短原文依据；无法完成时明确说明，"
                "不要把推测写成已核实的事实。"
            ),
        },
        {"role": "user", "content": prompt},
    ]

    for _ in range(MAX_TURNS):
        response = client.chat.completions.create(
            model=MODEL,
            messages=sub_messages,
            tools=BASE_TOOLS,
            tool_choice="auto",
        )
        choice = response.choices[0]
        message = choice.message
        sub_messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            if choice.finish_reason != "stop":
                return f"子 Agent 未正常结束：{choice.finish_reason}"
            print("[Subagent done]")
            return message.content or "Error: 子 Agent 没有返回总结"

        # 参数可能因长度或请求中断而不完整；只有正常的工具调用轮次才执行。
        if choice.finish_reason != "tool_calls":
            return f"子 Agent 的工具调用未正常结束：{choice.finish_reason}"

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

    return f"Error: 子 Agent 达到 {MAX_TURNS} 轮上限，未能返回最终总结。"


TASK_TOOL = {
    "type": "function",
    "function": {
        "name": "task",
        "description": (
            "把需要较长调查的聚焦子任务交给新上下文；"
            "返回文件路径和证据摘要，未完成时明确说明。"
        ),
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
                "你是主 Agent。遇到需要较长调查的聚焦子任务时，"
                "可以调用 task；结合其返回的路径和证据回答，"
                "并明确区分已核实结论与未完成部分。"
            ),
        },
        {"role": "user", "content": user_text},
    ]

    subagent_runs = 0
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
            if choice.finish_reason != "stop":
                return f"主 Agent 未正常结束：{choice.finish_reason}"
            return message.content or ""

        if choice.finish_reason != "tool_calls":
            return f"主 Agent 的工具调用未正常结束：{choice.finish_reason}"

        for tool_call in message.tool_calls:
            if tool_call.function.name == "task":
                if subagent_runs >= MAX_SUBAGENT_RUNS:
                    result = f"Error: 单次请求最多委派 {MAX_SUBAGENT_RUNS} 次。"
                else:
                    subagent_runs += 1
                    result = run_tool(tool_call, TOOL_HANDLERS)
            else:
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
