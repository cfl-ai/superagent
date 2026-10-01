"""层基类与任务上下文。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from superagent.core.state import TaskStateMachine, TaskState


@dataclass
class TaskContext:
    """单次任务上下文。"""

    task_id: str
    user_input: str
    language: str = "zh"
    project_dir: Path = field(default_factory=Path)
    state: TaskStateMachine = field(default_factory=TaskStateMachine)
    plan: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def note(self, message: str) -> None:
        self.notes.append(message)


class Layer(ABC):
    """能力层统一接口。"""

    name: str = "layer"

    @abstractmethod
    def run(self, ctx: TaskContext, runtime) -> Any:
        """执行该层职责。runtime 为 :class:`superagent.core.runtime.Runtime`。"""
