"""第 3 层：语言解析与需求规划（修订版第 5 节(六) + 第 3 层架构）。

- 语言识别：中/英启发式
- 简短输入：枚举可能性，等待确认（不擅自生产）
- 完整输入：直接产出任务计划
- LLM 驱动：配置真实模型时用 LLM 解析意图/枚举/规划；失败自动回退确定性实现
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from superagent.layers.base import Layer, TaskContext


def detect_language(text: str) -> str:
    """启发式语言识别：含 CJK 判为 zh，否则按英文/其他。"""
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return "zh" if cjk > 0 else "en"


def is_short(text: str, threshold: int = 10) -> bool:
    """简短输入判定（去除空白后字符数）。"""
    return len(re.sub(r"\s+", "", text)) <= threshold


@dataclass
class Enumeration:
    """简短输入的可能性枚举。"""

    original: str
    possibilities: list[dict] = field(default_factory=list)
    needs_confirmation: bool = True


class PlanningLayer(Layer):
    name = "layer3_planning"

    def run(self, ctx: TaskContext, runtime) -> dict:
        ctx.language = detect_language(ctx.user_input)
        ctx.note(f"识别语言: {ctx.language}")

        if is_short(ctx.user_input):
            enum = self._enumerate(ctx.user_input, ctx.language, runtime)
            ctx.artifacts["enumeration"] = enum
            ctx.plan = {"pending_confirmation": True, "possibilities": enum.possibilities}
            return {"language": ctx.language, "enumeration": enum, "await_confirmation": True}

        plan = self._plan(ctx.user_input, ctx.language, runtime)
        ctx.plan = plan
        return {"language": ctx.language, "plan": plan, "await_confirmation": False}

    # ---- LLM 辅助 ----
    def _llm_json(self, runtime, system: str, user: str) -> dict | list | None:
        """调用 LLM 并解析 JSON；失败/非 JSON 返回 None（触发确定性回退）。"""
        from superagent.llm.backend import strip_code_fence
        try:
            text = runtime.llm.complete([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
        except Exception:  # noqa: BLE001
            return None
        if not text or text.startswith("[mock]"):
            return None
        try:
            text = strip_code_fence(text)
            return json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            return None

    def _enumerate(self, text: str, lang: str, runtime) -> Enumeration:
        data = self._llm_json(
            runtime,
            "你是资深任务解析器。用户输入简短，枚举所有合理创作方向。"
            "只输出 JSON 数组，每项含 direction 与 desc 两个字段。",
            f"输入: {text}\n语言: {lang}",
        )
        if isinstance(data, list) and data:
            return Enumeration(original=text, possibilities=data, needs_confirmation=True)
        return self.enumerate(text, lang)

    def _plan(self, text: str, lang: str, runtime) -> dict:
        data = self._llm_json(
            runtime,
            "你是资深任务规划器。将需求拆解为可执行计划，只输出 JSON："
            '{"goal":str, "production":{"kind":"code|design|video|agent|general","name":str,"spec":str},'
            ' "references":[{"kind":"url|file","url":str,"title":str}], "sysops":{"ops":[]}}',
            f"需求: {text}\n语言: {lang}",
        )
        if isinstance(data, dict) and data.get("goal"):
            data["pending_confirmation"] = False
            data.setdefault("production", {"kind": "general", "spec": text})
            data.setdefault("references", [])
            data.setdefault("sysops", {"ops": []})
            return data
        return self.plan(text, lang)

    # ---- 确定性回退 ----
    def enumerate(self, text: str, lang: str) -> Enumeration:
        directions = [
            {"direction": "代码工程", "desc": "全栈网页/后端/桌面小软件/脚本"},
            {"direction": "平面设计", "desc": "Logo/海报/UI/网页视觉"},
            {"direction": "视频制片", "desc": "剧本/分镜/剪辑/调色"},
            {"direction": "Agent 开发", "desc": "自研生产级 Agent"},
        ]
        return Enumeration(original=text, possibilities=directions, needs_confirmation=True)

    def plan(self, text: str, lang: str) -> dict:
        return {
            "pending_confirmation": False,
            "goal": text,
            "production": {"kind": "general", "spec": text},
            "references": [],
            "sysops": {"ops": []},
        }
