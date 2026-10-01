"""可插拔 LLM 后端（修订版第 13 节技术选型）。

- OpenAIBackend：OpenAI 兼容 Chat Completions API（纯标准库 urllib，零依赖）。
- MockBackend：确定性回显，用于无密钥离线测试。
- NullBackend：静默，用于纯编排测试。

通过 `SUPERAGENT_LLM_API_KEY` 环境变量注入密钥。
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from superagent.core.config import LLMConfig
from superagent.core.errors import LLMBackendError


def strip_code_fence(text: str) -> str:
    """剥离 Markdown 代码围栏（```lang ... ```）。"""
    text = text.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]  # 去掉首行 ``` 及语言标记
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]  # 去掉末尾 ```
    return "\n".join(lines).strip()


class LLMBackend(ABC):
    @abstractmethod
    def complete(self, messages: list[dict[str, str]], **kwargs) -> str:
        """返回模型文本回复。"""


class OpenAIBackend(LLMBackend):
    def __init__(self, config: LLMConfig):
        self.config = config
        # 多源回退：SUPERAGENT_LLM_API_KEY → OPENAI_API_KEY
        self.api_key = os.environ.get(config.api_key_env) or os.environ.get("OPENAI_API_KEY", "")

    def complete(self, messages: list[dict[str, str]], **kwargs) -> str:
        if not self.api_key:
            raise LLMBackendError(
                f"缺少 API Key，请设置环境变量 {self.config.api_key_env}"
            )
        url = self.config.base_url.rstrip("/") + "/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": kwargs.get("temperature", self.config.temperature),
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_s) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
        except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMBackendError(f"LLM 调用失败: {exc}") from exc


class MockBackend(LLMBackend):
    """确定性回显后端：返回输入与提示拼接，便于离线验证编排逻辑。"""

    def complete(self, messages: list[dict[str, str]], **kwargs) -> str:
        last = messages[-1]["content"] if messages else ""
        return f"[mock] 已收到指令：{last[:80]}"


class NullBackend(LLMBackend):
    def complete(self, messages: list[dict[str, str]], **kwargs) -> str:
        return ""


# OpenAI 兼容提供商预设：provider 名 → base_url 与默认模型
PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    "zhipu": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    "bailian": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "model": "qwen-plus"},
}


def generate_image(prompt: str, *, model: str = "cogview-3-flash", size: str = "1024x1024") -> str:
    """文本生成图像（智谱 CogView，OpenAI 兼容 images 端点）。返回图片 URL。"""
    api_key = os.environ.get("ZHIPU_API_KEY", "")
    if not api_key:
        raise LLMBackendError("缺少 ZHIPU_API_KEY，无法生成图像")
    url = "https://open.bigmodel.cn/api/paas/v4/images/generations"
    payload = {"model": model, "prompt": prompt, "size": size}
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["data"][0]["url"]
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError) as exc:
        raise LLMBackendError(f"图像生成失败: {exc}") from exc


def build_backend(config: LLMConfig) -> LLMBackend:
    provider = config.provider.lower()
    if provider in PROVIDER_PRESETS:
        preset = PROVIDER_PRESETS[provider]
        # 环境变量可覆盖 base_url / model，密钥优先取 {PROVIDER}_API_KEY
        cfg = LLMConfig(
            provider="openai",
            base_url=os.environ.get("OPENAI_BASE_URL", preset["base_url"]),
            api_key_env=f"{provider.upper()}_API_KEY",
            model=os.environ.get("SUPERAGENT_LLM_MODEL", preset["model"]),
            timeout_s=config.timeout_s,
            temperature=config.temperature,
        )
        backend = OpenAIBackend(cfg)
        if not backend.api_key:
            backend.api_key = os.environ.get(config.api_key_env) or os.environ.get("OPENAI_API_KEY", "")
        return backend
    if provider == "openai":
        return OpenAIBackend(config)
    if provider == "auto":
        # 有密钥则用真实 OpenAI，否则回退 mock（便于离线开发）
        if os.environ.get(config.api_key_env) or os.environ.get("OPENAI_API_KEY"):
            return OpenAIBackend(config)
        return MockBackend()
    if provider == "mock":
        return MockBackend()
    if provider == "null":
        return NullBackend()
    raise LLMBackendError(f"未知 LLM provider: {config.provider}")
