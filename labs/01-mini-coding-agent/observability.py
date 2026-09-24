"""把 AgentSession 现有事件接成 Phoenix 轨迹。

只有加载 Lab 06 时才导入 Phoenix 依赖，前面的实战仍只需基础依赖。
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import contextmanager, nullcontext
from typing import Any, Iterator

logger = logging.getLogger(__name__)
MAX_ATTRIBUTE_CHARS = 8_000
_observer: PhoenixTraceObserver | None = None


def enable_phoenix() -> PhoenixTraceObserver:
    """在 Agent 创建 OpenAI 兼容客户端之前注册 Phoenix。"""
    global _observer
    if _observer is not None:
        return _observer

    try:
        from phoenix.otel import register
    except ImportError as exc:
        raise SystemExit(
            "Lab 06 需要先安装扩展依赖："
            "uv sync --group observability"
        ) from exc

    # Python Agent 在宿主机运行，所以这里连接发布到本机的 Phoenix 端口。
    os.environ.setdefault("PHOENIX_COLLECTOR_ENDPOINT", "http://127.0.0.1:6006")
    if not os.environ["PHOENIX_COLLECTOR_ENDPOINT"].strip():
        os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = "http://127.0.0.1:6006"
    project_name = os.getenv("PHOENIX_PROJECT_NAME", "ai-is-simple-lab-06")
    provider = register(
        project_name=project_name,
        auto_instrument=True,
        batch=False,
    )
    _observer = PhoenixTraceObserver(provider.get_tracer("ai-is-simple.lab06"))
    return _observer


def current_observer() -> PhoenixTraceObserver | None:
    """如果可观测性扩展已启用，返回事件桥。"""
    return _observer


class PhoenixTraceObserver:
    """把现有 Agent 事件变成一条父 Trace 和多个子 Span。"""

    def __init__(self, tracer: Any):
        self.tracer = tracer
        self._run_span: Any = None
        self._model_context: Any = None
        self._tool_contexts: dict[str, tuple[Any, Any]] = {}
        self._turn_index = 0
        self._warned = False

    @contextmanager
    def agent_run(self, prompt: str, session_id: str = "") -> Iterator[None]:
        """让一次用户请求保持为当前上下文，使自动生成的模型 Span 成为它的子项。

        传入 session_id 时，同一段多轮对话的每条 Trace 都带上相同的 session.id，
        Phoenix 会把它们归到同一个 Session。
        """
        attributes = {
            "openinference.span.kind": "AGENT",
            "input.value": _bounded(prompt),
        }
        if session_id:
            attributes["session.id"] = session_id
        try:
            context = self.tracer.start_as_current_span("agent.run", attributes=attributes)
            span = context.__enter__()
        except Exception:
            self._warn_once("Could not start Phoenix trace; continuing without tracing.")
            yield
            return

        self._run_span = span
        self._turn_index = 0
        try:
            # using_session puts session.id into the context so auto-instrumented LLM spans carry it too.
            with _session_context(session_id):
                yield
        except Exception as exc:
            try:
                _mark_error(span, str(exc))
                span.record_exception(exc)
            except Exception:
                self._warn_once("Could not record the Agent error in Phoenix.")
            raise
        finally:
            self._close_nested_spans()
            self._run_span = None
            self._safe_close(context)

    def on_event(self, event: dict) -> None:
        """观察事件，同时保持网页收到的事件不变。"""
        try:
            self._on_event(event)
        except Exception:
            # A tracing outage must not stop the actual Agent task.
            self._warn_once("Phoenix tracing failed; continuing without further trace details.")
            self._close_nested_spans()

    def _on_event(self, event: dict) -> None:
        event_type = event.get("type")

        if event_type == "thinking":
            self._close_model_span()
            self._turn_index += 1
            self._model_context = self._start_span(
                "agent.model_turn",
                {
                    "openinference.span.kind": "AGENT",
                    "agent.turn.index": self._turn_index,
                },
            )
        elif event_type == "assistant_message":
            self._close_model_span()
            content = event.get("content")
            if self._run_span is not None and content:
                self._run_span.set_attribute("output.value", _bounded(content))
        elif event_type == "tool_call":
            # The model span ends after it has produced the complete tool call.
            self._close_model_span()
            call_id = str(event.get("call_id", ""))
            name = str(event.get("name", "unknown"))
            attributes = {
                "openinference.span.kind": "TOOL",
                "tool.name": name,
                "input.value": _bounded(event.get("arguments", {})),
                "input.mime_type": "application/json",
            }
            if call_id:
                attributes["tool.call.id"] = call_id
            self._tool_contexts[call_id] = self._start_span("agent.tool", attributes)
        elif event_type == "tool_result":
            call_id = str(event.get("call_id", ""))
            context_and_span = self._tool_contexts.pop(call_id, None)
            if context_and_span is None:
                return
            context, span = context_and_span
            result = str(event.get("content", ""))
            span.set_attribute("output.value", _bounded(result))
            exit_code = _bash_exit_code(result)
            if result.startswith("Error:") or (exit_code is not None and exit_code != 0):
                span.set_attribute("tool.outcome", "error")
                _mark_error(span, result[:MAX_ATTRIBUTE_CHARS])
            elif result.startswith("Blocked:"):
                span.set_attribute("tool.outcome", "blocked")
            else:
                span.set_attribute("tool.outcome", "success")
            self._safe_close(context)

    def _start_span(self, name: str, attributes: dict) -> tuple[Any, Any]:
        context = self.tracer.start_as_current_span(name, attributes=attributes)
        return context, context.__enter__()

    def _close_model_span(self) -> None:
        if self._model_context is not None:
            context, _span = self._model_context
            self._model_context = None
            self._safe_close(context)

    def _close_nested_spans(self) -> None:
        self._close_model_span()
        for context, _span in self._tool_contexts.values():
            self._safe_close(context)
        self._tool_contexts.clear()

    def _safe_close(self, context: Any) -> None:
        try:
            context.__exit__(None, None, None)
        except Exception:
            self._warn_once("Could not close a Phoenix span; continuing without further trace details.")

    def _warn_once(self, message: str) -> None:
        if not self._warned:
            logger.warning(message, exc_info=True)
            self._warned = True


def _session_context(session_id: str) -> Any:
    if not session_id:
        return nullcontext()
    from openinference.instrumentation import using_session

    return using_session(session_id)


def _bounded(value: Any) -> str:
    if isinstance(value, str):
        rendered = value
    else:
        rendered = json.dumps(value, ensure_ascii=False, default=str)
    if len(rendered) <= MAX_ATTRIBUTE_CHARS:
        return rendered
    return rendered[:MAX_ATTRIBUTE_CHARS] + "…（已截断）"


def _mark_error(span: Any, description: str) -> None:
    from opentelemetry.trace import Status, StatusCode

    span.set_status(Status(StatusCode.ERROR, description))


def _bash_exit_code(result: str) -> int | None:
    first_line, _, _ = result.partition("\n")
    if not first_line.startswith("exit_code="):
        return None
    try:
        return int(first_line.removeprefix("exit_code="))
    except ValueError:
        return None
