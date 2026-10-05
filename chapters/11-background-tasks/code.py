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
    """用线程模拟慢任务；状态和待收集通知都只保存在当前进程中。"""

    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.ready: list[str] = []
        self.lock = threading.Lock()

    def start(self, label: str, seconds: int = 2) -> str:
        if not isinstance(label, str) or not label.strip():
            raise ValueError("任务名称不能为空")
        if len(label) > 120:
            raise ValueError("任务名称不能超过 120 个字符")
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, int)
            or not 1 <= seconds <= 10
        ):
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
        try:
            worker.start()
        except Exception as exc:
            with self.lock:
                job = self.jobs[job_id]
                job["status"] = "failed"
                job["error"] = type(exc).__name__
                self.ready.append(job_id)
            return f"后台任务启动失败：{job_id}（{type(exc).__name__}）"
        return f"后台任务已启动：{job_id}（{label}）"

    def _run(self, job_id: str, label: str, seconds: int) -> None:
        try:
            time.sleep(seconds)
            result = f"{label} 已完成，耗时约 {seconds} 秒。"
            status = "completed"
            error = ""
        except Exception as exc:
            result = ""
            status = "failed"
            # 示例只把错误类型交给模型，避免把线程内部细节原样暴露出去。
            error = type(exc).__name__

        with self.lock:
            job = self.jobs.get(job_id)
            if job is None:
                return
            job["status"] = status
            job["result"] = result
            job["error"] = error
            self.ready.append(job_id)

    def collect(self) -> str:
        with self.lock:
            ready_ids = list(self.ready)
            self.ready.clear()
            completed = [dict(self.jobs[job_id]) for job_id in ready_ids]
            running = [
                dict(job)
                for job in self.jobs.values()
                if job["status"] == "running"
            ]

        lines = []
        for job in completed:
            if job["status"] == "completed":
                lines.append(
                    f"[task_notification] {job['id']} status=completed: "
                    f"{job['result']}"
                )
            else:
                lines.append(
                    f"[task_notification] {job['id']} status=failed "
                    f"error={job['error']}"
                )
        if running:
            lines.append(
                "仍在运行："
                + "、".join(f"{job['id']}（{job['label']}）" for job in running)
            )
        return "\n".join(lines) or "(没有新的后台结果)"


BACKGROUND = BackgroundManager()


def start_background_job(label: str, seconds: int = 2) -> str:
    return BACKGROUND.start(label, seconds)


def collect_background_jobs() -> str:
    """取出新完成任务的一次性通知，并附上仍在运行的任务。"""
    return BACKGROUND.collect()


def list_files(pattern: str = "chapters/**/*.md") -> str:
    if not isinstance(pattern, str):
        return "Error: pattern 必须是字符串"
    pattern_path = Path(pattern)
    if (
        pattern_path.is_absolute()
        or ".." in pattern_path.parts
        or any(part.startswith(".") for part in pattern_path.parts)
    ):
        return "Error: pattern 只能在项目目录内使用"
    matches = []
    for path in WORKDIR.glob(pattern):
        try:
            resolved = path.resolve()
            relative = resolved.relative_to(WORKDIR)
        except (OSError, ValueError):
            continue
        if path.is_file() and not any(
            part.startswith(".") for part in relative.parts
        ):
            matches.append(str(relative))
    matches.sort()
    return "\n".join(matches[:100]) or "(没有找到文件)"


def read_file(path: str, limit: int = 40) -> str:
    if not isinstance(path, str):
        return "Error: path 必须是字符串"
    relative_path = Path(path)
    if (
        relative_path.is_absolute()
        or ".." in relative_path.parts
        or any(part.startswith(".") for part in relative_path.parts)
    ):
        return "Error: 只能读取项目内的非隐藏路径"
    if (
        isinstance(limit, bool)
        or not isinstance(limit, int)
        or not 1 <= limit <= 200
    ):
        return "Error: limit 必须是 1 到 200 之间的整数"

    file_path = (WORKDIR / relative_path).resolve()
    try:
        file_path.relative_to(WORKDIR)
    except ValueError:
        return "Error: 路径不能跳出项目目录"
    if any(part.startswith(".") for part in file_path.relative_to(WORKDIR).parts):
        return "Error: 只能读取项目内的非隐藏路径"
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except Exception as exc:
        return f"Error: 读取失败（{type(exc).__name__}）"
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
                    "label": {
                        "type": "string",
                        "description": "任务名称",
                        "maxLength": 120,
                    },
                    "seconds": {
                        "type": "integer",
                        "description": "模拟耗时，1 到 10 秒",
                        "minimum": 1,
                        "maximum": 10,
                    },
                },
                "required": ["label"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "collect_background_jobs",
            "description": "收集新完成任务的一次性通知，并查看仍在运行的任务。",
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
                    "limit": {"type": "integer", "minimum": 1, "maximum": 200},
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
                "或任务明显耗时且还有独立工作可做时，才使用 start_background_job。"
                "后台启动后可以继续处理独立的读取任务，之后用 "
                "collect_background_jobs 查询结果。查询若返回 running，"
                "不能说任务已完成；不要连续空转查询。"
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
        choice = response.choices[0]
        message = choice.message
        messages.append(message.model_dump(exclude_none=True))
        if not message.tool_calls:
            if choice.finish_reason != "stop":
                return f"模型未正常结束：{choice.finish_reason}；后台任务可能仍在运行或待收集。"
            return message.content or ""

        if choice.finish_reason != "tool_calls":
            return f"工具调用未正常结束：{choice.finish_reason}；没有执行这轮工具。"

        for tool_call in message.tool_calls:
            result = run_tool_call(tool_call)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(result),
                }
            )

    return "达到最大轮数，循环停止；后台任务可能仍需下一轮收集。"


def run_tool_call(tool_call) -> str:
    """把模型返回的参数当作不可信输入，并让错误能回到模型上下文。"""
    name = tool_call.function.name
    try:
        arguments = json.loads(tool_call.function.arguments or "{}")
    except (json.JSONDecodeError, TypeError):
        return "Error: 工具参数不是有效的 JSON 对象"
    if not isinstance(arguments, dict):
        return "Error: 工具参数必须是 JSON 对象"

    handler = TOOL_HANDLERS.get(name)
    if handler is None:
        return f"Error: 未知工具 {name}"
    try:
        return str(handler(**arguments))
    except (TypeError, ValueError) as exc:
        return f"Error: {exc}"
    except Exception as exc:
        return f"Error: 工具执行失败（{type(exc).__name__}）"


if __name__ == "__main__":
    query = input("请输入任务（例如：后台运行一个 3 秒任务，同时读取 README.md）：\n> ")
    print(agent_loop(query))
