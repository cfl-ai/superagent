"""合规去水印（修订版第 5 节(五)5 合规范围内画面修复去水印）。

仅限去除「自有生成素材」的水印（如 CogVideoX/CogView 生成内容自带水印），
用 ffmpeg delogo 抹除指定区域。严禁去除第三方版权素材水印（S0 硬阻断）。
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from superagent.core.errors import PermissionDenied, SuperAgentError


def remove_watermark(media_url: str, output: str | Path, region: tuple[int, int, int, int] = (10, 10, 200, 80)) -> str:
    """用 ffmpeg delogo 去除自有素材水印，返回输出路径。

    region: (x, y, w, h) 水印区域，需自行根据素材调整。
    """
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        src = td / ("src" + Path(urllib.request.urlparse(media_url).path).suffix or ".mp4")
        req = urllib.request.Request(media_url, headers={"User-Agent": "SuperAgent/0.1"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            src.write_bytes(resp.read())

        x, y, w, h = region
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(src), "-vf", f"delogo=x={x}:y={y}:w={w}:h={h}",
             "-c:v", "libx264", "-crf", "23", "-c:a", "aac", str(out)],
            capture_output=True, text=True, timeout=600,
        )
        if r.returncode != 0:
            raise SuperAgentError(f"去水印失败: {r.stderr.strip()[-400:]}")
        return str(out)


def remove_image_watermark(image_url: str, output: str | Path, region: tuple[int, int, int, int] = (10, 10, 200, 80)) -> str:
    """去除自有图片水印（ffmpeg delogo 同样适用于图片）。"""
    return remove_watermark(image_url, output, region)
