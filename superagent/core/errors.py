"""统一异常体系。

所有框架内部错误继承 :class:`SuperAgentError`，便于上层统一捕获与审计。
"""
from __future__ import annotations


class SuperAgentError(Exception):
    """框架根异常。"""

    code = "SUPERAGENT_ERROR"

    def __init__(self, message: str, *, code: str | None = None, **context):
        self.message = message
        self.code = code or self.code
        self.context = context or {}
        super().__init__(message)

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "context": self.context}


class ConfigError(SuperAgentError):
    code = "CONFIG_ERROR"


class PermissionDenied(SuperAgentError):
    """S0 硬阻断或权限不足。"""

    code = "PERMISSION_DENIED"

    def __init__(self, message: str, *, action: str, level: str, **context):
        super().__init__(message, action=action, level=level, **context)


class ApprovalRequired(SuperAgentError):
    """S1 操作需人工审批；异常本身可携带审批请求对象。"""

    code = "APPROVAL_REQUIRED"

    def __init__(self, message: str, *, request=None, **context):
        super().__init__(message, **context)
        self.request = request


class ApprovalTimeout(SuperAgentError):
    code = "APPROVAL_TIMEOUT"


class SnapshotError(SuperAgentError):
    code = "SNAPSHOT_ERROR"


class SourceTraceError(SuperAgentError):
    code = "SOURCE_TRACE_ERROR"


class LLMBackendError(SuperAgentError):
    code = "LLM_BACKEND_ERROR"


class ToolRegistryError(SuperAgentError):
    code = "TOOL_REGISTRY_ERROR"


class StateMachineError(SuperAgentError):
    code = "STATE_MACHINE_ERROR"


class SelfCheckFailed(SuperAgentError):
    """自检/质量评分不达标。"""

    code = "SELF_CHECK_FAILED"
