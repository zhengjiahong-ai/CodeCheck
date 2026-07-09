# CodeCheck — AI 驱动的代码审查 Harness

[![CI](https://github.com/nju-ai4se/codecheck/actions/workflows/ci.yml/badge.svg)](https://github.com/nju-ai4se/codecheck/actions/workflows/ci.yml)

**CodeCheck** 是一个编码智能体（Coding Agent）Harness，实现了 AI 驱动代码审查系统的核心循环：**审查 → 修复 → 验证 → 回滚 → 重试 → 收敛**。它是对"Agent = LLM + Harness"原则的实践——LLM 决定做什么，但 Harness（治理、反馈、上下文、工具调度）全部是确定性的、可测试的代码。

## 功能概览

- **扫描**源码，使用确定性正则规则检查（硬编码密钥、裸 except、调试 print、eval、SQL 注入等）
- **分析**代码，使用 LLM 辅助的语义规则（逻辑错误、未处理异常、SQL 注入风险等）
- **自动修复**检测到的问题，并通过运行测试和 lint 验证每次修复
- **回滚**失败的修复，将失败上下文反馈给 LLM 后重试
- **拦截**危险操作，使用基于代码的护栏系统
- **追踪**跨会话的审查历史、误报记录和修复模式

## 快速开始

### 1. 安装

```bash
# 从源码安装
git clone https://github.com/nju-ai4se/codecheck.git
cd codecheck
pip install -e ".[dev]"

# 或通过 Docker
docker pull ghcr.io/nju-ai4se/codecheck:latest
```

### 2. 配置 API Key

```bash
# 交互式配置（推荐 — 加密存储）
codecheck config --set-key

# 或通过环境变量（安全性较低）
export CODE_CHECK_API_KEY=sk-your-key-here
```

### 3. 运行审查

```bash
# 审查当前目录
codecheck review .

# 审查并自动修复
codecheck review . --fix

# 审查指定文件
codecheck review src/main.py

# 仅审查变更文件
codecheck review --diff

# 保存 JSON 报告
codecheck review . --output report.json
```

### 4. 安装 Git Hook

```bash
# 阻止提交含有未修复问题的代码
codecheck install-hook

# 移除 Hook
codecheck uninstall-hook
```

## Docker 使用

```bash
# 构建镜像
docker build -t codecheck .

# 运行审查
docker run -v $(pwd):/workspace -v ~/.codecheck:/root/.codecheck codecheck review /workspace

# 使用 docker-compose
docker-compose run --rm codecheck review /workspace
```

## Key 安全配置

CodeCheck 需要调用 LLM API，因此需要 API Key。以下是安全配置方式：

| 方式 | 安全性 | 说明 |
|------|--------|------|
| `codecheck config --set-key` | **最佳** | 使用 Fernet（AES-128-CBC + HMAC）+ PBKDF2 主密码加密。Key 不会以明文形式落盘。 |
| `CODE_CHECK_API_KEY` 环境变量 | **可用** | 进程环境变量中为明文。建议使用 `.env` 文件而非 `export`。绝不要提交 `.env`。 |
| 硬编码在源码中 | **禁止** | 会被确定性规则检测到。永远不要这样做。 |

**威胁模型**：攻击者即使获取了 `~/.codecheck/credentials.enc` 文件的访问权限，没有主密码也无法解密。主密码从不存储。环境变量对同一用户下的所有进程可见。

## 项目结构

```
codecheck/
├── src/codecheck/
│   ├── agent/          # Agent 主循环 + 上下文构建器
│   ├── cli/            # CLI 命令（review、config、hooks）
│   ├── config/         # .codecheck.yaml 加载器 + 模式定义
│   ├── credentials/    # 加密 API Key 存储
│   ├── feedback/       # 修复 → 测试 → 回滚 → 重试 循环
│   ├── guardrails/     # 确定性操作护栏（HITL）
│   ├── hooks/          # Git pre-commit hook 集成
│   ├── llm/            # LLM 抽象层（DeepSeek + Mock）
│   ├── memory/         # 审查历史 + 误报追踪
│   ├── rules/          # 确定性 + LLM 辅助规则引擎
│   └── tools/          # 文件、Shell、Git 工具
├── tests/              # 268 个测试（全部可在无真实 LLM 下运行）
├── .codecheck/         # 内置规则（rules.yaml）
├── Dockerfile          # 多阶段 Docker 构建
├── docker-compose.yml  # 简化本地 Docker 使用
└── .github/workflows/  # CI/CD（测试 + lint + Docker 构建）
```

## 架构设计

CodeCheck 实现了完整的编码智能体 Harness，包含六个维度：

| 维度 | 实现方式 | 是否确定性？ |
|------|----------|-------------|
| **决策** | Agent 主循环：上下文→LLM→解析→调度→循环 | 是（循环逻辑是代码） |
| **工具** | 读写文件、执行 Shell、Git 操作、测试/lint 运行器 | 是（所有工具是代码） |
| **记忆** | SQLite 存储审查历史、误报追踪 | 是（存储是代码） |
| **治理** | 权限矩阵 + 危险操作人工确认（HITL） | 是（护栏是代码） |
| **反馈** | 修复→测试→回滚→重试→收敛 循环 | 是（循环是代码） |
| **配置** | `.codecheck.yaml` 配置规则、排除项、测试命令 | 是（解析是代码） |

**"深度维度"** 是反馈闭环——它不仅仅是提示 LLM "修复它"，而是确定性的代码，能够：
1. 在每次修复尝试前备份文件
2. 应用修复，运行测试和 lint
3. 如果任一失败，恢复备份并将失败输出反馈给 LLM
4. 最多重复 `max_fix_rounds` 次
5. 所有轮次都失败后标记为"需人工处理"

## 开发指南

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
make test
# 或: pytest --tb=short -v

# 运行 lint
make lint
# 或: ruff check src/ tests/

# 运行特定测试
pytest tests/cli/test_review.py -v
```

## 测试理念

- **268 个测试**无需网络或真实 LLM 即可通过
- 所有核心机制（护栏、反馈闭环、工具调度、记忆）均使用 mock LLM 测试
- 16 个 Hook 测试、17 个 CLI 测试、10 个配置测试，以及 Agent、规则、工具、反馈、护栏、记忆等模块测试
- CI 在 Python 3.10 和 3.12 上运行
- 仅 5 个测试需要 `CODE_CHECK_TEST_LIVE=1`（DeepSeek 集成测试）

## 已知限制

- **平台**：Linux/macOS 为主。Windows 可通过 Docker 使用。
- **LLM 提供商**：默认使用 DeepSeek API。OpenAI 兼容的提供商可通过配置使用。
- **文件类型**：Python、JavaScript、TypeScript、Java、Go、Rust、C/C++。
- **修复验证**：需要项目配置测试命令（默认为 `pytest`）。
- **无真正沙箱**：Shell 命令以用户权限运行。护栏是门禁，不是容器。
- **记忆系统**：基于 SQLite。ChromaDB 向量搜索已规划但尚未实现。

## 安全边界

CodeCheck 设计为在开发机器上运行。它：

- **不会**在未配置 API Key 的情况下将代码发送到任何外部服务
- **不会**以明文形式将 API Key 存储在磁盘上
- **不会**在未经护栏检查的情况下执行 Shell 命令
- **会**允许你审查和确认危险操作（HITL）
- **会**按配置运行你的测试套件——测试拥有对你系统的完全访问权限

**绝不要提交你的 API Key 或 `.env` 文件**。内置的 `no-hardcoded-secret` 规则能捕获明显的泄露，但不能替代良好的安全习惯。

## 许可证

MIT — 详见 [LICENSE](LICENSE) 文件。

---

基于 [Superpowers](https://github.com/obra/superpowers) 方法论构建：规范驱动、子代理开发、人类拥有。

注：机制演示在tools文件夹里
