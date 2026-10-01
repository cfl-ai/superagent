"""工具/Skill 注册表（修订版第 5 节(七) 功能自主扩展）。

支持运行时注册新工具，新工具纳入权限分级与安全校验。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from superagent.core.errors import ToolRegistryError

ToolFn = Callable[..., Any]


@dataclass
class Tool:
    name: str
    fn: ToolFn
    description: str = ""
    action: str = ""  # 关联权限动作名，用于分级
    high_risk: bool = False
    metadata: dict = field(default_factory=dict)

    def __call__(self, *args, **kwargs):
        return self.fn(*args, **kwargs)


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ToolRegistryError(f"工具已存在: {tool.name}")
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool:
        if name not in self._tools:
            raise ToolRegistryError(f"工具不存在: {name}")
        return self._tools[name]

    def names(self) -> list[str]:
        return sorted(self._tools)

    def list(self) -> list[Tool]:
        return [self._tools[n] for n in sorted(self._tools)]
