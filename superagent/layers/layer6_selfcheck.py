"""第 6 层：幻觉自检与质量管控（修订版第 5 节(八) + 第 9 节）。

- 资料来源核验（recheck）
- 独立 Scorer 评分；< 阈值触发改良迭代
"""
from __future__ import annotations

from superagent.core.errors import SelfCheckFailed
from superagent.layers.base import Layer, TaskContext
from superagent.quality.rubric import Domain


class SelfCheckLayer(Layer):
    name = "layer6_selfcheck"

    def run(self, ctx: TaskContext, runtime) -> dict:
        report = self.check(ctx, runtime)
        ctx.artifacts["quality_report"] = report.to_dict()
        threshold = runtime.config.quality.pass_threshold
        if not report.passed(threshold):
            raise SelfCheckFailed(
                f"质量评分 {report.total} < {threshold}，触发改良迭代",
                domain=report.domain.value, total=report.total,
            )
        return {"report": report.to_dict(), "passed": True}

    def check(self, ctx: TaskContext, runtime):
        """独立评分 + 来源核验。"""
        stale = runtime.sources.recheck()
        issues = [{"location": "sources", "severity": "medium", "fix": "标记失效来源", "detail": s.ref} for s in stale]
        # 依据生产物类型选择领域 rubric
        kind = ctx.plan.get("production", {}).get("kind", "general")
        domain = {
            "code": Domain.CODE,
            "agent": Domain.AGENT,
            "design": Domain.DESIGN,
            "video": Domain.VIDEO,
        }.get(kind, Domain.DOCUMENT)
        # 基础评分：来源全部有效则来源维度满分，否则扣分
        src_score = 10.0 if not stale else max(0.0, 10.0 - len(stale))
        dims = {d: 8.0 for d in _domain_dims(domain)}
        src_dim = "来源标注" if domain is Domain.DOCUMENT else "来源有效性"
        if src_dim in dims:
            dims[src_dim] = src_score
        return runtime.scorer.score(domain, dims, issues)


def _domain_dims(domain: Domain) -> list[str]:
    mapping = {
        Domain.CODE: ["可运行性", "正确性", "来源有效性", "交付质感"],
        Domain.DESIGN: ["视觉规范", "分辨率/色彩", "无AI畸形", "来源有效性"],
        Domain.VIDEO: ["镜头连贯", "动作真实", "无畸变失真", "来源有效性"],
        Domain.AGENT: ["可部署性", "可复现性", "无幻觉", "来源有效性"],
        Domain.DOCUMENT: ["准确性", "结构化", "来源标注", "交付质感"],
    }
    return mapping[domain]
