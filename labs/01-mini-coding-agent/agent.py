#!/usr/bin/env python3
"""实战篇 01：一个安全边界明确、可以真正运行的简易 Coding Agent。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash")
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
API_KEY = os.getenv("DEEPSEEK_API_KEY")
MAX_TURNS = int(os.getenv("CODING_AGENT_MAX_TURNS", "12"))
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if not API_KEY:
    raise SystemExit("请先在 .env 中填写 DEEPSEEK_API_KEY。")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


def tool_schema(name: str, description: str, properties: dict, required=None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


TOOLS = [
    tool_schema(
        "read",
        "读取一个工作区内的 UTF-8 文本文件。需要列文件或搜索内容时，请使用 bash。",
        {
            "path": {"type": "string"},
            "start_line": {"type": "integer", "description": "起始行号，默认 1"},
            "end_line": {"type": "integer", "description": "结束行号，默认 160"},
        },
        ["path"],
    ),
    tool_schema(
        "write",
        "创建或覆盖一个文本文件；执行前一定会向用户请求确认。",
        {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        ["path", "content"],
    ),
    tool_schema(
        "edit",
        "把文件中的一段旧文本替换成新文本；要求旧文本只出现一次，并会请求确认。",
        {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
        },
        ["path", "old_text", "new_text"],
    ),
    tool_schema(
        "bash",
        "在工作区中运行 Bash 命令；可用于列文件、搜索代码、查看 Git 状态和运行检查。只读命令自动执行，其他命令会请求确认。",
        {
            "command": {"type": "string", "description": "要运行的 Bash 命令"},
        },
        ["command"],
    ),
]


class SessionStore:
    """用 JSONL 保存消息，既能回看，也能为下一次会话留下入口。"""

    def __init__(self, path: Path | None):
        self.path = path
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[dict]:
        if not self.path or not self.path.is_file():
            return []
        messages = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return messages

    def append(self, message: dict) -> None:
        if not self.path:
            return
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(message, ensure_ascii=False) + "\n")


class SafeTools:
    """所有文件和进程动作都从这里经过，先限制范围，再决定是否执行。"""

    BLOCKED_PARTS = {".git", ".venv", "__pycache__", ".coding-agent-sessions"}
    READ_ONLY_COMMANDS = {
        "pwd",
        "ls",
        "find",
        "rg",
        "grep",
        "cat",
        "head",
        "tail",
        "sed",
        "awk",
        "git",
        "wc",
        "sort",
        "file",
    }
    BLOCKED_COMMAND_PARTS = (
        ".env",
        ".git",
        ".venv",
        "__pycache__",
        ".coding-agent-sessions",
        "/etc/",
        "~/.ssh",
        ".ssh/",
    )

    def __init__(self, workspace: Path):
        self.workspace = workspace.resolve()

    def _target(self, user_path: str) -> Path | None:
        candidate = Path(user_path).expanduser()
        if candidate.is_absolute():
            return None
        target = (self.workspace / candidate).resolve()
        if not target.is_relative_to(self.workspace):
            return None
        relative = target.relative_to(self.workspace)
        if any(part in self.BLOCKED_PARTS or part == ".env" or part.startswith(".env.") for part in relative.parts):
            return None
        return target

    def _confirm(self, action: str) -> bool:
        """非交互环境默认拒绝写入和执行，避免 Agent 悄悄修改用户文件。"""
        if not sys.stdin.isatty():
            return False
        answer = input(f"\n[需要确认] {action}\n允许吗？[y/N] ").strip().lower()
        return answer in {"y", "yes", "是"}

    def read(self, path: str, start_line: int = 1, end_line: int = 160) -> str:
        target = self._target(path)
        if not target or not target.is_file():
            return "Error: 文件不存在、越过工作区，或属于受保护目录。"
        if target.stat().st_size > 512_000:
            return "Error: 文件太大，请先缩小读取范围。"
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            return "Error: 这不是 UTF-8 文本文件。"
        start_line = max(1, start_line)
        end_line = min(len(lines), max(start_line, end_line))
        selected = [f"{number}: {lines[number - 1]}" for number in range(start_line, end_line + 1)]
        return "\n".join(selected) or "(文件为空)"

    def write(self, path: str, content: str) -> str:
        target = self._target(path)
        if not target:
            return "Error: 目标路径越过工作区或属于受保护目录。"
        if len(content) > 100_000:
            return "Error: 单次写入不能超过 100KB。"
        if not self._confirm(f"写入文件 {target.relative_to(self.workspace)}"):
            return "Write blocked: 用户没有批准写入。"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"已写入 {target.relative_to(self.workspace)}。"

    def edit(self, path: str, old_text: str, new_text: str) -> str:
        target = self._target(path)
        if not target or not target.is_file():
            return "Error: 文件不存在、越过工作区，或属于受保护目录。"
        content = target.read_text(encoding="utf-8")
        occurrences = content.count(old_text)
        if occurrences != 1:
            return f"Error: old_text 出现了 {occurrences} 次，必须恰好出现 1 次。"
        if not self._confirm(f"修改文件 {target.relative_to(self.workspace)}"):
            return "Edit blocked: 用户没有批准修改。"
        target.write_text(content.replace(old_text, new_text), encoding="utf-8")
        return f"已修改 {target.relative_to(self.workspace)}。"

    def _bash_is_read_only(self, command: str) -> bool:
        """只自动放行一个简单的只读命令，组合命令统一要求确认。"""
        if not command.strip() or any(operator in command for operator in (";", "&&", "||", "|", ">", "<", "`", "$(")):
            return False
        try:
            parts = shlex.split(command)
        except ValueError:
            return False
        if not parts or parts[0] not in self.READ_ONLY_COMMANDS:
            return False
        if parts[0] == "git" and len(parts) > 1:
            if parts[1] not in {"status", "diff", "log", "show", "branch", "rev-parse"}:
                return False
            # 这些参数可能写文件或改变 Git 状态，不能因为命令以 git 开头就自动放行。
            dangerous_git_flags = {"-D", "-d", "--delete", "--edit", "--output", "-o"}
            return not any(
                argument in dangerous_git_flags or argument.startswith("--output=")
                for argument in parts[2:]
            )
        if parts[0] == "sed":
            return not any(argument in {"-i", "--in-place"} or argument.startswith("-i") for argument in parts[1:])
        if parts[0] == "find":
            return not any(argument in {"-delete", "-exec", "-execdir", "-ok", "-okdir"} for argument in parts[1:])
        if parts[0] == "awk":
            return "system(" not in command and "\n" not in command
        return True

    def bash(self, command: str) -> str:
        normalized = command.casefold()
        if any(part in normalized for part in self.BLOCKED_COMMAND_PARTS):
            return "Bash blocked: 命令触及 .env、.git、虚拟环境、会话目录或系统敏感路径。"
        if not self._bash_is_read_only(command) and not self._confirm(f"运行 Bash：{command}"):
            return "Bash blocked: 非交互环境默认拒绝需要确认的命令。"
        # 不把 API Key 传给子进程，避免命令意外打印密钥。
        child_env = os.environ.copy()
        for secret_name in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            child_env.pop(secret_name, None)
        try:
            completed = subprocess.run(
                command,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
                env=child_env,
                shell=True,
            )
        except subprocess.TimeoutExpired:
            return "Error: Bash 命令运行超过 20 秒，已停止等待。"
        output = (completed.stdout + completed.stderr).strip()
        return f"exit_code={completed.returncode}\n{output[-8000:]}"

    def dispatch(self, name: str, arguments: dict) -> str:
        handlers = {
            "read": self.read,
            "write": self.write,
            "edit": self.edit,
            "bash": self.bash,
        }
        handler = handlers.get(name)
        if not handler:
            return f"Error: 未知工具 {name}"
        try:
            return str(handler(**arguments))
        except Exception as exc:
            return f"Error: 工具执行失败：{exc}"


class CodingAgent:
    # 先做一个很轻量的 Harness 分流：普通聊天不需要把工具暴露给模型。
    TOOL_INTENT_WORDS = (
        "文件", "目录", "代码", "项目", "仓库", "终端", "命令", "脚本", "测试",
        "读取", "查看", "搜索", "列出", "修改", "编辑", "写入", "创建", "删除",
        "运行", "执行", "检查", "实现", "修复", "重构", "部署", "read", "write",
        "edit", "bash", "list", "search", "file", "folder", "directory", "repo",
        "code", "run", "test", "check", "fix", "implement", "refactor", "git", "pytest",
        "npm", "python",
    )
    GREETING_ONLY = re.compile(
        r"^(hi|hello|hey|yo|你好|您好|嗨|哈喽|早上好|晚上好|晚安|在吗|谢谢|感谢)[!！,.，。？?\s~～]*$",
        re.IGNORECASE,
    )
    CONCEPT_HINTS = ("什么是", "是什么", "怎么理解", "解释一下", "介绍一下", "为什么", "区别", "原理", "概念")
    WORK_ACTION_WORDS = (
        "读取", "查看", "列出", "搜索", "修改", "编辑", "写入", "创建", "删除", "运行", "执行",
        "检查", "实现", "修复", "重构", "部署", "read", "write", "edit", "bash", "list", "search",
        "run", "test", "check", "fix", "implement", "refactor", "git", "pytest", "npm", "python",
    )

    def __init__(self, workspace: Path, session: SessionStore):
        self.workspace = workspace
        self.tools = SafeTools(workspace)
        self.session = session
        self.messages = session.load()
        if not self.messages or self.messages[0].get("role") != "system":
            self.messages = [{"role": "system", "content": self.system_prompt()}]

    def system_prompt(self) -> str:
        return (
            "你是一个谨慎、简洁的中文 Coding Agent。\n"
            f"当前工作区：{self.workspace}\n"
            "你只有四个工具：read、write、edit、bash。列目录、搜索代码、查看 Git 状态和运行检查，都优先通过 bash 完成。\n"
            "如果用户只是问候、闲聊或询问概念，不需要访问工作区时，直接用文字回答，不要调用工具。\n"
            "先阅读和搜索，再提出修改；修改文件或运行需要确认的 Bash 命令前必须调用工具，程序会向用户请求确认。\n"
            "不要访问 .env、.git、.venv 或会话目录。每次修改后说明改了什么，并在用户批准时运行相关检查。"
        )

    @classmethod
    def needs_tools(cls, request: str) -> bool:
        """判断请求是否可能需要工作区能力；不确定时保持聊天模式更自然。"""
        text = request.strip().casefold()
        if not text or cls.GREETING_ONLY.fullmatch(text):
            return False
        has_path = bool(re.search(r"(?:^|[\s`])(?:\.{0,2}/|[\w.-]+\.(?:py|md|ts|js|json|toml|yaml|yml))", text))
        if any(hint in text for hint in cls.CONCEPT_HINTS) and not has_path and not any(
            word in text for word in cls.WORK_ACTION_WORDS
        ):
            return False
        if any(word in text for word in cls.TOOL_INTENT_WORDS):
            return True
        # 文件扩展名和相对路径通常已经足够说明用户想操作项目。
        return has_path

    def save(self, message: dict) -> None:
        self.messages.append(message)
        self.session.append(message)

    def reset(self) -> None:
        self.messages = [{"role": "system", "content": self.system_prompt()}]

    def run(self, request: str) -> str:
        self.save({"role": "user", "content": request})
        # 闲聊时不把工具定义发给模型，避免模型为了“做点什么”而误调用 bash。
        if not self.needs_tools(request):
            response = client.chat.completions.create(
                model=MODEL,
                messages=self.messages,
            )
            message = response.choices[0].message
            self.save(message.model_dump(exclude_none=True))
            return message.content or ""

        for turn in range(1, MAX_TURNS + 1):
            response = client.chat.completions.create(
                model=MODEL,
                messages=self.messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            message = response.choices[0].message
            assistant = message.model_dump(exclude_none=True)
            self.save(assistant)
            if not message.tool_calls:
                return message.content or ""
            for tool_call in message.tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments or "{}")
                    print(f"[tool] {tool_call.function.name}({json.dumps(arguments, ensure_ascii=False)})")
                    result = self.tools.dispatch(tool_call.function.name, arguments)
                except json.JSONDecodeError as exc:
                    result = f"Error: 工具参数不是有效 JSON：{exc}"
                tool_message = {"role": "tool", "tool_call_id": tool_call.id, "content": result}
                self.save(tool_message)
                print(f"[result] {result[:300]}")
        return f"达到 {MAX_TURNS} 轮上限，已停止自动执行；请检查当前会话后再继续。"


def new_session_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return PROJECT_ROOT / ".coding-agent-sessions" / f"session-{stamp}.jsonl"


def print_help() -> None:
    print(
        "命令：\n"
        "  /help     查看帮助\n"
        "  /clear    清空当前内存上下文（不删除会话文件）\n"
        "  /quit     退出\n\n"
        "例子：用 bash 列出 labs 目录，读取其中的 README，然后告诉我这个 Agent 有哪些工具。"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="一个参考 Pi Harness 理念实现的简易 Coding Agent")
    parser.add_argument("--workspace", type=Path, default=PROJECT_ROOT, help="工作区路径，默认是本项目根目录")
    parser.add_argument("--session", type=Path, help="继续某个 JSONL 会话")
    parser.add_argument("--no-session", action="store_true", help="不保存会话")
    parser.add_argument("prompt", nargs="?", help="直接执行一条任务后退出")
    args = parser.parse_args()

    workspace = args.workspace.expanduser().resolve()
    if not workspace.is_dir():
        raise SystemExit(f"工作区不存在：{workspace}")
    session_path = None if args.no_session else (args.session or new_session_path())
    agent = CodingAgent(workspace, SessionStore(session_path))

    if args.prompt:
        print(agent.run(args.prompt))
        return

    print("简易 Coding Agent 已启动。输入 /help 查看帮助，输入 /quit 退出。")
    while True:
        try:
            user_text = input("\n你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已退出。")
            return
        if not user_text:
            continue
        if user_text == "/quit":
            print("已退出。")
            return
        if user_text == "/help":
            print_help()
            continue
        if user_text == "/clear":
            agent.reset()
            print("当前上下文已清空，会话文件仍然保留。")
            continue
        print(f"\nAgent> {agent.run(user_text)}")


if __name__ == "__main__":
    main()
