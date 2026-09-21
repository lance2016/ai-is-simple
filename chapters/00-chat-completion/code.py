#!/usr/bin/env python3
"""第 00 章：用两次 Chat Completion 看懂 messages 如何保持上下文。"""

import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
API_KEY = os.getenv("DEEPSEEK_API_KEY")

if not API_KEY:
    raise SystemExit("请先在 .env 中填写 DEEPSEEK_API_KEY。")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

# messages 就是这一次请求希望模型看到的上下文。
messages = [
    {
        "role": "system",
        "content": "你是一个简洁的中文助手。回答时请记住用户告诉你的信息。",
    },
    {"role": "user", "content": "我叫小明。请简单介绍一下 Python。"},
]

# 第一次请求：模型只看到当前 messages。
response = client.chat.completions.create(
    model=MODEL,
    messages=messages,
)
assistant_message = response.choices[0].message
print("第一轮：", assistant_message.content or "")

# 关键：把 assistant 回复放回 messages，下一次请求才有完整历史。
messages.append(assistant_message.model_dump(exclude_none=True))
messages.append({"role": "user", "content": "我叫什么名字？"})

# 第二次请求：程序把第一轮历史和新问题一起发给模型。
response = client.chat.completions.create(
    model=MODEL,
    messages=messages,
)
print("第二轮：", response.choices[0].message.content or "")
