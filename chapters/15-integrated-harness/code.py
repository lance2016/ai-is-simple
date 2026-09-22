#!/usr/bin/env python3
"""第 15 章：把工具、权限、记忆、任务和 MCP 接到同一个 Agent Loop。"""

from __future__ import annotations

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


def function_tool(name: str, description: str, properties: dict, required=None) -> dict:
    """统一生成 OpenAI SDK 的工具描述，避免工具定义和分发逻辑脱节。"""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


class Harness:
    """一个教学版运行底座：能力可以增加，但主循环不需要重写。"""

    def __init__(self):
        self.memories: list[str] = []
        self.tasks: list[dict] = []
        self.events: list[str] = []
        self.mcp_servers: set[str] = set()

    def system_prompt(self) -> str:
        connected = ", ".join(sorted(self.mcp_servers)) or "无"
        memory = "；".join(self.memories[-3:]) or "无"
        return (
            "你是一个简洁的中文 Agent。模型只负责决定下一步，Harness 负责执行。\n"
            f"当前已连接的 MCP Server：{connected}\n"
            f"当前记忆：{memory}\n"
            "需要外部能力时，先连接对应能力，再调用已经出现在工具池中的工具。"
        )

    def tool_schemas(self) -> list[dict]:
        tools = [
            function_tool(
                "read_file",
                "读取项目根目录中允许访问的教学文档。",
                {"path": {"type": "string"}},
                ["path"],
            ),
            function_tool(
                "remember",
                "保存一条对后续任务有帮助的短记忆。",
                {"note": {"type": "string"}},
                ["note"],
            ),
            function_tool(
                "create_task",
                "创建一个简单的后续任务。",
                {"subject": {"type": "string"}},
                ["subject"],
            ),
            function_tool(
                "list_tasks",
                "列出当前 Harness 中的任务。",
                {},
            ),
            function_tool(
                "connect_mcp",
                "连接一个已经登记的 MCP Server；连接后下一轮会出现它的工具。",
                {"server": {"type": "string"}},
                ["server"],
            ),
        ]
        if "project_docs" in self.mcp_servers:
            tools.append(
                function_tool(
                    "mcp__project_docs__search",
                    "在项目 README、Agents.md 和 SOURCES.md 中搜索关键词。",
                    {"query": {"type": "string"}},
                    ["query"],
                )
            )
        return tools

    def before_tool(self, name: str, arguments: dict) -> str | None:
        """PreToolUse：先拦截未知能力，再允许具体 handler 执行。"""
        known = {tool["function"]["name"] for tool in self.tool_schemas()}
        if name not in known:
            return f"权限拒绝：工具 {name} 不在当前工具池中。"
        if name.startswith("mcp__") and "project_docs" not in self.mcp_servers:
            return "权限拒绝：MCP Server 尚未连接。"
        return None

    def after_tool(self, name: str, result: str) -> None:
        """PostToolUse：保留一条轻量事件，便于审计和教学观察。"""
        self.events.append(f"{name}: {result[:80]}")

    def read_file(self, path: str) -> str:
        allowed = {"README.md", "Agents.md", "SOURCES.md"}
        relative = Path(path)
        if relative.is_absolute() or relative.as_posix() not in allowed:
            return "Error: 教学示例只允许读取 README.md、Agents.md 或 SOURCES.md。"
        target = (WORKDIR / relative).resolve()
        if not target.is_relative_to(WORKDIR) or not target.is_file():
            return "Error: 文件不存在或越过项目边界。"
        return target.read_text(encoding="utf-8")[:6000]

    def remember(self, note: str) -> str:
        note = note.strip()
        if not note:
            return "Error: note 不能为空。"
        self.memories.append(note[:300])
        return f"已保存记忆 #{len(self.memories)}。"

    def create_task(self, subject: str) -> str:
        subject = subject.strip()
        if not subject:
            return "Error: subject 不能为空。"
        task = {"id": f"task_{len(self.tasks) + 1}", "subject": subject, "status": "pending"}
        self.tasks.append(task)
        return json.dumps(task, ensure_ascii=False)

    def list_tasks(self) -> str:
        return json.dumps(self.tasks, ensure_ascii=False) or "[]"

    def connect_mcp(self, server: str) -> str:
        if server != "project_docs":
            return "Error: 只登记了 project_docs 这个教学 Server。"
        self.mcp_servers.add(server)
        return "已连接 project_docs；下一轮工具池将出现 mcp__project_docs__search。"

    def mcp_search(self, query: str) -> str:
        if not query.strip():
            return "Error: query 不能为空。"
        results = []
        for filename in ("README.md", "Agents.md", "SOURCES.md"):
            path = WORKDIR / filename
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if query.casefold() in line.casefold():
                    results.append(f"{filename}:{number}: {line.strip()}")
        return "\n".join(results[:12]) or "(没有找到匹配内容)"

    def dispatch(self, name: str, arguments: dict) -> str:
        blocked = self.before_tool(name, arguments)
        if blocked:
            return blocked
        if name == "read_file":
            result = self.read_file(**arguments)
        elif name == "remember":
            result = self.remember(**arguments)
        elif name == "create_task":
            result = self.create_task(**arguments)
        elif name == "list_tasks":
            result = self.list_tasks()
        elif name == "connect_mcp":
            result = self.connect_mcp(**arguments)
        elif name == "mcp__project_docs__search":
            result = self.mcp_search(**arguments)
        else:
            result = f"Error: 未实现工具 {name}。"
        self.after_tool(name, result)
        return str(result)

    def compact(self, messages: list[dict]) -> list[dict]:
        """只保留最近几轮，演示 Harness 可以在模型前整理上下文。"""
        if len(messages) <= 14:
            return messages
        return [
            messages[0],
            {"role": "system", "content": "较早的工具细节已压缩；保留其结论继续工作。"},
            *messages[-10:],
        ]


def agent_loop(user_text: str) -> str:
    harness = Harness()
    messages = [
        {"role": "system", "content": harness.system_prompt()},
        {"role": "user", "content": user_text},
    ]
    for _ in range(MAX_TURNS):
        messages[0]["content"] = harness.system_prompt()
        messages = harness.compact(messages)
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=harness.tool_schemas(),
            tool_choice="auto",
        )
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))
        if not message.tool_calls:
            return message.content or ""
        for tool_call in message.tool_calls:
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
                result = harness.dispatch(tool_call.function.name, arguments)
            except Exception as exc:
                result = f"Error: 工具参数或执行失败：{exc}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result,
                }
            )
    return "达到最大轮数，Harness 主动停止；请检查工具调用和上下文。"


if __name__ == "__main__":
    query = input("请输入任务（例如：连接项目文档 MCP，搜索 assets，并记住结果）：\n> ")
    print(agent_loop(query))
