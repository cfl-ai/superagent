"""运行时装配：将配置 + 四大基座 + 各层依赖连接成一个 Runtime。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from superagent.core.config import Config
from superagent.core.events import EventBus
from superagent.core.registry import ToolRegistry
from superagent.core.skills import SkillRegistry
from superagent.hitl.approval import ApprovalQueue
from superagent.llm.backend import LLMBackend, build_backend
from superagent.observability.telemetry import Telemetry
from superagent.quality.rubric import Scorer
from superagent.security.audit import AuditLogger
from superagent.security.auth import AuthManager
from superagent.security.permissions import PermissionPolicy
from superagent.security.snapshot import SnapshotManager
from superagent.sourcing.registry import SourceRegistry


@dataclass
class Runtime:
    config: Config
    audit: AuditLogger
    snapshots: SnapshotManager
    policy: PermissionPolicy
    auth: AuthManager
    sources: SourceRegistry
    telemetry: Telemetry
    approvals: ApprovalQueue
    tools: ToolRegistry
    skills: SkillRegistry
    llm: LLMBackend
    events: EventBus
    scorer: Scorer
    # 可选：交互式/注入式审批回调 ApprovalRequest -> (Decision, feedback)
    approver: object = None

    def close(self) -> None:
        self.telemetry.close()
        self.audit.close()


def build_runtime(config: Config) -> Runtime:
    config.ensure_dirs()
    telemetry = Telemetry(
        config.log_dir,
        heartbeat_interval_s=config.observability.heartbeat_interval_s,
    )
    audit = AuditLogger(config.audit_db_path)
    policy = PermissionPolicy(config.security)
    runtime = Runtime(
        config=config,
        audit=audit,
        snapshots=SnapshotManager(config.snapshot_dir),
        policy=policy,
        auth=AuthManager(),
        sources=SourceRegistry(config.manifest_path),
        telemetry=telemetry,
        approvals=ApprovalQueue(config.approvals_path, timeout_s=config.hitl.timeout_s),
        tools=ToolRegistry(),
        skills=SkillRegistry(),
        llm=build_backend(config.llm),
        events=EventBus(),
        scorer=Scorer(),
    )
    runtime.events.subscribe("action", lambda e, p: telemetry.metrics.incr("actions"))
    return runtime
