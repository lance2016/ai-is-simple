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
RECENT_TOOL_TURNS = 3


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

    def before_tool(self, name: str, offered_tool_names: set[str]) -> str | None:
        """检查模型本轮实际拿到的能力清单和当前连接状态。"""
        if name not in offered_tool_names:
            return f"权限拒绝：工具 {name} 不在本轮工具清单中。"
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

    def dispatch(self, name: str, arguments: dict, offered_tool_names: set[str]) -> str:
        """检查并执行单个调用；拒绝和执行结果都经过同一个记录点。"""
        blocked = self.before_tool(name, offered_tool_names)
        if blocked:
            result = blocked
        elif not isinstance(arguments, dict):
            result = "Error: 工具参数必须是 JSON 对象。"
        else:
            try:
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
            except Exception as exc:
                # 把失败作为工具结果交还模型，不让实现细节或本机路径泄露到对话。
                result = f"Error: 工具执行失败（{type(exc).__name__}）。"
        self.after_tool(name, str(result))
        return str(result)

    def compact(self, messages: list[dict]) -> list[dict]:
        """保留初始请求和最近完整工具交互，不切断 tool_call 与结果的配对。"""
        if len(messages) <= 2:
            return messages

        # 每个模型工具回合及其全部结果作为一组，避免留下没有对应结果的 tool_call。
        groups: list[list[dict]] = []
        index = 2  # 第 0 条是动态 system prompt，第 1 条是初始用户请求。
        while index < len(messages):
            item = messages[index]
            group = [item]
            index += 1
            if item.get("role") == "assistant" and item.get("tool_calls"):
                expected_ids = {call["id"] for call in item["tool_calls"]}
                received_ids = set()
                while index < len(messages) and messages[index].get("role") == "tool":
                    tool_result = messages[index]
                    group.append(tool_result)
                    received_ids.add(tool_result.get("tool_call_id"))
                    index += 1
                # 不保留不完整的调用组；正常情况下每个调用都会有一个结果。
                if not expected_ids.issubset(received_ids):
                    continue
            groups.append(group)

        kept_groups = groups[-RECENT_TOOL_TURNS:]
        return [messages[0], messages[1], *(item for group in kept_groups for item in group)]


def agent_loop(user_text: str) -> str:
    harness = Harness()
    messages = [
        {"role": "system", "content": harness.system_prompt()},
        {"role": "user", "content": user_text},
    ]
    for _ in range(MAX_TURNS):
        messages[0]["content"] = harness.system_prompt()
        messages = harness.compact(messages)
        turn_tools = harness.tool_schemas()
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=turn_tools,
            tool_choice="auto",
        )
        choice = response.choices[0]
        message = choice.message
        messages.append(message.model_dump(exclude_none=True))

        if choice.finish_reason == "stop" and not message.tool_calls:
            return message.content or ""
        if choice.finish_reason != "tool_calls" or not message.tool_calls:
            return (
                "模型本轮没有正常完成（"
                f"finish_reason={choice.finish_reason}）；Harness 未把它当作任务完成。"
            )

        offered_tool_names = {
            tool["function"]["name"] for tool in turn_tools
        }
        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
            except (json.JSONDecodeError, TypeError):
                result = "Error: 工具参数不是合法 JSON。"
                harness.after_tool(tool_name, result)
            else:
                result = harness.dispatch(tool_name, arguments, offered_tool_names)
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
