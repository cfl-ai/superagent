"""质量 rubric 与独立评分（修订版第 9 节）。

评分者与生产流程解耦：生产层产出物交给独立 Scorer 评分，
避免自评闭环。7 分制；< 7 分触发改良迭代。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Domain(str, Enum):
    CODE = "code"
    DESIGN = "design"
    VIDEO = "video"
    AGENT = "agent"
    DOCUMENT = "document"


# 各领域 rubric 维度及权重（和为 1.0）
_RUBRICS: dict[Domain, dict[str, float]] = {
    Domain.CODE: {"可运行性": 0.3, "正确性": 0.3, "来源有效性": 0.2, "交付质感": 0.2},
    Domain.DESIGN: {"视觉规范": 0.3, "分辨率/色彩": 0.2, "无AI畸形": 0.3, "来源有效性": 0.2},
    Domain.VIDEO: {"镜头连贯": 0.25, "动作真实": 0.25, "无畸变失真": 0.25, "来源有效性": 0.25},
    Domain.AGENT: {"可部署性": 0.3, "可复现性": 0.3, "无幻觉": 0.2, "来源有效性": 0.2},
    Domain.DOCUMENT: {"准确性": 0.3, "结构化": 0.2, "来源标注": 0.3, "交付质感": 0.2},
}


@dataclass
class QualityReport:
    domain: Domain
    scores: dict[str, float] = field(default_factory=dict)
    issues: list[dict] = field(default_factory=list)
    total: float = 0.0

    def passed(self, threshold: float = 7.0) -> bool:
        return self.total >= threshold

    def to_dict(self) -> dict:
        return {
            "domain": self.domain.value,
            "scores": self.scores,
            "total": round(self.total, 2),
            "issues": self.issues,
            "passed": self.passed(),
        }


class Scorer:
    """独立评分器：接收各维度原始分（0-10），加权得总分。"""

    def score(self, domain: Domain, dimension_scores: dict[str, float], issues: list[dict] | None = None) -> QualityReport:
        rubric = _RUBRICS[domain]
        total = 0.0
        scores: dict[str, float] = {}
        for dim, weight in rubric.items():
            raw = dimension_scores.get(dim, 0.0)
            raw = max(0.0, min(10.0, raw))
            scores[dim] = raw
            total += raw * weight
        return QualityReport(
            domain=domain,
            scores=scores,
            issues=issues or [],
            total=round(total, 2),
        )

    def score_pass_fail(self, domain: Domain, pass_all: bool = True, issues: list[dict] | None = None) -> QualityReport:
        """便捷：全维度满分/零分，用于演示与基础测试。"""
        dims = {d: (10.0 if pass_all else 0.0) for d in _RUBRICS[domain]}
        return self.score(domain, dims, issues)
