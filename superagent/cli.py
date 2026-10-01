"""命令行入口。

用法示例：
    python -m superagent run "帮我做一个登录页面"            # 完整流水线（终审交互式提示）
    python -m superagent run "hi"                            # 简短输入 → 枚举可能性
    python -m superagent audit --limit 20                    # 查询审计日志
    python -m superagent pending                              # 列出待审批
    python -m superagent approve <id> approve                 # 后台模式审批
    python -m superagent sysinfo                              # 系统信息
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from superagent.core.config import Config
from superagent.core.orchestrator import Orchestrator
from superagent.core.runtime import build_runtime
from superagent.hitl.approval import Decision
from superagent.layers.layer1_sysops import list_processes, memory_info


def _interactive_approver(req):
    """交互式审批回调：在终端内联询问人工决策。"""
    print(f"\n[审批] 动作={req.action}  对象={req.resource}")
    print(f"       原因={req.reason}")
    while True:
        ans = input("放行(approve) / 修改(revise) / 驳回(reject)？默认 approve: ").strip().lower() or "approve"
        if ans in {"approve", "a", "y"}:
            return Decision.APPROVE, ""
        if ans in {"revise", "r"}:
            feedback = input("修改意见: ").strip()
            return Decision.REVISE, feedback
        if ans in {"reject", "x", "n"}:
            feedback = input("驳回原因: ").strip()
            return Decision.REJECT, feedback
        print("输入无效，请重试。")


def _load_runtime(args) -> tuple:
    config = Config.load(args.config)
    runtime = build_runtime(config)
    return config, runtime


def cmd_run(args) -> int:
    config, runtime = _load_runtime(args)
    if args.auto_approve:
        runtime.approver = lambda req: (Decision.APPROVE, "auto")
    else:
        runtime.approver = _interactive_approver
    orch = Orchestrator(runtime)
    try:
        result = orch.run(args.text, project_root=args.project_dir)
    except Exception as exc:  # noqa: BLE001
        runtime.telemetry.log("error", f"任务失败: {exc}")
        print(f"[失败] {exc}", file=sys.stderr)
        return 1
    finally:
        runtime.close()
    import json
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


def cmd_audit(args) -> int:
    config, runtime = _load_runtime(args)
    rows = runtime.audit.query(limit=args.limit, action=args.action, level=args.level)
    runtime.close()
    for r in rows:
        print(f"{r['ts']} [{r['level']}] {r['action']} -> {r['result']}  obj={r['object']}")
    return 0


def cmd_pending(args) -> int:
    config, runtime = _load_runtime(args)
    pending = runtime.approvals.pending()
    runtime.close()
    if not pending:
        print("无待审批请求。")
        return 0
    for p in pending:
        print(f"{p.id}  {p.action}  对象={p.resource}  原因={p.reason}")
    return 0


def cmd_approve(args) -> int:
    config, runtime = _load_runtime(args)
    try:
        decision = Decision(args.decision)
    except ValueError:
        print(f"非法决策: {args.decision}", file=sys.stderr)
        return 2
    try:
        req = runtime.approvals.decide(args.request_id, decision, args.feedback or "")
        print(f"已处理 {req.id}: {req.decision.value}")
    except KeyError as exc:
        print(f"[错误] {exc}", file=sys.stderr)
        return 1
    finally:
        runtime.close()
    return 0


def cmd_sysinfo(args) -> int:
    import platform
    print("platform:", platform.platform())
    print("python:", platform.python_version())
    print("memory:", memory_info())
    if args.processes:
        print("top processes:")
        for p in list_processes(args.processes):
            print(f"  {p['name']:30s} {p['pid']:>8s}  {p['mem_kb']} KB")
    return 0


def cmd_chat(args) -> int:
    config, runtime = _load_runtime(args)
    reply = runtime.llm.complete([{"role": "user", "content": args.message}])
    runtime.close()
    print(reply)
    return 0


def cmd_ping(args) -> int:
    config, runtime = _load_runtime(args)
    from superagent.llm.backend import MockBackend, NullBackend, OpenAIBackend

    backend = runtime.llm
    if isinstance(backend, OpenAIBackend):
        if not backend.api_key:
            print(f"[未配置] provider=openai 但缺少 API Key。请设置环境变量 {config.llm.api_key_env} 或 OPENAI_API_KEY，"
                  f"或写入项目根目录 .env 文件。")
            runtime.close()
            return 1
        print(f"provider={config.llm.provider}  model={backend.config.model}  base_url={backend.config.base_url}")
        try:
            reply = backend.complete([{"role": "user", "content": "请只回复两个字：pong"}])
            print(f"[连接成功] {reply[:120]}")
            runtime.close()
            return 0
        except Exception as exc:  # noqa: BLE001
            print(f"[连接失败] {exc}")
            runtime.close()
            return 1
    if isinstance(backend, (MockBackend, NullBackend)):
        print(f"[回退后端] {type(backend).__name__}（provider={config.llm.provider}）—— 未接入真实 OpenAI。")
        runtime.close()
        return 0
    runtime.close()
    return 0


def cmd_serve(args) -> int:
    from superagent.server import main as serve_main
    return serve_main(["--host", args.host, "--port", str(args.port)]
                      + (["--config", args.config] if args.config else [])
                      + (["--auto-approve"] if args.auto_approve else []))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="superagent", description="SuperAgent 生产/企业级自主 Agent")
    parser.add_argument("--config", default=None, help="配置文件路径")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="执行任务")
    p_run.add_argument("text", help="用户输入")
    p_run.add_argument("--project-dir", default=None, help="项目根目录")
    p_run.add_argument("--auto-approve", action="store_true", help="自动放行（仅演示/受信任环境）")
    p_run.set_defaults(func=cmd_run)

    p_audit = sub.add_parser("audit", help="查询审计日志")
    p_audit.add_argument("--limit", type=int, default=50)
    p_audit.add_argument("--action", default=None)
    p_audit.add_argument("--level", default=None)
    p_audit.set_defaults(func=cmd_audit)

    p_pending = sub.add_parser("pending", help="列出待审批")
    p_pending.set_defaults(func=cmd_pending)

    p_approve = sub.add_parser("approve", help="后台模式审批")
    p_approve.add_argument("request_id")
    p_approve.add_argument("decision", choices=["approve", "revise", "reject"])
    p_approve.add_argument("--feedback", default=None)
    p_approve.set_defaults(func=cmd_approve)

    p_sys = sub.add_parser("sysinfo", help="系统信息")
    p_sys.add_argument("--processes", type=int, default=0)
    p_sys.set_defaults(func=cmd_sysinfo)

    p_chat = sub.add_parser("chat", help="与 LLM 对话（验证真实接入）")
    p_chat.add_argument("message", help="消息内容")
    p_chat.set_defaults(func=cmd_chat)

    p_ping = sub.add_parser("ping", help="检测 OpenAI 连接与密钥有效性")
    p_ping.set_defaults(func=cmd_ping)

    p_serve = sub.add_parser("serve", help="启动生产 HTTP 服务")
    p_serve.add_argument("--host", default="0.0.0.0")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--auto-approve", action="store_true")
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
