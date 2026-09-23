#!/usr/bin/env python3
"""实战篇 04：把一个真实的 MCP Server 接进 Coding Agent。

启动时做三件事：
  1. 把 Server 当成子进程拉起来，用 stdin / stdout 说 JSON-RPC；
  2. 握手（initialize），再问它有哪些工具（tools/list）；
  3. 每个远程工具包成一个 Tool，名字加上服务名前缀，和本地工具放进同一个工具池。

之后模型调用 notes__read_note，和调用 read 走的是同一条路：
同一个 _execute 入口，同一套授权弹窗。MCP 只负责"工具在哪、怎么调"，不负责"该不该调"。

启动：
  uv run python labs/01-mini-coding-agent/server.py --lab 04
"""

from __future__ import annotations

import atexit
import json
import subprocess
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01-mini-coding-agent"))

from agent import Extension, Tool, ToolError, Workspace  # noqa: E402

# 页面空白时显示的示例任务，点一下就填进输入框。
SAMPLES = (
    "列出我的笔记，读一下 agent-loop",
    "新建一篇叫 test 的笔记，内容写 hello",
)

PROTOCOL_VERSION = "2025-06-18"
HERE = Path(__file__).resolve().parent

# 要连哪些 Server 写死在这里。trust_read_only_hint 表示：是否相信它自己声明的"只读"。
# 自己写的 Server 可以信；来路不明的 Server 应该设成 False，每次调用都问你。
SERVERS = {
    "notes": {"command": [sys.executable, str(HERE / "notes_server.py")], "trust_read_only_hint": True},
}


class McpClient:
    """一个 Server 对应一个客户端。请求一问一答，按 id 对上号。"""

    def __init__(self, name: str, command: list[str]):
        self.name = name
        # stderr 不接管，Server 打的日志直接出现在终端里。
        self.process = subprocess.Popen(
            command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding="utf-8"
        )
        self._next_id = 0
        self._lock = threading.Lock()
        atexit.register(self.close)
        self.request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "mini-coding-agent", "version": "0.1.0"},
        })
        # 握手的最后一步是一条通知，告诉 Server 可以开始干活了。
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def request(self, method: str, params: dict | None = None) -> dict:
        # 同一时刻只让一个请求在路上，读回来的那行一定是它的答复（或者一条可以跳过的通知）。
        with self._lock:
            self._next_id += 1
            request_id = self._next_id
            self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
            while True:
                line = self.process.stdout.readline()
                if not line:
                    raise ToolError(f"MCP Server {self.name} 已经退出。")
                message = json.loads(line)
                if message.get("id") == request_id:
                    break
        if "error" in message:
            raise ToolError(f"MCP Server {self.name} 报错：{message['error'].get('message')}")
        return message["result"]

    def _send(self, message: dict) -> None:
        self.process.stdin.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.process.stdin.flush()

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()


class McpTool(Tool):
    """把一个远程工具包装成本地 Tool。模型分不出它来自哪里，Harness 分得出。"""

    def __init__(self, client: McpClient, spec: dict, trust_read_only_hint: bool):
        self.client = client
        self.remote_name = spec["name"]
        # 函数名里不能有点号，所以用双下划线分隔：notes__read_note。
        self.name = f"{client.name}__{spec['name']}"
        self.description = f"[MCP · {client.name}] {spec.get('description', '')}"
        self.input_schema = spec.get("inputSchema") or {"type": "object", "properties": {}}
        self.read_only = trust_read_only_hint and bool((spec.get("annotations") or {}).get("readOnlyHint"))

    def schema(self) -> dict:
        # 参数结构直接用 Server 给的 JSON Schema，不再自己拼。
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.input_schema},
        }

    def confirm_prompt(self, workspace: Workspace, **kwargs) -> str | None:
        if self.read_only:
            return None
        return f"调用 MCP 工具 {self.name}，参数：{json.dumps(kwargs, ensure_ascii=False)}"

    def run(self, workspace: Workspace, **kwargs) -> str:
        result = self.client.request("tools/call", {"name": self.remote_name, "arguments": kwargs})
        text = "\n".join(item.get("text", "") for item in result.get("content", []) if item.get("type") == "text")
        if result.get("isError"):
            raise ToolError(text or "MCP 工具返回了错误。")
        return text or "（MCP 工具没有返回文字）"


class McpExtension(Extension):
    name = "mcp"

    def __init__(self):
        tools = []
        for server_name, config in SERVERS.items():
            client = McpClient(server_name, config["command"])
            # 工具很多的 Server 会分页返回（nextCursor），这个小例子只有一页，就不处理了。
            for spec in client.request("tools/list")["tools"]:
                tools.append(McpTool(client, spec, config["trust_read_only_hint"]))
        self.tools = tuple(tools)

    def system_prompt(self, workspace: Workspace) -> str:
        names = "、".join(tool.name for tool in self.tools)
        return (
            f"名字形如“服务名__工具名”的工具来自外部 MCP Server：{names}。"
            "它们不操作工作区里的文件，用户问到笔记时用它们。"
        )


def create(workspace: Workspace) -> Extension:
    return McpExtension()
