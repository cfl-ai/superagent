#!/usr/bin/env python
"""通过 paramiko 远程探测/部署 SuperAgent。

凭据从环境变量读取，绝不落盘：
    SA_HOST, SA_USER, SA_PASS, SA_PORT(默认22), SA_LLM_KEY, SA_LLM_PROVIDER(默认deepseek)

用法：
    python deploy/remote.py probe     # 探测服务器环境（只读，不修改）
    python deploy/remote.py deploy    # 上传 + 解压 + 写.env + docker compose 部署 + 健康检查
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paramiko

ROOT = Path(__file__).resolve().parent.parent
TARBALL = ROOT / "superagent-deploy.tar.gz"
APP_DIR = "/opt/superagent"
PORT = "8000"


def env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name)
    if v:
        return v
    if default is not None:
        return default
    print(f"[错误] 缺少环境变量 {name}", file=sys.stderr)
    sys.exit(1)


def connect() -> paramiko.SSHClient:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(
        hostname=env("SA_HOST"),
        port=int(env("SA_PORT", "22")),
        username=env("SA_USER"),
        password=env("SA_PASS"),
        timeout=20,
        allow_agent=False,
        look_for_keys=False,
    )
    return c


def run(c: paramiko.SSHClient, cmd: str, timeout: int = 180) -> tuple[int, str, str]:
    _in, out, err = c.exec_command(cmd, timeout=timeout)
    o = out.read().decode("utf-8", "replace")
    e = err.read().decode("utf-8", "replace")
    code = out.channel.recv_exit_status()
    return code, o, e


def probe() -> int:
    c = connect()
    print("=== 系统信息 ===")
    for label, cmd in [
        ("内核", "uname -a"),
        ("发行版", "cat /etc/os-release 2>/dev/null | head -4"),
        ("CPU", "nproc"),
        ("内存", "free -h"),
        ("磁盘", "df -h / "),
    ]:
        code, out, err = run(c, cmd)
        print(f"--- {label} ---")
        print(out.strip())
    print("=== Docker ===")
    code, out, err = run(c, "docker --version 2>&1; docker compose version 2>&1")
    print(out.strip() or err.strip())
    print("=== 现有容器 ===")
    code, out, err = run(c, "docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}' 2>&1")
    print(out.strip() or err.strip())
    print("=== 监听端口 ===")
    code, out, err = run(c, "(ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null) | head -30")
    print(out.strip() or err.strip())
    c.close()
    return 0


def deploy() -> int:
    c = connect()
    llm_key = env("SA_LLM_KEY")
    provider = env("SA_LLM_PROVIDER", "deepseek")

    print("==> 上传部署包")
    if not TARBALL.exists():
        print(f"[错误] 未找到 {TARBALL}，请先执行 bash deploy/package.sh")
        return 1
    sftp = c.open_sftp()
    sftp.put(str(TARBALL), "/opt/superagent-deploy.tar.gz")
    sftp.close()

    print("==> 解压到 /opt/superagent")
    code, out, err = run(c, f"mkdir -p {APP_DIR} && tar -xzf /opt/superagent-deploy.tar.gz -C {APP_DIR} && ls {APP_DIR}")
    print(out.strip() or err.strip())

    print("==> 写入 .env")
    api_key = os.environ.get("SA_API_KEY", "")
    lf_sk = os.environ.get("SA_LANGFUSE_SK", "")
    lf_pk = os.environ.get("SA_LANGFUSE_PK", "")
    env_content = f"SUPERAGENT_LLM_PROVIDER={provider}\nDEEPSEEK_API_KEY={llm_key}\n"
    if api_key:
        env_content += f"SUPERAGENT_API_KEY={api_key}\n"
    if lf_pk and lf_sk:
        env_content += f"LANGFUSE_PUBLIC_KEY={lf_pk}\nLANGFUSE_SECRET_KEY={lf_sk}\n"
    code, out, err = run(c, f"cat > {APP_DIR}/.env <<'EOF'\n{env_content}EOF\nchmod 600 {APP_DIR}/.env")
    if code != 0:
        print(err.strip()); return 1

    print("==> 构建镜像")
    code, out, err = run(c, f"cd {APP_DIR} && docker build -t superagent:latest . 2>&1", timeout=900)
    print((out or err)[-2500:])
    if code != 0:
        print("镜像构建失败"); return 1

    print("==> 启动容器（独立端口 8000，限制 1 CPU / 512M 内存，不抢占现有项目）")
    run_cmd = (
        f"docker rm -f superagent 2>/dev/null; "
        f"docker run -d --name superagent --restart unless-stopped "
        f"--memory=512m --cpus=1 "
        f"-p 0.0.0.0:{PORT}:8000 "
        f"--env-file {APP_DIR}/.env "
        f"-v {APP_DIR}/data:/app/data "
        f"-v {APP_DIR}/projects:/app/projects "
        f"superagent:latest"
    )
    code, out, err = run(c, run_cmd)
    print((out or err).strip())
    if code != 0:
        print("容器启动失败"); return 1

    print("==> 健康检查")
    import time
    time.sleep(5)
    code, out, err = run(c, f"curl -fsS http://127.0.0.1:{PORT}/health 2>&1")
    print(out.strip() or err.strip())
    if code == 0:
        print("✅ 部署成功")
        c.close()
        return 0
    print("健康检查失败，容器日志：")
    code, out, err = run(c, "docker logs superagent 2>&1 | tail -30")
    print((out or err).strip())
    c.close()
    return 1


def verify() -> int:
    c = connect()
    print("=== 容器状态 ===")
    code, out, err = run(c, "docker ps --filter name=superagent --format '{{.Names}}  {{.Status}}  {{.Ports}}'")
    print(out.strip() or err.strip())
    print("=== 健康检查状态 ===")
    code, out, err = run(c, "docker inspect --format '{{.State.Health.Status}}' superagent")
    print(out.strip() or err.strip())
    print("=== /health ===")
    code, out, err = run(c, f"curl -fsS http://127.0.0.1:{PORT}/health 2>&1")
    print(out.strip() or err.strip())
    print("=== /ping（真实 LLM 连通）===")
    code, out, err = run(c, f"curl -fsS http://127.0.0.1:{PORT}/ping 2>&1")
    print(out.strip() or err.strip())
    print("=== 全部容器（确认现有项目未受影响）===")
    code, out, err = run(c, "docker ps --format '{{.Names}}  {{.Status}}'")
    print(out.strip() or err.strip())
    c.close()
    return 0


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if mode == "probe":
        raise SystemExit(probe())
    if mode == "deploy":
        raise SystemExit(deploy())
    if mode == "verify":
        raise SystemExit(verify())
    print("用法: python deploy/remote.py probe|deploy|verify")
    raise SystemExit(2)
