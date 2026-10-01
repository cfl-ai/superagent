"""第 5 层：全能生产层（修订版第 5 节(三)(四)(五)）。

多模态生产入口，产出真实文件：
- code：全栈代码脚手架（LLM 生成 main.py，写文件 + 测试骨架）
- design：生成多套 HTML 视觉设计候选（LLM 生成，需 HITL 择优）
- video：生成完整剧本 + 分镜脚本（LLM 生成，markdown 落盘）
- agent：生成可运行 Agent 脚手架（LLM 生成，部署前 S1 审批）
所有 LLM 调用失败自动回退确定性脚手架，保证离线可用。
"""
from __future__ import annotations

from pathlib import Path

from superagent.layers.base import Layer, TaskContext


class ProductionLayer(Layer):
    name = "layer5_production"

    def run(self, ctx: TaskContext, runtime) -> dict:
        spec = ctx.plan.get("production", {})
        kind = spec.get("kind", "general")
        if kind == "code":
            return {"code": self._produce_code(ctx, spec, runtime)}
        if kind == "design":
            return {"design": self._produce_design(ctx, spec, runtime)}
        if kind == "video":
            return {"video": self._produce_video(ctx, spec, runtime)}
        if kind == "agent":
            return {"agent": self._produce_agent(ctx, spec, runtime)}
        return {"status": "produced", "kind": kind}

    # ---- LLM 辅助 ----
    def _llm_text(self, runtime, system: str, user: str) -> str | None:
        try:
            text = runtime.llm.complete([
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ])
            if text and not text.startswith("[mock]") and text.strip():
                return text.strip()
        except Exception:  # noqa: BLE001
            pass
        return None

    # ---- 代码 ----
    def _produce_code(self, ctx: TaskContext, spec: dict, runtime, fix_hint: str = "") -> dict:
        name = spec.get("name", "app")
        project = ctx.project_dir / name
        project.mkdir(parents=True, exist_ok=True)
        main_code = self._llm_code(spec, runtime, fix_hint=fix_hint)
        (project / "README.md").write_text(f"# {name}\n\n{spec.get('spec', '')}\n", encoding="utf-8")
        (project / "main.py").write_text(main_code, encoding="utf-8")
        tests_dir = project / "tests"
        tests_dir.mkdir(exist_ok=True)
        (tests_dir / "test_main.py").write_text(
            'import subprocess\n\n\ndef test_main_runs():\n    r = subprocess.run(["python", "-c", "import sys; sys.path.insert(0, \'.\'); import main; main.main()"],\n                       cwd=".", capture_output=True, text=True)\n    assert r.returncode == 0\n',
            encoding="utf-8",
        )
        ctx.artifacts["code_project"] = str(project)
        return {"project": str(project), "files": ["README.md", "main.py", "tests/test_main.py"]}

    def _llm_code(self, spec: dict, runtime, fix_hint: str = "") -> str:
        from superagent.llm.backend import strip_code_fence
        user = f"需求: {spec.get('spec', '')}"
        if fix_hint:
            user += f"\n\n上次生成的代码验证失败，错误如下，请修复后重新只输出完整代码：\n{fix_hint}"
        text = self._llm_text(
            runtime,
            "你是资深全栈工程师。根据需求生成一个可运行的单文件 Python main.py，只输出代码，不要解释。",
            user,
        )
        if text:
            return strip_code_fence(text) + "\n"
        name = spec.get("name", "app")
        return (
            'def main():\n'
            f'    print("Hello from {name}")\n\n\n'
            'if __name__ == "__main__":\n'
            '    main()\n'
        )

    # ---- 设计 ----
    def _produce_design(self, ctx: TaskContext, spec: dict, runtime) -> dict:
        from superagent.llm.backend import strip_code_fence
        design_dir = ctx.project_dir / "03_设计稿"
        design_dir.mkdir(parents=True, exist_ok=True)
        styles = [
            ("modern_minimal", "现代极简风格，大量留白，柔和配色，清晰栅格"),
            ("brand_business", "商务品牌风格，稳重配色，品牌感强，栅格布局"),
        ]
        candidates = []
        for i, (label, style) in enumerate(styles, 1):
            html = self._llm_text(
                runtime,
                f"你是资深商业设计师。为以下需求生成一个完整单文件 HTML 网页设计（含内联 CSS）。"
                f"设计要求：{style}。只输出完整 HTML 代码，不要解释。",
                f"需求: {spec.get('spec', '')}",
            )
            if html:
                html = strip_code_fence(html)
                path = design_dir / f"candidate_{i}_{label}.html"
                path.write_text(html, encoding="utf-8")
                candidates.append({"path": str(path), "style": label})
        # SVG Logo（矢量，无需位图生成模型）
        svg = self._llm_text(
            runtime,
            "你是品牌设计师。为以下需求设计一个简洁 SVG Logo（纯矢量，含 viewBox，"
            "不超过 200 行，只输出 SVG 代码）。",
            f"需求: {spec.get('spec', '')}",
        )
        if svg:
            svg = strip_code_fence(svg)
            logo_path = design_dir / "logo.svg"
            logo_path.write_text(svg, encoding="utf-8")
            ctx.artifacts["design_logo"] = str(logo_path)
            candidates.append({"path": str(logo_path), "style": "logo"})
        ctx.artifacts["design_candidates"] = candidates
        return {"design": {"candidates": candidates, "note": "多套候选已生成，需 HITL 择优"}}

    # ---- 视频 ----
    def _produce_video(self, ctx: TaskContext, spec: dict, runtime) -> dict:
        video_dir = ctx.project_dir / "04_视频"
        video_dir.mkdir(parents=True, exist_ok=True)
        script = self._llm_text(
            runtime,
            "你是专业导演兼编剧。为以下需求写一份完整剧本：包含主题、人物/角色、分场大纲、"
            "每场动作与台词。输出 markdown。",
            f"需求: {spec.get('spec', '')}",
        ) or f"# 剧本\n\n需求：{spec.get('spec', '')}\n\n（待生成）\n"
        storyboard = self._llm_text(
            runtime,
            "你是专业分镜师。基于剧本写分镜脚本：表格列（镜号、景别、运镜、画面内容、台词/音效、时长）。输出 markdown。",
            f"剧本: {script}",
        ) or f"# 分镜脚本\n\n（待生成）\n"
        script_path = video_dir / "剧本.md"
        storyboard_path = video_dir / "分镜脚本.md"
        script_path.write_text(script, encoding="utf-8")
        storyboard_path.write_text(storyboard, encoding="utf-8")
        ctx.artifacts["video_script"] = str(script_path)

        # 可选：关键帧画面生成（智谱 CogView，默认关闭以节省配额）
        frames = []
        n_frames = int(spec.get("frames", 0) or 0)
        if n_frames > 0:
            from superagent.llm.backend import generate_image
            for i in range(n_frames):
                try:
                    url = generate_image(f"分镜第{i+1}帧：{script[:120]}")
                    frames.append({"frame": i + 1, "url": url})
                except Exception as exc:  # noqa: BLE001
                    frames.append({"frame": i + 1, "error": str(exc)})
        return {"video": {"script": str(script_path), "storyboard": str(storyboard_path), "frames": frames}}

    # ---- Agent 自研 ----
    def _produce_agent(self, ctx: TaskContext, spec: dict, runtime) -> dict:
        from superagent.hitl.approval import request_decision
        agent_dir = ctx.project_dir / "agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        main_code = self._llm_text(
            runtime,
            "你是大模型应用工程师。生成一个最小可运行的 Python Agent 主程序 main.py"
            "（含 Agent 主循环：接收任务→调用 LLM→输出结果），只输出代码。",
            f"需求: {spec.get('spec', '')}",
        )
        if main_code:
            from superagent.llm.backend import strip_code_fence
            (agent_dir / "main.py").write_text(strip_code_fence(main_code) + "\n", encoding="utf-8")
        (agent_dir / "README.md").write_text(
            f"# Agent\n\n{spec.get('spec', '')}\n\n部署前需人工审批。\n", encoding="utf-8"
        )
        # 部署属高危，S1 强制审批（登录授信不豁免）
        req = request_decision(
            runtime,
            "agent.deploy",
            resource=str(agent_dir),
            reason=spec.get("spec", ""),
        )
        if req.decision.value != "approve":
            raise RuntimeError(f"Agent 部署被驳回: {req.feedback}")
        ctx.artifacts["agent_project"] = str(agent_dir)
        return {"agent": {"status": "deployed", "dir": str(agent_dir)}}
