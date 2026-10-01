"""视频制片剪辑管线（修订版第 5 节(五)）。

基于 ffmpeg 实现：片段拼接 / 转场 / 字幕 / 调色 / 配乐合成。
输出合成后的成片。所有 ffmpeg 调用通过 subprocess，无第三方 Python 依赖。
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from superagent.core.errors import SuperAgentError

_GRADES = {
    "warm": "eq=brightness=0.03:saturation=1.15:contrast=1.03",
    "cinematic": "eq=saturation=0.92:contrast=1.08:brightness=-0.02",
    "vivid": "eq=saturation=1.25:contrast=1.05",
    "none": "",
}


def _run(cmd: list[str], timeout: int = 900) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise SuperAgentError(f"ffmpeg 失败: {r.stderr.strip()[:400]}")
    return r.stdout


def _download(url: str, path: Path) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": "SuperAgent/0.1"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        path.write_bytes(resp.read())
    return path


def _duration(path: Path) -> float:
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=60,
        )
        return float(out.stdout.strip())
    except (ValueError, subprocess.SubprocessError, OSError):
        return 5.0


def concat_clips(clip_urls: list[str], output: str | Path, transition: str = "fade", transition_s: float = 0.5) -> str:
    """下载多个视频片段，统一分辨率/帧率后用 xfade 转场拼接。返回输出路径。"""
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        paths = [_download(url, td / f"clip_{i}.mp4") for i, url in enumerate(clip_urls)]

        if len(paths) == 1:
            shutil.copy2(paths[0], out)
            return str(out)

        n = len(paths)
        inputs = [arg for p in paths for arg in ("-i", str(p))]
        fparts = [
            f"[{i}:v]scale=1280:720:force_original_aspect_ratio=decrease,"
            f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{i}]"
            for i in range(n)
        ]
        cur = "[v0]"
        for i in range(1, n):
            off = max(0.5, _duration(paths[i - 1]) - transition_s)
            nxt = f"[x{i}]"
            fparts.append(f"{cur}[v{i}]xfade=transition={transition}:duration={transition_s}:offset={off:.2f}{nxt}")
            cur = nxt
        fparts.append(f"{cur}format=yuv420p[vout]")
        _run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fparts), "-map", "[vout]",
              "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p", str(out)])
        return str(out)


def make_srt(subtitle_lines: list[str], total_s: float) -> str:
    """根据文本行生成 SRT 字幕，按时长均分。"""
    if not subtitle_lines:
        return ""
    seg = total_s / len(subtitle_lines)
    parts = []
    for i, line in enumerate(subtitle_lines):
        start = i * seg
        end = start + seg
        parts.append(f"{i + 1}\n{_ts(start)} --> {_ts(end)}\n{line}\n")
    return "\n".join(parts)


def _ts(s: float) -> str:
    h = int(s // 3600); m = int(s % 3600 // 60); sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:05.2f}".replace(".", ",")


def compose(clip_urls: list[str], output: str | Path, subtitle_lines: list[str] | None = None,
            grade: str = "warm", bgm_url: str | None = None) -> str:
    """完整剪辑管线：拼接 → 字幕 → 调色 →（配乐）。返回成片路径。"""
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.stem + "_concat.mp4")
    concat_clips(clip_urls, tmp)
    total = _duration(tmp)

    current = tmp
    # 字幕
    if subtitle_lines:
        srt_text = make_srt(subtitle_lines, total)
        srt_path = out.with_suffix(".srt")
        srt_path.write_text(srt_text, encoding="utf-8")
        sub_out = out.with_name(out.stem + "_sub.mp4")
        _run(["ffmpeg", "-y", "-i", str(current), "-vf",
              f"subtitles='{srt_path.name}':force_style='FontName=Microsoft YaHei,FontSize=20'",
              "-c:v", "libx264", "-crf", "23", "-c:a", "aac", str(sub_out)])
        current = sub_out

    # 调色
    eq = _GRADES.get(grade, "")
    if eq:
        grade_out = out.with_name(out.stem + "_grade.mp4")
        _run(["ffmpeg", "-y", "-i", str(current), "-vf", eq, "-c:v", "libx264", "-crf", "23", "-c:a", "aac", str(grade_out)])
        current = grade_out

    # 配乐（可选）
    if bgm_url:
        bgm_path = out.with_name(out.stem + "_bgm.mp3")
        _download(bgm_url, bgm_path)
        _run(["ffmpeg", "-y", "-i", str(current), "-i", str(bgm_path),
              "-filter_complex", "[1:a]volume=0.3[a1];[0:a][a1]amix=inputs=2:duration=first[a]",
              "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", str(out)])
        return str(out)

    if current != out:
        shutil.move(str(current), str(out))
    return str(out)
