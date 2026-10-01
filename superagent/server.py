"""生产 HTTP 服务（零第三方依赖，基于 stdlib http.server）。

端点：
    GET  /health     健康检查 + 运行时信息
    GET  /ping       LLM 连通性检测
    POST /run        执行任务 {text, auto_approve?}
    POST /chat       对话 {message}
    GET  /pending    待审批列表
    POST /approve    审批 {id, decision, feedback?}
    GET  /audit      审计日志查询

并发模型：ThreadingHTTPServer；审批队列线程安全，`/run` 遇到 S1 审批时
阻塞等待，操作员可用 `/approve` 并发放行，或 `auto_approve: true` 自动放行。
"""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from superagent import __version__
from superagent.core.orchestrator import Orchestrator
from superagent.core.runtime import Runtime
from superagent.hitl.approval import Decision, use_approver


def make_handler(runtime: Runtime, orchestrator: Orchestrator, auto_approve: bool = False):
    """返回绑定 runtime/orchestrator 的请求处理器类。"""

    class Handler(BaseHTTPRequestHandler):
        server_version = "SuperAgent/" + __version__

        # ---- 基础工具 ----
        def _send(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            if n <= 0:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                return {}

        def _approver(self, flag):
            if flag:
                return lambda req: (Decision.APPROVE, "auto")
            return None

        def log_message(self, *args) -> None:  # 静默默认日志，改用 telemetry
            pass

        # ---- GET ----
        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/health":
                return self._send({
                    "status": "ok",
                    "version": __version__,
                    "provider": runtime.config.llm.provider,
                    "model": getattr(runtime.llm, "config", None) and runtime.llm.config.model,
                    "role": runtime.config.security.default_role,
                })
            if path == "/ping":
                return self._ping()
            if path == "/pending":
                return self._send({"pending": [p.__dict__ for p in runtime.approvals.pending()]})
            if path == "/audit":
                qs = parse_qs(urlparse(self.path).query)
                rows = runtime.audit.query(limit=int(qs.get("limit", [50])[0]))
                return self._send({"events": rows})
            return self._send({"error": "not found"}, status=404)

        # ---- POST ----
        def do_POST(self):
            path = urlparse(self.path).path
            body = self._read_body()
            if path == "/run":
                return self._run(body)
            if path == "/chat":
                return self._chat(body)
            if path == "/approve":
                return self._approve(body)
            return self._send({"error": "not found"}, status=404)

        # ---- 业务 ----
        def _ping(self):
            from superagent.llm.backend import OpenAIBackend
            if isinstance(runtime.llm, OpenAIBackend):
                try:
                    reply = runtime.llm.complete([{"role": "user", "content": "回复 pong"}])
                    return self._send({"ok": True, "reply": reply[:120]})
                except Exception as exc:  # noqa: BLE001
                    return self._send({"ok": False, "error": str(exc)}, status=502)
            return self._send({"ok": True, "backend": type(runtime.llm).__name__})

        def _run(self, body):
            text = (body.get("text") or "").strip()
            if not text:
                return self._send({"error": "text 不能为空"}, status=400)
            flag = body.get("auto_approve", auto_approve)
            try:
                with use_approver(self._approver(flag)):
                    result = orchestrator.run(text)
                return self._send({"ok": True, "result": result})
            except Exception as exc:  # noqa: BLE001
                runtime.telemetry.log("error", f"任务失败: {exc}")
                return self._send({"ok": False, "error": str(exc)}, status=500)

        def _chat(self, body):
            message = (body.get("message") or "").strip()
            if not message:
                return self._send({"error": "message 不能为空"}, status=400)
            try:
                reply = runtime.llm.complete([{"role": "user", "content": message}])
                return self._send({"reply": reply})
            except Exception as exc:  # noqa: BLE001
                return self._send({"error": str(exc)}, status=502)

        def _approve(self, body):
            req_id = body.get("id")
            try:
                decision = Decision(body.get("decision", "approve"))
            except ValueError:
                return self._send({"error": "非法 decision"}, status=400)
            try:
                req = runtime.approvals.decide(req_id, decision, body.get("feedback", ""))
                return self._send({"ok": True, "id": req.id, "decision": req.decision.value})
            except KeyError:
                return self._send({"error": f"审批请求不存在: {req_id}"}, status=404)

    return Handler


def create_server(runtime: Runtime, host: str = "0.0.0.0", port: int = 8000, auto_approve: bool = False):
    orchestrator = Orchestrator(runtime)
    handler = make_handler(runtime, orchestrator, auto_approve=auto_approve)
    return ThreadingHTTPServer((host, port), handler), orchestrator


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(prog="superagent-serve", description="SuperAgent 生产服务")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--config", default=None)
    parser.add_argument("--auto-approve", action="store_true", help="默认自动放行（仅受信任环境）")
    args = parser.parse_args(argv)

    from superagent.core.config import Config
    from superagent.core.runtime import build_runtime

    config = Config.load(args.config)
    runtime = build_runtime(config)
    server, _ = create_server(runtime, args.host, args.port, auto_approve=args.auto_approve)
    runtime.telemetry.log("info", f"SuperAgent 服务启动 http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        runtime.close()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
