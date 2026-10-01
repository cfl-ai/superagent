"""HITL 人工审批（修订版第 7 节）。

决策：放行 / 修改意见 / 驳回重做。支持超时、优先级、阻塞队列、
持久化到 JSONL 以便跨会话恢复。
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import queue
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from superagent.core.errors import ApprovalTimeout

# 上下文级审批回调：允许按请求/按线程覆盖运行时 approver
_current_approver = contextvars.ContextVar("superagent_approver", default=None)


@contextlib.contextmanager
def use_approver(approver):
    """在上下文中临时覆盖审批回调（返回 Decision 的二元组）。"""
    token = _current_approver.set(approver)
    try:
        yield
    finally:
        _current_approver.reset(token)


class Decision(str, Enum):
    APPROVE = "approve"      # 放行
    REVISE = "revise"        # 修改意见
    REJECT = "reject"        # 驳回重做


@dataclass
class ApprovalRequest:
    id: str
    action: str
    resource: str
    reason: str
    created_at: float
    timeout_s: float
    priority: int = 0
    decision: Decision | None = None
    feedback: str = ""
    decided_at: float | None = None

    @property
    def resolved(self) -> bool:
        return self.decision is not None


class ApprovalQueue:
    """线程安全的审批队列。produce 阻塞等待 decision。"""

    def __init__(self, storage_path: str | Path, timeout_s: float = 600.0):
        self.storage_path = Path(storage_path)
        self.timeout_s = timeout_s
        self._cond = threading.Condition()
        self._pending: dict[str, ApprovalRequest] = {}
        self._order: queue.PriorityQueue = queue.PriorityQueue()
        self._closed = False

    def request(
        self,
        action: str,
        resource: str = "",
        reason: str = "",
        *,
        priority: int = 0,
        timeout_s: float | None = None,
    ) -> ApprovalRequest:
        req = ApprovalRequest(
            id=uuid.uuid4().hex[:12],
            action=action,
            resource=resource,
            reason=reason,
            created_at=time.time(),
            timeout_s=timeout_s if timeout_s is not None else self.timeout_s,
            priority=priority,
        )
        with self._cond:
            self._pending[req.id] = req
            self._order.put((-req.priority, req.created_at, req.id))
            self._persist(req)
        return req

    def _persist(self, req: ApprovalRequest) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(req.__dict__, ensure_ascii=False) + "\n")

    def wait(self, req: ApprovalRequest, poll_s: float = 0.2) -> Decision:
        """阻塞等待决策，超时抛 ApprovalTimeout。"""
        deadline = time.time() + req.timeout_s
        with self._cond:
            while not req.resolved:
                if time.time() >= deadline:
                    self._pending.pop(req.id, None)
                    raise ApprovalTimeout(f"审批超时: {req.action} ({req.id})")
                self._cond.wait(timeout=poll_s)
            return req.decision  # type: ignore[return-value]

    def decide(self, req_id: str, decision: Decision, feedback: str = "") -> ApprovalRequest:
        with self._cond:
            req = self._pending.get(req_id)
            if req is None:
                raise KeyError(f"审批请求不存在: {req_id}")
            req.decision = decision
            req.feedback = feedback
            req.decided_at = time.time()
            self._pending.pop(req_id, None)
            self._persist(req)
            self._cond.notify_all()
        return req

    def pending(self) -> list[ApprovalRequest]:
        with self._cond:
            items = sorted(self._pending.values(), key=lambda r: r.created_at)
        return items

    def close(self) -> None:
        with self._cond:
            self._closed = True
            self._cond.notify_all()


def request_decision(runtime, action: str, resource: str = "", reason: str = "", *, priority: int = 0, timeout_s: float | None = None) -> ApprovalRequest:
    """统一的 S1 审批决策入口。

    - 若 runtime.approver 提供（交互式/注入式），内联决策；
    - 否则阻塞等待队列（配合 `approve` CLI 或后台服务）。
    """
    req = runtime.approvals.request(action, resource, reason, priority=priority, timeout_s=timeout_s)
    # 优先取上下文覆盖的 approver，其次运行时 approver，最后阻塞队列
    approver = _current_approver.get() or getattr(runtime, "approver", None)
    if approver is not None:
        decision, feedback = approver(req)
        return runtime.approvals.decide(req.id, decision, feedback)
    decision = runtime.approvals.wait(req)
    return req
