#!/usr/bin/env python3
"""第 11 章：把明确的慢任务放到后台，Agent Loop 继续处理别的事。"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
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


class BackgroundManager:
    """用线程模拟慢任务，并把完成结果放进待收集队列。"""

    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.ready: list[str] = []
        self.lock = threading.Lock()

    def start(self, label: str, seconds: int = 2) -> str:
        if not label.strip():
            raise ValueError("任务名称不能为空")
        if not 1 <= seconds <= 10:
            raise ValueError("示例只允许等待 1～10 秒")

        job_id = f"bg_{uuid.uuid4().hex[:8]}"
        with self.lock:
            self.jobs[job_id] = {
                "id": job_id,
                "label": label,
                "status": "running",
                "result": "",
            }

        worker = threading.Thread(
            target=self._run,
            args=(job_id, label, seconds),
            daemon=True,
        )
        worker.start()
        return f"后台任务已启动：{job_id}（{label}）"

    def _run(self, job_id: str, label: str, seconds: int) -> None:
        time.sleep(seconds)
        result = f"{label} 已完成，耗时约 {seconds} 秒。"
        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return
            job["status"] = "completed"
            job["result"] = result
            self.ready.append(job_id)

    def collect(self) -> str:
        with self.lock:
            ready_ids = list(self.ready)
            self.ready.clear()
            completed = [self.jobs[job_id] for job_id in ready_ids]
            running = [
                job for job in self.jobs.values() if job["status"] == "running"
            ]

        lines = [
            f"[task_notification] {job['id']}: {job['result']}"
            for job in completed
        ]
        if running:
            lines.append(
                "仍在运行：" + "、".join(job["id"] for job in running)
            )
        return "\n".join(lines) or "(没有新的后台结果)"


BACKGROUND = BackgroundManager()


def start_background_job(label: str, seconds: int = 2) -> str:
    return BACKGROUND.start(label, seconds)


def collect_background_jobs() -> str:
    return BACKGROUND.collect()


def list_files(pattern: str = "chapters/**/*.md") -> str:
    if Path(pattern).is_absolute() or ".." in Path(pattern).parts:
        return "Error: pattern 只能在项目目录内使用"
    matches = sorted(
        str(path.relative_to(WORKDIR))
        for path in WORKDIR.glob(pattern)
        if path.is_file()
    )
    return "\n".join(matches[:100]) or "(没有找到文件)"


def read_file(path: str, limit: int = 40) -> str:
    file_path = (WORKDIR / path).resolve()
    if not file_path.is_relative_to(WORKDIR):
        return "Error: 路径不能跳出项目目录"
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        return f"Error: {exc}"
    if len(lines) > limit:
        lines = lines[:limit] + [f"...（还有 {len(lines) - limit} 行）"]
    return "\n".join(lines)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "start_background_job",
            "description": "启动一个模拟慢任务，明确放到后台执行，不阻塞当前 Agent Loop。",
            "parameters": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "任务名称"},
                    "seconds": {"type": "integer", "description": "模拟耗时，1 到 10 秒"},
                },
                "required": ["label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "collect_background_jobs",
            "description": "收集已经完成的后台任务结果。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "列出项目中符合 pattern 的文件。",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "读取项目内的文本文件。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "limit": {"type": "integer"},
                },
                "required": ["path"],
            },
        },
    },
]

TOOL_HANDLERS = {
    "start_background_job": start_background_job,
    "collect_background_jobs": collect_background_jobs,
    "list_files": list_files,
    "read_file": read_file,
}


def agent_loop(user_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "你是一个简洁的中文助手。只有用户明确要求后台执行，"
                "或任务确实是慢任务时，才使用 start_background_job。"
                "后台启动后可以继续处理独立的读取任务，之后用 "
                "collect_background_jobs 收集结果。"
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

    return "达到最大轮数，循环停止；后台任务可能仍需下一轮收集。"


if __name__ == "__main__":
    query = input("请输入任务（例如：后台运行一个 3 秒任务，同时读取 README.md）：\n> ")
    print(agent_loop(query))
