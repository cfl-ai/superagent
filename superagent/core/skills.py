"""技能系统（修订版第 5 节(七) 功能自主扩展）。

技能是面向用户的可选择能力单元：内置技能 + 用户可添加自定义技能。
内置技能映射到各能力层；自定义技能可触发 ToolForge 实际创建工具函数。
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict

_BUILTIN = [
    ("chat", "对话", "通用", "通用多轮对话", False),
    ("code", "代码工程", "生产", "全栈代码开发 + 真实运行验证 + 自动修复", False),
    ("design", "平面设计", "生产", "HTML 设计多候选 + SVG Logo", False),
    ("video", "视频制片", "生产", "剧本 + 分镜脚本 + 视频生成", False),
    ("image_gen", "图片生成", "媒体", "文生图（智谱 CogView）", False),
    ("video_gen", "视频生成", "媒体", "文生视频（智谱 CogVideoX）", False),
    ("search", "联网检索", "工具", "Bing/DuckDuckGo 全网检索 + 来源登记", False),
    ("file", "文件解析", "工具", "txt/md/json/csv/xlsx/docx 解析 + LLM 分析", False),
    ("sysops", "系统运维", "工具", "进程/内存/截屏/键鼠/窗口", False),
    ("toolforge", "工具扩展", "扩展", "自主创建并集成新工具", False),
]


@dataclass
class Skill:
    id: str
    name: str
    description: str = ""
    category: str = "自定义"
    enabled: bool = True
    builtin: bool = False


class SkillRegistry:
    def __init__(self):
        self._skills: dict[str, Skill] = {
            sid: Skill(id=sid, name=name, category=cat, description=desc, builtin=True)
            for sid, name, cat, desc, _ in _BUILTIN
        }

    def list(self) -> list[dict]:
        return [asdict(s) for s in self._skills.values()]

    def get(self, sid: str) -> Skill | None:
        return self._skills.get(sid)

    def add(self, name: str, description: str = "", category: str = "自定义") -> Skill:
        import uuid
        sid = "custom_" + uuid.uuid4().hex[:8]
        skill = Skill(id=sid, name=name, description=description, category=category)
        self._skills[sid] = skill
        return skill

    def set_enabled(self, sid: str, enabled: bool) -> bool:
        s = self._skills.get(sid)
        if s is None:
            return False
        s.enabled = enabled
        return True

    def remove(self, sid: str) -> bool:
        s = self._skills.get(sid)
        if s is None or s.builtin:
            return False
        del self._skills[sid]
        return True
