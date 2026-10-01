"""配置加载与运行时上下文。

配置为 JSON（零第三方依赖），支持环境变量覆盖关键项。
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from superagent.core.errors import ConfigError


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_dotenv(path: Path) -> None:
    """极简 .env 加载：读取 KEY=VALUE 行，仅设置尚未定义的环境变量。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


@dataclass
class LLMConfig:
    provider: str = "mock"  # mock | openai | null
    base_url: str = "https://api.openai.com/v1"
    api_key_env: str = "SUPERAGENT_LLM_API_KEY"
    model: str = "gpt-4o-mini"
    timeout_s: float = 60.0
    temperature: float = 0.2


@dataclass
class SecurityConfig:
    default_role: str = "visitor"  # visitor | operator | admin
    audit_db_path: str = "data/audit.db"
    snapshot_dir: str = "data/snapshots"
    # 白名单：S2 自动放行且不触发审批的操作（前缀匹配）
    whitelist_prefixes: list[str] = field(
        default_factory=lambda: [
            "read.", "search.", "venv.pip.install.", "venv.npm.install.",
            "font.install.", "template.install.", "cache.clean.",
            "production.", "tool.run.",
        ]
    )
    # S1 需审批的前缀
    approval_prefixes: list[str] = field(
        default_factory=lambda: [
            "system.install.", "software.install.", "file.delete.",
            "agent.deploy.", "delivery.submit.", "registry.modify.",
            "system.clean.", "driver.", "tool.create.high_risk.",
        ]
    )
    # S0 硬阻断前缀
    blocked_prefixes: list[str] = field(
        default_factory=lambda: [
            "system.delete.core.", "registry.write.", "driver.modify.",
            "watermark.remove.third_party.",
        ]
    )


@dataclass
class HITLConfig:
    timeout_s: float = 600.0
    storage_path: str = "data/approvals.jsonl"


@dataclass
class SourcingConfig:
    manifest_path: str = "01_需求文档/参考资料清单.md"


@dataclass
class ObservabilityConfig:
    log_dir: str = "data/logs"
    heartbeat_interval_s: float = 5.0
    alert_enabled: bool = True


@dataclass
class QualityConfig:
    pass_threshold: float = 7.0
    max_iterations: int = 3


@dataclass
class Config:
    project_root: Path = field(default_factory=Path.cwd)
    llm: LLMConfig = field(default_factory=LLMConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    hitl: HITLConfig = field(default_factory=HITLConfig)
    sourcing: SourcingConfig = field(default_factory=SourcingConfig)
    observability: ObservabilityConfig = field(default_factory=ObservabilityConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)

    # ---- 路径解析 ----
    @property
    def audit_db_path(self) -> Path:
        return self.project_root / self.security.audit_db_path

    @property
    def snapshot_dir(self) -> Path:
        return self.project_root / self.security.snapshot_dir

    @property
    def approvals_path(self) -> Path:
        return self.project_root / self.hitl.storage_path

    @property
    def manifest_path(self) -> Path:
        return self.project_root / self.sourcing.manifest_path

    @property
    def log_dir(self) -> Path:
        return self.project_root / self.observability.log_dir

    def ensure_dirs(self) -> None:
        for p in (self.snapshot_dir, self.manifest_path.parent, self.log_dir):
            p.mkdir(parents=True, exist_ok=True)

    # ---- 序列化 ----
    def to_dict(self) -> dict[str, Any]:
        return {
            "llm": self.llm.__dict__,
            "security": self.security.__dict__,
            "hitl": self.hitl.__dict__,
            "sourcing": self.sourcing.__dict__,
            "observability": self.observability.__dict__,
            "quality": self.quality.__dict__,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any], project_root: Path) -> "Config":
        cfg = cls(project_root=project_root)
        for section, datacls in (
            ("llm", LLMConfig),
            ("security", SecurityConfig),
            ("hitl", HITLConfig),
            ("sourcing", SourcingConfig),
            ("observability", ObservabilityConfig),
            ("quality", QualityConfig),
        ):
            if section in d:
                known = {f.name for f in datacls.__dataclass_fields__.values()}
                setattr(cfg, section, datacls(**{k: v for k, v in d[section].items() if k in known}))
        return cfg

    @classmethod
    def load(cls, path: str | Path | None = None) -> "Config":
        if path is None:
            path = Path(os.environ.get("SUPERAGENT_CONFIG", "config/default.json"))
        path = Path(path)
        root = path.parent.parent
        # 加载项目根目录 .env（若存在）
        load_dotenv(root / ".env")
        if not path.exists():
            # 无配置文件时使用默认值
            return cls(project_root=root)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"读取配置失败: {path}: {exc}") from exc
        cfg = cls.from_dict(data, project_root=root)
        # 环境变量覆盖（优先级高于配置文件）
        cfg.llm.provider = os.environ.get("SUPERAGENT_LLM_PROVIDER", cfg.llm.provider)
        cfg.llm.model = os.environ.get("SUPERAGENT_LLM_MODEL", cfg.llm.model)
        cfg.llm.base_url = os.environ.get("OPENAI_BASE_URL", cfg.llm.base_url)
        if _env_bool("SUPERAGENT_DRY_RUN", False):
            cfg.security.default_role = "visitor"
        return cfg
