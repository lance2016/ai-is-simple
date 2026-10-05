#!/usr/bin/env python3
"""第 12 章：保存简单的 Cron 任务，到点后把 prompt 放回 Agent Loop。"""

from __future__ import annotations

import json
import os
import secrets
import threading
from datetime import datetime
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
SCHEDULE_FILE = WORKDIR / ".scheduled_tasks.json"
MAX_TURNS = 8


def parse_field(expression: str, minimum: int, maximum: int) -> set[int]:
    """支持 *、*/N、单值、范围和逗号组合，足够解释 Cron 的核心。"""
    values: set[int] = set()
    for item in expression.split(","):
        item = item.strip()
        if item == "*":
            values.update(range(minimum, maximum + 1))
        elif item.startswith("*/"):
            step = int(item[2:])
            if step <= 0:
                raise ValueError("Cron 步长必须大于 0")
            values.update(range(minimum, maximum + 1, step))
        elif "-" in item:
            start_text, end_text = item.split("-", 1)
            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError("Cron 范围必须从小到大")
            values.update(range(start, end + 1))
        else:
            values.add(int(item))

    if not values or not values.issubset(set(range(minimum, maximum + 1))):
        raise ValueError(f"Cron 数值必须在 {minimum}～{maximum} 之间")
    return values


def cron_matches(expression: str, moment: datetime) -> bool:
    fields = expression.split()
    if len(fields) != 5:
        raise ValueError("Cron 必须有 5 段：分 时 日 月 周")
    minute, hour, day, month, weekday = fields
    # 常见 Cron 把星期日记作 0 或 7；datetime.weekday() 从周一开始。
    cron_weekday = (moment.weekday() + 1) % 7
    weekday_values = parse_field(weekday, 0, 7)
    if 7 in weekday_values:
        weekday_values.add(0)

    day_of_month_matches = moment.day in parse_field(day, 1, 31)
    day_of_week_matches = cron_weekday in weekday_values
    # crontab(5) 的常见规则：日和星期都写成具体范围时，两者命中其一即可。
    if "*" in day or "*" in weekday:
        day_matches = day_of_month_matches and day_of_week_matches
    else:
        day_matches = day_of_month_matches or day_of_week_matches

    return (
        moment.minute in parse_field(minute, 0, 59)
        and moment.hour in parse_field(hour, 0, 23)
        and moment.month in parse_field(month, 1, 12)
        and day_matches
    )


class CronStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.Lock()
        self.jobs = self._load()

    def _load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            jobs = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(jobs, list):
                raise ValueError("任务文件顶层必须是列表")
            required = {
                "id", "cron", "prompt", "recurring", "enabled",
                "pending_delivery", "last_fired",
            }
            for job in jobs:
                if not isinstance(job, dict) or not required.issubset(job):
                    raise ValueError("任务记录缺少必要字段")
                if (
                    not isinstance(job["id"], str)
                    or not isinstance(job["cron"], str)
                    or not isinstance(job["prompt"], str)
                    or not isinstance(job["recurring"], bool)
                    or not isinstance(job["enabled"], bool)
                    or not isinstance(job["pending_delivery"], bool)
                    or (job["last_fired"] is not None and not isinstance(job["last_fired"], str))
                ):
                    raise ValueError("任务记录字段类型不正确")
                cron_matches(job["cron"], datetime.now())
            return jobs
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ) as exc:
            raise RuntimeError(f"无法读取定时任务文件：{exc}") from exc

    def _save(self) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self.jobs, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def schedule(self, cron: str, prompt: str, recurring: bool = True) -> str:
        if not isinstance(cron, str):
            raise ValueError("cron 必须是字符串")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt 必须是非空字符串")
        if len(prompt) > 2000:
            raise ValueError("prompt 最多 2000 个字符")
        if not isinstance(recurring, bool):
            raise ValueError("recurring 必须是布尔值")
        cron_matches(cron, datetime.now())
        with self.lock:
            job = {
                "id": f"cron_{secrets.token_hex(4)}",
                "cron": cron,
                "prompt": prompt,
                "recurring": recurring,
                "enabled": True,
                "pending_delivery": False,
                "last_fired": None,
            }
            self.jobs.append(job)
            try:
                self._save()
            except OSError:
                self.jobs.pop()
                raise
        return f"已创建 {job['id']}：{cron} -> {prompt}"

    def list_jobs(self) -> str:
        with self.lock:
            if not self.jobs:
                return "(还没有定时任务)"
            return "\n".join(
                f"{job['id']} | {job['cron']} | "
                f"{'启用' if job['enabled'] else '停用'} | {job['prompt']}"
                for job in self.jobs
            )

    def cancel(self, job_id: str) -> str:
        if not isinstance(job_id, str):
            return "Error: job_id 必须是字符串"
        with self.lock:
            for job in self.jobs:
                if job["id"] == job_id:
                    previous = job.copy()
                    job["enabled"] = False
                    job["pending_delivery"] = False
                    try:
                        self._save()
                    except OSError:
                        job.update(previous)
                        raise
                    return f"已停用 {job_id}"
        return f"找不到定时任务：{job_id}"

    def poll_due(self, moment: datetime) -> list[dict]:
        marker = moment.strftime("%Y-%m-%d %H:%M")
        fired = []
        with self.lock:
            previous = [job.copy() for job in self.jobs]
            changed = False
            for job in self.jobs:
                if not job["enabled"] or job["pending_delivery"]:
                    continue
                if job["last_fired"] == marker:
                    continue
                if cron_matches(job["cron"], moment):
                    job["last_fired"] = marker
                    job["pending_delivery"] = True
                    if not job["recurring"]:
                        job["enabled"] = False
                    fired.append(job.copy())
                    changed = True
            if changed:
                try:
                    self._save()
                except OSError:
                    self.jobs = previous
                    raise
        return fired

    def pending_jobs(self) -> list[dict]:
        """读取待交付任务但不确认；Agent 完成后再调用 acknowledge。"""
        with self.lock:
            return [job.copy() for job in self.jobs if job["pending_delivery"]]

    def acknowledge(self, job_ids: list[str]) -> None:
        """Agent 正常结束后确认投递，失败时保留标记以便之后重试。"""
        pending_ids = set(job_ids)
        if not pending_ids:
            return
        with self.lock:
            previous = [job.copy() for job in self.jobs]
            changed = False
            for job in self.jobs:
                if job["id"] in pending_ids and job["pending_delivery"]:
                    job["pending_delivery"] = False
                    changed = True
            if changed:
                try:
                    self._save()
                except OSError:
                    self.jobs = previous
                    raise


SCHEDULER = CronStore(SCHEDULE_FILE)


def schedule_cron(cron: str, prompt: str, recurring: bool = True) -> str:
    try:
        return SCHEDULER.schedule(cron, prompt, recurring)
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        return f"Error: {exc}"


def list_crons() -> str:
    return SCHEDULER.list_jobs()


def cancel_cron(job_id: str) -> str:
    return SCHEDULER.cancel(job_id)


def poll_cron(now: str = "") -> str:
    try:
        moment = (
            datetime.strptime(now, "%Y-%m-%d %H:%M")
            if now
            else datetime.now()
        )
        fired = SCHEDULER.poll_due(moment)
        return "\n".join(
            f"已到期：{job['id']} -> {job['prompt']}" for job in fired
        ) or "(当前没有到期任务)"
    except (OSError, TypeError, ValueError, RuntimeError) as exc:
        return f"Error: {exc}"


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "schedule_cron",
            "description": "创建一个 5 段 Cron 定时任务，例如 */5 * * * *。",
            "parameters": {
                "type": "object",
                "properties": {
                    "cron": {"type": "string", "maxLength": 100},
                    "prompt": {"type": "string", "maxLength": 2000},
                    "recurring": {"type": "boolean"},
                },
                "required": ["cron", "prompt"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_crons",
            "description": "列出已经保存的定时任务。",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_cron",
            "description": "停用一个定时任务。",
            "parameters": {
                "type": "object",
                "properties": {"job_id": {"type": "string"}},
                "required": ["job_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "poll_cron",
            "description": "检查当前时间或指定时间是否有到期任务。",
            "parameters": {
                "type": "object",
                "properties": {
                    "now": {
                        "type": "string",
                        "description": "可选，格式 YYYY-MM-DD HH:MM",
                        "maxLength": 16,
                    }
                },
                "additionalProperties": False,
            },
        },
    },
]

TOOL_HANDLERS = {
    "schedule_cron": schedule_cron,
    "list_crons": list_crons,
    "cancel_cron": cancel_cron,
    "poll_cron": poll_cron,
}


def agent_loop(user_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个简洁的中文助手。需要未来自动执行时使用 schedule_cron。"
                "定时任务只是把 prompt 放进队列，进程必须保持运行，"
                "此教学 CLI 只会在用户下一次输入时处理到期任务；"
                "不要把 Cron 和后台执行命令混为一谈。"
            ),
        },
        {"role": "user", "content": user_text},
    ]

    scheduled = SCHEDULER.pending_jobs()
    scheduled_ids = [job["id"] for job in scheduled]
    for job in scheduled:
        messages.append(
            {
                "role": "user",
                "content": f"[Scheduled {job['id']}] {job['prompt']}",
            }
        )

    for _ in range(MAX_TURNS):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
        )
        choice = response.choices[0]
        message = choice.message
        messages.append(message.model_dump(exclude_none=True))

        if not message.tool_calls:
            if choice.finish_reason != "stop":
                return f"模型未正常结束（{choice.finish_reason}）；定时任务仍保留待处理状态。"
            SCHEDULER.acknowledge(scheduled_ids)
            return message.content or ""

        if choice.finish_reason != "tool_calls":
            return f"工具调用未正常结束（{choice.finish_reason}）；定时任务仍保留待处理状态。"

        for tool_call in message.tool_calls:
            name = tool_call.function.name
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError("工具参数必须是 JSON 对象")
                handler = TOOL_HANDLERS.get(name)
                result = handler(**arguments) if handler else f"Error: 未知工具 {name}"
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
    return "达到最大轮数，循环停止；请检查定时任务状态。"


def scheduler_loop(stop_event: threading.Event) -> None:
    while not stop_event.wait(1):
        try:
            SCHEDULER.poll_due(datetime.now())
        except Exception as exc:
            print(f"[scheduler] {exc}")


if __name__ == "__main__":
    stop = threading.Event()
    thread = threading.Thread(target=scheduler_loop, args=(stop,), daemon=True)
    thread.start()
    try:
        while True:
            try:
                query = input("请输入任务（输入 exit 退出）：\n> ")
            except EOFError:
                break
            if query.strip().lower() in {"exit", "quit"}:
                break
            if query.strip():
                print(agent_loop(query))
    finally:
        stop.set()
