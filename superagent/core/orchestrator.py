"""主事件流编排器（修订版第 4 节主事件流）。

将语言解析 → 权限校验 → 规划 → 检索 → 生产 → 自检 → 终审 → 归档交付
串成一条可控事件流。简短输入时枚举可能性等待确认，不擅自生产。
"""
from __future__ import annotations

import uuid
from pathlib import Path

from superagent.core.errors import SuperAgentError
from superagent.core.runtime import Runtime
from superagent.core.state import TaskState, TaskStateMachine
from superagent.layers.base import TaskContext
from superagent.layers.layer1_sysops import SystemOpsLayer
from superagent.layers.layer2_network import NetworkLayer
from superagent.layers.layer3_planning import PlanningLayer
from superagent.layers.layer5_production import ProductionLayer
from superagent.layers.layer6_selfcheck import SelfCheckLayer
from superagent.layers.layer7_delivery import DeliveryLayer


class Orchestrator:
    """按主事件流编排一次任务。"""

    def __init__(self, runtime: Runtime):
        self.runtime = runtime
        self.planning = PlanningLayer()
        self.network = NetworkLayer()
        self.sysops = SystemOpsLayer()
        self.production = ProductionLayer()
        self.selfcheck = SelfCheckLayer()
        self.delivery = DeliveryLayer()

    def new_context(self, user_input: str, project_root: str | Path | None = None) -> TaskContext:
        task_id = uuid.uuid4().hex[:12]
        root = Path(project_root) if project_root else self.runtime.config.project_root / "projects" / task_id
        root.mkdir(parents=True, exist_ok=True)
        return TaskContext(task_id=task_id, user_input=user_input, project_dir=root)

    def run(self, user_input: str, project_root: str | Path | None = None) -> dict:
        """执行一次完整任务。简短输入返回枚举结果并等待确认。"""
        ctx = self.new_context(user_input, project_root)
        self.runtime.telemetry.log("info", "任务开始", task_id=ctx.task_id, input=user_input[:120])
        self.runtime.telemetry.metrics.incr("tasks")

        # 1. 语言解析与规划
        plan_result = self.planning.run(ctx, self.runtime)
        if plan_result.get("await_confirmation"):
            # 简短输入：保持 PENDING_CONFIRM，等待用户确认方向
            self.runtime.telemetry.log("info", "简短输入，等待确认方向", task_id=ctx.task_id)
            return {
                "task_id": ctx.task_id,
                "await_confirmation": True,
                "enumeration": plan_result["enumeration"].possibilities,
            }

        # 2. 权限校验（登录状态决定高阶操作是否放行）
        ctx.state.transition(TaskState.PLANNED)
        self.runtime.telemetry.log("info", "规划完成", task_id=ctx.task_id)

        # 2.5 工具缺口评估与自主扩展（修订版第 3 层 + 第 5 节(七)）
        from superagent.core.toolforge import ToolForge
        forge = ToolForge()
        for need in forge.assess(self.runtime, user_input):
            try:
                forge.forge(
                    self.runtime,
                    need.get("name", ""),
                    need.get("description", ""),
                    need.get("high_risk", False),
                )
                ctx.note(f"已创建新工具: {need.get('name')}")
            except Exception as exc:  # noqa: BLE001
                ctx.note(f"工具创建失败 {need.get('name')}: {exc}")

        # 3. 资料检索
        ctx.state.transition(TaskState.RETRIEVING)
        self.network.run(ctx, self.runtime)

        # 4. 系统运维（若计划要求）
        self.sysops.run(ctx, self.runtime)

        # 5. 生产（生产前按角色门控：未登录 visitor 强制人工审批）
        from superagent.security.permissions import Action, PermissionGate, Role
        role = Role(self.runtime.config.security.default_role)
        gate = PermissionGate(self.runtime.policy, role)
        gate.enforce_with_runtime(
            self.runtime,
            Action("production.run", resource=ctx.task_id),
            reason=user_input,
        )
        ctx.state.transition(TaskState.PRODUCING)
        produced = self._produce_and_verify(ctx)
        ctx.artifacts["produced"] = produced

        # 6. 自检与评分（不达标自动迭代）
        ctx.state.transition(TaskState.SELF_CHECKING)
        self._selfcheck_with_retry(ctx)

        # 7. 终审 + 归档交付
        ctx.state.transition(TaskState.PENDING_APPROVAL)
        delivery = self.delivery.run(ctx, self.runtime)
        ctx.state.transition(TaskState.APPROVED)
        ctx.state.transition(TaskState.ARCHIVED)

        self.runtime.telemetry.log("info", "任务完成", task_id=ctx.task_id)
        return {
            "task_id": ctx.task_id,
            "await_confirmation": False,
            "state": ctx.state.state.value,
            "artifacts": ctx.artifacts,
            "delivery": delivery,
            "notes": ctx.notes,
        }

    def confirm(self, task_id: str, direction: str, elaborated: str = "") -> dict:
        """用户确认简短输入的创作方向后，续跑任务。"""
        # 简化：以确认后的方向重新执行（真实系统应恢复上下文，此处以新输入承接）
        return self.run(elaborated or direction)

    def _selfcheck_with_retry(self, ctx: TaskContext) -> None:
        max_iter = self.runtime.config.quality.max_iterations
        for i in range(max_iter):
            try:
                self.selfcheck.run(ctx, self.runtime)
                return
            except SuperAgentError as exc:
                ctx.note(f"自检迭代 {i + 1}/{max_iter}: {exc.message}")
                if i == max_iter - 1:
                    ctx.state.transition(TaskState.FAILED)
                    raise

    def _produce_and_verify(self, ctx: TaskContext):
        """生产 + 代码真实运行验证 + 自动修复循环（对应修订版可运行性约束）。"""
        spec = ctx.plan.get("production", {})
        kind = spec.get("kind", "general")
        produced = self.production.run(ctx, self.runtime)
        if kind != "code":
            return produced

        from superagent.quality.verifier import verify_code
        project = ctx.artifacts.get("code_project")
        if not project:
            return produced

        errors: list[str] = []
        for attempt in range(self.runtime.config.quality.max_iterations):
            ok, errors = verify_code(project)
            if ok:
                self.runtime.telemetry.log("info", "代码验证通过", task_id=ctx.task_id)
                break
            ctx.note(f"代码验证失败，第 {attempt + 1} 次修复：{errors[0][:120]}")
            produced = self.production._produce_code(
                ctx, spec, self.runtime, fix_hint="\n".join(errors)
            )
            ctx.artifacts["code_project"] = produced["project"]
        else:
            raise SuperAgentError(f"代码验证多次失败：{' | '.join(errors[:3])}")
        ctx.artifacts["code_verified"] = True
        return produced
