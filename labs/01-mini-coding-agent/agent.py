#!/usr/bin/env python3
"""实战篇 01：一个最小但完整的 Coding Agent 内核。

这个文件只关心三件事：
  1. 工具长什么样（Tool 及其四个子类）
  2. 工具能碰哪些文件（Workspace）
  3. 模型和工具怎么来回交替（CodingAgent.run）

界面在 server.py 里，两边只靠两个回调连接：
  confirm(action) -> bool   需要授权时问用户
  emit(event)     -> None   把每一步广播给界面
这样 Agent 本身完全不知道浏览器的存在。
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# 配置全部来自环境变量，代码里不写死任何密钥。
# DeepSeek-V4.1-Flash 在 API 中的正式名字是 deepseek-flash，这里顺手兼容产品名写法。
MODEL_ALIASES = {"v4.1-flash": "deepseek-flash", "deepseek-v4.1-flash": "deepseek-flash"}
_requested_model = os.getenv("DEEPSEEK_MODEL", "deepseek-flash").strip()
MODEL = MODEL_ALIASES.get(_requested_model, _requested_model)
BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
MAX_TURNS = int(os.getenv("CODING_AGENT_MAX_TURNS", "12"))


def create_client() -> OpenAI:
    """延迟到真正要用的时候才建客户端，这样 import 这个文件不会有副作用。"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise SystemExit("请先在项目根目录的 .env 里填写 DEEPSEEK_API_KEY。")
    return OpenAI(api_key=api_key, base_url=BASE_URL)


class ToolError(Exception):
    """工具没法继续时抛出。CodingAgent 会把它变成一句模型看得懂的错误，而不是让程序崩掉。"""


class Workspace:
    """工作区边界。所有文件操作都要先过这里，越界的路径根本拿不到。"""

    BLOCKED_NAMES = {".git", ".venv", "__pycache__", "node_modules"}

    def __init__(self, root: Path):
        self.root = root.resolve()

    def resolve(self, user_path: str) -> Path:
        """把模型给的相对路径变成真实路径，顺便检查它有没有越界。"""
        if Path(user_path).is_absolute():
            raise ToolError("只能使用相对于工作区的路径。")
        # resolve() 会把 ../ 真正展开，所以想靠 "a/../../etc/passwd" 绕出去会在这一步露馅。
        target = (self.root / user_path).resolve()
        if not target.is_relative_to(self.root):
            raise ToolError("这个路径在工作区外面。")
        parts = target.relative_to(self.root).parts
        if any(part in self.BLOCKED_NAMES or part.startswith(".env") for part in parts):
            raise ToolError("这是受保护的文件或目录，Agent 不能碰。")
        return target

    def label(self, target: Path) -> str:
        """给用户看的短路径，比绝对路径清爽。"""
        return str(target.relative_to(self.root))


class Tool:
    """一个工具 = 给模型看的说明书 + 要不要授权 + 真正干活的代码。

    三件事写在同一个类里，所以新增工具只要再写一个子类，然后加进 TOOLS。
    """

    name: str = ""
    description: str = ""
    parameters: dict = {}
    required: tuple[str, ...] = ()

    def schema(self) -> dict:
        """转成 OpenAI 兼容接口要的 JSON Schema。模型看到的就是这段。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": list(self.required),
                    "additionalProperties": False,
                },
            },
        }

    def confirm_prompt(self, workspace: Workspace, **kwargs) -> str | None:
        """返回一句给用户看的话表示这一步要授权；返回 None 表示只读，可以直接做。"""
        return None

    def run(self, workspace: Workspace, **kwargs) -> str:
        raise NotImplementedError


class ReadTool(Tool):
    name = "read"
    description = "读取工作区里的一个 UTF-8 文本文件。列目录或全文搜索请用 bash。"
    parameters = {
        "path": {"type": "string", "description": "相对工作区的文件路径"},
        "start_line": {"type": "integer", "description": "起始行号，默认 1"},
        "end_line": {"type": "integer", "description": "结束行号，默认 200"},
    }
    required = ("path",)
    MAX_BYTES = 512_000

    def run(self, workspace: Workspace, path: str, start_line: int = 1, end_line: int = 200) -> str:
        target = workspace.resolve(path)
        if not target.is_file():
            raise ToolError(f"{path} 不是一个文件。")
        if target.stat().st_size > self.MAX_BYTES:
            raise ToolError("文件超过 500KB，请用 bash 配合 sed 只取需要的片段。")
        try:
            lines = target.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            raise ToolError("这不是 UTF-8 文本文件。")
        start = max(1, start_line)
        end = min(len(lines), max(start, end_line))
        # 带上行号，模型之后用 edit 定位时更准。
        numbered = [f"{n}: {lines[n - 1]}" for n in range(start, end + 1)]
        return "\n".join(numbered) or "(文件为空)"


class WriteTool(Tool):
    name = "write"
    description = "创建或整体覆盖一个文本文件。执行前会请求用户授权。"
    parameters = {
        "path": {"type": "string", "description": "相对工作区的文件路径"},
        "content": {"type": "string", "description": "完整的文件内容"},
    }
    required = ("path", "content")
    MAX_CHARS = 100_000

    def confirm_prompt(self, workspace: Workspace, path: str, content: str) -> str:
        # 在这里就把路径和大小检查做掉，免得弹出一个注定会失败的授权框。
        target = workspace.resolve(path)
        if len(content) > self.MAX_CHARS:
            raise ToolError("单次写入不能超过 100KB。")
        return f"写入文件 {workspace.label(target)}（{len(content)} 个字符）"

    def run(self, workspace: Workspace, path: str, content: str) -> str:
        target = workspace.resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"已写入 {workspace.label(target)}。"


class EditTool(Tool):
    name = "edit"
    description = "把文件里的一段旧文本换成新文本。旧文本必须只出现一次。执行前会请求用户授权。"
    parameters = {
        "path": {"type": "string", "description": "相对工作区的文件路径"},
        "old_text": {"type": "string", "description": "要被替换的原文，必须唯一"},
        "new_text": {"type": "string", "description": "替换后的新文本"},
    }
    required = ("path", "old_text", "new_text")

    def confirm_prompt(self, workspace: Workspace, path: str, old_text: str, new_text: str) -> str:
        target = workspace.resolve(path)
        return f"修改文件 {workspace.label(target)}"

    def run(self, workspace: Workspace, path: str, old_text: str, new_text: str) -> str:
        target = workspace.resolve(path)
        if not target.is_file():
            raise ToolError(f"{path} 不是一个文件。")
        content = target.read_text(encoding="utf-8")
        # 要求只出现一次，避免模型因为匹配太宽而一次改坏好几处。
        count = content.count(old_text)
        if count != 1:
            raise ToolError(f"old_text 在文件里出现了 {count} 次，必须恰好 1 次。")
        target.write_text(content.replace(old_text, new_text), encoding="utf-8")
        return f"已修改 {workspace.label(target)}。"


class BashTool(Tool):
    name = "bash"
    description = "在工作区里运行 Bash 命令，用来列目录、搜索代码、查看 Git 状态或跑检查。"
    parameters = {"command": {"type": "string", "description": "要运行的 Bash 命令"}}
    required = ("command",)

    # 规则只有一句话：单条命令、不含 shell 操作符、首词在白名单里，才算只读。
    # 其余一律请求授权。规则简单意味着不容易看漏，也不容易被花式写法绕过。
    READ_ONLY = {
        "ls", "pwd", "cat", "head", "tail", "wc", "file", "tree", "grep", "rg",
        "git status", "git diff", "git log", "git branch",
    }
    SHELL_OPERATORS = ("|", ">", "<", ";", "&", "`", "$(")
    BLOCKED_WORDS = (".env", ".git/", ".ssh", "/etc/", "sudo")
    TIMEOUT_SECONDS = 20
    MAX_OUTPUT = 8000

    def _is_read_only(self, command: str) -> bool:
        if any(operator in command for operator in self.SHELL_OPERATORS):
            return False
        try:
            parts = shlex.split(command)
        except ValueError:
            return False
        if not parts:
            return False
        # 白名单里既有单词（ls），也有两词前缀（git status），一次比较覆盖两种。
        return parts[0] in self.READ_ONLY or " ".join(parts[:2]) in self.READ_ONLY

    def confirm_prompt(self, workspace: Workspace, command: str) -> str | None:
        if any(word in command.casefold() for word in self.BLOCKED_WORDS):
            raise ToolError("命令触及密钥、Git 内部目录或系统敏感路径，已拦截。")
        return None if self._is_read_only(command) else f"运行命令：{command}"

    def run(self, workspace: Workspace, command: str) -> str:
        # 不把 API Key 传给子进程，免得一句 env 就把密钥打印出来。
        child_env = os.environ.copy()
        for secret in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
            child_env.pop(secret, None)
        try:
            done = subprocess.run(
                command,
                shell=True,
                cwd=workspace.root,
                env=child_env,
                capture_output=True,
                text=True,
                timeout=self.TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise ToolError(f"命令运行超过 {self.TIMEOUT_SECONDS} 秒，已经中止。")
        output = (done.stdout + done.stderr).strip()
        return f"exit_code={done.returncode}\n{output[-self.MAX_OUTPUT:]}"


TOOLS: dict[str, Tool] = {tool.name: tool for tool in (ReadTool(), WriteTool(), EditTool(), BashTool())}

SYSTEM_PROMPT = """你是一个谨慎、简洁的中文 Coding Agent。

当前工作区：{workspace}

你有四个工具：read、write、edit、bash。列目录、搜索代码、查看 Git 状态、运行检查，都用 bash 完成。
先读再改：动手修改之前，先用 read 或 bash 把相关文件看清楚。
写入文件、修改文件和有副作用的命令，程序会弹窗让用户授权，你不需要自己承诺安全。
如果用户只是打招呼或者问概念，直接用文字回答，不要调用工具。
每次改完东西，用一两句话说明改了什么。"""


class CodingAgent:
    """Agent Loop 本体：模型提出工具调用 → 程序执行 → 结果回到模型，直到模型不再要工具。"""

    def __init__(
        self,
        workspace: Workspace,
        confirm: Callable[[str], bool],
        emit: Callable[[dict], None],
        client: OpenAI | None = None,
    ):
        self.workspace = workspace
        self.confirm = confirm
        self.emit = emit
        self.client = client or create_client()
        self.messages: list[dict] = [self._system_message()]
        # 用户随时可能喊停。停止只在"安全的缝隙"里生效：收流的间隙、每个工具执行之前。
        self._stop = threading.Event()

    def _system_message(self) -> dict:
        return {"role": "system", "content": SYSTEM_PROMPT.format(workspace=self.workspace.root)}

    def reset(self) -> None:
        """只清空上下文。工作区里已经改过的文件不会回滚。"""
        self.messages = [self._system_message()]

    def stop(self) -> None:
        """可以从别的线程调用。正在跑的那条 bash 命令不会被打断，但它之后的步骤都不会再执行。"""
        self._stop.set()

    def run(self, request: str) -> None:
        """跑完一轮任务。过程通过 emit 广播，不返回字符串。"""
        self._stop.clear()
        self.messages.append({"role": "user", "content": request})
        self.emit({"type": "user_message", "content": request})

        for _ in range(MAX_TURNS):
            message = self._ask_model()
            if self._stop.is_set():
                # 半截的 tool call 参数不完整，不能执行，也不能留在上下文里：
                # 接口要求每个 tool call 都有对应的结果，留下它下一轮请求会直接报错。
                if message["content"]:
                    self.messages.append({"role": "assistant", "content": message["content"]})
                    self.emit({"type": "assistant_message", "content": message["content"]})
                self.emit({"type": "stopped"})
                return
            self.messages.append(message)
            if message["content"]:
                self.emit({"type": "assistant_message", "content": message["content"]})
            # 模型这一轮没要工具，说明它认为信息够了，任务到此结束。
            if not message.get("tool_calls"):
                return
            for call in message["tool_calls"]:
                self._handle_tool_call(call)
            if self._stop.is_set():
                self.emit({"type": "stopped"})
                return

        self.emit({"type": "assistant_message", "content": f"连续执行了 {MAX_TURNS} 轮还没结束，先停下来等你确认。"})

    def _ask_model(self) -> dict:
        """流式请求模型：文字边生成边推给界面，最后拼回一条完整的 assistant 消息。

        不开流式的话，模型要把整段话（或整个 write 的文件内容）生成完才返回，
        用户只能对着空白干等；开了流式，第一个字出来就能看到。
        """
        self.emit({"type": "thinking"})
        stream = self.client.chat.completions.create(
            model=MODEL,
            messages=self.messages,
            tools=[tool.schema() for tool in TOOLS.values()],
            tool_choice="auto",
            stream=True,
        )
        content: list[str] = []
        reasoning: list[str] = []
        calls: dict[int, dict] = {}
        for chunk in stream:
            if self._stop.is_set():
                stream.close()
                break
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                content.append(delta.content)
                self.emit({"type": "assistant_delta", "content": delta.content})
            # 思考模式会把推理过程单独放在 reasoning_content 里，原样留着，下一轮请求还要带上。
            piece = getattr(delta, "reasoning_content", None)
            if piece:
                reasoning.append(piece)
            # tool call 也是一小块一小块到的：同一个 index 的 id、名字、参数片段要拼在一起。
            for part in delta.tool_calls or []:
                call = calls.setdefault(
                    part.index, {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}
                )
                if part.id:
                    call["id"] = part.id
                if part.function and part.function.name:
                    call["function"]["name"] += part.function.name
                    # 名字先到、参数后到。大文件的 write 参数可能要生成好几秒，先告诉界面在忙什么。
                    self.emit({"type": "tool_call_pending", "name": call["function"]["name"]})
                if part.function and part.function.arguments:
                    call["function"]["arguments"] += part.function.arguments

        message: dict = {"role": "assistant", "content": "".join(content)}
        if reasoning:
            message["reasoning_content"] = "".join(reasoning)
        if calls:
            message["tool_calls"] = [calls[index] for index in sorted(calls)]
        return message

    def _handle_tool_call(self, call: dict) -> None:
        name = call["function"]["name"]
        raw_arguments = call["function"]["arguments"] or "{}"
        try:
            arguments = json.loads(raw_arguments)
        except json.JSONDecodeError:
            arguments = None

        self.emit({
            "type": "tool_call",
            "call_id": call["id"],
            "name": name,
            "arguments": arguments if arguments is not None else raw_arguments,
        })

        if arguments is None:
            result = "Error: 工具参数不是合法 JSON，请重新生成。"
        else:
            result = self._execute(name, arguments)

        # 工具结果必须以 role=tool 回到消息列表，模型下一轮才看得到。
        self.messages.append({"role": "tool", "tool_call_id": call["id"], "content": result})
        self.emit({"type": "tool_result", "call_id": call["id"], "content": result})

    def _execute(self, name: str, arguments: dict) -> str:
        """工具的唯一执行入口：先问要不要授权，再真正执行，出错也只返回文字。"""
        # 同一轮里排在后面的工具，停止之后也要给一个结果，保证每个 tool call 都有回应。
        if self._stop.is_set():
            return "Blocked: 任务已停止。"
        tool = TOOLS.get(name)
        if tool is None:
            return f"Error: 没有名为 {name} 的工具。"
        try:
            action = tool.confirm_prompt(self.workspace, **arguments)
            if action and not self.confirm(action):
                return "Blocked: 任务已停止。" if self._stop.is_set() else "Blocked: 用户拒绝了这一步。"
            return tool.run(self.workspace, **arguments)
        except ToolError as exc:
            return f"Error: {exc}"
        except TypeError as exc:
            return f"Error: 工具参数不对：{exc}"
        except Exception as exc:
            # 工具崩了不能把整个 Agent 带崩，把错误交回模型让它自己想办法。
            return f"Error: 工具执行失败：{type(exc).__name__}: {exc}"
