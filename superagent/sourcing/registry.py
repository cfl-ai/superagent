"""资料溯源登记与失效核验（修订版第 8 节 schema）。

字段：来源类型 / 标题(名称) / 时间 / 内容哈希 / 许可 / 引用位置 / 失效复检。
统一写入 `01_需求文档/参考资料清单.md`。
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from superagent.core.errors import SourceTraceError

SourceType = Literal["url", "file"]


@dataclass
class SourceRecord:
    source_type: SourceType
    title: str
    ref: str  # URL 或本地路径
    captured_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    content_hash: str = ""
    license_note: str = ""
    cited_at: str = ""
    recheck_interval_days: int = 7
    status: str = "active"  # active | stale | dead

    def compute_hash(self, content: bytes | None) -> str:
        if content is None:
            return ""
        self.content_hash = hashlib.sha256(content).hexdigest()
        return self.content_hash

    def to_md_row(self) -> str:
        return (
            f"| {self.source_type} | {self.title} | {self.ref} | "
            f"{self.captured_at} | `{self.content_hash[:12]}` | "
            f"{self.license_note or '-'} | {self.cited_at or '-'} | {self.status} |"
        )


_MD_HEADER = (
    "| 来源类型 | 标题/名称 | URL/路径 | 记录时间 | 内容哈希 | 许可 | 引用位置 | 状态 |\n"
    "|---|---|---|---|---|---|---|---|\n"
)


class SourceRegistry:
    def __init__(self, manifest_path: str | Path):
        self.manifest_path = Path(manifest_path)
        self.records: list[SourceRecord] = []
        self._load_existing()

    def _load_existing(self) -> None:
        if not self.manifest_path.exists():
            return
        # 简单重放：仅保留头部记录；不解析已存在的表格行，避免格式耦合。
        # 完整历史以 append 模式维护在 manifest 中，内存态从本次会话重建。
        pass

    def add(
        self,
        source_type: SourceType,
        title: str,
        ref: str,
        *,
        content: bytes | None = None,
        license_note: str = "",
        cited_at: str = "",
        recheck_interval_days: int = 7,
    ) -> SourceRecord:
        if not ref:
            raise SourceTraceError("来源 ref 不能为空")
        rec = SourceRecord(
            source_type=source_type,
            title=title,
            ref=ref,
            license_note=license_note,
            cited_at=cited_at,
            recheck_interval_days=recheck_interval_days,
        )
        rec.compute_hash(content)
        self.records.append(rec)
        self._append(rec)
        return rec

    def _append(self, rec: SourceRecord) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self.manifest_path.write_text(
                "# 参考资料清单\n\n" + _MD_HEADER, encoding="utf-8"
            )
        with self.manifest_path.open("a", encoding="utf-8") as f:
            f.write(rec.to_md_row() + "\n")

    def mark_stale(self, ref: str, status: str = "stale") -> None:
        for r in self.records:
            if r.ref == ref:
                r.status = status

    def find(self, ref: str) -> SourceRecord | None:
        for r in self.records:
            if r.ref == ref:
                return r
        return None

    def list_active(self) -> list[SourceRecord]:
        return [r for r in self.records if r.status == "active"]

    def recheck(self) -> list[SourceRecord]:
        """返回已失效（本地文件不存在或标记 stale）的记录，供上层标记风险。"""
        stale = []
        for r in self.records:
            if r.source_type == "file" and not Path(r.ref).exists():
                r.status = "dead"
                stale.append(r)
        return stale
