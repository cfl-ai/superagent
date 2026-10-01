"""第 1 层：Windows 智能运维（修订版第 5 节(一)）。

提供可实际执行的只读探测与受限清理：
- sysinfo / memory_info（ctypes GlobalMemoryStatusEx）
- list_processes（tasklist）
- clean_temp（S2 白名单，操作前快照 + 审计）

桌面接管（截图/键鼠）为高风险能力，提供接口但默认 S1 审批接入。
"""
from __future__ import annotations

import ctypes
import platform
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from superagent.core.errors import SuperAgentError
from superagent.layers.base import Layer, TaskContext


class _MemoryStatusEx(ctypes.Structure):
    _fields_ = [
        ("dwLength", ctypes.c_ulong),
        ("dwMemoryLoad", ctypes.c_ulong),
        ("ullTotalPhys", ctypes.c_ulonglong),
        ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong),
        ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong),
        ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


def memory_info() -> dict:
    """Windows 物理内存信息（仅 Windows 有效）。"""
    if platform.system() != "Windows":
        return {"platform": platform.system(), "note": "memory_info 仅 Windows 支持"}
    stat = _MemoryStatusEx()
    stat.dwLength = ctypes.sizeof(_MemoryStatusEx)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
    gb = 1024 ** 3
    return {
        "platform": "Windows",
        "load_percent": stat.dwMemoryLoad,
        "total_gb": round(stat.ullTotalPhys / gb, 2),
        "available_gb": round(stat.ullAvailPhys / gb, 2),
    }


def list_processes(limit: int = 50) -> list[dict]:
    """列出占用内存最高的进程（Windows tasklist）。"""
    if platform.system() != "Windows":
        return []
    try:
        out = subprocess.run(
            ["tasklist", "/fo", "csv", "/nh"],
            capture_output=True, text=True, timeout=20, check=False,
        )
        rows = []
        for line in out.stdout.splitlines():
            parts = [p.strip().strip('"') for p in line.split('","')]
            if len(parts) >= 5:
                rows.append({
                    "name": parts[0],
                    "pid": parts[1],
                    "session": parts[2],
                    "session_num": parts[3],
                    "mem_kb": parts[4].replace(",", "").replace(" K", ""),
                })
        rows.sort(key=lambda r: int(r["mem_kb"]) if r["mem_kb"].isdigit() else 0, reverse=True)
        return rows[:limit]
    except (OSError, subprocess.SubprocessError):
        return []


class SystemOpsLayer(Layer):
    name = "layer1_sysops"

    def run(self, ctx: TaskContext, runtime) -> dict:
        plan = ctx.plan.get("sysops", {})
        if not plan:
            return {"status": "skipped"}

        result: dict = {}
        for op in plan.get("ops", []):
            name = op.get("name")
            if name == "sysinfo":
                result["sysinfo"] = {
                    "platform": platform.platform(),
                    "python": platform.python_version(),
                }
            elif name == "memory":
                result["memory"] = memory_info()
            elif name == "processes":
                result["processes"] = list_processes(op.get("limit", 30))
            elif name == "clean_temp":
                result["clean_temp"] = self._clean_temp(runtime, days=op.get("days", 7))
            elif name == "screenshot":
                from superagent.layers.gui import capture_screen
                result["screenshot"] = capture_screen(op.get("path"))
            elif name == "click":
                from superagent.layers.gui import move_click
                result["click"] = move_click(op.get("x", 0), op.get("y", 0))
            elif name == "type":
                from superagent.layers.gui import type_text
                result["type"] = type_text(op.get("text", ""))
            elif name == "windows":
                from superagent.layers.gui import list_windows
                result["windows"] = list_windows()
        return result

    def _clean_temp(self, runtime, days: int = 7) -> dict:
        """清理临时目录中超过 days 天的文件（S2 白名单操作，先快照+审计）。"""
        action = "cache.clean.temp"
        temp_dir = Path(tempfile.gettempdir())
        # 快照（只针对将删除的文件清单）
        snapshot = runtime.snapshots.create(str(temp_dir)) if runtime.config.security.default_role != "visitor" else None
        cutoff = time.time() - days * 86400
        deleted = 0
        try:
            for p in temp_dir.rglob("*"):
                try:
                    if p.is_file() and p.stat().st_mtime < cutoff:
                        p.unlink()
                        deleted += 1
                except OSError:
                    continue
            runtime.audit.record(
                subject=runtime.config.security.default_role,
                action=action, level="S2", result="success",
                obj=str(temp_dir), meta={"deleted": deleted},
            )
            return {"temp_dir": str(temp_dir), "deleted": deleted}
        except OSError as exc:
            runtime.audit.record(
                subject=runtime.config.security.default_role,
                action=action, level="S2", result="failed",
                obj=str(temp_dir), meta={"error": str(exc)},
            )
            raise SuperAgentError(f"临时清理失败: {exc}") from exc
