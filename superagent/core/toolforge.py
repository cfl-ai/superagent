"""自主工具扩展闭环（修订版第 5 节(七)）。

流程：LLM 评估缺口 → LLM 编写工具函数 → 语法校验 → 高危检测 + 人工审批 →
执行并注册进工具池。新工具同样纳入幻觉/安全校验。
"""
from __future__ import annotations

import re

from superagent.core.errors import ToolRegistryError
from superagent.core.registry import Tool

_HIGH_RISK_PATTERNS = [
    r"\bopen\s*\(", r"subprocess", r"\bos\.", r"socket", r"urllib",
    r"requests", r"shutil", r"__import__", r"\beval\s*\(", r"\bexec\s*\(",
    r"\binput\s*\(", r"\bPath\s*\(",
]


class ToolForge:
    """按需创建、测试、集成新工具。"""

    def assess(self, runtime, task_text: str, max_tools: int = 3) -> list[dict]:
        """LLM 评估当前工具集是否缺少必要工具。失败返回 []（不阻断主流程）。"""
        from superagent.layers.layer3_planning import PlanningLayer
        data = PlanningLayer()._llm_json(
            runtime,
            "你是工具架构师。给定任务与现有工具列表，判断是否缺少必要工具函数。"
            "只输出 JSON 数组，每项含 name(英文函数名)、description(中文说明)、high_risk(bool)。"
            "不需要新工具则输出 []。",
            f"任务: {task_text}\n现有工具: {runtime.tools.names()}",
        )
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict) and d.get("name")][:max_tools]
        return []

    def forge(self, runtime, name: str, description: str = "", high_risk: bool = False) -> Tool:
        """编写并集成一个工具。返回已注册的 Tool。"""
        if name in runtime.tools.names():
            return runtime.tools.get(name)

        code = self._generate(runtime, name, description)
        if not code:
            raise ToolRegistryError(f"工具生成失败: {name}")

        from superagent.llm.backend import strip_code_fence
        code = strip_code_fence(code)
        compile(code, f"<tool:{name}>", "exec")  # 语法校验（幻觉拦截第一道）

        detected_risk = high_risk or self._is_high_risk(code)
        action = "tool.create.high_risk" if detected_risk else "tool.create"
        if detected_risk:
            # 高危工具创建触发人工审批（修订版约束）
            from superagent.hitl.approval import request_decision
            req = request_decision(runtime, action, resource=name, reason=description or name)
            if req.decision.value != "approve":
                raise ToolRegistryError(f"高危工具审批未通过: {name}")

        ns: dict = {}
        exec(code, ns)  # noqa: S102 - 已通过语法校验 + 高危审批
        fn = ns.get(name)
        if not callable(fn):
            raise ToolRegistryError(f"生成的代码中未找到函数 {name}")

        tool = Tool(name=name, fn=fn, description=description, action=action, high_risk=detected_risk)
        runtime.tools.register(tool)
        runtime.audit.record(
            subject=runtime.config.security.default_role,
            action=action,
            level="S1" if detected_risk else "S3",
            result="success",
            obj=name,
            meta={"description": description},
        )
        runtime.telemetry.log("info", f"已集成新工具: {name}", kind="toolforge")
        return tool

    def _generate(self, runtime, name: str, description: str) -> str | None:
        from superagent.layers.layer5_production import ProductionLayer
        return ProductionLayer()._llm_text(
            runtime,
            "你是资深工具开发者。编写一个自包含、无副作用的 Python 函数，"
            f"函数名必须是 {name}。只输出 def 定义与必要的 import，不要 main、不要测试、不要解释。",
            f"函数名: {name}\n功能: {description}",
        )

    @staticmethod
    def _is_high_risk(code: str) -> bool:
        return any(re.search(p, code) for p in _HIGH_RISK_PATTERNS)
