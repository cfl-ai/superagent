# SuperAgent

生产 / 企业级**自主 AI Agent 框架**，严格依据以下两份设计文档实现：

- 《超级全能自主Agent_设计文档_修订版.md》
- 《超级全能自主Agent_评审报告.md》

**零第三方依赖**（核心仅用 Python 标准库，Python ≥ 3.10），开箱即用。

---

## 一、这是什么

SuperAgent 把一个「自主智能体」拆成 **7 层能力 + 4 大横向基座 + 1 条主事件流**，并把安全（S0–S3 操作分级）、审计、回滚、资料溯源、HITL 审批作为**一等公民**内置，而非事后补充。

```
┌──────────────────────────────────────────────┐
│ L7 人工决策交付层  终审 · 归档 · 打包          │
│ L6 幻觉自检层      独立评分 · 来源核验         │
│ L5 全能生产层      编码/设计/视频/Agent 自研    │
│ L4 权限风控层      S0-S3 分级 · 审计（贯穿）    │
│ L3 语言解析规划层  多语言 · 枚举 · 任务拆解     │
│ L2 网络探索层      抓取 · 资料溯源             │
│ L1 系统运维层      进程/内存 · 受限清理         │
└──────────────────────────────────────────────┘
   贯穿基座：①安全审计 ②回滚快照 ③可观测性 ④资料溯源
```

---

## 二、快速开始

```bash
# 无需 pip install（核心零依赖）
python -m superagent --help
python -m superagent sysinfo --processes 5          # 系统信息 + 进程 Top5

# 简短输入 → 枚举可能性，等待确认（不擅自生产）
python -m superagent run "hi"

# 完整任务 → 交互式终审（在终端放行/修改/驳回）
python -m superagent run "请帮我开发一个响应式登录页面，包含用户名密码表单和验证码"

# 演示/受信任环境：自动放行（仍会写入审计）
python -m superagent run "..." --auto-approve
```

运行测试：

```bash
python -m unittest discover -s tests -v   # 19 个用例
```

---

## 三、命令行

| 命令 | 说明 |
|------|------|
| `run <文本> [--project-dir X] [--auto-approve]` | 执行任务；简短输入枚举可能性 |
| `audit [--limit N] [--action X] [--level S0..S3]` | 查询审计日志 |
| `pending` | 列出待审批请求 |
| `approve <id> approve\|revise\|reject [--feedback ...]` | 后台模式审批 |
| `sysinfo [--processes N]` | 系统信息 / 内存 / 进程 |
| `chat <消息>` | 与 LLM 直接对话（验证真实接入） |
| `ping` | 检测 LLM 提供商连通性与密钥有效性 |
| `serve [--host H] [--port P] [--auto-approve]` | 启动生产 HTTP 服务 |

### HTTP 服务

`python -m superagent serve` 启动生产服务（`/health /ping /run /chat /pending /approve /audit`），
详见 [`deploy/README.md`](deploy/README.md)。

---

## 四、目录结构

```
superagent/
├── superagent/
│   ├── core/          # 编排器、状态机、配置、事件、工具注册、运行时
│   ├── security/      # 权限分级 S0-S3、角色认证、审计(SQLite)、快照回滚
│   ├── sourcing/      # 资料溯源（schema 落盘 参考资料清单.md）
│   ├── hitl/          # HITL 审批队列（超时/优先级/决策/持久化）
│   ├── observability/ # 结构化日志、指标、告警、心跳
│   ├── llm/           # 可插拔 LLM 后端（openai/mock/null，纯 urllib）
│   ├── quality/       # 独立评分 rubric（7 分制，各领域维度）
│   ├── layers/        # L1/L2/L3/L5/L6/L7 能力层
│   └── cli.py         # 命令行入口
├── config/default.json# 分级前缀、HITL、溯源、质量阈值等配置
├── tests/             # 19 个单元/集成测试
└── pyproject.toml
```

---

## 五、安全模型（S0–S3）

| 级别 | 定义 | 处置 | 示例 |
|------|------|------|------|
| S0 禁止 | 不可逆高危 | 硬阻断 + 上报 | 删系统核心文件、改注册表、篡改驱动、去第三方水印 |
| S1 审批 | 高风险/主观 | 强制人工审批（**登录授信不豁免**） | 系统安装、删除文件、Agent 部署、对外交付 |
| S2 白名单 | 低风险常规 | 自动 + 审计 | venv 内 pip/npm、字体、临时缓存清理 |
| S3 自动审计 | 无风险只读 | 自动 + 审计 | 预览、检索、读文件 |

分级通过 `config/default.json` 的前缀匹配 + 内置表实现（见 `security/permissions.py`）。

**审计**：所有 S1/S2/S3 操作写入 SQLite，字段与修订版 6.4 节一致（event_id/ts/subject/action/object/level/approval_chain/result/rollback）。

**回滚**：S1 操作前对目标做文件级快照，失败按清单回滚（`security/snapshot.py`）。

---

## 六、HITL 审批

- 强制节点：软件安装、Agent 部署、交付终审（`delivery.submit`）等。
- 决策：放行 / 修改意见 / 驳回重做。
- 支持**交互式**（`run` 默认内联询问）与**后台模式**（`pending` + `approve`，持久化到 `data/approvals.jsonl`）。
- 超时：等待超时抛 `ApprovalTimeout`，任务挂起保留现场，不私自放行。

---

## 七、资料溯源

所有外部引用记录固定字段：来源类型 / 标题 / URL·路径 / 时间 / 内容哈希(SHA-256) / 许可 / 引用位置 / 状态，统一写入 `01_需求文档/参考资料清单.md`，失效来源自动标记（`sourcing/registry.py`）。

---

## 八、可插拔 LLM（已接入真实模型）

内置 OpenAI 兼容提供商预设，`config/default.json` 或 `.env` 的 `SUPERAGENT_LLM_PROVIDER` 一键切换：

| provider | base_url | 默认模型 | 密钥环境变量 |
|----------|----------|---------|-------------|
| `deepseek` | api.deepseek.com/v1 | deepseek-chat | `DEEPSEEK_API_KEY` |
| `zhipu` | open.bigmodel.cn/api/paas/v4 | glm-4-flash | `ZHIPU_API_KEY` |
| `bailian` | dashscope.aliyuncs.com/compatible-mode/v1 | qwen-plus | `BAILIAN_API_KEY` |
| `openai` | api.openai.com/v1 | gpt-4o-mini | `SUPERAGENT_LLM_API_KEY` / `OPENAI_API_KEY` |
| `auto` | — | — | 有密钥走 OpenAI，否则回退 mock |
| `mock` / `null` | — | — | 离线回显 / 静默（测试用） |

```bash
# 方式一：.env（已 gitignore）
SUPERAGENT_LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-...

# 方式二：环境变量（幂等，可临时覆盖）
$env:SUPERAGENT_LLM_PROVIDER = "zhipu"
$env:ZHIPU_API_KEY = "..."

# 验证
python -m superagent ping
python -m superagent chat "你好"
```

规划层（L3）与生产层（L5）已接入 LLM 驱动，调用失败自动回退确定性逻辑，保证离线可用。
---

## 九、质量管控（独立评分）

生产层产出交给**独立 Scorer**（`quality/rubric.py`）评分，与生产流程解耦，避免自评闭环。各领域（代码/设计/视频/Agent/文档）有独立 rubric 维度与权重；< 7 分自动改良迭代，超阈值暂停上报。

---

## 十、设计文档映射

| 修订版章节 | 实现位置 |
|-----------|---------|
| §4 统一架构 / 主事件流 | `core/orchestrator.py` |
| §5 能力清单(十二) | `layers/*.py` |
| §6 权限分级 + 审计 + 回滚 | `security/*.py` |
| §7 HITL | `hitl/approval.py` |
| §8 资料溯源 | `sourcing/registry.py` |
| §9 质量 rubric | `quality/rubric.py` |
| §11 状态机 | `core/state.py` |
| §12 可观测性 | `observability/telemetry.py` |
| §10 合规红线 | `permissions.py` S0 阻断项 + 文档 |

---

## 十一、合规红线（已内置）

- 去水印仅限自有素材；**禁止去除第三方水印**（S0 硬阻断 `watermark.remove.third_party`）。
- 「消除 AI 痕迹」= 消除廉价 AI 感，不隐瞒 AI 参与。
- Agent 部署、对外交付强制人工审批。
