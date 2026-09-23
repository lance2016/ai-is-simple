#!/usr/bin/env python3
"""一个最小的 MCP Server：管理 notes/ 目录下的 Markdown 笔记。

MCP 的 stdio 传输很朴素：客户端把 JSON-RPC 请求一行一行写进本进程的 stdin，
本进程把响应一行一行写到 stdout。stdout 只能放协议消息，日志要写到 stderr。

只实现三个方法就够用了：
  initialize   握手，告诉客户端协议版本和自己能提供什么
  tools/list   列出工具：名字、说明、参数的 JSON Schema
  tools/call   调用一个工具，结果装在 content 列表里
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

PROTOCOL_VERSION = "2025-06-18"
NOTES_DIR = Path(__file__).resolve().parent / "notes"
# 笔记名只允许字母、数字、中文、下划线和横线：Server 也要守自己的边界，不能被传个 ../ 就绕出去。
NOTE_NAME = re.compile(r"^[\w-]{1,64}$")

TOOLS = [
    {
        "name": "list_notes",
        "description": "列出所有笔记的名字。",
        "inputSchema": {"type": "object", "properties": {}},
        # annotations 是 Server 自己声明的提示，客户端信不信由它自己决定。
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "read_note",
        "description": "读取一篇笔记的全文。",
        "inputSchema": {
            "type": "object",
            "properties": {"name": {"type": "string", "description": "笔记名，不带 .md"}},
            "required": ["name"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "add_note",
        "description": "新建一篇笔记。同名笔记已存在时会失败，不会覆盖。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "笔记名，不带 .md"},
                "content": {"type": "string", "description": "笔记内容，Markdown 格式"},
            },
            "required": ["name", "content"],
        },
        "annotations": {"readOnlyHint": False},
    },
]


def note_path(name: str) -> Path:
    if not NOTE_NAME.match(name):
        raise ValueError("笔记名只能包含字母、数字、中文、下划线和横线。")
    return NOTES_DIR / f"{name}.md"


def call_tool(name: str, arguments: dict) -> str:
    if name == "list_notes":
        names = sorted(path.stem for path in NOTES_DIR.glob("*.md"))
        return "\n".join(names) or "（还没有笔记）"
    if name == "read_note":
        path = note_path(arguments["name"])
        if not path.is_file():
            raise ValueError(f"没有叫 {arguments['name']} 的笔记。")
        return path.read_text(encoding="utf-8")
    if name == "add_note":
        path = note_path(arguments["name"])
        if path.exists():
            raise ValueError(f"笔记 {arguments['name']} 已经存在。")
        path.write_text(arguments["content"], encoding="utf-8")
        return f"已新建笔记 {arguments['name']}。"
    raise ValueError(f"没有名为 {name} 的工具。")


def handle(request: dict) -> dict | None:
    method = request.get("method")
    # 没有 id 的是通知（比如 notifications/initialized），按协议不能回复。
    if "id" not in request:
        return None
    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "notes", "version": "0.1.0"},
        }
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = request.get("params") or {}
        try:
            text, is_error = call_tool(params.get("name", ""), params.get("arguments") or {}), False
        except (ValueError, KeyError) as exc:
            # 工具自己的错误放在结果里（isError），让模型看得到；协议层的错误才用 error。
            text, is_error = f"{type(exc).__name__}: {exc}", True
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    else:
        return {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32601, "message": f"不支持的方法：{method}"}}
    return {"jsonrpc": "2.0", "id": request["id"], "result": result}


def main() -> None:
    NOTES_DIR.mkdir(exist_ok=True)
    for line in sys.stdin:
        if not line.strip():
            continue
        response = handle(json.loads(line))
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
