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


def make_handler(runtime: Runtime, orchestrator: Orchestrator, auto_approve: bool = False, api_key: str | None = None):
    """返回绑定 runtime/orchestrator 的请求处理器类。

    api_key：若设置（或环境变量 SUPERAGENT_API_KEY），则除 /health 外的端点需
    携带 X-API-Key 或 Authorization: Bearer 头，否则返回 401。
    """
    import os
    api_key = api_key if api_key is not None else os.environ.get("SUPERAGENT_API_KEY", "")

    class Handler(BaseHTTPRequestHandler):
        server_version = "SuperAgent/" + __version__

        # ---- 基础工具 ----
        def _authorize(self) -> bool:
            if not api_key:
                return True
            token = self.headers.get("X-API-Key", "")
            auth = self.headers.get("Authorization", "")
            if not token and auth.startswith("Bearer "):
                token = auth[7:]
            return token == api_key

        def _serve_index(self) -> None:
            """服务 Web 控制台静态页。"""
            from pathlib import Path
            index = Path(__file__).resolve().parent / "web" / "index.html"
            if not index.exists():
                return self._send({"error": "web ui not found"}, status=404)
            body = index.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
            if path in ("/", "/index.html"):
                return self._serve_index()
            if not self._authorize():
                return self._send({"error": "unauthorized"}, status=401)
            if path == "/ping":
                return self._ping()
            if path == "/pending":
                return self._send({"pending": [p.__dict__ for p in runtime.approvals.pending()]})
            if path == "/audit":
                qs = parse_qs(urlparse(self.path).query)
                rows = runtime.audit.query(limit=int(qs.get("limit", [50])[0]))
                return self._send({"events": rows})
            if path == "/skills":
                return self._send({"skills": runtime.skills.list()})
            if path == "/orders":
                return self._orders()
            if path.startswith("/media/"):
                return self._serve_media(path)
            return self._send({"error": "not found"}, status=404)

        # ---- POST ----
        def do_POST(self):
            path = urlparse(self.path).path
            if path == "/health":
                return self._send({"status": "ok"})
            if not self._authorize():
                return self._send({"error": "unauthorized"}, status=401)
            body = self._read_body()
            if path == "/run":
                return self._run(body)
            if path == "/chat":
                return self._chat(body)
            if path == "/approve":
                return self._approve(body)
            if path == "/upload":
                return self._upload(body)
            if path == "/image":
                return self._image(body)
            if path == "/video":
                return self._video(body)
            if path == "/skills":
                return self._skills(body)
            if path == "/video/edit":
                return self._video_edit(body)
            if path == "/video/fight":
                return self._video_fight(body)
            if path == "/video/dewatermark":
                return self._video_dewatermark(body)
            if path == "/video/compose":
                return self._video_compose(body)
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

        def _upload(self, body):
            """文件上传解析分析：{filename, content(base64)|text, analyze?}。"""
            import base64
            from superagent.files.parser import parse_bytes

            filename = body.get("filename") or "upload.txt"
            if body.get("content"):
                try:
                    raw = base64.b64decode(body["content"])
                except Exception:  # noqa: BLE001
                    return self._send({"error": "content 不是合法的 base64"}, status=400)
            elif body.get("text") is not None:
                raw = body["text"].encode("utf-8")
            else:
                return self._send({"error": "缺少 content(base64) 或 text"}, status=400)

            try:
                parsed = parse_bytes(filename, raw)
            except Exception as exc:  # noqa: BLE001
                return self._send({"ok": False, "error": f"解析失败: {exc}"}, status=422)

            # 记录来源（本地文件路径）
            runtime.sources.add("file", filename, filename)

            result = {
                "ok": True,
                "filename": filename,
                "kind": parsed.get("kind"),
                "meta": parsed.get("meta", {}),
                "preview": parsed.get("text", "")[:500],
                "chars": len(parsed.get("text", "")),
            }

            # 可选 LLM 分析
            if body.get("analyze"):
                prompt = body.get("prompt") or "请分析总结这份文档的核心内容、关键信息与结论。"
                try:
                    analysis = runtime.llm.complete([
                        {"role": "system", "content": "你是资深文档分析师。"},
                        {"role": "user", "content": f"{prompt}\n\n文档《{filename}》内容：\n{parsed['text'][:8000]}"},
                    ])
                    result["analysis"] = analysis
                except Exception as exc:  # noqa: BLE001
                    result["analysis_error"] = str(exc)
            return self._send(result)

        def _image(self, body):
            """文生图（智谱 CogView）。{prompt, count?} -> {urls[]}（多候选）"""
            prompt = (body.get("prompt") or "").strip()
            if not prompt:
                return self._send({"error": "prompt 不能为空"}, status=400)
            count = max(1, min(int(body.get("count", 1) or 1), 4))
            try:
                from superagent.llm.backend import generate_image
                urls = [generate_image(prompt) for _ in range(count)]
                return self._send({"ok": True, "urls": urls, "prompt": prompt, "count": count})
            except Exception as exc:  # noqa: BLE001
                return self._send({"ok": False, "error": str(exc)}, status=502)

        def _video(self, body):
            """文生视频（智谱 CogVideoX，异步提交+轮询，耗时约 1-3 分钟）。{prompt} -> {url}"""
            prompt = (body.get("prompt") or "").strip()
            if not prompt:
                return self._send({"error": "prompt 不能为空"}, status=400)
            try:
                from superagent.llm.backend import generate_video
                url = generate_video(prompt)
                return self._send({"ok": True, "url": url, "prompt": prompt})
            except Exception as exc:  # noqa: BLE001
                return self._send({"ok": False, "error": str(exc)}, status=502)

        def _skills(self, body):
            """技能管理：{action: add|toggle|remove, ...}"""
            from dataclasses import asdict
            action = body.get("action", "add")
            if action == "add":
                name = (body.get("name") or "").strip()
                if not name:
                    return self._send({"error": "name 不能为空"}, status=400)
                desc = body.get("description", "")
                skill = runtime.skills.add(name, desc, body.get("category", "自定义"))
                if body.get("forge"):
                    try:
                        from superagent.core.toolforge import ToolForge
                        ToolForge().forge(runtime, "custom_" + name.lower().replace(" ", "_")[:20], desc)
                        skill.description = desc + "（已部署工具）"
                    except Exception as exc:  # noqa: BLE001
                        return self._send({"ok": True, "skill": asdict(skill), "forge_error": str(exc)})
                return self._send({"ok": True, "skill": asdict(skill)})
            if action == "toggle":
                ok = runtime.skills.set_enabled(body.get("id", ""), bool(body.get("enabled", True)))
                return self._send({"ok": ok})
            if action == "remove":
                ok = runtime.skills.remove(body.get("id", ""))
                return self._send({"ok": ok})
            return self._send({"error": "未知 action"}, status=400)

        def _orders(self):
            """接单检索：{category?} -> {orders: [{title,url,category}]}"""
            qs = parse_qs(urlparse(self.path).query)
            category = qs.get("category", ["开发"])[0]
            from superagent.layers.layer2_network import NetworkLayer
            try:
                orders = NetworkLayer().search_orders(category, max_results=10)
                return self._send({"ok": True, "orders": orders})
            except Exception as exc:  # noqa: BLE001
                return self._send({"ok": False, "error": str(exc)}, status=502)

        def _serve_media(self, path):
            """服务 media 目录下的成片文件。"""
            from pathlib import Path
            name = path.split("/media/", 1)[-1]
            if "/" in name or ".." in name:
                return self._send({"error": "bad path"}, status=400)
            media_dir = runtime.config.project_root / "data" / "media"
            f = media_dir / name
            if not f.exists():
                return self._send({"error": "not found"}, status=404)
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _video_edit(self, body):
            """视频剪辑：{clips:[urls], subtitles?:[lines], grade?, bgm?} -> {url}"""
            clips = body.get("clips") or []
            if not clips or not isinstance(clips, list):
                return self._send({"error": "clips 不能为空（视频 URL 列表）"}, status=400)
            import uuid
            from superagent.media.video_editor import compose
            media_dir = runtime.config.project_root / "data" / "media"
            media_dir.mkdir(parents=True, exist_ok=True)
            name = f"composed_{uuid.uuid4().hex[:10]}.mp4"
            try:
                compose(
                    clips,
                    media_dir / name,
                    subtitle_lines=body.get("subtitles"),
                    grade=body.get("grade", "warm"),
                    bgm_url=body.get("bgm"),
                )
                return self._send({"ok": True, "url": f"/media/{name}", "name": name})
            except Exception as exc:  # noqa: BLE001
                return self._send({"ok": False, "error": str(exc)}, status=502)

        def _video_fight(self, body):
            """打斗镜头生成：{style?: street|martial|military, description?} -> {url}"""
            from superagent.media.fight import build_fight_prompt, generate_fight
            style = body.get("style", "street")
            desc = (body.get("description") or "").strip()
            try:
                url = generate_fight(style, desc)
                runtime.audit.record(
                    subject=runtime.config.security.default_role,
                    action="video.fight.generate", level="S3", result="success", obj=style,
                )
                return self._send({"ok": True, "url": url, "prompt": build_fight_prompt(style, desc)})
            except Exception as exc:  # noqa: BLE001
                return self._send({"ok": False, "error": str(exc)}, status=502)

        def _video_dewatermark(self, body):
            """合规去水印（仅限自有生成素材）：{url, region?: [x,y,w,h]} -> {url}"""
            media_url = (body.get("url") or "").strip()
            if not media_url:
                return self._send({"error": "url 不能为空"}, status=400)
            region = body.get("region") or [10, 10, 200, 80]
            if not (isinstance(region, list) and len(region) == 4):
                return self._send({"error": "region 需为 [x,y,w,h]"}, status=400)
            import uuid
            from superagent.media.watermark import remove_watermark
            media_dir = runtime.config.project_root / "data" / "media"
            media_dir.mkdir(parents=True, exist_ok=True)
            name = f"clean_{uuid.uuid4().hex[:10]}.mp4"
            try:
                remove_watermark(media_url, media_dir / name, tuple(int(v) for v in region))
                runtime.audit.record(
                    subject=runtime.config.security.default_role,
                    action="watermark.remove.self", level="S3", result="success", obj=media_url[:80],
                )
                return self._send({"ok": True, "url": f"/media/{name}", "name": name})
            except Exception as exc:  # noqa: BLE001
                return self._send({"ok": False, "error": str(exc)}, status=502)

        def _video_compose(self, body):
            """多场景片段合成成片：{scenes:[{type,description,view?,style?}], grade?} -> {url}"""
            scenes = body.get("scenes") or []
            if not scenes or not isinstance(scenes, list):
                return self._send({"error": "scenes 不能为空"}, status=400)
            import uuid
            from superagent.media.video_production import compose_scenes
            media_dir = runtime.config.project_root / "data" / "media"
            media_dir.mkdir(parents=True, exist_ok=True)
            name = f"film_{uuid.uuid4().hex[:10]}.mp4"
            try:
                compose_scenes(scenes, media_dir / name, grade=body.get("grade", "warm"))
                return self._send({"ok": True, "url": f"/media/{name}", "name": name})
            except Exception as exc:  # noqa: BLE001
                return self._send({"ok": False, "error": str(exc)}, status=502)

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
