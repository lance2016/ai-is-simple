#!/usr/bin/env python3
"""第 01 章：用 DeepSeek + OpenAI SDK 跑一个最小 Agent Loop。"""

import json
import os
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not API_KEY:
    raise SystemExit("请先在 .env 中填写 DEEPSEEK_API_KEY。")

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_today",
            "description": "获取今天的日期。",
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    }
]


def get_today() -> str:
    """工具真正执行的地方。"""
    return datetime.now().strftime("%Y-%m-%d")


def run_tool(tool_call) -> str:
    """根据模型的选择，执行对应工具并返回结果。"""
    name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments or "{}")

    if name == "get_today":
        return get_today()

    return f"未知工具：{name}，参数：{arguments}"


def agent_loop(user_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个简洁的中文助手。"
                "如果用户询问今天的日期，请调用 get_today；"
                "其他问题直接回答。"
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

        # 没有工具调用：模型已经可以直接回答，循环结束。
        if not message.tool_calls:
            return message.content or ""

        # 有工具调用：Python 执行工具，再把结果送回模型。
        for tool_call in message.tool_calls:
            result = run_tool(tool_call)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )


if __name__ == "__main__":
    print(agent_loop("今天是几号？"))
