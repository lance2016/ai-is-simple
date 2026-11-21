#!/usr/bin/env python3
"""第 11 章：把明确的慢任务放到后台，Agent Loop 继续处理别的事。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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


# The model picks a job NAME; the argv is fixed here and never comes from the model.
CHECK_SYNTAX_SCRIPT = """
import ast, pathlib, sys
files = sorted(p for d in ("chapters", "labs") for p in pathlib.Path(d).rglob("*.py"))
bad = 0
for path in files:
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        bad += 1
        print(f"{path}:{exc.lineno}: {exc.msg}")
print(f"已检查 {len(files)} 个文件，{bad} 个有语法错误")
sys.exit(1 if bad else 0)
"""
JOBS = {
    "check_syntax": {
        "description": "解析 chapters/ 和 labs/ 下所有 .py 文件，检查语法",
        "argv": [sys.executable, "-B", "-c", CHECK_SYNTAX_SCRIPT],
    },
    "run_demo_tests": {
        "description": "运行 labs/05-verify/demo 的单元测试（这个练习目录故意留了 bug）",
        "argv": [sys.executable, "-B", "-m", "unittest", "discover", "-s", "labs/05-verify/demo"],
    },
}
JOB_TIMEOUT = 30
OUTPUT_TAIL_CHARS = 2000
SECRET_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def child_env() -> dict[str, str]:
    # load_dotenv() put the API key into os.environ; a test run needs no credentials.
    env = {
        name: value
        for name, value in os.environ.items()
        if not any(marker in name.upper() for marker in SECRET_ENV_MARKERS)
    }
    # No .pyc files in the project; UTF-8 so the Chinese output decodes cleanly.
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    return env


class BackgroundManager:
    """每个后台任务一个线程；状态和待收集通知都只保存在当前进程中。"""

    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.ready: list[str] = []
        self.lock = threading.Lock()

    def start(self, job: str, delay_seconds: int = 3) -> str:
        if not isinstance(job, str) or job not in JOBS:
            raise ValueError(f"未知任务，只能从这些名字里选：{'、'.join(JOBS)}")
        if (
            isinstance(delay_seconds, bool)
            or not isinstance(delay_seconds, int)
            or not 0 <= delay_seconds <= 10
        ):
            raise ValueError("delay_seconds 必须是 0 到 10 之间的整数")

        job_id = f"bg_{uuid.uuid4().hex[:8]}"
        with self.lock:
            self.jobs[job_id] = {
                "id": job_id,
                "job": job,
                "status": "running",
                "exit_code": None,
                "output": "",
            }

        worker = threading.Thread(target=self._run, args=(job_id, job, delay_seconds), daemon=True)
        worker.start()
        return f"后台任务已启动：{job_id}（{job}），status=running"

    def _run(self, job_id: str, job: str, delay_seconds: int) -> None:
        # Teaching delay only: the real jobs finish too fast to be seen running.
        time.sleep(delay_seconds)
        try:
            proc = subprocess.run(
                JOBS[job]["argv"],
                shell=False,
                cwd=WORKDIR,
                env=child_env(),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=JOB_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            self._finish(job_id, "failed", None, f"超过 {JOB_TIMEOUT} 秒，子进程已被终止")
        except Exception as exc:
            self._finish(job_id, "failed", None, f"子进程没有跑起来（{type(exc).__name__}）")
        else:
            status = "succeeded" if proc.returncode == 0 else "failed"
            self._finish(job_id, status, proc.returncode, proc.stdout + proc.stderr)

    def _finish(self, job_id: str, status: str, exit_code: int | None, output: str) -> None:
        """Record a terminal state; a failed job is kept, never silently dropped."""
        with self.lock:
            record = self.jobs[job_id]
            record["status"] = status
            record["exit_code"] = exit_code
            # Tracebacks carry absolute paths; the model does not need the home directory.
            output = output.replace(str(WORKDIR), ".").strip()
            # Summaries and failures sit at the end of test output, so keep the tail.
            record["output"] = output[-OUTPUT_TAIL_CHARS:]
            self.ready.append(job_id)

    def collect(self) -> str:
        with self.lock:
            finished = [dict(self.jobs[job_id]) for job_id in self.ready]
            self.ready.clear()
            running = [dict(r) for r in self.jobs.values() if r["status"] == "running"]

        lines = []
        for record in finished:
            lines.append(
                f"[task_notification] {record['id']} job={record['job']} "
                f"status={record['status']} exit_code={record['exit_code']}\n"
                f"输出末尾：\n{record['output'] or '(没有输出)'}"
            )
        for record in running:
            lines.append(f"[仍在运行] {record['id']} job={record['job']} status=running")
        return "\n".join(lines) or "(没有新的后台结果)"


BACKGROUND = BackgroundManager()


def start_background_job(job: str, delay_seconds: int = 3) -> str:
    return BACKGROUND.start(job, delay_seconds)


def collect_background_jobs() -> str:
    """取出新结束任务的一次性通知，并附上仍在运行的任务。"""
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
            "description": (
                "在后台运行一个预设任务，立刻返回任务 ID，不阻塞当前 Agent Loop。"
                "只能选任务名，不能传命令。可选任务："
                + "；".join(f"{name}＝{job['description']}" for name, job in JOBS.items())
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "job": {"type": "string", "enum": list(JOBS)},
                    "delay_seconds": {
                        "type": "integer",
                        "description": "教学用延迟：开跑前先等几秒，方便观察 running 状态",
                        "minimum": 0,
                        "maximum": 10,
                    },
                },
                "required": ["job"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "collect_background_jobs",
            "description": "收集新结束任务的一次性通知（成功或失败），并查看仍在运行的任务。",
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
                "collect_background_jobs 查询结果。结果里是 status=running 时，"
                "不能说任务已结束，也不要连续空转查询，告诉用户稍后再问即可。"
                "status=failed 时如实报告退出码和关键输出，不要说成成功。"
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
            # Show the first line so the learner can watch running / failed go by.
            first_line = result.partition("\n")[0][:100]
            print(f"  [tool] {tool_call.function.name}: {first_line}")
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
    print("输入任务，空行或 exit 退出。例如：后台跑 run_demo_tests，然后告诉我任务 ID。")
    # Keep the process alive between inputs: BACKGROUND (and its worker threads)
    # must outlive a single agent_loop call, or the result is never collected.
    try:
        while True:
            query = input("> ").strip()
            if not query or query.lower() in {"exit", "quit"}:
                break
            print(agent_loop(query))
    except (EOFError, KeyboardInterrupt):
        print()
