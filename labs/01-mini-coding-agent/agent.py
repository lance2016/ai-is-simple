#!/usr/bin/env python3
"""实战篇 01：一个安全边界明确、可以真正运行的简易 Coding Agent。"""

from __future__ import annotations

import argparse
import html
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

# Unix 下 input() 不一定会自动启用行编辑；导入 readline 后，方向键、退格和历史记录才会正常工作。
# Windows 没有这个标准库模块时，保留普通 input() 作为降级方案。
try:
    import readline  # noqa: F401
except ImportError:
    readline = None

load_dotenv()

# 把模型配置放在环境变量中，代码本身只负责读取配置。
# DeepSeek API 中，DeepSeek-V4.1-Flash 对外使用的模型名是 deepseek-flash。
# 这样可以在不修改源码的情况下切换模型、接口地址和循环上限。
MODEL_ALIASES = {
    # 兼容读者可能按产品名填写的版本名，最终仍使用官方 API 模型名。
    "v4.1-flash": "deepseek-flash",
    "deepseek-v4.1-flash": "deepseek-flash",
    "deepseek-v4-flash": "deepseek-flash",
}
REQUESTED_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip().casefold()
MODEL = MODEL_ALIASES.get(REQUESTED_MODEL, REQUESTED_MODEL)
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
API_KEY = os.getenv("DEEPSEEK_API_KEY")
MAX_TURNS = int(os.getenv("CODING_AGENT_MAX_TURNS", "12"))
PROJECT_ROOT = Path(__file__).resolve().parents[2]

if not API_KEY:
    raise SystemExit("请先在 .env 中填写 DEEPSEEK_API_KEY。")

client = OpenAI(api_key=API_KEY, base_url=BASE_URL)


def tool_schema(name: str, description: str, properties: dict, required=None) -> dict:
    # OpenAI 兼容接口使用 JSON Schema 描述工具参数。
    # 模型看到的是这个“说明书”，真正执行仍然要经过 SafeTools.dispatch()。
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


# 工具尽量保持少量：通用的列目录、搜索和检查交给 bash，
# 文件读写则用结构更明确的 read / write / edit 表达。
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


# 某些兼容层会把工具调用作为 DSML 文本放进 message.content，而不是放在
# message.tool_calls 中。这个格式不是标准 Chat Completions 返回值，
# 这里只做兼容解析，正常情况下仍优先使用原生 tool_calls。
DSML_INVOKE_RE = re.compile(
    r'<\s*/?\s*\|\s*\|\s*DSML\s*\|\s*\|\s*invoke\s+'
    r'name=["\'](?P<name>[^"\']+)["\']\s*>(?P<body>.*?)'
    r'<\s*/?\s*\|\s*\|\s*DSML\s*\|\s*\|\s*invoke\s*>',
    re.IGNORECASE | re.DOTALL,
)
DSML_PARAMETER_RE = re.compile(
    r'<\s*/?\s*\|\s*\|\s*DSML\s*\|\s*\|\s*parameter\s+'
    r'name=["\'](?P<name>[^"\']+)["\'](?:\s+string=["\'][^"\']*["\'])?\s*>'
    r'(?P<value>.*?)'
    r'<\s*/?\s*\|\s*\|\s*DSML\s*\|\s*\|\s*parameter\s*>',
    re.IGNORECASE | re.DOTALL,
)


def parse_dsml_tool_calls(content: str) -> list[dict]:
    """把兼容层返回的 DSML 文本转换成标准 tool_calls 结构。"""
    # 不同兼容层可能输出全角竖线（｜｜），或者在 XML 结束标签前多输出一个反斜杠。
    # 先做归一化，再使用同一套正则解析，避免把这些显示差异扩散到主循环里。
    normalized = content.replace("｜", "|")
    normalized = re.sub(r"\\(?=\s*<\s*/?\s*\|)", "", normalized)
    if "dsml" not in normalized.casefold() or "invoke" not in normalized.casefold():
        return []

    calls = []
    for index, invoke in enumerate(DSML_INVOKE_RE.finditer(normalized), start=1):
        arguments = {
            parameter.group("name"): html.unescape(parameter.group("value")).strip()
            for parameter in DSML_PARAMETER_RE.finditer(invoke.group("body"))
        }
        calls.append(
            {
                "id": f"dsml_call_{index}",
                "type": "function",
                "function": {
                    "name": invoke.group("name"),
                    "arguments": json.dumps(arguments, ensure_ascii=False),
                },
            }
        )
    return calls


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
        # 一行一条 JSON，某一行损坏时跳过它，不影响剩余历史记录加载。
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return messages

    def append(self, message: dict) -> None:
        if not self.path:
            return
        # ensure_ascii=False 让中文保持可读，后续也方便直接打开 JSONL 学习消息结构。
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
        # 工具参数中的路径必须是相对路径，并且解析后仍在工作区内。
        # resolve() 可以处理 ../ 这类路径，避免用字符串拼接绕过目录边界。
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
        # 只把“是否执行”的决定交给用户，不把安全判断交给模型自己承诺。
        answer = input(f"\n[需要确认] {action}\n允许吗？[y/N] ").strip().lower()
        return answer in {"y", "yes", "是"}

    def read(self, path: str, start_line: int = 1, end_line: int = 160) -> str:
        # 读取工具是只读操作，所以不需要确认；但仍然要经过路径和大小检查。
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
        # 写入和编辑会改变工作区，必须先通过统一的确认入口。
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
        # 要求 old_text 只出现一次，可以避免模型因为匹配过宽而误改多个位置。
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
        # 这里不是完整的 Shell 解析器，而是教学示例中的保守白名单。
        # 只要出现管道、重定向或命令替换，就要求用户明确确认。
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
        # bash 是能力出口：模型可以提出命令，但能否执行由这里的规则决定。
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
        # 所有工具调用都从同一个入口进入，便于集中记录、拦截和扩展。
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
        # 没有历史消息时，先放入 system 消息，给模型说明角色、边界和工具用法。
        if not self.messages or self.messages[0].get("role") != "system":
            self.messages = [{"role": "system", "content": self.system_prompt()}]

    def system_prompt(self) -> str:
        # system prompt 负责告诉模型“应该怎么做”，但不能替代程序的安全检查。
        return (
            "你是一个谨慎、简洁的中文 Coding Agent。\n"
            f"当前工作区：{self.workspace}\n"
            "你只有四个工具：read、write、edit、bash。列目录、搜索代码、查看 Git 状态和运行检查，都优先通过 bash 完成。\n"
            "如果用户只是问候、闲聊或询问概念，不需要访问工作区时，直接用文字回答，不要调用工具。\n"
            "需要操作时请使用接口提供的原生 function tool call，不要把 <| DSML |> 之类的内部格式当作普通文字输出。\n"
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
        # 消息同时进入内存和 JSONL：内存供当前请求使用，文件供下次会话恢复。
        self.messages.append(message)
        self.session.append(message)

    def reset(self) -> None:
        # /clear 只清空当前上下文，不删除磁盘上的历史，方便回看学习。
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

        # Agent Loop 的核心：模型决定下一步 -> 程序执行工具 -> 结果回到模型。
        for turn in range(1, MAX_TURNS + 1):
            response = client.chat.completions.create(
                model=MODEL,
                messages=self.messages,
                tools=TOOLS,
                tool_choice="auto",
            )
            message = response.choices[0].message
            assistant = message.model_dump(exclude_none=True)
            tool_calls = [
                {
                    "id": tool_call.id,
                    "type": tool_call.type,
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in (message.tool_calls or [])
            ]

            if not tool_calls:
                # 兼容少数网关把工具调用塞进 content 的情况，避免把原始 DSML
                # 直接展示给用户。标准返回仍然应该走上面的 message.tool_calls。
                tool_calls = parse_dsml_tool_calls(message.content or "")
                if tool_calls:
                    assistant.pop("content", None)
                    assistant["tool_calls"] = tool_calls
                    print("[compat] 已将兼容层返回的 DSML 转换为工具调用")

            self.save(assistant)
            # 没有 tool_calls 代表模型认为信息已经足够，可以直接回答并结束本轮任务。
            if not tool_calls:
                return message.content or ""
            for tool_call in tool_calls:
                try:
                    # 工具参数来自模型生成的 JSON，解析失败时把错误作为工具结果回传，
                    # 让模型有机会自行修正，而不是让整个 Agent 直接崩溃。
                    arguments = json.loads(tool_call["function"]["arguments"] or "{}")
                    tool_name = tool_call["function"]["name"]
                    print(f"[tool] {tool_name}({json.dumps(arguments, ensure_ascii=False)})")
                    result = self.tools.dispatch(tool_name, arguments)
                except json.JSONDecodeError as exc:
                    result = f"Error: 工具参数不是有效 JSON：{exc}"
                tool_message = {"role": "tool", "tool_call_id": tool_call["id"], "content": result}
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
    # 命令行参数负责启动方式；具体的 Agent 行为仍集中在 CodingAgent 中。
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
        # 传入一次性任务时执行一轮请求后退出，适合脚本和自动化检查。
        print(agent.run(args.prompt))
        return

    print("简易 Coding Agent 已启动。输入 /help 查看帮助，输入 /quit 退出。")
    while True:
        try:
            # 交互模式把每次输入交给同一个 agent，因此可以保留上下文。
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
        # 普通文本才进入模型；斜杠命令由 Harness 本地处理。
        print(f"\nAgent> {agent.run(user_text)}")


if __name__ == "__main__":
    main()
