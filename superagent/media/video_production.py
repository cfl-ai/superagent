"""视频制片：多场景片段合成（打斗场景作为片段嵌入成片）。

修订版第 5 节(五)：多视角差异化运镜 + 打斗镜头作为片段 + 合成成片。
"""
from __future__ import annotations

from pathlib import Path

# 多视角差异化镜头语言（修订版 (五)3）
CAMERA_VIEWS = {
    "first_person": "主观第一视角，镜头随主体运动",
    "tracking": "跟拍镜头，镜头平稳跟随主体",
    "low_angle": "低机位压迫镜头，仰拍增强压迫感",
    "high_angle": "高位俯瞰镜头，俯拍展现全局",
    "orbit": "环绕运镜，镜头围绕主体旋转",
    "closeup": "特写镜头，聚焦关键细节",
    "slow_motion": "慢镜头，动作细节放大",
}


def build_scene_prompt(description: str, view: str | None = None) -> str:
    """构建带多视角镜头语言的场景提示词。"""
    if view and view in CAMERA_VIEWS:
        return f"{description}。{CAMERA_VIEWS[view]}。"
    return description


def compose_scenes(scenes: list[dict], output: str | Path, grade: str = "warm",
                   subtitle_lines: list[str] | None = None) -> str:
    """将多个场景（普通/打斗）作为片段生成并合成一部视频。

    scenes: [{type: normal|fight, description, view?, style?}]
    """
    from superagent.llm.backend import generate_video
    from superagent.media.fight import generate_fight
    from superagent.media.video_editor import compose

    urls = []
    for s in scenes:
        desc = (s.get("description") or "").strip()
        if not desc:
            continue
        if s.get("type") == "fight":
            urls.append(generate_fight(s.get("style", "street"), desc))
        else:
            urls.append(generate_video(build_scene_prompt(desc, s.get("view"))))

    if not urls:
        raise ValueError("无有效场景")

    subs = subtitle_lines if subtitle_lines else [s.get("description", "") for s in scenes]
    return compose(urls, output, subtitle_lines=subs, grade=grade)
