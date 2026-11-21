#!/usr/bin/env python3
"""第 15 章：把循环、工具、权限和一项可选能力装进同一个 Harness。"""

from __future__ import annotations

import json
import os
from enum import Enum
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
ROOT_READABLE_FILES = {"README.md", "Agents.md", "SOURCES.md", "STYLE_GUIDE.md"}
MCP_SERVERS = {"project_docs": "在项目根目录的教学文档里搜索关键词"}


class Decision(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


def function_tool(name: str, description: str, properties: dict) -> dict:
    """统一生成工具描述；本例所有参数都是必填的。"""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": list(properties),
                "additionalProperties": False,
            },
        },
    }


def safe_path(relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise ValueError("path 必须是非空字符串")
    path = (WORKDIR / relative_path).resolve()
    if not path.is_relative_to(WORKDIR):
        raise ValueError("路径不能跳出项目目录")
    return path


def safe_read_path(relative_path: str) -> Path:
    """和第 03 章相同的读取范围：根目录教学文档和 chapters/，敏感路径一律拒绝。"""
    path = safe_path(relative_path)
    if any(part.startswith((".env", ".git")) for part in path.parts):
        raise ValueError("不能读取 .env 或 .git 等敏感路径")
    is_root_doc = path.parent == WORKDIR and path.name in ROOT_READABLE_FILES
    if not (is_root_doc or (WORKDIR / "chapters") in path.parents):
        raise ValueError("示例只允许读取根目录教学文档或 chapters/ 下的文件")
    return path


def safe_write_path(relative_path: str) -> Path:
    path = safe_path(relative_path)
    if (WORKDIR / "notes") not in path.parents:
        raise ValueError("写入范围仅限 notes/ 目录")
    return path


def confirm_in_terminal(name: str, arguments: dict) -> bool:
    """把确认绑定到这一次显示的路径和内容。"""
    try:
        choice = input(
            f"准备执行 {name}，写入 {arguments['path']}，完整内容如下：\n"
            f"{arguments['content']}\n允许吗？[y/N] "
        ).strip().lower()
    except EOFError:
        # Nobody can confirm in a non-interactive run, so refuse.
        return False
    return choice in {"y", "yes"}


class Harness:
    """包在模型外面的那层程序：准备上下文和工具、检查并执行调用、保存状态。

    一个实例服务多次用户请求，所以需要跨请求保留的东西放在这里，不放在 messages 里。
    """

    def __init__(self, confirm=confirm_in_terminal):
        self.confirm = confirm
        self.mcp_servers: set[str] = set()
        self.notes_written: list[str] = []

    # 职责一：准备上下文。每一轮都按当前状态重新生成，状态变了模型马上知道。
    def system_prompt(self) -> str:
        connected = "、".join(sorted(self.mcp_servers)) or "无"
        notes = "、".join(self.notes_written) or "无"
        return (
            "你是一个简洁的中文 Agent。你只负责决定下一步，执行和权限判断由程序完成。\n"
            f"已连接的 MCP Server：{connected}\n"
            f"本次运行已写入的笔记：{notes}\n"
            "需要外部能力时先连接；新工具要到下一轮才会出现在工具清单里。"
        )

    # 职责二：准备工具清单。模型这一轮能选什么，由这里决定。
    def tool_schemas(self) -> list[dict]:
        tools = [
            function_tool(
                "read_file",
                "读取项目根目录的教学文档或 chapters/ 下的文件。",
                {"path": {"type": "string"}},
            ),
            function_tool(
                "write_note",
                "向 notes/ 目录写入一条笔记。执行前需要用户确认。",
                {"path": {"type": "string"}, "content": {"type": "string"}},
            ),
            function_tool(
                "delete_file",
                "删除项目内的文件。教学示例中禁止使用。",
                {"path": {"type": "string"}},
            ),
            function_tool(
                "connect_mcp",
                "连接一个已登记的 MCP Server，连接后下一轮会多出它的工具。"
                f"可选：{json.dumps(MCP_SERVERS, ensure_ascii=False)}",
                {"server": {"type": "string", "enum": sorted(MCP_SERVERS)}},
            ),
        ]
        # The optional capability: it only changes what this method returns.
        if "project_docs" in self.mcp_servers:
            tools.append(
                function_tool(
                    "mcp__project_docs__search",
                    "在项目 README.md、Agents.md 和 SOURCES.md 中搜索关键词。",
                    {"query": {"type": "string"}},
                )
            )
        return tools

    # 职责三：检查调用。只做判断，不在这里等待用户输入。
    def check_permission(
        self, name: str, arguments: dict, offered_tool_names: set[str]
    ) -> tuple[Decision, str]:
        # A tool connected in this very batch was not in the list the model saw; refuse it.
        if name not in offered_tool_names:
            return Decision.DENY, f"工具 {name} 不在本轮工具清单中"
        if name == "delete_file":
            return Decision.DENY, "示例程序不允许删除文件"
        try:
            if name == "read_file":
                safe_read_path(arguments.get("path"))
            elif name == "write_note":
                safe_write_path(arguments.get("path"))
                if not isinstance(arguments.get("content"), str):
                    raise ValueError("content 必须是字符串")
                return Decision.ASK, "写入文件会改变工作区"
        except ValueError as exc:
            return Decision.DENY, str(exc)
        return Decision.ALLOW, ""

    # 职责四：执行，并把成功、拒绝和失败都变成一段交回模型的文字。
    def dispatch(self, name: str, arguments: dict, offered_tool_names: set[str]) -> str:
        decision, reason = self.check_permission(name, arguments, offered_tool_names)
        if decision is Decision.DENY:
            return f"Permission denied: {reason}"
        if decision is Decision.ASK and not self.confirm(name, arguments):
            return "Permission denied: 用户没有确认"
        handlers = {
            "read_file": self.read_file,
            "write_note": self.write_note,
            "connect_mcp": self.connect_mcp,
            "mcp__project_docs__search": self.mcp_search,
        }
        try:
            return str(handlers[name](**arguments))
        except Exception as exc:
            # Hand the failure back as a tool result without leaking local paths.
            return f"Error: 工具执行失败（{type(exc).__name__}）。"

    def read_file(self, path: str) -> str:
        return safe_read_path(path).read_text(encoding="utf-8")[:6000]

    def write_note(self, path: str, content: str) -> str:
        target = safe_write_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        # 职责五：保存状态。下一次用户请求的 system prompt 里会带上它。
        self.notes_written.append(path)
        return f"已写入 {path}"

    def connect_mcp(self, server: str) -> str:
        if server not in MCP_SERVERS:
            return f"Error: 没有登记 {server}，可选：{'、'.join(sorted(MCP_SERVERS))}。"
        self.mcp_servers.add(server)
        return f"已连接 {server}；下一轮工具清单将出现 mcp__{server}__search。"

    def mcp_search(self, query: str) -> str:
        """进程内模拟的 Server：没有真实 MCP 协议，真实实现见实战篇 Lab 04。"""
        if not isinstance(query, str) or not query.strip():
            return "Error: query 不能为空。"
        results = []
        for filename in ("README.md", "Agents.md", "SOURCES.md"):
            lines = (WORKDIR / filename).read_text(encoding="utf-8").splitlines()
            for number, line in enumerate(lines, 1):
                if query.casefold() in line.casefold():
                    results.append(f"{filename}:{number}: {line.strip()[:200]}")
        return "\n".join(results[:12]) or "(没有找到匹配内容)"


def agent_loop(harness: Harness, user_text: str) -> str:
    """和第 01 章是同一个循环；多出来的事情都交给 harness。"""
    messages = [
        {"role": "system", "content": harness.system_prompt()},
        {"role": "user", "content": user_text},
    ]
    for _ in range(MAX_TURNS):
        messages[0]["content"] = harness.system_prompt()
        turn_tools = harness.tool_schemas()
        offered_tool_names = {tool["function"]["name"] for tool in turn_tools}
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=turn_tools,
            tool_choice="auto",
        )
        choice = response.choices[0]
        message = choice.message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            if choice.finish_reason != "stop":
                return f"模型未正常结束：{choice.finish_reason}"
            return message.content or ""
        if choice.finish_reason != "tool_calls":
            return f"工具调用未正常结束：{choice.finish_reason}"

        for tool_call in message.tool_calls:
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
            except (json.JSONDecodeError, TypeError):
                arguments = None
            if isinstance(arguments, dict):
                result = harness.dispatch(tool_call.function.name, arguments, offered_tool_names)
            else:
                result = "Error: 工具参数必须是合法的 JSON 对象。"
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
    return "达到最大轮数，循环停止；请检查任务是否真的完成。"


if __name__ == "__main__":
    # One Harness for the whole run: connections and notes survive across requests,
    # while each request starts with a fresh messages list.
    harness = Harness()
    while True:
        try:
            query = input("请输入任务（例如：连接项目文档 MCP，搜索 assets；直接回车退出）：\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not query:
            break
        print(agent_loop(harness, query))
