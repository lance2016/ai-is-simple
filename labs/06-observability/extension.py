#!/usr/bin/env python3
"""实战篇 06：给 Agent 加运行记录，方便排查问题"""

from __future__ import annotations

import sys
from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parents[1] / "01-mini-coding-agent"
sys.path.insert(0, str(AGENT_DIR))

from agent import Extension, Workspace  # noqa: E402
from observability import enable_phoenix  # noqa: E402

DEMO = "demo"
SAMPLES = (
    "只读 calculator.py，解释 calculate_total 的计算过程，不要修改文件。",
    "calculator.py 里的 calculate_total 返回结果不对，请定位并修正；改完后运行 python3 -m py_compile calculator.py 验证。",
    '运行 python3 -c "raise RuntimeError(\'phoenix demo\')"，观察执行失败后再解释错误。',
)


class ObservabilityExtension(Extension):
    name = "observability"


def create(workspace: Workspace) -> Extension:
    # 先注册 OpenAI SDK 的自动追踪，再由 AgentSession 把现有事件补成父子 span。
    enable_phoenix()
    return ObservabilityExtension()
