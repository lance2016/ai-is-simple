#!/usr/bin/env python3
"""第 16 章：用一次 Workflow 工具调用启动固定、并行、可恢复的编排。"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
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
STORE = Path(os.getenv("WORKFLOW_STORE", WORKDIR / ".workflow-runtime"))
MAX_TURNS = 8
WORKFLOW_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
RUN_ID_RE = re.compile(r"^wf_[A-Za-z0-9][A-Za-z0-9._-]{0,63}_[0-9a-f]{8}$")


class WorkflowError(Exception):
    """工作流名称、参数或恢复状态不合法。"""


class Journal:
    """把每一步的结果写到磁盘，让中断后可以跳过已完成步骤。"""

    def __init__(self, run_id: str, data: dict):
        self.run_id = run_id
        self.data = data
        self.lock = threading.RLock()
        STORE.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return STORE / f"{self.run_id}.json"

    @classmethod
    def new(cls, name: str, args: dict) -> "Journal":
        run_id = f"wf_{name}_{secrets.token_hex(4)}"
        data = {"run_id": run_id, "name": name, "args": args, "status": "running", "steps": {}}
        journal = cls(run_id, data)
        journal.save()
        return journal

    @classmethod
    def resume(cls, run_id: str) -> "Journal":
        if not RUN_ID_RE.fullmatch(run_id):
            raise WorkflowError("resume_from_run_id 格式不正确。")
        path = STORE / f"{run_id}.json"
        if not path.is_file():
            raise WorkflowError(f"找不到工作流运行记录：{run_id}")
        return cls(run_id, json.loads(path.read_text(encoding="utf-8")))

    def save(self) -> None:
        with self.lock:
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(temporary, self.path)

    def cached(self, step: str) -> str | None:
        with self.lock:
            entry = self.data["steps"].get(step)
            return entry["result"] if entry and entry["status"] == "completed" else None

    def complete_step(self, step: str, result: str) -> None:
        with self.lock:
            self.data["steps"][step] = {"status": "completed", "result": result}
            self.save()

    def finish(self, result: dict) -> None:
        with self.lock:
            self.data["status"] = "completed"
            self.data["result"] = result
            self.save()


def ask_agent(label: str, prompt: str) -> str:
    """工作流内部的 agent()：每次调用都得到稳定的文本结果。"""
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "你是工作流中的一个专职分析员，只回答当前小步骤。"},
            {"role": "user", "content": f"步骤：{label}\n\n{prompt}"},
        ],
    )
    return response.choices[0].message.content or "(没有返回内容)"


class WorkflowContext:
    def __init__(self, journal: Journal):
        self.journal = journal

    def phase(self, title: str) -> None:
        print(f"[phase] {title}")

    def log(self, message: str) -> None:
        print(f"[workflow] {message}")

    def agent(self, step: str, prompt: str) -> str:
        cached = self.journal.cached(step)
        if cached is not None:
            self.log(f"跳过已完成步骤：{step}")
            return cached
        result = ask_agent(step, prompt)
        self.journal.complete_step(step, result)
        return result

    def parallel(self, jobs: list[tuple[str, str]]) -> dict[str, str]:
        """并行屏障：所有独立步骤完成后，才把结果交给下一阶段。"""
        with ThreadPoolExecutor(max_workers=min(4, len(jobs))) as pool:
            futures = {
                pool.submit(self.agent, step, prompt): step
                for step, prompt in jobs
            }
            return {step: future.result() for future, step in futures.items()}


def review_project(ctx: WorkflowContext, args: dict) -> dict:
    subject = args.get("subject", "理解这个项目的 Agent 运行方式")
    ctx.phase("并行检查")
    findings = ctx.parallel(
        [
            (
                "check_concept",
                f"围绕“{subject}”，用初学者能懂的话说明 Agent Loop 和 Harness 的关系。",
            ),
            (
                "check_structure",
                "根据项目结构，说明 README、章节代码和 assets 分别承担什么作用。",
            ),
        ]
    )
    ctx.phase("汇总结果")
    summary = ctx.agent(
        "synthesis",
        "把下面两个独立检查合并成 3 条简短结论，不要添加没有依据的新事实：\n"
        + json.dumps(findings, ensure_ascii=False, indent=2),
    )
    return {"subject": subject, "findings": findings, "summary": summary}


WORKFLOWS = {
    "review_project": {
        "description": "并行检查项目概念和结构，再汇总成学习笔记。",
        "phases": ["并行检查", "汇总结果"],
        "runner": review_project,
    }
}


def validate_workflow(name: str, args: dict) -> None:
    if not WORKFLOW_NAME_RE.fullmatch(name) or name not in WORKFLOWS:
        raise WorkflowError(f"未知或不安全的 Workflow：{name}")
    if not isinstance(args, dict):
        raise WorkflowError("args 必须是对象。")


def run_workflow(name: str, args: dict | None = None, resume_from_run_id: str | None = None) -> dict:
    args = args or {}
    validate_workflow(name, args)
    journal = Journal.resume(resume_from_run_id) if resume_from_run_id else Journal.new(name, args)
    if journal.data.get("name") != name:
        raise WorkflowError("恢复记录的 Workflow 名称不匹配。")
    if journal.data.get("status") == "completed":
        return {"run_id": journal.run_id, "status": "completed", "result": journal.data["result"], "resumed": True}
    result = WORKFLOWS[name]["runner"](WorkflowContext(journal), journal.data.get("args", args))
    journal.finish(result)
    return {"run_id": journal.run_id, "status": "completed", "result": result, "resumed": bool(resume_from_run_id)}


def list_workflows() -> str:
    return json.dumps(
        [{"name": name, "description": meta["description"], "phases": meta["phases"]} for name, meta in WORKFLOWS.items()],
        ensure_ascii=False,
        indent=2,
    )


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_workflows",
            "description": "列出已经注册的可信 Workflow。",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_workflow",
            "description": "运行一个已注册的固定编排；可以传入上次的 run_id 继续。",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "args": {"type": "object"},
                    "resume_from_run_id": {"type": "string"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
]


def agent_loop(user_text: str) -> str:
    messages = [
        {
            "role": "system",
            "content": "你是简洁的中文助手。先用 list_workflows 了解可用编排，再按用户需求调用已注册 Workflow。"
            "Workflow 的代码和元数据由宿主维护，不能让用户输入任意可执行代码。",
        },
        {"role": "user", "content": user_text},
    ]
    for _ in range(MAX_TURNS):
        response = client.chat.completions.create(model=MODEL, messages=messages, tools=TOOLS, tool_choice="auto")
        message = response.choices[0].message
        messages.append(message.model_dump(exclude_none=True))
        if not message.tool_calls:
            return message.content or ""
        for tool_call in message.tool_calls:
            try:
                arguments = json.loads(tool_call.function.arguments or "{}")
                if tool_call.function.name == "list_workflows":
                    result = list_workflows()
                elif tool_call.function.name == "run_workflow":
                    result = json.dumps(run_workflow(**arguments), ensure_ascii=False, indent=2)
                else:
                    result = f"Error: 未知工具 {tool_call.function.name}"
            except Exception as exc:
                result = f"Error: Workflow 执行失败：{exc}"
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})
    return "达到最大轮数，主循环停止；如果需要继续，请使用上一次返回的 run_id。"


if __name__ == "__main__":
    query = input("请输入任务（例如：运行 review_project 工作流，分析这个项目）：\n> ")
    print(agent_loop(query))
