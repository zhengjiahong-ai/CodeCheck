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

---

## 2026-07-07 · T5: 工具系统

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-07 |
| **Task 编号** | T5 |
| **触发技能** | 直接实现（使用 git worktree 隔离） |
| **涉及文件** | `base.py` (Tool + ToolResult), `registry.py` (ToolRegistry), `file_tools.py` (ReadFile + WriteFile), `shell_tools.py` (RunShell + RunTest + RunLint), `git_tools.py` (GitDiff + GitLog + GitBlame), 4 个测试文件 |
| **AI 输出** | 8 个工具类 + 注册中心 + OpenAI function calling schema 生成 |
| **人工干预** | 修复 `test_run_failing_command`：error message 是 "exited with code" 而非 "exit code" |
| **验证结果** | 127 passed, 5 skipped (41 new T5 tests + 86 existing) |
| **Commit** | `33957ba` |

---

## 2026-07-07 · T6: 规则引擎

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-07 |
| **Task 编号** | T6 |
| **触发技能** | 直接实现（使用 git worktree 隔离） |
| **涉及文件** | `models.py` (Rule/Issue/Severity), `loader.py` (YAML加载+验证), `deterministic.py` (正则匹配), `llm_assisted.py` (LLM语义匹配+JSON提取), `engine.py` (RuleEngine 5阶段流水线), 3 个测试文件 |
| **AI 输出** | 完整混合规则引擎：确定性逐行正则匹配、LLM辅助语义分析（3种JSON提取fallback）、去重合并（dual_confirmed标记）、误报过滤、严重度排序 |
| **人工干预** | 1) 修复 `test_llm_finds_issues`：LLM matcher 对每个 rule 独立调用 LLM，2 个 rule 产生 2 个 issue 而非 1 个；2) 修复 6 个 B904/B007 ruff lint 问题 (from e/from None, _location) |
| **验证结果** | 163 passed, 5 skipped (36 new T6 tests) |
| **Commit** | `3d3a89d` |

---

## 2026-07-07 · T7: 治理护栏

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-07 |
| **Task 编号** | T7 |
| **触发技能** | 直接实现（使用 git worktree 隔离） |
| **涉及文件** | `src/codecheck/guardrails/guard.py` (PermissionLevel/Action/GuardResult/DEFAULT_PERMISSIONS/guardrail), `tests/guardrails/test_guard.py` (18 用例) |
| **AI 输出** | 确定性权限矩阵：13 个工具分三级 (AUTO/CONFIRM/FORBIDDEN)，白名单原则，guardrail() 纯函数 |
| **人工干预** | 无 — 一次通过，18/18 tests passed |
| **验证结果** | 183 passed, 5 skipped (18 new T7 tests) |
| **Commit** | `69fe8e4` |

---

## 2026-07-07 · T8: 记忆系统

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-07 |
| **Task 编号** | T8 |
| **触发技能** | 直接实现（使用 git worktree 隔离） |
| **涉及文件** | `store.py` (MemoryStore + ReviewRecord + FalsePositiveRecord), `sqlite_store.py` (SQLite 3表+4索引+WAL), `tests/memory/test_sqlite_store.py` (11 用例) |
| **AI 输出** | SQLite 记忆系统：review_history/false_positives/fix_history 三表，文件过滤/限制条数/误报查重/上下文管理器 |
| **人工干预** | 修复 `test_empty_db_path_creates_default`：`Path.expanduser()` 不经过 `os.path.expanduser`，改用 `monkeypatch.setenv("HOME", ...)` |
| **验证结果** | 194 passed, 5 skipped (11 new T8 tests) |
| **Commit** | `53bd72c` |

---

## 2026-07-07 · T9: Agent 主循环

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-07 |
| **Task 编号** | T9 |
| **触发技能** | 直接实现（使用 git worktree 隔离） |
| **涉及文件** | `context.py` (ContextBuilder + 系统提示模板), `parser.py` (parse_review_report + 3种JSON提取), `loop.py` (AgentLoop + ReviewReport), `tests/agent/test_loop.py` (9 用例), `tests/agent/test_parser.py` (10 用例) |
| **AI 输出** | 完整 Agent 主循环：上下文构建(工具+规则+输出格式) → LLM调用 → 护栏检查 → 工具执行 → 结果回灌 → 停机判断 |
| **人工干预** | 无 — 一次通过，19/19 tests passed |
| **验证结果** | 213 passed, 5 skipped (19 new T9 tests) |
| **Commit** | `8de4a85` |

---

## 2026-07-07 · T10: 反馈闭环

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-07 |
| **Task 编号** | T10 |
| **触发技能** | 直接实现（使用 git worktree 隔离） |
| **涉及文件** | `backup.py` (backup/restore + metadata), `verifier.py` (run_tests/run_lint), `reporter.py` (FixReport/FixAttempt/SingleFixResult), `loop.py` (FeedbackLoop + FIX_PROMPT + _parse_fix_response), 3 个测试文件 |
| **AI 输出** | 完整反馈闭环：修复生成→备份→应用→测试验证→回滚→重试→收敛，LLM只用于修复生成，其余均为确定性代码 |
| **人工干预** | 1) 修复 `workspace_root` 未使用变量；2) 修复 `test_multiple_issues_processed`：多个 issue 需要不同的 MockRule (不同 old_string)，第一个 consume 第二个 not |
| **验证结果** | 235 passed, 5 skipped (22 new T10 tests) |
| **Commit** | `b554bad` |

---

## 2026-07-09 · T11: CLI 入口

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-09 |
| **Task 编号** | T11 |
| **触发技能** | 直接实现（使用 git worktree 隔离） |
| **涉及文件** | `src/codecheck/cli/review.py` (review 命令实现), `src/codecheck/cli/config_cmd.py` (config 命令实现), `src/codecheck/cli/main.py` (连线), `src/codecheck/tools/registry.py` (register_defaults), `tests/cli/test_review.py` (7 用例), `tests/cli/test_config.py` (10 用例), `.codecheck/rules.yaml` (修复 YAML 转义) |
| **AI 输出** | 完整 CLI 实现：review 命令（文件扫描→规则引擎→Agent 主循环→反馈闭环→JSON 输出），config 命令（status/set-key/clear-key），终端彩色输出，退出码规范 |
| **人工干预** | 1) 修复 YAML 转义问题：`rules.yaml` 中 `\s` 在 YAML 双引号字符串中为非法转义序列，改用 `|-` 块标量写法；2) 修复 config_cmd.py 架构：原为 Click 命令装饰器，但被 main.py 作为普通函数调用导致 TypeError，改为纯函数；3) 修复 test_cli_smoke.py 中 `test_review_empty_dir` 测试：review 命令现在实际扫描文件，传入 `.` 会扫描项目自身源码发现 issues 导致 exit code 1，改为使用临时空目录 |
| **验证结果** | 268 passed, 5 skipped (17 new CLI tests) |
| **Commit** | `d2378b0` |
| **教训** | 1) YAML 双引号字符串中 `\s` 等正则转义需写为 `\\s` 或改用单引号/块标量；2) Click 命令装饰器与普通函数不能混用——如果函数需要被其他 Click 命令调用，应去掉装饰器，由调用方传递参数 |

---

## 2026-07-09 · T12: Git Hook 集成

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-09 |
| **Task 编号** | T12 |
| **触发技能** | 直接实现（使用 git worktree 隔离） |
| **涉及文件** | `src/codecheck/hooks/pre_commit.py` (hook 安装/卸载/版本检测), `src/codecheck/hooks/__init__.py`, `src/codecheck/cli/main.py` (连线), `tests/hooks/test_pre_commit.py` (16 用例) |
| **AI 输出** | 完整 Git Hook 集成：可执行 hook 脚本生成（含版本标记）、install/uninstall、--force 覆盖、安全检查（只移除自家 hook）、退出码区分 |
| **人工干预** | 1) 修复 `get_hook_path`：当 `repo_root` 参数传入时，函数直接构造 `.git/hooks/pre-commit` 路径但未检查 `.git` 是否存在，导致 `test_get_hook_path_not_in_repo` 测试失败（未抛出 FileNotFoundError）。修复：添加 `git_dir.exists()` 显式检查；2) 修复 worktree 嵌套问题：T12 worktree 最初在 T11 worktree 内部创建，导致路径混乱，删除后从 main 分支重新创建 |
| **验证结果** | 268 passed, 5 skipped (16 new hook tests) |
| **Commit** | `037c321` |
| **教训** | 1) `git worktree add` 要注意当前所在目录——在 worktree 内执行会在嵌套路径创建；2) Hook 脚本必须标记自身身份（如 `# CodeCheck pre-commit hook`），否则卸载时无法区分自家 hook 和用户自定义 hook |

---

## 2026-07-09 · T13, T14, T15: Docker 分发, CI/CD, README

| 字段 | 内容 |
|------|------|
| **时间** | 2026-07-09 |
| **Task 编号** | T13, T14, T15 |
| **触发技能** | 直接实现（合并 T11/T12 到 main 后直接修改） |
| **涉及文件** | `Dockerfile` (多阶段构建), `.dockerignore` (更新), `docker-compose.yml` (新增), `.github/workflows/ci.yml` (多 Python 版本矩阵), `README.md` (完整重写) |
| **AI 输出** | T13: 多阶段 Docker 构建（builder→runtime），非 root 用户运行，docker-compose 简化本地使用；T14: CI 增加 Python 3.10/3.12 矩阵测试、测试报告 artifacts 上传、Docker 内运行 review 冒烟测试；T15: 完整 README（简介/安装/运行/安全配置/架构/安全边界/已知限制/CI 徽章） |
| **人工干预** | 无 — 一次通过 |
| **验证结果** | 268 passed, 5 skipped, 所有 CLI 命令正常 |
| **Commit** | `ad8f815` (T13-T15), `020961d` (PLAN.md 更新) |
| **教训** | T13-T15 无代码依赖，合入 main 后直接修改效率更高，无需 worktree 隔离 |