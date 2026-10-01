"""事件总线（轻量发布/订阅，供各层解耦通信）。"""
from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any, Callable

Handler = Callable[[str, Any], None]


class EventBus:
    def __init__(self):
        self._lock = threading.Lock()
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event: str, handler: Handler) -> None:
        with self._lock:
            self._subs[event].append(handler)

    def publish(self, event: str, payload: Any = None) -> None:
        with self._lock:
            handlers = list(self._subs.get(event, []))
        for h in handlers:
            try:
                h(event, payload)
            except Exception:  # noqa: BLE001
                # 事件处理器异常不应中断主流程；由可观测性层记录
                pass
