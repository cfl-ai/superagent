"""审计日志（修订版第 6.4 节 schema）。

全量记录 S0/S1/S2/S3 操作，写入 SQLite（结构化查询）+ JSONL（可追加），
字段与规范一致：event_id / timestamp / subject / action / object /
level / approval_chain / result / rollback。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    event_id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    subject TEXT NOT NULL,
    action TEXT NOT NULL,
    object TEXT NOT NULL DEFAULT '',
    level TEXT NOT NULL,
    approval_chain TEXT NOT NULL DEFAULT '[]',
    result TEXT NOT NULL,
    rollback TEXT NOT NULL DEFAULT '',
    meta TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_events(ts);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_events(action);
"""


class AuditLogger:
    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def record(
        self,
        *,
        subject: str,
        action: str,
        level: str,
        result: str,
        obj: str = "",
        approval_chain: list[dict] | None = None,
        rollback: str = "",
        meta: dict[str, Any] | None = None,
    ) -> str:
        event_id = str(uuid.uuid4())
        row = {
            "event_id": event_id,
            "ts": self._now(),
            "subject": subject,
            "action": action,
            "object": obj,
            "level": level,
            "approval_chain": json.dumps(approval_chain or [], ensure_ascii=False),
            "result": result,
            "rollback": rollback,
            "meta": json.dumps(meta or {}, ensure_ascii=False),
        }
        with self._lock:
            self._conn.execute(
                """INSERT INTO audit_events
                   (event_id, ts, subject, action, object, level,
                    approval_chain, result, rollback, meta)
                   VALUES (:event_id, :ts, :subject, :action, :object, :level,
                           :approval_chain, :result, :rollback, :meta)""",
                row,
            )
            self._conn.commit()
        return event_id

    def query(self, limit: int = 50, action: str | None = None, level: str | None = None) -> list[dict]:
        sql = "SELECT * FROM audit_events"
        conds, params = [], []
        if action:
            conds.append("action = ?")
            params.append(action)
        if level:
            conds.append("level = ?")
            params.append(level)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY ts DESC LIMIT ?"
        params.append(limit)
        cur = self._conn.execute(sql, params)
        cols = [c[0] for c in cur.description]
        out = []
        for r in cur.fetchall():
            d = dict(zip(cols, r))
            d["approval_chain"] = json.loads(d["approval_chain"])
            d["meta"] = json.loads(d["meta"])
            out.append(d)
        return out

    def close(self) -> None:
        with self._lock:
            self._conn.close()
