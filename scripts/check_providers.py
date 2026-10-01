"""检测各 OpenAI 兼容提供商的连通性（密钥从环境变量读取，不落盘）。

用法：
    $env:DEEPSEEK_API_KEY="..."; $env:ZHIPU_API_KEY="..."; $env:BAILIAN_API_KEY="..."
    python scripts/check_providers.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from superagent.core.config import LLMConfig
from superagent.llm.backend import OpenAIBackend

PROVIDERS = [
    ("deepseek", "https://api.deepseek.com/v1", "deepseek-chat", "DEEPSEEK_API_KEY"),
    ("zhipu", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash", "ZHIPU_API_KEY"),
    ("bailian", "https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus", "BAILIAN_API_KEY"),
]


def main() -> int:
    ok = 0
    for name, base_url, model, env in PROVIDERS:
        key = os.environ.get(env, "")
        if not key:
            print(f"[{name:9s}] 跳过（未提供 {env}）")
            continue
        backend = OpenAIBackend(LLMConfig(provider="openai", base_url=base_url, model=model))
        backend.api_key = key
        try:
            reply = backend.complete(
                [{"role": "user", "content": "请只回复两个字：pong"}], temperature=0.0
            )
            print(f"[{name:9s}] ✅ 连通  -> {reply[:80]}")
            ok += 1
        except Exception as exc:  # noqa: BLE001
            print(f"[{name:9s}] ❌ 失败  -> {exc}")
    print(f"\n可连通提供商: {ok}/{len(PROVIDERS)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
