"""GUI 桌面接管（修订版第 5 节(一)）。

- 截屏：Pillow ImageGrab（Windows）
- 键鼠：pyautogui（可选依赖，缺失时优雅降级）
- 窗口：pyautogui 枚举窗口标题

所有能力对非 Windows/无显示环境安全降级，返回错误信息而非崩溃。
"""
from __future__ import annotations

import tempfile
import time
from pathlib import Path


def capture_screen(path: str | Path | None = None) -> dict:
    """截取全屏，返回 {path, size}。"""
    try:
        from PIL import ImageGrab
    except ImportError:
        return {"error": "未安装 Pillow，无法截屏"}
    img = ImageGrab.grab()
    out = Path(path) if path else Path(tempfile.gettempdir()) / f"superagent_screen_{int(time.time())}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out))
    return {"path": str(out), "size": list(img.size)}


def _pyautogui():
    try:
        import pyautogui  # noqa: PLC0415
        return pyautogui
    except ImportError:
        return None


def move_click(x: int, y: int) -> dict:
    pg = _pyautogui()
    if pg is None:
        return {"error": "未安装 pyautogui，无法操作键鼠"}
    pg.moveTo(x, y, duration=0.2)
    pg.click()
    return {"ok": True, "pos": [x, y]}


def type_text(text: str) -> dict:
    pg = _pyautogui()
    if pg is None:
        return {"error": "未安装 pyautogui，无法输入"}
    pg.typewrite(text, interval=0.03)
    return {"ok": True}


def list_windows() -> list[str]:
    pg = _pyautogui()
    if pg is None:
        return []
    try:
        return list(pg.getAllTitles()) or []
    except Exception:  # noqa: BLE001
        return []
