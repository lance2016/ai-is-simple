#!/usr/bin/env python3
"""第 10 章：把任务、依赖和进度保存到 .tasks/*.json。"""

from __future__ import annotations

import json
import os
import re
import secrets
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
TASKS_DIR = WORKDIR / ".tasks"
TASK_ID_PATTERN = re.compile(r"^task_[0-9a-f]{8}$")
MAX_TURNS = 8


class TaskStore:
    """把每个任务保存成一个 JSON 文件。"""

    def _path(self, task_id: str) -> Path:
        if not TASK_ID_PATTERN.fullmatch(task_id):
            raise ValueError(f"无效的任务 ID：{task_id}")
        return TASKS_DIR / f"{task_id}.json"

    def create(self, subject: str, description: str = "") -> dict:
        subject = subject.strip()
        if not subject:
            raise ValueError("任务标题不能为空")
        TASKS_DIR.mkdir(parents=True, exist_ok=True)
        while True:
            task = {
                "id": f"task_{secrets.token_hex(4)}",
                "subject": subject,
                "description": description,
                "status": "pending",
                "owner": None,
                "blockedBy": [],
            }
            path = self._path(task["id"])
            try:
                with path.open("x", encoding="utf-8") as handle:
                    json.dump(task, handle, ensure_ascii=False, indent=2)
                return task
            except FileExistsError:
                continue

    def load(self, task_id: str) -> dict:
        return json.loads(self._path(task_id).read_text(encoding="utf-8"))

    def save(self, task: dict) -> None:
        self._path(task["id"]).write_text(
            json.dumps(task, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list(self) -> list[dict]:
        if not TASKS_DIR.exists():
            return []
        return [self.load(path.stem) for path in sorted(TASKS_DIR.glob("task_*.json"))]

    def dependencies_ready(self, task: dict) -> bool:
        return all(self.load(dep)["status"] == "completed" for dep in task["blockedBy"])

    def depends_on(self, task_id: str, target_id: str, seen: set[str] | None = None) -> bool:
        seen = seen or set()
        if task_id in seen:
            return False
        seen.add(task_id)
        task = self.load(task_id)
        if target_id in task["blockedBy"]:
            return True
        return any(self.depends_on(dep, target_id, seen) for dep in task["blockedBy"])


TASKS = TaskStore()


def create_task(subject: str, description: str = "") -> str:
    task = TASKS.create(subject, description)
    return f"Created {task['id']}: {task['subject']}"


def update_task(task_id: str, add_blocked_by: list[str]) -> str:
    task = TASKS.load(task_id)
    if task["status"] != "pending" or task["owner"] is not None:
        return "只能给未领取的 pending 任务添加依赖"

    for dependency in add_blocked_by:
        if dependency == task_id:
            return "任务不能依赖自己"
        TASKS.load(dependency)
        if TASKS.depends_on(dependency, task_id):
            return "检测到循环依赖，更新被拒绝"

    task["blockedBy"] = list(dict.fromkeys(task["blockedBy"] + add_blocked_by))
    TASKS.save(task)
    return f"Updated {task_id}: blockedBy={task['blockedBy']}"


def list_tasks() -> str:
    tasks = TASKS.list()
    if not tasks:
        return "(还没有任务)"
    markers = {"pending": "[ ]", "in_progress": "[>]", "completed": "[x]"}
    return "\n".join(
        f"{markers.get(task['status'], '[?]')} {task['id']} "
        f"{task['subject']} owner={task['owner'] or '-'} "
        f"blockedBy={','.join(task['blockedBy']) or '-'}"
        for task in tasks
    )


def get_task(task_id: str) -> str:
    return json.dumps(TASKS.load(task_id), ensure_ascii=False, indent=2)


def claim_task(task_id: str, owner: str = "agent") -> str:
    task = TASKS.load(task_id)
    if task["status"] != "pending":
        return f"任务当前状态是 {task['status']}，不能领取"
    if not TASKS.dependencies_ready(task):
        return f"任务仍被阻塞：{task['blockedBy']}"
    task["status"] = "in_progress"
    task["owner"] = owner
    TASKS.save(task)
    return f"已领取 {task_id}：{task['subject']}"


def complete_task(task_id: str, owner: str = "agent") -> str:
    task = TASKS.load(task_id)
    if task["status"] != "in_progress":
        return f"任务当前状态是 {task['status']}，不能完成"
    if task["owner"] != owner:
        return f"任务负责人是 {task['owner']}，不是 {owner}"

    # 先记录完成前的可领取状态，避免每次完成任务都重复报告旧的解锁项。
    ready_before = {
        candidate["id"]
        for candidate in TASKS.list()
        if candidate["status"] == "pending"
        and candidate["blockedBy"]
        and TASKS.dependencies_ready(candidate)
    }
    task["status"] = "completed"
    TASKS.save(task)

    unblocked = [
        candidate["subject"]
        for candidate in TASKS.list()
        if candidate["status"] == "pending"
        and candidate["blockedBy"]
        and candidate["id"] not in ready_before
        and TASKS.dependencies_ready(candidate)
    ]
    result = f"已完成 {task_id}：{task['subject']}"
    if unblocked:
        result += f"\n现在可以开始：{', '.join(unblocked)}"
    return result


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "创建任务并返回运行时生成的任务 ID。",
            "parameters": {
                "type": "object",
                "properties": {
                    "subject": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["subject"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_task",
            "description": "给 pending 任务添加 blockedBy 依赖。",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "add_blocked_by": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["task_id", "add_blocked_by"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "列出所有任务的状态、负责人和依赖。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_task",
            "description": "查看一个任务的完整信息。",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "claim_task",
            "description": "领取一个依赖已完成的 pending 任务。",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_task",
            "description": "完成当前 agent 已领取的任务。",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "create_task": create_task,
    "update_task": update_task,
    "list_tasks": list_tasks,
    "get_task": get_task,
    "claim_task": claim_task,
    "complete_task": complete_task,
}


def agent_loop(user_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个简洁的中文任务助手。创建多个任务时，"
                "先创建所有节点，再使用返回的 task_id 设置依赖。"
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

    return "达到最大轮数，循环停止；请检查任务状态和实际交付物。"


if __name__ == "__main__":
    query = input("请输入一个任务管理请求：\n> ")
    print(agent_loop(query))
