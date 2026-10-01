# SuperAgent 部署指南

部署到阿里云 2 核服务器，**独立目录 + 独立端口 + 独立服务**，不影响现有两个项目。

## 最快路径：使用打包文件

已生成 `superagent-deploy.tar.gz`（38 KB，不含密钥/虚拟环境），上传到服务器解压即可：

```bash
# 本机上传
scp superagent-deploy.tar.gz user@服务器:/opt/

# 服务器上
mkdir -p /opt/superagent
tar -xzf /opt/superagent-deploy.tar.gz -C /opt/superagent
cd /opt/superagent
cp .env.example .env && vim .env          # 填入 DEEPSEEK_API_KEY
docker compose up -d --build
curl http://127.0.0.1:8000/health          # 应返回 {"status":"ok",...}
```

---

## 前置

- 服务器：Linux（Ubuntu/CentOS 均可），Python 3.10+ 或 Docker
- 端口：`8000`（可改），建议仅本机回环 + nginx 反代对外开放
- 密钥：`.env`（含 `DEEPSEEK_API_KEY` 等，勿提交 git）

---

## 方案 A：Docker（推荐，隔离最干净）

```bash
# 1. 上传代码到服务器（scp 或 git）
scp -r superagent/ user@服务器:/opt/superagent

# 2. 在服务器上
cd /opt/superagent
cp .env.example .env && vim .env          # 填入密钥
docker compose up -d --build

# 3. 验证
curl http://127.0.0.1:8000/health
```

已通过 `docker-compose.yml` 限制 `mem_limit: 1g / cpus: 1.0`，不抢占现有项目资源。

---

## 方案 B：systemd + venv（无 Docker）

```bash
# 1. 上传代码到 /opt/superagent
# 2. 以 root 执行
sudo bash /opt/superagent/deploy/deploy.sh

# 3. 填入密钥后重启
sudo vim /opt/superagent/.env
sudo systemctl restart superagent
sudo systemctl status superagent
```

服务以非 root 用户 `superagent` 运行，`CPUQuota=100% / MemoryMax=1G` 限制资源。

---

## 方案 C：手动跑（临时验证）

```bash
cd /opt/superagent
export SUPERAGENT_LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=sk-...
python -m superagent serve --host 0.0.0.0 --port 8000
```

---

## nginx 反向代理（可选，对外开放）

```nginx
server {
    listen 80;
    server_name agent.example.com;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_read_timeout 300s;   # /run 可能较久
    }
}
```

---

## API 示例

```bash
# 健康检查
curl http://127.0.0.1:8000/health

# LLM 连通性
curl http://127.0.0.1:8000/ping

# 执行任务（自动放行，用于演示）
curl -X POST http://127.0.0.1:8000/run \
  -H "Content-Type: application/json" \
  -d '{"text":"用Python写一个斐波那契命令行工具","auto_approve":true}'

# 执行任务（需人工审批：先 /pending 看 id，再 /approve 放行）
curl -X POST http://127.0.0.1:8000/run \
  -H "Content-Type: application/json" \
  -d '{"text":"开发一个登录页面"}'
curl http://127.0.0.1:8000/pending
curl -X POST http://127.0.0.1:8000/approve \
  -H "Content-Type: application/json" \
  -d '{"id":"<请求id>","decision":"approve"}'

# 对话
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"你好"}'

# 文件上传解析分析（base64 内容 + 可选 LLM 分析）
curl -X POST http://127.0.0.1:8000/upload \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <API_KEY>" \
  -d '{"filename":"report.txt","content":"<base64>","analyze":true}'
```

---

## 对外访问（公网）

服务默认 `0.0.0.0:8000` + **API Key 鉴权**（`.env` 中 `SUPERAGENT_API_KEY`，除 `/health` 外均需 `X-API-Key` 头）。

公网访问需在**阿里云控制台安全组**放行端口：

1. 阿里云控制台 → ECS → 实例 `47.109.30.40` → 安全组 → 配置规则 → 入方向
2. 添加规则：协议 **TCP**、端口 **8000**、授权对象 `0.0.0.0/0`（或限制为你的 IP 更安全）

放行后：
```bash
curl -H "X-API-Key: <API_KEY>" http://47.109.30.40:8000/health
```

> 安全提醒：该服务是「可执行代码 + 审批门控」的控制面，务必启用 API Key 鉴权，
> 建议经 nginx 反代 + HTTPS 对外开放，而非直接裸暴露。

---

## Langfuse 可观测性（可选）

在 `.env` 配置 `LANGFUSE_PUBLIC_KEY`（`pk-lf-...`）+ `LANGFUSE_SECRET_KEY`（`sk-lf-...`）后重启，
每次任务与 LLM 调用自动上报 trace/generation。缺失任一密钥则自动禁用（不影响主流程）。

---

## 回滚 / 停止

```bash
# Docker
docker compose down          # 停止
docker compose down -v       # 停止并清理

# systemd
sudo systemctl stop superagent
sudo systemctl disable superagent
sudo rm -rf /opt/superagent /etc/systemd/system/superagent.service
```
