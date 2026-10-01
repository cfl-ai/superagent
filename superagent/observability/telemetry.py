"""可观测性：结构化日志 + 指标 + 告警 + 心跳（修订版第 12 节）。"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


class Metrics:
    """简单线程安全计数器。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}

    def incr(self, name: str, n: int = 1) -> None:
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + n

    def get(self, name: str) -> int:
        with self._lock:
            return self._counters.get(name, 0)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counters)


class Telemetry:
    def __init__(
        self,
        log_dir: str | Path,
        *,
        heartbeat_interval_s: float = 5.0,
        alert_hook: Callable[[str], None] | None = None,
    ):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.metrics = Metrics()
        self.alert_hook = alert_hook
        self._heartbeat_interval = heartbeat_interval_s
        self._stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None

        self.logger = logging.getLogger("superagent")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            fh = logging.FileHandler(self.log_dir / "agent.log", encoding="utf-8")
            fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
            sh = logging.StreamHandler()
            sh.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
            self.logger.addHandler(fh)
            self.logger.addHandler(sh)

    def log(self, level: str, message: str, **fields) -> None:
        getattr(self.logger, level, self.logger.info)(message)
        # 结构化 JSONL
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "level": level, "message": message, **fields}
        with (self.log_dir / "events.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def alert(self, message: str) -> None:
        self.metrics.incr("alerts")
        self.log("warning", message, kind="alert")
        if self.alert_hook:
            try:
                self.alert_hook(message)
            except Exception as exc:  # noqa: BLE001
                self.logger.error("告警回调失败: %s", exc)

    # ---- 心跳 ----
    def start_heartbeat(self) -> None:
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._stop.clear()
        self._heartbeat_thread = threading.Thread(target=self._beat, daemon=True)
        self._heartbeat_thread.start()

    def _beat(self) -> None:
        while not self._stop.wait(self._heartbeat_interval):
            self.log("debug", "heartbeat", kind="heartbeat")
            self.metrics.incr("heartbeats")

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        """停止心跳并关闭日志句柄，释放文件。"""
        self.stop()
        for handler in list(self.logger.handlers):
            try:
                handler.close()
                self.logger.removeHandler(handler)
            except Exception:  # noqa: BLE001
                pass
