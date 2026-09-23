#!/usr/bin/env python3
"""把 Agent 的每一步搬到浏览器里。

只用 Python 标准库：http.server 提供几个接口，SSE（Server-Sent Events，
服务器单向往页面推消息的标准做法）负责把事件实时送到页面上。

三个类各管一件事：
  EventLog        记录并广播事件
  PermissionGate  把 Agent 线程的"要不要执行"变成网页上的一次点击
  AgentSession    把 Agent、事件流、授权开关装在一起
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from agent import CodingAgent, Workspace

INDEX_FILE = Path(__file__).resolve().parent / "web" / "index.html"


class EventLog:
    """带编号的事件列表。编号让页面刷新或断线重连之后能接着上次的位置读。"""

    def __init__(self):
        self._condition = threading.Condition()
        self._events: list[dict] = []

    def publish(self, event: dict) -> None:
        with self._condition:
            # 时间戳让界面能显示每一步发生在什么时候、工具跑了多久。
            self._events.append({"id": len(self._events) + 1, "time": time.time(), **event})
            self._condition.notify_all()

    def read_after(self, cursor: int, timeout: float) -> list[dict]:
        """返回编号大于 cursor 的事件。没有新事件就等一会儿，超时返回空列表。"""
        with self._condition:
            if len(self._events) <= cursor:
                self._condition.wait(timeout=timeout)
            return self._events[cursor:]


class PermissionGate:
    """Agent 线程在这里停下来，等网页上点"允许"或"拒绝"。"""

    TIMEOUT_SECONDS = 300

    def __init__(self, events: EventLog):
        self.events = events
        self._condition = threading.Condition()
        self._pending: dict[str, bool | None] = {}

    def ask(self, action: str) -> bool:
        """给 CodingAgent 用的 confirm 回调。会阻塞，直到页面给出答复。"""
        request_id = uuid.uuid4().hex
        with self._condition:
            self._pending[request_id] = None
        self.events.publish({"type": "permission_request", "request_id": request_id, "action": action})

        deadline = time.monotonic() + self.TIMEOUT_SECONDS
        with self._condition:
            while self._pending[request_id] is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    # 没人回应就当作拒绝：宁可不做，也不要背着用户动文件。
                    self._pending[request_id] = False
                    break
                self._condition.wait(remaining)
            allowed = bool(self._pending.pop(request_id))

        self.events.publish({"type": "permission_result", "request_id": request_id, "allowed": allowed})
        return allowed

    def resolve(self, request_id: str, allowed: bool) -> bool:
        """页面点击后调用。找不到对应请求说明它已经超时或被处理过了。"""
        with self._condition:
            if request_id not in self._pending:
                return False
            self._pending[request_id] = allowed
            self._condition.notify_all()
            return True


class AgentSession:
    """一次浏览器会话：一个 Agent、一条事件流、一个授权开关。"""

    def __init__(self, workspace: Workspace):
        self.events = EventLog()
        self.gate = PermissionGate(self.events)
        self.agent = CodingAgent(workspace, confirm=self.gate.ask, emit=self.events.publish)
        self._lock = threading.Lock()
        self._running = False
        # 第一条事件带上工作区路径，页面一连上就知道自己在操作哪个目录。
        self.events.publish({"type": "ready", "workspace": str(workspace.root)})

    def submit(self, prompt: str) -> bool:
        """同一时间只跑一个任务。任务放到后台线程，HTTP 请求立刻返回。"""
        prompt = prompt.strip()
        with self._lock:
            if self._running or not prompt:
                return False
            self._running = True
        self.events.publish({"type": "busy"})
        threading.Thread(target=self._run, args=(prompt,), daemon=True).start()
        return True

    def _run(self, prompt: str) -> None:
        try:
            self.agent.run(prompt)
        except Exception as exc:
            # 异常也要出现在时间线上，不然页面只会一直显示"运行中"。
            self.events.publish({"type": "error", "content": f"{type(exc).__name__}: {exc}"})
        finally:
            with self._lock:
                self._running = False
            self.events.publish({"type": "idle"})

    def reset(self) -> bool:
        with self._lock:
            if self._running:
                return False
        self.agent.reset()
        self.events.publish({"type": "reset"})
        return True


class RequestHandler(BaseHTTPRequestHandler):
    """四个接口：一个页面、一条事件流、发消息、答复授权。"""

    protocol_version = "HTTP/1.1"
    server_version = "MiniCodingAgent/2.0"
    SSE_HEARTBEAT_SECONDS = 15

    @property
    def session(self) -> AgentSession:
        return self.server.session

    def log_message(self, *args) -> None:
        # 事件流是长连接，默认日志会把终端刷满。
        pass

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/events":
            self._stream_events()
        elif path in ("/", "/index.html"):
            self._send_bytes(INDEX_FILE.read_bytes(), "text/html; charset=utf-8")
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        try:
            payload = self._read_json()
        except ValueError:
            self._send_json({"error": "请求体不是合法 JSON。"}, HTTPStatus.BAD_REQUEST)
            return

        if self.path == "/api/message":
            accepted = self.session.submit(str(payload.get("message", "")))
            self._send_json({"accepted": accepted}, HTTPStatus.OK if accepted else HTTPStatus.CONFLICT)
        elif self.path == "/api/permission":
            resolved = self.session.gate.resolve(
                str(payload.get("request_id", "")), bool(payload.get("allowed"))
            )
            self._send_json({"resolved": resolved}, HTTPStatus.OK if resolved else HTTPStatus.NOT_FOUND)
        elif self.path == "/api/reset":
            done = self.session.reset()
            self._send_json({"reset": done}, HTTPStatus.OK if done else HTTPStatus.CONFLICT)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def _stream_events(self) -> None:
        """SSE：把新事件一条条写进这个连接，直到页面关掉。"""
        query = parse_qs(urlparse(self.path).query)
        try:
            cursor = int(query.get("after", ["0"])[0])
        except ValueError:
            cursor = 0

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        try:
            while True:
                events = self.session.events.read_after(cursor, self.SSE_HEARTBEAT_SECONDS)
                if not events:
                    # 心跳既能防止中间层掐断连接，也能顺便发现页面已经关了。
                    self.wfile.write(b": keep-alive\n\n")
                else:
                    for event in events:
                        line = json.dumps(event, ensure_ascii=False)
                        self.wfile.write(f"data: {line}\n\n".encode("utf-8"))
                    cursor = events[-1]["id"]
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("请求体太大。")
        if length == 0:
            return {}  # /api/reset 不需要参数，空请求体是正常的。
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        self._send_bytes(
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
            status,
        )

    def _send_bytes(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


class AgentServer(ThreadingHTTPServer):
    """把 session 挂在 server 上，handler 通过 self.server.session 拿，不用全局变量。"""

    daemon_threads = True

    def __init__(self, address: tuple[str, int], session: AgentSession):
        super().__init__(address, RequestHandler)
        self.session = session


def main() -> None:
    project_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="带网页界面的最小 Coding Agent")
    parser.add_argument("--workspace", type=Path, default=project_root, help="Agent 能操作的目录，默认是本项目根目录")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认只允许本机访问")
    parser.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    args = parser.parse_args()

    root = args.workspace.expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"工作区不存在：{root}")

    session = AgentSession(Workspace(root))
    server = AgentServer((args.host, args.port), session)
    print(f"Agent 已启动：http://{args.host}:{args.port}")
    print(f"工作区：{root}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
