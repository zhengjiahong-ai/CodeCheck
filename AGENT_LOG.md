# AGENT_LOG.md — CodeCheck 开发过程日志

> 按时间顺序记录关键节点。每条包含：时间戳与 task 编号、触发的 Superpowers 技能、关键 prompt/context 配置、subagent 输出的关键片段或 commit hash、人工干预（修改了什么、为什么）、学到的教训。

---

## 2026-07-07 · Brainstorming + SPEC + PLAN

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-07 上午 |
| **触发技能** | brainstorming → writing-plans |
| **关键 Prompt** | "我们要开始 AI4SE 期末项目，目标是构建一个 Coding Agent Harness。请启动 brainstorming 技能" |
| **人工干预** | 在 24 个 brainstorming 问题中做出所有设计决策（反馈闭环深度、B 模式修复流程、混合规则、三级记忆、Docker 分发等），AI 仅提供选项，所有决策由人做出 |
| **产出** | `SPEC.md`, `SPEC_PROCESS.md`, `PLAN.md` |
| **教训** | Brainstorming 结构化递进（7 轮 24 问题）比一次性问所有问题更有效；每个问题给出选项比开放提问降低了决策负担 |

---

## 2026-07-07 · SPEC/PLAN 技术细节补充

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-07 下午 |
| **触发** | 另一个 AI 对 SPEC/PLAN 的审阅反馈 |
| **关键决策** | Python 3.12 开发基准、tiktoken + cl100k_base 估算、IR 中间协议、MockProvider 三级匹配（keyword/regex/exact）、5 类异常层次、Click 命令树在 T1 定死、Provider 构造函数接受具体参数而非 Config 对象 |
| **人工干预** | 逐一确认了 12 个技术细节决策，更新了 SPEC.md 和 PLAN.md |
| **产出** | SPEC.md 新增 §3.9 LLM 抽象层；PLAN.md T1/T2 更新 |

---

## 2026-07-07 · T1: 项目脚手架

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-07 |
| **Task 编号** | T1 |
| **触发技能** | 直接实现（未使用 subagent） |
| **关键 Prompt** | "那现在依据文档要求开始实现具体代码" |
| **涉及文件** | `pyproject.toml`, `src/codecheck/__init__.py`, `__main__.py`, `cli/main.py`, `Makefile`, `.codecheck/rules.yaml`, `tests/test_cli_smoke.py` |
| **AI 输出** | 完整的项目脚手架，Click 命令树（review/config/install-hook/uninstall-hook 全部 pass），5 条内置确定性规则 YAML，Makefile |
| **人工干预** | 无 |
| **验证结果** | 5/5 smoke tests passed, `pip install -e .` 成功 |
| **Commit** | `51d9bb2` |

---

## 2026-07-07 · T2: LLM 抽象层

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-07 |
| **Task 编号** | T2 |
| **触发技能** | 直接实现（未使用 subagent） |
| **涉及文件** | `provider.py` (IR 协议), `exceptions.py` (5 子类), `deepseek_provider.py`, `mock_provider.py` (三级匹配), `tests/llm/test_provider.py` (22 用例), `tests/llm/test_deepseek.py` (5 集成用例) |
| **AI 输出** | 完整的 LLM 抽象层，IR 中间协议，MockProvider 支持 keyword/regex/exact + tool_calls + exception + delay + consume，DeepSeekProvider 异常映射 |
| **人工干预** | 修复 `test_keyword_match`：测试内容 `"SELECT * FROM users"` 不包含字面 `"SQL"`，改为 `"This code has SQL injection risk"` |
| **验证结果** | 28 passed, 5 skipped (DeepSeek 集成测试需 `CODE_CHECK_TEST_LIVE=1`) |
| **Commit** | `51d9bb2`（与 T1 合并提交） |
| **教训** | MockProvider 的 keyword 匹配是字面子串匹配（不是语义），测试用例需要确保内容真的包含 keyword 字符串 |

---

## 2026-07-07 · CI/Docker 分发基础

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-07 |
| **Task 编号** | T13, T14（提前完成） |
| **触发** | 用户指令："先完成基础的分发和git ci文件编写" |
| **涉及文件** | `.github/workflows/ci.yml`, `Dockerfile`, `.dockerignore`, `.gitignore` |
| **AI 输出** | 3-job CI（unit-test + lint + docker-build），多阶段 Dockerfile，完善的 .dockerignore |
| **人工干预** | 无 |
| **验证结果** | CI 配置语法正确，Dockerfile 结构合理（待项目完成后验证 docker build） |
| **Commit** | `5fa6ebc`, `80c566b`, `e402b65`

---

## 2026-07-07 · T3: 配置系统

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-07 |
| **Task 编号** | T3 |
| **触发技能** | 直接实现（使用 git worktree 隔离） |
| **涉及文件** | `src/codecheck/config/schema.py` (6 dataclass), `src/codecheck/config/loader.py` (查找/解析/验证/CLI覆盖), `src/codecheck/config/__init__.py`, `tests/config/test_loader.py` (29 用例), `tests/config/fixtures/valid_config.yaml`, `tests/config/fixtures/invalid_types.yaml` |
| **AI 输出** | 完整的配置系统：向上查找 .codecheck.yaml、6 个 dataclass 配置结构、类型验证（string/int/bool/list）、CLI 覆盖合并 |
| **人工干预** | 1) 修复 `test_load_valid_config`：fixture 文件名为 `valid_config.yaml` 而非 `.codecheck.yaml`，`load_config()` 只搜索 `.codecheck.yaml`，改用 tmp_path 复制内容；2) 重命名 `TestConfig` → `TestRunnerConfig` 避免 pytest 采集警告；3) 添加 `filterwarnings` 抑制 dataclass 采集警告 |
| **验证结果** | 57 passed, 5 skipped (29 new T3 tests + 28 existing T1/T2 tests) |
| **Commit** | `aea61ed` |

---

## 2026-07-07 · T4: 凭据安全存储

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-07 |
| **Task 编号** | T4 |
| **触发技能** | 直接实现（使用 git worktree 隔离） |
| **涉及文件** | `src/codecheck/credentials/store.py` (CredentialStore + get_api_key), `src/codecheck/credentials/prompt.py` (交互式录入), `src/codecheck/credentials/__init__.py`, `tests/credentials/test_store.py` (29 用例) |
| **AI 输出** | 完整凭据安全存储：Fernet AES-128-CBC + HMAC 加密, PBKDF2-HMAC-SHA256 密钥派生, 600 文件权限, 交互式引导录入, 环境变量 fallback |
| **人工干预** | 无 — 一次通过，29/29 tests passed |
| **验证结果** | 86 passed, 5 skipped (29 new T4 tests + 28 T1/T2 + 29 T3) |
| **Commit** | `442ed8a` |