#!/usr/bin/env python3
"""实战篇 01 的本地网页界面：把 Agent Loop 和权限请求变成可见事件。"""

from __future__ import annotations

import argparse
import importlib.util
import json
import mimetypes
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse


LAB_DIR = Path(__file__).resolve().parent
WEB_DIR = LAB_DIR / "web"


def load_agent_module():
    """加载同目录的 agent.py，让终端版和网页版本共用同一套安全工具。"""
    spec = importlib.util.spec_from_file_location("mini_coding_agent", LAB_DIR / "agent.py")
    if not spec or not spec.loader:
        raise RuntimeError("无法加载 agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


agent_module = load_agent_module()


class WebSession:
    """管理一个浏览器会话，并把 Agent 内部事件保存成可轮询的时间线。"""

    def __init__(self):
        self.condition = threading.Condition()
        self.events: list[dict] = []
        self.next_event_id = 0
        self.pending_permissions: dict[str, bool | None] = {}
        self.running = False
        self.agent = agent_module.CodingAgent(
            workspace=agent_module.PROJECT_ROOT,
            session=agent_module.SessionStore(None),
            confirm_callback=self.ask_permission,
            event_callback=self.publish,
        )

    def publish(self, event: dict) -> None:
        """给每个事件编号，前端只需要请求上次编号之后的新事件。"""
        with self.condition:
            self.next_event_id += 1
            self.events.append({"id": self.next_event_id, "time": time.time(), **event})
            # 保留最近一段事件，避免一个长时间运行的页面无限增长内存。
            self.events = self.events[-500:]
            self.condition.notify_all()

    def snapshot(self, after: int = 0) -> dict:
        with self.condition:
            return {
                "events": [event for event in self.events if event["id"] > after],
                "running": self.running,
                "workspace": str(agent_module.PROJECT_ROOT),
            }

    def ask_permission(self, action: str) -> bool:
        """阻塞 Agent 线程，直到用户在网页上点击允许或拒绝。"""
        permission_id = uuid.uuid4().hex
        with self.condition:
            self.pending_permissions[permission_id] = None
        self.publish(
            {
                "type": "permission_requested",
                "permission_id": permission_id,
                "action": action,
            }
        )

        deadline = time.monotonic() + 300
        with self.condition:
            while self.pending_permissions[permission_id] is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self.pending_permissions[permission_id] = False
                    break
                self.condition.wait(timeout=remaining)
            allowed = bool(self.pending_permissions.pop(permission_id))

        self.publish(
            {
                "type": "permission_resolved",
                "permission_id": permission_id,
                "allowed": allowed,
            }
        )
        return allowed

    def resolve_permission(self, permission_id: str, allowed: bool) -> bool:
        with self.condition:
            if permission_id not in self.pending_permissions:
                return False
            self.pending_permissions[permission_id] = allowed
            self.condition.notify_all()
            return True

    def submit(self, prompt: str) -> bool:
        prompt = prompt.strip()
        if not prompt:
            return False
        with self.condition:
            if self.running:
                return False
            self.running = True
        threading.Thread(target=self._run, args=(prompt,), daemon=True).start()
        return True

    def _run(self, prompt: str) -> None:
        try:
            self.agent.run(prompt)
        except Exception as exc:  # 把异常也放进时间线，而不是让网页静默卡住。
            self.publish({"type": "error", "content": f"{type(exc).__name__}: {exc}"})
        finally:
            with self.condition:
                self.running = False
            self.publish({"type": "run_finished"})

    def reset(self) -> None:
        with self.condition:
            if self.running:
                return
        self.agent.reset()
        self.publish({"type": "reset"})


SESSION = WebSession()


class RequestHandler(BaseHTTPRequestHandler):
    """只提供本地静态页面和几个 JSON 接口，不引入额外 Web 框架。"""

    server_version = "MiniCodingAgent/0.1"

    def log_message(self, format: str, *args) -> None:
        # 默认不把每次轮询都刷满终端；启动信息仍会在 main() 中打印。
        return

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if length > 1_000_000:
            raise ValueError("请求体不能超过 1MB")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/events":
            query = parse_qs(parsed.query)
            try:
                after = int(query.get("after", ["0"])[0])
            except ValueError:
                after = 0
            self.send_json(SESSION.snapshot(after))
            return

        relative = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
        target = (WEB_DIR / relative).resolve()
        if not target.is_relative_to(WEB_DIR.resolve()) or not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        try:
            payload = self.read_json()
            if self.path == "/api/message":
                accepted = SESSION.submit(str(payload.get("message", "")))
                if not accepted:
                    self.send_json({"error": "当前已有任务运行，或消息为空。"}, HTTPStatus.CONFLICT)
                    return
                self.send_json({"accepted": True}, HTTPStatus.ACCEPTED)
                return
            if self.path == "/api/permission":
                permission_id = str(payload.get("permission_id", ""))
                allowed = bool(payload.get("allowed", False))
                resolved = SESSION.resolve_permission(permission_id, allowed)
                if not resolved:
                    self.send_json({"error": "权限请求不存在或已经处理。"}, HTTPStatus.NOT_FOUND)
                    return
                self.send_json({"resolved": True})
                return
            if self.path == "/api/reset":
                SESSION.reset()
                self.send_json({"reset": True})
                return
            self.send_json({"error": "未知接口。"}, HTTPStatus.NOT_FOUND)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


def main() -> None:
    parser = argparse.ArgumentParser(description="启动简易 Coding Agent 的本地网页界面")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址，默认只允许本机访问")
    parser.add_argument("--port", type=int, default=8765, help="监听端口，默认 8765")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), RequestHandler)
    print(f"Agent Workbench 已启动：http://{args.host}:{args.port}")
    print(f"工作区：{agent_module.PROJECT_ROOT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
