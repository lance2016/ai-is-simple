#!/usr/bin/env python3
"""实战篇 08：用固定案例给 Agent 的回答和工具选择打分。"""

from __future__ import annotations

from agent import CodingAgent, Extension, Workspace

CASES = (
    {
        "id": "chat",
        "question": "你好，简单说说你能帮我做什么。",
        "expected": {"required_terms": ["代码"], "must_use_read": False},
    },
    {
        "id": "concept",
        "question": "不用访问工作区，用一句话解释 Agent 的工具调用是什么意思。",
        "expected": {"required_terms": ["工具"], "must_use_read": False},
    },
    {
        "id": "read-policy",
        "question": "请先读取 deployment-policy.md，再告诉我最多可以重试几次、等待多久。",
        "expected": {"required_terms": ["2", "30"], "must_use_read": True},
    },
)

SAMPLES = tuple(case["question"] for case in CASES)
DEMO = "demo"
_CASES_BY_PROMPT = {case["question"]: case for case in CASES}


def collect_result(messages: list[dict]) -> dict:
    """从一段已完成的对话中取最终回复和模型实际选择的工具。"""
    for index in range(len(messages) - 1, 0, -1):
        if messages[index].get("role") == "user":
            messages = messages[index:]
            break

    answer = ""
    for message in reversed(messages):
        if message.get("role") == "assistant" and not message.get("tool_calls"):
            answer = str(message.get("content") or "").strip()
            if answer:
                break

    tools_used = [
        call.get("function", {}).get("name", "")
        for message in messages
        for call in message.get("tool_calls") or []
    ]
    return {"answer": answer, "tools_used": tools_used}


def grade_case(output: dict, expected: dict) -> dict[str, bool]:
    """两个可复现的基础评分：答案包含关键事实、工具选择符合预期。"""
    answer = str(output.get("answer", "")).casefold()
    required_terms = expected.get("required_terms", [])
    expected_read = bool(expected.get("must_use_read"))
    tools_used = set(output.get("tools_used", []))
    expected_tools = {"read"} if expected_read else set()
    return {
        "required_facts": all(str(term).casefold() in answer for term in required_terms),
        "tool_selection": tools_used == expected_tools,
    }


class EvaluationExtension(Extension):
    name = "evaluation"

    def __init__(self, case: dict | None = None, *, read_only: bool = False):
        self.case = case
        self.read_only = read_only

    def system_prompt(self, workspace: Workspace) -> str:
        instruction = (
            "本次练习可能会用固定案例评估你的行为。只根据工作区中可核实的信息回答；"
            "用户明确说不用访问工作区时，不要调用工具。"
        )
        if self.read_only:
            instruction += "本次评估只开放 read 工具，不要尝试 write、edit 或 bash。"
        return instruction

    def on_stop(self, agent: CodingAgent) -> str | None:
        case = self.case or _case_for_messages(agent.messages)
        if case is None:
            return None
        result = collect_result(agent.messages)
        scores = grade_case(result, case["expected"])
        passed = all(scores.values())
        agent.emit({
            "type": "note",
            "content": (
                f"案例评估：{'通过' if passed else '有一项未通过'}；"
                f"关键事实 {'✓' if scores['required_facts'] else '✗'}，"
                f"工具选择 {'✓' if scores['tool_selection'] else '✗'}。"
            ),
        })
        return None


def _case_for_messages(messages: list[dict]) -> dict | None:
    for message in reversed(messages):
        if message.get("role") == "user":
            return _CASES_BY_PROMPT.get(str(message.get("content") or ""))
    return None


def create(workspace: Workspace) -> Extension:
    return EvaluationExtension()
