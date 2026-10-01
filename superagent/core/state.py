"""任务状态机（修订版第 11 节）。

状态：待确认 → 已规划 → 检索中 → 生产中 → 自检中 → 待审批 →
已通过 → 已归档/已交付；异常态：已挂起 / 已驳回 / 已失败。
"""
from __future__ import annotations

from enum import Enum

from superagent.core.errors import StateMachineError


class TaskState(str, Enum):
    PENDING_CONFIRM = "pending_confirm"
    PLANNED = "planned"
    RETRIEVING = "retrieving"
    PRODUCING = "producing"
    SELF_CHECKING = "self_checking"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    ARCHIVED = "archived"
    DELIVERED = "delivered"
    SUSPENDED = "suspended"
    REJECTED = "rejected"
    FAILED = "failed"


_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.PENDING_CONFIRM: {TaskState.PLANNED, TaskState.FAILED},
    TaskState.PLANNED: {TaskState.RETRIEVING, TaskState.SUSPENDED, TaskState.FAILED},
    TaskState.RETRIEVING: {TaskState.PRODUCING, TaskState.FAILED},
    TaskState.PRODUCING: {TaskState.SELF_CHECKING, TaskState.SUSPENDED, TaskState.FAILED},
    TaskState.SELF_CHECKING: {TaskState.PRODUCING, TaskState.PENDING_APPROVAL, TaskState.SUSPENDED, TaskState.FAILED},
    TaskState.PENDING_APPROVAL: {TaskState.APPROVED, TaskState.REJECTED, TaskState.SUSPENDED},
    TaskState.APPROVED: {TaskState.ARCHIVED, TaskState.FAILED},
    TaskState.ARCHIVED: {TaskState.DELIVERED, TaskState.FAILED},
    TaskState.REJECTED: {TaskState.PLANNED, TaskState.PRODUCING, TaskState.FAILED},
    TaskState.SUSPENDED: {TaskState.PLANNED, TaskState.PRODUCING, TaskState.FAILED},
    TaskState.FAILED: set(),
    TaskState.DELIVERED: set(),
}


class TaskStateMachine:
    def __init__(self, initial: TaskState = TaskState.PENDING_CONFIRM):
        self.state = initial

    def transition(self, to: TaskState) -> None:
        if to not in _TRANSITIONS[self.state]:
            raise StateMachineError(f"非法状态迁移: {self.state.value} -> {to.value}")
        self.state = to

    def __repr__(self) -> str:
        return f"<TaskStateMachine {self.state.value}>"
