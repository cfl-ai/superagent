"""打斗镜头编排（修订版第 5 节(五)2：人体力学、发力逻辑、受力反馈）。

支持街头格斗 / 武术 / 军警近身搏杀多种风格，生成符合人体力学的打斗视频。
"""
from __future__ import annotations

FIGHT_STYLES = {
    "street": "街头格斗风格：近身缠斗、直拳勾拳组合、肘击膝撞，动作迅猛直接、招招致命",
    "martial": "武术格斗风格：身法灵活、寸劲发力、招式连贯，刚柔并济、收发自如",
    "military": "军警近身搏杀风格：擒拿锁技、关节控制、快速制服，简洁高效、一击制敌",
}

_MECHANICS = (
    "遵循人体力学：发力由脚掌蹬地→腰胯扭转→肩背传导→拳脚释放，重心稳定下沉，"
    "动作有蓄力与爆发两个阶段；受力方有真实反馈：格挡卸力、身体后仰、缓冲退步。"
    "打斗真实有力，避免花哨无力的动作，镜头有冲击感。"
)


def build_fight_prompt(style: str = "street", description: str = "") -> str:
    """构建符合人体力学的打斗镜头提示词。"""
    base = FIGHT_STYLES.get(style, FIGHT_STYLES["street"])
    desc = f"。{description.strip('。')}" if description else ""
    return f"{base}{desc}。{_MECHANICS}"


def generate_fight(style: str = "street", description: str = "", model: str = "cogvideox-flash") -> str:
    """生成打斗视频，返回视频 URL。"""
    from superagent.llm.backend import generate_video
    prompt = build_fight_prompt(style, description)
    return generate_video(prompt, model=model)
