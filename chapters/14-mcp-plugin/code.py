#!/usr/bin/env python3
"""第 14 章：用一个本地 MCP 风格注册表理解外部工具如何进入工具池。"""

from __future__ import annotations

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


class MCPServer:
    """用最小接口模拟一个可发现、可调用的外部工具服务器。"""

    def __init__(self, name: str, tools: list[dict], handlers: dict):
        self.name = name
        self.tools = tools
        self.handlers = handlers

    def manifest(self) -> list[dict]:
        return [
            {
                "server": self.name,
                "name": tool["name"],
                "description": tool["description"],
            }
            for tool in self.tools
        ]

    def call(self, tool_name: str, arguments: dict) -> str:
        handler = self.handlers.get(tool_name)
        if handler is None:
            return f"Error: {self.name} 没有工具 {tool_name}"
        try:
            return str(handler(**arguments))
        except Exception as exc:
            return f"Error: 外部工具执行失败：{exc}"


def search_project_docs(query: str) -> str:
    """演示外部服务器可以提供项目搜索能力；这里只读根目录文档。"""
    if not query.strip():
        return "Error: query 不能为空"
    results = []
    for path in [WORKDIR / "README.md", WORKDIR / "Agents.md"]:
        text = path.read_text(encoding="utf-8")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if query.lower() in line.lower():
                results.append(f"{path.name}:{line_number}: {line.strip()}")
    return "\n".join(results[:10]) or "(没有找到匹配内容)"


def get_external_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


REGISTRY = [
    MCPServer(
        "project_docs",
        [
            {
                "name": "search",
                "description": "在项目 README 和 Agents.md 中搜索关键词。",
            }
        ],
        {"search": search_project_docs},
    ),
    MCPServer(
        "clock",
        [{"name": "now", "description": "返回当前本地时间。"}],
        {"now": get_external_time},
    ),
]


def list_mcp_tools() -> str:
    """发现阶段：只返回工具清单，不执行任何工具。"""
    manifest = [tool for server in REGISTRY for tool in server.manifest()]
    return json.dumps(manifest, ensure_ascii=False, indent=2)


def call_mcp_tool(server: str, tool: str, arguments: dict | None = None) -> str:
    """调用阶段：先按 server 找到命名空间，再按 tool 分发。"""
    for registered in REGISTRY:
        if registered.name == server:
            return registered.call(tool, arguments or {})
    return f"Error: 未发现 MCP Server：{server}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_mcp_tools",
            "description": "发现已经连接的 MCP Server 和它们提供的工具。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "call_mcp_tool",
            "description": "调用已发现的 MCP 工具；必须提供 server、tool 和 arguments。",
            "parameters": {
                "type": "object",
                "properties": {
                    "server": {"type": "string"},
                    "tool": {"type": "string"},
                    "arguments": {"type": "object"},
                },
                "required": ["server", "tool"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "list_mcp_tools": list_mcp_tools,
    "call_mcp_tool": call_mcp_tool,
}


def agent_loop(user_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个简洁的中文助手。需要外部能力时，先用 list_mcp_tools 发现工具，"
                "再用 call_mcp_tool 调用准确的 server 和 tool。"
                "MCP 工具和本地工具一样需要经过程序注册与参数校验。"
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
            name = tool_call.function.name
            arguments = json.loads(tool_call.function.arguments or "{}")
            handler = TOOL_HANDLERS.get(name)
            try:
                result = handler(**arguments) if handler else f"未知工具：{name}"
            except Exception as exc:
                result = f"Error: {exc}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                }
            )
    return "达到最大轮数，循环停止；请检查 MCP 工具发现和调用过程。"


if __name__ == "__main__":
    query = input("请输入任务（例如：搜索项目中关于 assets 的说明）：\n> ")
    print(agent_loop(query))
