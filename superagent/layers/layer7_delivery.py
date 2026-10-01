"""第 7 层：人工决策交付层（修订版第 5 节(九) + 第 7 节）。

- 归档：项目分类目录 + 参考资料清单
- 打包 ZIP + README
- 对外提交（delivery.submit）前必须人工终审
"""
from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

from superagent.core.errors import SuperAgentError
from superagent.layers.base import Layer, TaskContext


class DeliveryLayer(Layer):
    name = "layer7_delivery"

    def run(self, ctx: TaskContext, runtime) -> dict:
        # 归档（分类子目录）
        archive = self._archive(ctx, runtime)
        ctx.artifacts["archive"] = archive
        # 打包
        package = self._package(ctx, runtime)
        ctx.artifacts["delivery_package"] = package
        # 对外提交前强制人工终审
        self._require_approval(ctx, runtime)
        return {"archive": archive, "package": package, "approved": True}

    def _archive(self, ctx: TaskContext, runtime) -> dict:
        root = ctx.project_dir
        for sub in ("01_需求文档", "02_源代码", "03_设计稿", "04_视频", "05_交付包"):
            (root / sub).mkdir(parents=True, exist_ok=True)
        # 确保参考资料清单存在
        if not runtime.config.manifest_path.exists():
            runtime.config.manifest_path.parent.mkdir(parents=True, exist_ok=True)
            runtime.config.manifest_path.write_text("# 参考资料清单\n\n", encoding="utf-8")
        return {"root": str(root), "structure": ["01_需求文档", "02_源代码", "03_设计稿", "04_视频", "05_交付包"]}

    def _package(self, ctx: TaskContext, runtime) -> str:
        pkg_dir = ctx.project_dir / "05_交付包"
        pkg_dir.mkdir(parents=True, exist_ok=True)
        zip_path = pkg_dir / f"{ctx.task_id}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in sorted(ctx.project_dir.rglob("*")):
                if p.is_file() and "05_交付包" not in p.parts and ".zip" not in p.suffix:
                    zf.write(p, p.relative_to(ctx.project_dir))
        return str(zip_path)

    def _require_approval(self, ctx: TaskContext, runtime) -> None:
        """对外提交前必须人工终审（对应修订版硬规则）。"""
        from superagent.hitl.approval import request_decision

        req = request_decision(
            runtime,
            "delivery.submit",
            resource=str(ctx.project_dir),
            reason="交付包提交客户前人工终审",
        )
        if req.decision.value != "approve":
            raise SuperAgentError(f"交付被驳回：{req.feedback}")
        runtime.audit.record(
            subject=runtime.config.security.default_role,
            action="delivery.submit", level="S1", result="approved",
            obj=str(ctx.project_dir),
            approval_chain=[{"decision": req.decision.value, "feedback": req.feedback}],
        )
