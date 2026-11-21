#!/usr/bin/env python3
"""第 13 章：每个队友用自己的 messages 调用模型，靠任务板和收件箱协作。"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
API_KEY = os.getenv("DEEPSEEK_API_KEY")
if not API_KEY:
    raise SystemExit("请先在 .env 中填写 DEEPSEEK_API_KEY。")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
MAX_TURNS = 8
MAX_TEAMMATES = 4
# Each task costs one teammate model call, so this also caps the team's spend.
MAX_TEAM_TASKS = 8
TEAMMATE_CALL_TIMEOUT = 30.0
# Longer than the teammate call timeout, so a task in progress normally settles within one wait.
COLLECT_TIMEOUT = 60.0


class TaskBoard:
    """共享任务板：发现和认领分开，但认领本身必须加锁。"""

    def __init__(self):
        self.tasks: dict[str, dict] = {}
        self.changed = threading.Condition()

    def create(self, subject: str) -> str:
        subject = subject.strip()
        if not subject:
            raise ValueError("任务标题不能为空")
        task_id = f"team_{secrets.token_hex(4)}"
        with self.changed:
            self.tasks[task_id] = {
                "id": task_id,
                "subject": subject,
                "status": "pending",
                "owner": None,
            }
        return task_id

    def claim_next(self, owner: str) -> dict | None:
        with self.changed:
            for task in self.tasks.values():
                if task["status"] == "pending" and task["owner"] is None:
                    task["status"] = "in_progress"
                    task["owner"] = owner
                    return task.copy()
        return None

    def finish(self, task_id: str, status: str) -> None:
        """Close a claimed task as completed or failed."""
        with self.changed:
            self.tasks[task_id]["status"] = status

    def render(self) -> str:
        with self.changed:
            if not self.tasks:
                return "(还没有团队任务)"
            return "\n".join(
                f"{task['status']} {task['id']} {task['subject']} "
                f"owner={task['owner'] or '-'}"
                for task in self.tasks.values()
            )

    def all_settled(self) -> bool:
        # `failed` counts as settled, or one broken teammate keeps the Lead waiting.
        with self.changed:
            return all(
                task["status"] in ("completed", "failed")
                for task in self.tasks.values()
            )


class MessageBus:
    """把队友结果放进 Lead 收件箱，不共享 messages 数组。"""

    def __init__(self):
        self.messages: list[dict] = []
        self.lock = threading.Lock()

    def send(self, sender: str, content: str, message_type: str) -> None:
        with self.lock:
            self.messages.append(
                {"from": sender, "type": message_type, "content": content}
            )

    def read_for_lead(self) -> str:
        with self.lock:
            messages = list(self.messages)
            self.messages.clear()
        if not messages:
            return "(Lead 收件箱为空)"
        return "\n".join(
            f"[{item['type']}] {item['from']}: {item['content']}"
            for item in messages
        )


def run_teammate(name: str, subject: str) -> tuple[str, str]:
    """Run one task in the teammate's own context; return (status, text)."""
    # Built per task inside the teammate thread. The SDK client is safe to share
    # across threads; a messages list is not, so the Lead's list never comes in here.
    teammate_messages = [
        {
            "role": "system",
            "content": (
                f"你是团队成员 {name}，负责独立完成 Lead 分给你的一项任务。"
                "你没有工具，也看不到 Lead 和其他队友的对话；"
                "只根据任务本身，用不超过三句话给出结果。"
                "信息不足时直接说明缺什么，不要编造。"
            ),
        },
        {"role": "user", "content": subject},
    ]
    try:
        # Short timeout and no SDK retries: a stuck call has to end as `failed`
        # instead of holding the task in in_progress.
        response = client.with_options(
            timeout=TEAMMATE_CALL_TIMEOUT, max_retries=0
        ).chat.completions.create(model=MODEL, messages=teammate_messages)
        choice = response.choices[0]
        if choice.finish_reason != "stop" or not choice.message.content:
            return "failed", f"模型没有正常给出结果（finish_reason={choice.finish_reason}）"
        return "completed", choice.message.content
    except Exception as exc:
        # Only the type goes back to the Lead; raw API errors may echo request details.
        return "failed", f"模型调用出错（{type(exc).__name__}）"


class TeamRuntime:
    def __init__(self):
        self.board = TaskBoard()
        self.bus = MessageBus()
        self.stop_event = threading.Event()
        self.workers: dict[str, threading.Thread] = {}
        # 让 Lead 等待任务完成和消息写入都结束后，再一次性读取结果。
        self.changed = threading.Condition()

    def create_tasks(self, subjects: list[str]) -> str:
        if self.stop_event.is_set():
            return "Error: 团队正在关闭，不能再创建任务"
        if len(self.board.tasks) + len(subjects) > MAX_TEAM_TASKS:
            return f"Error: 任务板最多放 {MAX_TEAM_TASKS} 项任务，每项都要花一次模型调用"
        ids = [self.board.create(subject) for subject in subjects]
        return "已创建团队任务：" + "、".join(ids)

    def spawn(self, names: list[str]) -> str:
        if self.stop_event.is_set():
            return "Error: 团队正在关闭，不能再启动队友"
        started = []
        new_names = [name for name in names if name not in self.workers]
        if len(self.workers) + len(new_names) > MAX_TEAMMATES:
            return f"Error: 一个团队最多启动 {MAX_TEAMMATES} 名队友"
        for name in new_names:
            thread = threading.Thread(
                target=self._worker,
                args=(name,),
                daemon=True,
            )
            self.workers[name] = thread
            thread.start()
            started.append(name)
        return "已启动队友：" + "、".join(started) if started else "(没有新队友)"

    def _worker(self, name: str) -> None:
        while not self.stop_event.is_set():
            task = self.board.claim_next(name)
            if task is None:
                time.sleep(0.1)
                continue
            print(f"[{name}] 认领 {task['id']}：{task['subject']}")
            status, text = run_teammate(name, task["subject"])
            with self.changed:
                self.board.finish(task["id"], status)
                self.bus.send(name, f"{task['id']}《{task['subject']}》：{text}", status)
                self.changed.notify_all()
            print(f"[{name}] {task['id']} -> {status}")

    def collect_messages(self, timeout: float = COLLECT_TIMEOUT) -> str:
        # With no running teammate nothing can change; waiting would only stall the Lead.
        if not self.workers or self.stop_event.is_set():
            return (
                f"{self.bus.read_for_lead()}\n没有运行中的队友；任务板当前状态：\n"
                f"{self.board.render()}"
            )
        with self.changed:
            settled = self.changed.wait_for(self.board.all_settled, timeout=timeout)
            messages = self.bus.read_for_lead()
        if settled:
            return messages
        return f"{messages}\n等待超时，任务板当前状态：\n{self.board.render()}"

    def shutdown(self) -> str:
        self.stop_event.set()
        for thread in self.workers.values():
            thread.join(timeout=2)
        return "团队已请求关闭；当前任务状态：\n" + self.board.render()


TEAM = TeamRuntime()


def create_team_tasks(subjects: list[str]) -> str:
    try:
        subjects = validate_items(subjects, "subjects", MAX_TEAM_TASKS, 200)
        return TEAM.create_tasks(subjects)
    except (TypeError, ValueError) as exc:
        return f"Error: {exc}"


def spawn_teammates(names: list[str]) -> str:
    try:
        names = validate_items(names, "names", MAX_TEAMMATES, 32)
        if len(set(names)) != len(names):
            raise ValueError("names 中不能有重复名字")
        return TEAM.spawn(names)
    except (TypeError, ValueError) as exc:
        return f"Error: {exc}"


def list_team_tasks() -> str:
    return TEAM.board.render()


def collect_team_messages() -> str:
    return TEAM.collect_messages()


def validate_items(values: list[str], field: str, limit: int, max_length: int) -> list[str]:
    if not isinstance(values, list) or not 1 <= len(values) <= limit:
        raise ValueError(f"{field} 必须包含 1～{limit} 项")
    cleaned = []
    for value in values:
        if not isinstance(value, str):
            raise ValueError(f"{field} 中每一项都必须是字符串")
        value = value.strip()
        if not value or len(value) > max_length:
            raise ValueError(f"{field} 中的内容不能为空且不能超过 {max_length} 个字符")
        cleaned.append(value)
    return cleaned


def shutdown_team() -> str:
    return TEAM.shutdown()


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "create_team_tasks",
            "description": "创建共享任务板上的多个独立任务；每项任务会花一次队友模型调用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "subjects": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_TEAM_TASKS,
                        "items": {"type": "string", "minLength": 1, "maxLength": 200},
                    }
                },
                "required": ["subjects"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spawn_teammates",
            "description": "启动队友线程；队友认领任务后用自己的 messages 调用一次模型。",
            "parameters": {
                "type": "object",
                "properties": {
                    "names": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": MAX_TEAMMATES,
                        "items": {"type": "string", "minLength": 1, "maxLength": 32},
                    }
                },
                "required": ["names"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_team_tasks",
            "description": "查看共享任务板。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "collect_team_messages",
            "description": "等队友处理完任务，收取它们发给 Lead 的结果或失败消息。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shutdown_team",
            "description": "请求所有队友平滑关闭。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

TOOL_HANDLERS = {
    "create_team_tasks": create_team_tasks,
    "spawn_teammates": spawn_teammates,
    "list_team_tasks": list_team_tasks,
    "collect_team_messages": collect_team_messages,
    "shutdown_team": shutdown_team,
}


def agent_loop(user_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是 Lead Agent。简单问候、闲聊和无需协作的问题直接回答。"
                "面对彼此独立且值得并行的任务，先创建任务，再启动队友；"
                "收集并汇总结果后请求关闭团队。"
                "队友没有工具，每项任务只调用一次模型，所以任务标题要写成能独立回答的完整问题。"
                "failed 的任务要如实告诉用户；completed 只表示队友交了结果，不代表结果已验证。"
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
            handler = TOOL_HANDLERS.get(name)
            try:
                if handler is None:
                    result = f"Error: 未知工具：{name}"
                else:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    if not isinstance(arguments, dict):
                        raise ValueError("工具参数必须是 JSON 对象")
                    result = handler(**arguments)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                result = f"Error: 工具参数无效：{exc}"
            except Exception as exc:
                result = f"Error: 工具执行失败（{type(exc).__name__}）"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                }
            )
    return "达到最大轮数，循环停止；请检查任务板和队友消息。"


if __name__ == "__main__":
    query = input("请输入团队任务（例如：并行完成三个独立的小调查）：\n> ")
    try:
        print(agent_loop(query))
    finally:
        if TEAM.workers:
            TEAM.shutdown()
