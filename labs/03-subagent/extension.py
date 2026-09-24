#!/usr/bin/env python3
"""实战篇 03：让子 Agent 帮忙调查项目

只加一个工具 task。它背后是另一个 CodingAgent：
  - 有自己的 messages，中间读了什么、跑了什么，都不进主 Agent 的上下文；
  - 授权回调永远返回 False，所以它只能读，不能改；
  - 没有挂任何扩展，所以它手里没有 task，不能再往下委派；
  - 最后只把一段总结交回来，作为 task 的工具结果。

启动：
  uv run python labs/01-mini-coding-agent/server.py --lab 03
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "01-mini-coding-agent"))

from agent import CodingAgent, Extension, Tool, Workspace  # noqa: E402

# 页面空白时显示的示例任务，点一下就填进输入框。
SAMPLES = (
    "请交给子 Agent 调查：chapters 目录下哪几章的 code.py 用到了 threading 模块？交回章节名列表。",
    "pyproject.toml 里有哪些依赖？",
)

SUBAGENT_RULES = """你是一个子 Agent，只负责完成主 Agent 交给你的一个调查任务。
你只能读：read 和只读的 bash 命令（ls、cat、grep 等）。写文件、改文件、其他命令都会被拒绝，不要尝试。
调查完，用一段简短的总结回答：结论是什么，依据是哪些文件的哪些位置。
主 Agent 只看得到你最后这段话，看不到你中间的过程，所以关键证据要写进总结里。"""


class SubagentRules(Extension):
    name = "subagent-rules"

    def system_prompt(self, workspace: Workspace) -> str:
        return SUBAGENT_RULES


class TaskTool(Tool):
    name = "task"
    description = (
        "把一个范围清楚、需要读很多文件的调查交给子 Agent。"
        "子 Agent 有独立的上下文，只能读不能改，最后只交回一段总结。"
        "读一两个文件就能回答的事，直接用 read 或 bash，不要用它。"
    )
    parameters = {"prompt": {"type": "string", "description": "交给子 Agent 的完整任务说明，要写清楚查什么、交回什么"}}
    required = ("prompt",)

    def run(self, workspace: Workspace, prompt: str) -> str:
        replies: list[str] = []
        tool_calls = 0

        # 子 Agent 的事件不发给网页，只在这里收集：它说的话，和它调用了几次工具。
        def collect(event: dict) -> None:
            nonlocal tool_calls
            if event["type"] == "assistant_message":
                replies.append(event["content"])
            elif event["type"] == "tool_call":
                tool_calls += 1

        child = CodingAgent(workspace, confirm=lambda action: False, emit=collect, extensions=(SubagentRules(),))
        child.run(prompt)
        summary = replies[-1] if replies else "子 Agent 没有给出总结。"
        # 顺手告诉主 Agent 省下了多少：这几次调用的原始结果都没有进主上下文。
        return f"{summary}\n\n（子 Agent 调用了 {tool_calls} 次工具，过程没有放进你的上下文。）"


class SubagentExtension(Extension):
    name = "subagent"
    tools = (TaskTool(),)


def create(workspace: Workspace) -> Extension:
    return SubagentExtension()
