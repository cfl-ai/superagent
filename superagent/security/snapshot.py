"""快照与回滚（修订版第 6.5 节）。

S1 高危操作前对目标文件/目录做快照（复制到快照目录 + 清单），
失败时按清单回滚。不支持整机还原点，仅文件级快照，安全可控。
"""
from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from superagent.core.errors import SnapshotError


@dataclass
class SnapshotEntry:
    relative: str
    original: str  # 快照内副本路径
    kind: str = "file"  # file | dir


@dataclass
class Snapshot:
    id: str
    created_at: str
    target: str
    entries: list[SnapshotEntry] = field(default_factory=list)
    manifest_path: Path | None = None
    target_kind: str = "file"  # file | dir


class SnapshotManager:
    def __init__(self, snapshot_dir: str | Path):
        self.snapshot_dir = Path(snapshot_dir)
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def create(self, target: str | Path) -> Snapshot:
        """对 target 做快照。target 不存在时返回空快照。"""
        target = Path(target)
        snap_id = uuid.uuid4().hex[:12]
        snap_dir = self.snapshot_dir / snap_id
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap = Snapshot(
            id=snap_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            target=str(target),
        )
        if not target.exists():
            snap.manifest_path = snap_dir / "manifest.json"
            self._write_manifest(snap_dir, snap)
            return snap
        if target.is_file():
            snap.target_kind = "file"
            dst = snap_dir / target.name
            shutil.copy2(target, dst)
            snap.entries.append(SnapshotEntry(target.name, str(dst), "file"))
        elif target.is_dir():
            snap.target_kind = "dir"
            for p in target.rglob("*"):
                rel = p.relative_to(target).as_posix()
                dst = snap_dir / rel
                if p.is_file():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, dst)
                    snap.entries.append(SnapshotEntry(rel, str(dst), "file"))
        snap.manifest_path = snap_dir / "manifest.json"
        self._write_manifest(snap_dir, snap)
        return snap

    def _write_manifest(self, snap_dir: Path, snap: Snapshot) -> None:
        data = {
            "id": snap.id,
            "created_at": snap.created_at,
            "target": snap.target,
            "target_kind": snap.target_kind,
            "entries": [e.__dict__ for e in snap.entries],
        }
        (snap_dir / "manifest.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def rollback(self, snap: Snapshot) -> None:
        """按快照恢复 target 到快照时点。"""
        target = Path(snap.target)
        try:
            if not snap.entries and not target.exists():
                return
            for e in snap.entries:
                src = Path(e.original)
                if not src.exists():
                    raise SnapshotError(f"快照副本缺失: {src}")
                if snap.target_kind == "file":
                    dst = target
                else:
                    dst = target / e.relative
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        except OSError as exc:
            raise SnapshotError(f"回滚失败: {exc}") from exc

    def load(self, snap_id: str) -> Snapshot:
        manifest = self.snapshot_dir / snap_id / "manifest.json"
        if not manifest.exists():
            raise SnapshotError(f"快照不存在: {snap_id}")
        data = json.loads(manifest.read_text(encoding="utf-8"))
        snap = Snapshot(
            id=data["id"],
            created_at=data["created_at"],
            target=data["target"],
            entries=[SnapshotEntry(**e) for e in data["entries"]],
            manifest_path=manifest,
            target_kind=data.get("target_kind", "file"),
        )
        return snap
