"""Langfuse LLM 可观测性追踪（修订版第 12 节可观测性）。

通过 Langfuse 公开 ingestion REST API 上报 trace/generation，零 SDK 依赖。
认证：Basic(pk:sk)。配置：LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY。
默认 host=https://cloud.langfuse.com。缺少任一密钥则自动禁用（不阻塞主流程）。
"""
from __future__ import annotations

import base64
import json
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

from superagent.core.errors import LLMBackendError


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class LangfuseClient:
    def __init__(self, public_key: str = "", secret_key: str = "", host: str = "https://cloud.langfuse.com"):
        import os
        self.public_key = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        self.secret_key = secret_key or os.environ.get("LANGFUSE_SECRET_KEY", "")
        self.host = (host or os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")).rstrip("/")
        self.enabled = bool(self.public_key and self.secret_key)
        self._lock = threading.Lock()

    def _auth_header(self) -> str:
        token = base64.b64encode(f"{self.public_key}:{self.secret_key}".encode()).decode()
        return f"Basic {token}"

    def _send_batch(self, events: list[dict]) -> None:
        if not self.enabled or not events:
            return
        url = self.host + "/api/public/ingestion"
        payload = json.dumps({"batch": events}).encode("utf-8")
        req = urllib.request.Request(
            url, data=payload, method="POST",
            headers={"Content-Type": "application/json", "Authorization": self._auth_header()},
        )
        try:
            with self._lock:
                urllib.request.urlopen(req, timeout=10)
        except (urllib.error.URLError, OSError):
            # 可观测性失败绝不影响主流程
            pass

    def record_task(self, name: str, input_data: dict | str | None = None, output_data: dict | str | None = None) -> str:
        """记录一次任务 trace，返回 trace_id。"""
        trace_id = uuid.uuid4().hex
        if not self.enabled:
            return trace_id
        event = {
            "id": trace_id,
            "type": "trace-create",
            "timestamp": _now(),
            "body": {
                "name": name,
                "input": input_data,
                "output": output_data,
                "metadata": {"framework": "superagent"},
            },
        }
        self._send_batch([event])
        return trace_id

    def record_generation(self, trace_id: str, name: str, model: str, input_data, output_data, usage: dict | None = None) -> str:
        """记录一次 LLM 调用 generation，挂到 trace 下。"""
        gen_id = uuid.uuid4().hex
        if not self.enabled:
            return gen_id
        body: dict = {
            "traceId": trace_id,
            "name": name,
            "input": input_data,
            "output": output_data,
            "model": model,
        }
        if usage:
            body["usage"] = usage
        event = {
            "id": gen_id,
            "type": "generation-create",
            "timestamp": _now(),
            "body": body,
        }
        self._send_batch([event])
        return gen_id


def build_langfuse() -> LangfuseClient:
    return LangfuseClient()


# ---- 模块级单例 + 上下文追踪（供 LLM 后端/编排器无侵入埋点）----
import contextvars  # noqa: E402

_client: LangfuseClient | None = None
_current_trace: contextvars.ContextVar[str] = contextvars.ContextVar("langfuse_trace_id", default="")


def client() -> LangfuseClient:
    global _client
    if _client is None:
        _client = build_langfuse()
    return _client


def set_trace(trace_id: str):
    return _current_trace.set(trace_id)


def reset_trace(token) -> None:
    _current_trace.reset(token)


def get_trace() -> str:
    return _current_trace.get()


def log_generation(name: str, model: str, input_data, output_data, usage: dict | None = None) -> None:
    """在当前 trace 上下文中记录一次 LLM 调用（无 trace 或未启用则静默跳过）。"""
    tid = get_trace()
    if tid and client().enabled:
        client().record_generation(tid, name, model, input_data, output_data, usage)
