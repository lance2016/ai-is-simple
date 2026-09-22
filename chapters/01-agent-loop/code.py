#!/usr/bin/env python3
"""第 01 章：用 DeepSeek + OpenAI SDK 跑一个最小 Agent Loop。"""

import json
import os
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

# 读取项目根目录的 .env，避免把 API Key 直接写进代码。
load_dotenv()

# 这些配置都可以在 .env 里替换；默认值让示例开箱即用。
MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not API_KEY:
    raise SystemExit("请先在 .env 中填写 DEEPSEEK_API_KEY。")

client = OpenAI(
    api_key=API_KEY,
    base_url=BASE_URL,
)

# 教学示例也要有停止边界，避免模型或工具异常时无限循环。
MAX_TURNS = 8

# 先告诉模型：它有哪些工具可以选择。
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
    """根据模型的选择，执行对应工具并返回结果。

    这里是 Harness 的工作：模型只提出请求，Python 真正执行动作。
    """
    name = tool_call.function.name
    arguments = json.loads(tool_call.function.arguments or "{}")

    if name == "get_today":
        return get_today()

    return f"未知工具：{name}，参数：{arguments}"


def agent_loop(user_text: str) -> str:
    # 用户任务只在循环开始时放入一次。
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

    for _ in range(MAX_TURNS):
        # 每一轮都把最新消息发给 DeepSeek，让它决定下一步。
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )

        # 先保存模型这次的回答，下一轮才能看见完整上下文。
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))

        # 没有工具调用：模型已经可以直接回答，循环结束。
        if not message.tool_calls:
            return message.content or ""

        # 有工具调用：Python 执行工具，再把结果送回模型。
        # 下一轮不会重新询问用户，而是从工具结果继续判断。
        for tool_call in message.tool_calls:
            result = run_tool(tool_call)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )

    return "达到最大轮数，循环停止；这只表示程序停了，不代表任务一定完成。"


if __name__ == "__main__":
    print(agent_loop("今天是几号？"))
