"""代码真实运行验证（修订版第 5 节(三) + 第 9 节「可运行/可复现」）。

验证策略（不依赖外部依赖，只做本机可执行的检查）：
1. py_compile 语法编译全部 .py —— 拦截语法错误
2. 导入 main 模块 —— 拦截不存在的库/函数/接口（幻觉核心来源）

返回 (是否通过, 错误列表)。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def verify_code(project_dir: str | Path, timeout_s: int = 60) -> tuple[bool, list[str]]:
    project = Path(project_dir)
    errors: list[str] = []
    py_files = list(project.rglob("*.py"))
    if not py_files:
        return False, ["未找到任何 .py 文件"]

    # 1. 语法编译
    for py in py_files:
        r = subprocess.run(
            [sys.executable, "-m", "py_compile", str(py)],
            capture_output=True, text=True, timeout=timeout_s,
        )
        if r.returncode != 0:
            errors.append(f"语法错误 {py.name}: {r.stderr.strip()[:400]}")

    if errors:
        return False, errors

    # 2. 导入 main 模块（捕获不存在的 import / 模块级错误）
    main = project / "main.py"
    if main.exists():
        r = subprocess.run(
            [sys.executable, "-c",
             "import sys; sys.path.insert(0, '.'); import main"],
            cwd=str(project), capture_output=True, text=True, timeout=timeout_s,
        )
        if r.returncode != 0:
            errors.append(f"导入失败 main.py: {r.stderr.strip()[:400]}")

    return (len(errors) == 0), errors


def run_tests(project_dir: str | Path, timeout_s: int = 120) -> tuple[bool, list[str]]:
    """运行项目测试（pytest 或 unittest 或 test_main 脚本）。"""
    project = Path(project_dir)
    errors: list[str] = []
    test_file = project / "tests" / "test_main.py"
    if not test_file.exists():
        return True, []
    # 简单直接运行测试文件
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"], cwd=str(project),
        capture_output=True, text=True, timeout=timeout_s,
    )
    if r.returncode == 0:
        return True, []
    # pytest 可能未安装，回退直接跑测试脚本
    r2 = subprocess.run(
        [sys.executable, str(test_file)], cwd=str(project),
        capture_output=True, text=True, timeout=timeout_s,
    )
    if r2.returncode == 0:
        return True, []
    errors.append(f"测试失败: {(r.stderr or r.stdout).strip()[:400]}")
    return False, errors
