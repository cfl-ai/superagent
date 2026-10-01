"""四级操作分级（S0-S3）与角色权限门控。

对应修订版第 6.2 节：
- S0 禁止   —— 硬阻断 + 上报
- S1 审批   —— 强制人工审批
- S2 白名单 —— 自动 + 审计
- S3 自动审计 —— 无风险只读，自动 + 审计

分级通过前缀匹配配置（见 :class:`SecurityConfig`），同时内置默认分类表，
可扩展。任何未匹配的操作默认归入 S3（安全默认：只读）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from superagent.core.config import SecurityConfig
from superagent.core.errors import PermissionDenied


class ActionLevel(str, Enum):
    S0_BLOCKED = "S0"      # 禁止
    S1_APPROVAL = "S1"     # 需审批
    S2_WHITELIST = "S2"    # 白名单自动
    S3_AUTO = "S3"         # 自动审计

    @property
    def requires_approval(self) -> bool:
        return self is ActionLevel.S1_APPROVAL

    @property
    def is_blocked(self) -> bool:
        return self is ActionLevel.S0_BLOCKED


class Role(str, Enum):
    VISITOR = "visitor"
    OPERATOR = "operator"
    ADMIN = "admin"


@dataclass(frozen=True)
class Action:
    """一次待分级/待执行的动作。"""

    name: str
    resource: str = ""
    metadata: dict | None = None


class PermissionPolicy:
    """基于前缀匹配 + 内置默认表的操作分级器。"""

    def __init__(self, config: SecurityConfig):
        self.config = config
        self._builtin = self._build_builtin()

    @staticmethod
    def _build_builtin() -> dict[str, ActionLevel]:
        # 内置默认表：精确动作名 → 级别
        builtin: dict[str, ActionLevel] = {
            "system.delete.core": ActionLevel.S0_BLOCKED,
            "registry.write": ActionLevel.S0_BLOCKED,
            "driver.modify": ActionLevel.S0_BLOCKED,
            "watermark.remove.third_party": ActionLevel.S0_BLOCKED,
            "system.install": ActionLevel.S1_APPROVAL,
            "software.install": ActionLevel.S1_APPROVAL,
            "file.delete": ActionLevel.S1_APPROVAL,
            "agent.deploy": ActionLevel.S1_APPROVAL,
            "delivery.submit": ActionLevel.S1_APPROVAL,
            "tool.create.high_risk": ActionLevel.S1_APPROVAL,
        }
        return builtin

    def classify(self, action: str) -> ActionLevel:
        # 1. 精确内置表
        if action in self._builtin:
            return self._builtin[action]
        # 2. 配置前缀：S0 优先，其次 S1，再 S2，最后默认 S3
        for prefix in self.config.blocked_prefixes:
            if action.startswith(prefix):
                return ActionLevel.S0_BLOCKED
        for prefix in self.config.approval_prefixes:
            if action.startswith(prefix):
                return ActionLevel.S1_APPROVAL
        for prefix in self.config.whitelist_prefixes:
            if action.startswith(prefix):
                return ActionLevel.S2_WHITELIST
        return ActionLevel.S3_AUTO


class PermissionGate:
    """执行前的门控。返回 None 表示放行；S1 抛 :class:`ApprovalRequired`；
    S0 抛 :class:`PermissionDenied`。"""

    def __init__(self, policy: PermissionPolicy, role: Role):
        self.policy = policy
        self.role = role

    def enforce(self, action: Action) -> ActionLevel:
        level = self.policy.classify(action.name)
        if level.is_blocked:
            raise PermissionDenied(
                f"操作被硬阻断: {action.name}",
                action=action.name, level=level.value,
            )
        # 未登录（访客）：白名单操作也升级为需审批，仅只读 S3 放行
        if self.role is Role.VISITOR and level is ActionLevel.S2_WHITELIST:
            from superagent.core.errors import ApprovalRequired
            raise ApprovalRequired(
                f"未登录，操作需人工审批: {action.name}",
                action=action.name, level=ActionLevel.S1_APPROVAL.value,
            )
        if level.requires_approval:
            # 登录授信不豁免 S1（对应评审 C2 裁决）
            from superagent.core.errors import ApprovalRequired
            raise ApprovalRequired(
                f"操作需要人工审批: {action.name}",
                action=action.name, level=level.value,
            )
        return level

    def level_of(self, action: Action) -> ActionLevel:
        return self.policy.classify(action.name)

    def enforce_with_runtime(self, runtime, action: Action, resource: str = "", reason: str = "") -> ActionLevel:
        """门控 + 审批一体化：S0 阻断、需审批则走审批队列（登录授信不豁免 S1），
        S2/S3 自动放行。返回放行级别。"""
        level = self.policy.classify(action.name)
        if level.is_blocked:
            raise PermissionDenied(
                f"操作被硬阻断: {action.name}",
                action=action.name, level=level.value,
            )
        needs_approval = level.requires_approval or (
            self.role is Role.VISITOR and level is ActionLevel.S2_WHITELIST
        )
        if needs_approval:
            from superagent.hitl.approval import request_decision
            req = request_decision(runtime, action.name, resource=resource or "", reason=reason)
            if req.decision.value != "approve":
                raise PermissionDenied(
                    f"操作未获人工批准: {action.name}（{req.feedback or '已驳回'}）",
                    action=action.name, level=level.value,
                )
        return level
