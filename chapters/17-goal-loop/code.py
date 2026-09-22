#!/usr/bin/env python3
"""第 17 章：模型想停不等于目标完成，交给独立判断器做最后检查。"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
GOAL_MODEL = os.getenv("DEEPSEEK_GOAL_MODEL", MODEL)
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not API_KEY:
    raise SystemExit("请先在 .env 中填写 DEEPSEEK_API_KEY。")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
WORKDIR = Path(__file__).resolve().parents[2]
MAX_TURNS = int(os.getenv("MAX_TURNS", "8"))
STOP_HOOK_BLOCK_CAP = int(os.getenv("STOP_HOOK_BLOCK_CAP", "4"))
MAX_GOAL_LENGTH = 4000
CLEAR_ALIASES = {"clear", "stop", "off", "reset", "none", "cancel"}


@dataclass
class GoalState:
    condition: str
    checks: int = 0
    set_at: float = 0.0
    last_reason: str = ""


@dataclass
class Evaluation:
    ok: bool
    reason: str
    impossible: bool = False


class GoalController:
    """Goal 是 Stop hook：只在模型想结束时检查，不替代工具本身做验证。"""

    def __init__(self):
        self.state: GoalState | None = None

    def set(self, condition: str) -> str:
        condition = condition.strip()
        if not condition or len(condition) > MAX_GOAL_LENGTH:
            return "Error: Goal 不能为空，且不能超过 4000 个字符。"
        self.state = GoalState(condition=condition, set_at=time.time())
        return f"已设置 Goal：{condition}"

    def clear(self) -> str:
        self.state = None
        return "已清除当前 Goal。"

    def status(self) -> str:
        if not self.state:
            return "当前没有活跃 Goal。"
        return json.dumps(
            {
                "condition": self.state.condition,
                "checks": self.state.checks,
                "last_reason": self.state.last_reason,
                "active": True,
            },
            ensure_ascii=False,
            indent=2,
        )

    def evaluate(self, messages: list[dict]) -> Evaluation:
        if not self.state:
            return Evaluation(ok=True, reason="没有活跃 Goal。")
        self.state.checks += 1
        if self.state.checks > STOP_HOOK_BLOCK_CAP:
            return Evaluation(ok=False, reason="连续检查次数达到上限，把控制权交还给用户。")
        transcript = render_transcript(messages)
        prompt = (
            "你是一个独立的 Goal 判断器，不执行工具，也不能读取文件。\n"
            "只根据对话中已经出现的具体证据判断，不要因为主模型说‘完成了’就直接放行。\n"
            "请严格只输出 JSON：{\"ok\": true/false, \"reason\": \"简短原因\", \"impossible\": true/false}\n\n"
            f"完成条件：{self.state.condition}\n\n"
            f"对话记录：\n{transcript}"
        )
        response = client.chat.completions.create(
            model=GOAL_MODEL,
            messages=[
                {"role": "system", "content": "你只负责判断目标是否已被对话证据满足。"},
                {"role": "user", "content": prompt},
            ],
        )
        raw = response.choices[0].message.content or ""
        data = parse_json(raw)
        if not isinstance(data, dict) or not isinstance(data.get("ok"), bool):
            return Evaluation(ok=False, reason="判断器返回格式不正确，不能安全放行。")
        reason = str(data.get("reason", "没有提供原因"))[:500]
        self.state.last_reason = reason
        return Evaluation(ok=data["ok"], reason=reason, impossible=bool(data.get("impossible", False)))


def parse_json(raw: str) -> dict | None:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def render_transcript(messages: list[dict], limit: int = 18000) -> str:
    chunks = []
    for message in messages[-14:]:
        content = message.get("content", "")
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        chunks.append(f"[{message.get('role')}] {content}")
    return "\n".join(chunks)[-limit:]


def list_chapters() -> str:
    chapters = sorted(path.name for path in (WORKDIR / "chapters").glob("[0-9][0-9]-*"))
    return json.dumps(chapters, ensure_ascii=False)


def read_project_file(path: str) -> str:
    relative = Path(path)
    valid_chapter_readme = re.fullmatch(r"chapters/[0-9]{2}-[^/]+/README\.md", relative.as_posix())
    if relative.is_absolute() or not (relative.as_posix() in {"README.md", "Agents.md", "SOURCES.md"} or valid_chapter_readme):
        return "Error: 只允许读取项目说明和章节 README。"
    target = (WORKDIR / relative).resolve()
    if not target.is_relative_to(WORKDIR) or not target.is_file():
        return "Error: 文件不存在或越过项目边界。"
    return target.read_text(encoding="utf-8")[:7000]


def check_chapter(chapter: str) -> str:
    if not re.fullmatch(r"[0-9]{2}-[a-z0-9-]+", chapter):
        return "Error: 章节名格式不正确。"
    readme = WORKDIR / "chapters" / chapter / "README.md"
    return json.dumps({"chapter": chapter, "exists": readme.is_file()}, ensure_ascii=False)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_chapters",
            "description": "列出项目中已经存在的章节目录。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_project_file",
            "description": "读取项目说明或章节 README，获取完成目标所需的证据。",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_chapter",
            "description": "检查一个章节 README 是否存在。",
            "parameters": {
                "type": "object",
                "properties": {"chapter": {"type": "string"}},
                "required": ["chapter"],
            },
        },
    },
]


def run_tool(name: str, arguments: dict) -> str:
    handlers = {
        "list_chapters": list_chapters,
        "read_project_file": read_project_file,
        "check_chapter": check_chapter,
    }
    handler = handlers.get(name)
    if not handler:
        return f"Error: 未知工具 {name}"
    try:
        return str(handler(**arguments))
    except Exception as exc:
        return f"Error: 工具执行失败：{exc}"


def parse_user_command(user_text: str, goal: GoalController) -> tuple[str, str | None]:
    if not user_text.startswith("/goal"):
        return user_text, None
    value = user_text[len("/goal"):].strip()
    if not value:
        return goal.status(), "status"
    if value.casefold() in CLEAR_ALIASES:
        return goal.clear(), "command"
    return goal.set(value), "set"


def agent_loop(user_text: str) -> str:
    goal = GoalController()
    first_message, command_type = parse_user_command(user_text, goal)
    if command_type in {"status", "command"}:
        return first_message
    if command_type == "set":
        first_message = f"请完成这个目标：{goal.state.condition}\n请先使用工具获取证据，再在结论中明确写出验证结果。"
    messages = [
        {
            "role": "system",
            "content": "你是一个简洁的中文 Agent。目标存在时，不能只凭感觉宣布完成；"
            "请调用工具取得证据，并在最终回复中明确写出证据。",
        },
        {"role": "user", "content": first_message},
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
        if message.tool_calls:
            for tool_call in message.tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    result = run_tool(tool_call.function.name, arguments)
                except Exception as exc:
                    result = f"Error: 参数解析失败：{exc}"
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
            continue
        answer = message.content or ""
        if not goal.state:
            return answer
        evaluation = goal.evaluate(messages)
        if evaluation.ok:
            return answer + f"\n\n[Goal 已通过] {evaluation.reason}"
        if evaluation.impossible or goal.state.checks >= STOP_HOOK_BLOCK_CAP:
            return answer + f"\n\n[Goal 暂停] {evaluation.reason}"
        messages.append(
            {
                "role": "user",
                "content": f"独立判断器认为还不能结束：{evaluation.reason}\n请继续完成目标并补充证据。",
            }
        )
    return "达到最大轮数，自动继续停止；Goal 保留给用户查看。"


if __name__ == "__main__":
    query = input("请输入任务（例如：/goal 找出第 15-17 章并总结它们的核心主题）：\n> ")
    print(agent_loop(query))
