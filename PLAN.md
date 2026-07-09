# PLAN.md — CodeCheck 实现计划

> 由 writing-plans 产出。每个 task 粒度足以由一个 subagent 在一次会话内完成。
> 任务状态：⬜ 待开始 | 🔄 进行中 | ✅ 已完成 | ❌ 阻塞

---

## 依赖关系总览

```
Phase 1: Foundation（可并行）
├── T1: 项目脚手架 ─────────────────────────┐
├── T2: LLM 抽象层 ─────────────────────────┤
├── T3: 配置系统 ───────────────────────────┤
└── T4: 凭据安全存储 ───────────────────────┤
                                             │
Phase 2: Core Mechanisms（依赖 T1，可并行）   │
├── T5: 工具系统 ◄──────────────────────────┤
├── T6: 规则引擎 ◄──────────────────────────┤
├── T7: 治理护栏 ◄──────────────────────────┤
└── T8: 记忆系统 ◄──────────────────────────┘
                    │
Phase 3: Integration（依赖 T2-T8）
├── T9: Agent 主循环
├── T10: 反馈闭环（重点深度）
├── T11: CLI 入口
└── T12: Git Hook 集成

Phase 4: Distribution & CI（依赖 T9-T12）
├── T13: Docker 分发
├── T14: CI/CD（GitHub Actions）
└── T15: README & 文档
```

---

## Phase 1: Foundation（基础层）

### T1: 项目脚手架与依赖管理

**目标**：初始化项目结构，配置开发依赖，建立可运行的空壳，定义 Click 命令树（函数体 pass）。

**涉及文件**：
- `pyproject.toml` — 项目元数据与依赖声明（`requires-python = ">=3.10"`，开发基准 3.12）
- `src/codecheck/__init__.py` — 包入口
- `src/codecheck/__main__.py` — `python -m codecheck` 入口
- `src/codecheck/cli/main.py` — Click 命令树（review / config / install-hook / uninstall-hook，函数体 pass）
- `tests/__init__.py` — 测试包
- `tests/test_cli_smoke.py` — 冒烟测试（`--help` 输出）
- `Makefile` — `make test` / `make lint` 等快捷命令
- `.codecheck/rules.yaml` — 内置 5 条确定性规则（仅 YAML，不含 Python 处理逻辑）

**预期实现要点**：
- 使用 `hatchling` 构建
- 依赖：`click`, `openai`（DeepSeek 兼容）, `chromadb`, `pyyaml`, `cryptography`, `tiktoken`, `pytest`, `pytest-mock`, `ruff`
- `make test` 运行 `pytest`，`make lint` 运行 `ruff check`
- Click 命令树在 T1 就定死，后续 task 只填充函数体：
  ```python
  @click.group()
  def main(): ...
  @main.command()
  @click.argument("path", default=".")
  @click.option("--diff", is_flag=True)
  @click.option("--fix", is_flag=True)
  @click.option("--max-rounds", type=int)
  @click.option("--output", type=click.Path())
  def review(path, diff, fix, max_rounds, output): pass  # T11 实现
  @main.command()
  @click.option("--status", is_flag=True)
  @click.option("--set-key", is_flag=True)
  @click.option("--clear-key", is_flag=True)
  def config(status, set_key, clear_key): pass  # T4 + T11 实现
  @main.command()
  def install_hook(): pass  # T12 实现
  @main.command()
  def uninstall_hook(): pass  # T12 实现
  ```
- 内置 5 条确定性规则（仅 YAML 定义，T6 才写匹配逻辑）：
  | # | 规则 ID | 类别 | 正则 pattern |
  |---|---------|------|-------------|
  | 1 | `no-hardcoded-secret` | security | `(api_key\|secret\|password\|token)\s*=\s*['"][^'"]+['"]` |
  | 2 | `no-bare-except` | style | `except\s*:` |
  | 3 | `no-debug-print` | style | `\bprint\s*\(` |
  | 4 | `sql-string-concat` | security | `('f'\|['"])\s*(SELECT\|INSERT\|UPDATE\|DELETE)\s` |
  | 5 | `dangerous-eval` | security | `\b(eval\|exec)\s*\(` |

**验证步骤**：
1. `pip install -e .` 成功
2. `python -m codecheck --help` 显示帮助信息，包含 review / config / install-hook / uninstall-hook 子命令
3. `make test` 运行通过（冒烟测试：CLI 可导入，`--help` 输出非空）
4. `make lint` 无错误
5. `.codecheck/rules.yaml` 存在且 YAML 格式合法

**依赖**：无
**可并行**：与 T2, T3, T4 并行

---

### T2: LLM 抽象层

**目标**：实现可注入 mock 的 LLM Provider 抽象，支持 DeepSeek 真实调用和 Mock 规则驱动调用。定义中间协议 IR 和异常层次。

**涉及文件**：
- `src/codecheck/llm/__init__.py`
- `src/codecheck/llm/provider.py` — `LLMProvider` 抽象基类 + `LLMResponse`/`ToolCall` 中间协议数据类
- `src/codecheck/llm/exceptions.py` — 异常层次（5 个子类）
- `src/codecheck/llm/deepseek_provider.py` — DeepSeek 真实实现
- `src/codecheck/llm/mock_provider.py` — Mock 规则驱动实现（`MockRule` + `MockProvider`）
- `tests/llm/test_provider.py` — MockProvider 单元测试
- `tests/llm/test_deepseek.py` — DeepSeekProvider 集成测试（仅 `CODE_CHECK_TEST_LIVE=1` 时运行）

**预期实现要点**：

1. **中间协议 IR**（不依赖任何供应商格式）：
   ```python
   @dataclass
   class ToolCall:
       id: str
       name: str
       arguments: dict  # JSON 解析后的 dict，参数类型校验由 T5 负责

   @dataclass
   class LLMResponse:
       content: str | None
       tool_calls: list[ToolCall] = field(default_factory=list)
       finish_reason: str = "stop"  # "stop" | "tool_calls" | "length"
       usage: dict | None = None
   ```

2. **Provider 抽象**：
   - `LLMProvider` 抽象类定义 `chat(messages, tools?) -> LLMResponse` 接口
   - `count_tokens(text: str) -> int` 默认使用 `tiktoken` + `cl100k_base` 估算
   - `DeepSeekProvider.__init__` 接受具体参数（`api_key`, `base_url`, `model`），不依赖 T3 的 `CodeCheckConfig`
   - API Key 获取优先级：构造函数参数 → 环境变量 `CODE_CHECK_API_KEY`

3. **MockProvider 三级匹配**：
   ```python
   @dataclass
   class MockRule:
       keyword: str | None = None    # 输入包含关键词
       regex: str | None = None      # 输入匹配正则
       exact: str | None = None      # 输入完全等于
       response_content: str | None = None
       tool_calls: list[ToolCall] | None = None  # 模拟工具调用
       finish_reason: str = "stop"
       consume: bool = True          # 匹配后消耗
       delay: int = 0                # 模拟延迟（ms）
       raise_error: LLMProviderError | None = None  # 模拟异常
   ```
   按注册顺序匹配，支持默认 fallback（`keyword=None`, `consume=False`）。

4. **异常层次**（5 个子类）：
   - `LLMProviderError`（基础）
   - `LLMAuthenticationError`（认证失败）
   - `LLMRateLimitError`（429）
   - `LLMInvalidRequestError`（参数错误）
   - `LLMTimeoutError`（超时）
   - `LLMContextOverflowError`（上下文溢出）
   - `DeepSeekProvider` 负责将 OpenAI SDK 异常映射为这些内部异常

**验证步骤**：
1. MockProvider keyword 匹配：注册 `MockRule(keyword="SQL", response_content="注入风险")` → 传入含 SQL 的代码 → 断言返回预期响应
2. MockProvider 工具调用：注册 `MockRule(exact="read_file:src/auth.py", tool_calls=[ToolCall(...)], finish_reason="tool_calls")` → 断言返回 tool_calls
3. MockProvider 正则匹配：注册 `MockRule(regex=r"修复.*sql", response_content="修复方案")` → 传入匹配文本 → 断言返回修复方案
4. MockProvider 异常模拟：注册 `MockRule(keyword="timeout", raise_error=LLMTimeoutError())` → 断言抛出异常
5. MockProvider 无规则匹配 → 返回默认 fallback 响应
6. MockProvider 消费规则（`consume=True`）→ 第二次相同输入不再匹配该规则
7. Token 计数：传入超长消息 → 验证 `count_tokens()` 返回合理值 > 0
8. LLMResponse 序列化 → 验证 IR 不依赖任何供应商格式
9. DeepSeekProvider 集成测试：`CODE_CHECK_TEST_LIVE=1` 时验证真实 API 调用正常

**依赖**：T1
**可并行**：与 T3, T4 并行

---

### T3: 配置系统

**目标**：实现 `.codecheck.yaml` 配置文件的加载、验证、默认值合并。

**涉及文件**：
- `src/codecheck/config/__init__.py`
- `src/codecheck/config/loader.py` — 配置加载器
- `src/codecheck/config/schema.py` — 配置结构定义（dataclass）
- `tests/config/test_loader.py` — 配置加载测试
- `tests/config/fixtures/valid_config.yaml` — 测试用有效配置
- `tests/config/fixtures/invalid_config.yaml` — 测试用无效配置

**预期实现要点**：
- 使用 `dataclass` 定义配置结构：`CodeCheckConfig`
- 从项目根目录向上查找 `.codecheck.yaml`（类似 `.gitignore` 的查找逻辑）
- 提供默认值（max_fix_rounds=3, diff_only=True, exclude_paths=["node_modules/", "*.min.js", "vendor/"]）
- 配置验证：必填字段检查、类型检查、路径合法性检查
- 支持 CLI 参数覆盖配置文件（`--max-rounds 5` 覆盖 `max_fix_rounds: 3`）

**验证步骤**：
1. 加载有效配置文件 → 返回正确填充的 `CodeCheckConfig` 对象
2. 配置文件不存在 → 返回全默认值配置
3. 无效配置文件 → 抛出明确错误信息（含行号和字段名）
4. CLI 参数覆盖：`--max-rounds 5` 覆盖配置文件中的 `max_fix_rounds: 3`

**依赖**：T1
**可并行**：与 T2, T4 并行

---

### T4: 凭据安全存储

**目标**：实现 API Key 的加密存储、读取、更新、清除，遵循 §3.1 安全要求。

**涉及文件**：
- `src/codecheck/credentials/__init__.py`
- `src/codecheck/credentials/store.py` — 加密存储核心逻辑
- `src/codecheck/credentials/prompt.py` — 引导用户录入 Key 的交互
- `tests/credentials/test_store.py` — 加密存储单元测试

**预期实现要点**：
- 使用 `cryptography` 库的 Fernet（AES-128-CBC + HMAC）加密
- 主密码通过 PBKDF2 派生为 Fernet key
- 存储位置：`~/.codecheck/credentials.enc`，文件权限 600
- 首次运行：`getpass` 隐藏输入 API Key → 设置主密码 → 加密写入
- 后续运行：输入主密码 → 解密到内存变量（不写入文件/日志/终端）
- `status` 命令：仅显示"已配置 / 未配置"
- `set-key` / `clear-key` 命令
- 支持环境变量 `CODE_CHECK_API_KEY` 作为 fallback（文档中标注风险）

**验证步骤**：
1. 写入 Key → 验证文件存在且内容非明文
2. 读取 Key → 验证解密后与原始 Key 一致
3. 错误主密码 → 验证解密失败，返回明确错误
4. 清除 Key → 验证文件被删除
5. 文件权限 → 验证为 600（或 Windows 等效）

**依赖**：T1
**可并行**：与 T2, T3 并行

---

## Phase 2: Core Mechanisms（核心机制层）

### T5: 工具系统

**目标**：实现工具注册、分发、执行、结果回灌的通用框架，以及所有 Agent 可用工具。

**涉及文件**：
- `src/codecheck/tools/__init__.py`
- `src/codecheck/tools/registry.py` — `ToolRegistry` 工具注册中心
- `src/codecheck/tools/base.py` — `Tool` 抽象基类 + `ToolResult` 数据类
- `src/codecheck/tools/file_tools.py` — `ReadFileTool`, `WriteFileTool`
- `src/codecheck/tools/shell_tools.py` — `RunTestTool`, `RunShellTool`, `RunLintTool`
- `src/codecheck/tools/git_tools.py` — `GitDiffTool`, `GitLogTool`, `GitBlameTool`
- `tests/tools/test_file_tools.py` — 文件工具测试（使用 tmp_path）
- `tests/tools/test_registry.py` — 注册中心测试

**预期实现要点**：
- `Tool` 抽象类：`name: str`, `description: str`, `parameters: dict`（JSON Schema）, `execute(**kwargs) -> ToolResult`
- `ToolRegistry`：注册、查找、列出所有工具、生成 OpenAI function calling 格式的工具描述
- `ReadFileTool`：支持行范围读取，处理编码错误（fallback 到 latin-1）
- `WriteFileTool`：精确字符串替换（old_string → new_string），替换失败返回错误
- `RunTestTool` / `RunShellTool`：`subprocess.run` 封装，支持 timeout，输出截断（防止上下文溢出）
- `GitDiffTool`：封装 `git diff --unified=5`，返回结构化 diff
- 所有工具执行后返回 `ToolResult(success, data, error)`

**验证步骤**：
1. 注册工具 → 列出工具 → 验证工具名和描述正确
2. `ReadFileTool` 读取测试文件 → 验证返回内容正确
3. `WriteFileTool` 替换字符串 → 验证文件内容改变 → 替换失败 → 验证文件未变
4. `RunShellTool` 执行 `echo hello` → 验证返回 `hello`
5. `RunShellTool` 超时 → 验证返回超时错误
6. `GitDiffTool` 在测试 repo 中运行 → 验证返回 diff 内容
7. `ToolRegistry` 生成 function calling schema → 验证格式符合 OpenAI 标准

**依赖**：T1
**可并行**：与 T6, T7, T8 并行

---

### T6: 规则引擎

**目标**：实现混合模式规则引擎（确定性正则匹配 + LLM 辅助语义审查）。

**涉及文件**：
- `src/codecheck/rules/__init__.py`
- `src/codecheck/rules/models.py` — `Rule`, `Issue`, `Severity` 数据类
- `src/codecheck/rules/loader.py` — YAML 规则文件加载器
- `src/codecheck/rules/deterministic.py` — 确定性规则匹配器
- `src/codecheck/rules/llm_assisted.py` — LLM 辅助规则匹配器
- `src/codecheck/rules/engine.py` — `RuleEngine` 主类（合并去重 + 误报过滤）
- `tests/rules/test_deterministic.py` — 确定性规则测试
- `tests/rules/test_llm_assisted.py` — LLM 辅助规则测试（使用 mock LLM）
- `tests/rules/test_engine.py` — 引擎集成测试
- `tests/rules/fixtures/sample_code.py` — 测试用代码样本

**预期实现要点**：
- `Rule` 数据类：`id, severity, type, pattern, description, prompt, category`
- `DeterministicMatcher`：对每个文件逐行应用正则规则，记录行号和匹配内容
- ReDoS 防护：正则编译时设置超时，单规则匹配超时则跳过
- `LLMAssistedMatcher`：将代码分段提交给 LLM Provider，附带规则 prompt，解析 LLM 返回的问题列表
- LLM 输出格式要求：JSON 数组 `[{file, line, severity, rule_id, message}]`
- `RuleEngine`：合并两种匹配器结果 → 按文件+行号去重（LLM+确定性同时命中 → 合并，标注"双重确认"）→ 与误报库比对过滤
- 内置规则集（至少 5 条确定性 + 3 条 LLM 辅助）

**验证步骤**：
1. 确定性规则：构造含 `api_key = "sk-xxx"` 的代码 → 断言被 `no-hardcoded-secret` 规则命中
2. 确定性规则：构造含 `except:` 的代码 → 断言被 `no-bare-except` 规则命中
3. 确定性规则：正常代码 → 断言无命中
4. LLM 辅助规则：使用 mock LLM（返回 `[{...}]`）→ 断言正确解析
5. 合并去重：同一行被两种规则命中 → 断言合并为一条
6. 误报过滤：加载误报库 → 已知误报被过滤
7. 规则文件 YAML 语法错误 → 断言加载时报错

**依赖**：T1, T2（LLM 抽象层）
**可并行**：与 T5, T7, T8 并行

---

### T7: 治理护栏

**目标**：实现确定性代码护栏，在危险操作执行前拦截，支持 HITL 确认。

**涉及文件**：
- `src/codecheck/guardrails/__init__.py`
- `src/codecheck/guardrails/guard.py` — `guardrail(action) -> GuardResult` 核心函数
- `src/codecheck/guardrails/permissions.py` — 权限矩阵配置
- `src/codecheck/guardrails/confirm.py` — 用户交互确认（`input` / `click.confirm`）
- `tests/guardrails/test_guard.py` — 护栏单元测试
- `tests/guardrails/test_permissions.py` — 权限矩阵测试

**预期实现要点**：
- `Action` 数据类：`tool_name: str`, `parameters: dict`
- `GuardResult` 数据类：`allowed: bool`, `require_confirm: bool`, `reason: str`
- 权限矩阵定义为字典：`{tool_name: PermissionLevel}`，`PermissionLevel = AUTO | CONFIRM | FORBIDDEN`
- 白名单原则：未知工具名 → 默认拒绝
- HITL 确认：`click.confirm(f"Allow: {action}?")` ，超时 60s 默认拒绝
- 同一会话内，同一类型操作首次确认后后续可自动（如 `write_file`）

**验证步骤**：
1. `guardrail(Action("read_file", ...))` → `{allowed: true, require_confirm: false}`
2. `guardrail(Action("write_file", ...))` → `{allowed: true, require_confirm: true}`
3. `guardrail(Action("git_push", ...))` → `{allowed: false, reason: "禁止操作"}`
4. `guardrail(Action("unknown_tool", ...))` → `{allowed: false}`（白名单原则）
5. 所有测试**不需要真实 LLM**，直接调用 `guardrail()` 函数

**依赖**：T1
**可并行**：与 T5, T6, T8 并行

---

### T8: 记忆系统

**目标**：实现三层次记忆存储（SQLite + YAML 规则 + ChromaDB 向量），支持审查历史、误报记录、语义检索。

**涉及文件**：
- `src/codecheck/memory/__init__.py`
- `src/codecheck/memory/store.py` — `MemoryStore` 抽象基类
- `src/codecheck/memory/sqlite_store.py` — SQLite 实现（审查历史、误报、修复策略）
- `src/codecheck/memory/vector_store.py` — ChromaDB 实现（语义检索）
- `src/codecheck/memory/embedding.py` — 代码片段向量化（使用 sentence-transformers 或 DeepSeek embedding API）
- `tests/memory/test_sqlite_store.py` — SQLite 存储测试
- `tests/memory/test_vector_store.py` — 向量存储测试（使用 mock embedding）

**预期实现要点**：
- `MemoryStore` 抽象类：`save_review(issue)`, `get_history(file_path)`, `mark_false_positive(issue)`, `is_false_positive(code_snippet)`
- `SQLiteStore`：实现 §SPEC 六 的数据模型（review_history, false_positives, fix_history 表）
- `VectorStore`：封装 ChromaDB，存储代码片段向量嵌入
- 语义检索：计算查询片段的 embedding → ChromaDB 余弦相似度检索 → 返回 top-k 结果
- 降级策略：ChromaDB 不可用 → 仅 SQLite 精确匹配（hash 比对）
- 首次运行自动初始化数据库和向量集合

**验证步骤**：
1. SQLite：保存审查记录 → 按文件路径检索 → 断言返回正确记录
2. SQLite：标记误报 → 相同 hash 的代码片段再次查询 → 断言被识别为误报
3. ChromaDB：存储向量 → 语义检索相似片段 → 断言返回相似结果
4. 降级：ChromaDB 不可用（mock 异常）→ 断言降级到 SQLite 精确匹配
5. 首次运行 → 断言自动创建数据库文件和集合

**依赖**：T1
**可并行**：与 T5, T6, T7 并行

---

## Phase 3: Integration（集成层）

### T9: Agent 主循环

**目标**：实现 Agent 主循环——组织上下文 → 调用 LLM → 解析动作 → 分发执行 → 回灌结果 → 停机判断。

**涉及文件**：
- `src/codecheck/agent/__init__.py`
- `src/codecheck/agent/loop.py` — `AgentLoop` 主类
- `src/codecheck/agent/context.py` — 上下文构建器
- `src/codecheck/agent/parser.py` — LLM 响应解析器
- `tests/agent/test_loop.py` — 主循环单元测试（使用 mock LLM）
- `tests/agent/test_parser.py` — 解析器测试

**预期实现要点**：
- `AgentLoop.run(target_path, config) -> ReviewReport`：
  ```
  while not should_stop():
      context = build_context(messages, tools, memory)
      response = llm_provider.chat(context)
      if response.has_tool_calls():
          for call in response.tool_calls:
              guard_result = guardrail(call)
              if not guard_result.allowed: continue
              if guard_result.require_confirm:
                  if not confirm(call): continue
              result = tool_registry.execute(call)
              messages.append({"role": "tool", "content": result})
      else:
          # 审查结论，进入反馈闭环
          break
  ```
- 停机条件：LLM 输出审查结论（无工具调用）、达到最大轮次、用户中断
- 上下文构建：系统提示 + 审查目标代码 + 相关记忆 + 工具列表
- 最大上下文窗口管理：token 计数，超出时裁剪最旧的非系统消息

**验证步骤**：
1. Mock LLM 返回"工具调用(read_file)" → 验证工具被执行 → 结果回灌 → LLM 再次被调用
2. Mock LLM 返回"审查结论(JSON)" → 验证循环退出，返回报告
3. Mock LLM 返回"工具调用(git_push)" → 验证护栏拦截 → 循环继续
4. 达到最大轮次 → 验证循环强制退出
5. 上下文窗口超限 → 验证早期消息被裁剪
6. 所有测试**使用 mock LLM**，不需要真实 API

**依赖**：T2（LLM 抽象层）, T5（工具系统）, T7（护栏）, T8（记忆系统）
**可并行**：与 T10 有依赖关系（T10 依赖 T9 的主循环）

---

### T10: 反馈闭环（重点深度维度）

**目标**：实现审查 → 修复 → 测试验证 → 失败回滚重试 → 收敛的完整反馈闭环。这是 CodeCheck 的核心深度机制。

**涉及文件**：
- `src/codecheck/feedback/__init__.py`
- `src/codecheck/feedback/loop.py` — `FeedbackLoop` 主类
- `src/codecheck/feedback/backup.py` — 文件备份与恢复
- `src/codecheck/feedback/verifier.py` — 测试/lint 验证器
- `src/codecheck/feedback/reporter.py` — 修复报告生成器
- `tests/feedback/test_loop.py` — 反馈闭环单元测试（使用 mock LLM + mock test runner）
- `tests/feedback/test_backup.py` — 备份恢复测试
- `tests/feedback/test_verifier.py` — 验证器测试

**预期实现要点**：
- `FeedbackLoop.process(issues, config) -> FixReport`：
  ```
  for issue in issues:
      for round in 1..max_rounds:
          fix = llm.generate_fix(issue, context, previous_failures)
          backup_path = backup_file(issue.file_path)
          success = apply_fix(fix)
          if not success: continue  # apply 失败，重试
          test_result = run_tests()
          lint_result = run_lint()
          if test_result.passed and lint_result.passed:
              mark_fixed(issue, fix, round)
              break
          else:
              restore_file(backup_path)
              previous_failures.append({
                  "round": round,
                  "diff": fix.diff,
                  "test_output": test_result.output,
                  "lint_output": lint_result.output
              })
      else:
          mark_needs_manual(issue, previous_failures)
  ```
- 文件备份：`backup_file(path)` → 复制到 `.codecheck/backups/{timestamp}/{filename}`
- 文件恢复：`restore_file(backup_path)` → 覆盖原文件
- 验证器：`run_tests()` 执行 `config.test.command`，`run_lint()` 执行 `ruff check`
- 失败分类：区分"测试失败"、"lint 失败"、"修复应用失败"三种情况，反馈给 LLM 时带上不同类型
- 收敛策略：每轮将上一轮的失败信息完整回灌给 LLM，让 LLM 调整策略
- 修复报告：`FixReport` 包含 `total_issues, fixed, needs_manual, false_positive, fixes_detail`

**验证步骤**：
1. 注入 mock LLM（第 1 轮返回有效修复，第 2 轮返回替代修复）+ mock test runner（第 1 轮返回失败，第 2 轮返回成功）→ 断言经历 2 轮后修复成功
2. 注入 mock LLM（3 轮均返回有效修复）+ mock test runner（3 轮均返回失败）→ 断言标记为"需人工介入"，输出 3 轮尝试历史
3. 备份文件 → 修改文件 → 恢复备份 → 断言文件内容与原始一致
4. 修复应用失败（old_string 不匹配）→ 断言重试（LLM 被要求重新生成）
5. 多问题在同一文件 → 断言逐个修复，每次修复后运行全量测试
6. 所有测试**使用 mock LLM + mock subprocess**，不需要真实 API 和真实命令执行

**依赖**：T9（Agent 主循环）, T6（规则引擎产出的问题列表）
**可并行**：无（依赖 T9 完成）

---

### T11: CLI 入口

**目标**：实现 `codecheck` 命令行工具，支持 `review` 子命令。

**涉及文件**：
- `src/codecheck/cli/__init__.py`
- `src/codecheck/cli/main.py` — CLI 主入口（Click 应用）
- `src/codecheck/cli/review.py` — `review` 命令实现
- `src/codecheck/cli/config_cmd.py` — `config` 子命令（凭据管理）
- `tests/cli/test_review.py` — CLI 集成测试（使用 mock LLM）
- `tests/cli/test_config.py` — 配置命令测试

**预期实现要点**：
- 使用 Click 框架
- `codecheck review [PATH] [--diff] [--fix] [--max-rounds N] [--output FILE]`
- `codecheck config --status | --set-key | --clear-key`
- `codecheck --version`
- 输出格式：终端彩色输出（问题按严重级别着色）+ JSON 报告文件
- 进度显示：当前文件 N/M、修复轮次
- 退出码：0 = 无问题或全部修复，1 = 发现问题，2 = 有需人工介入的问题，3 = 运行错误

**验证步骤**：
1. `codecheck --help` → 显示帮助信息
2. `codecheck review ./tests/fixtures/sample_project/` → 输出审查报告（使用 mock LLM）
3. `codecheck review --diff` → 仅审查变更文件
4. `codecheck review --fix --max-rounds 2` → 修复重试上限为 2
5. `codecheck review --output report.json` → 生成 JSON 报告文件
6. `codecheck config --status` → 显示凭据状态
7. 退出码测试：无问题 → 0，有问题 → 1

**依赖**：T9, T10, T4
**可并行**：与 T12 并行

---

### T12: Git Hook 集成

**目标**：实现 pre-commit hook，在 `git commit` 时自动触发审查。

**涉及文件**：
- `src/codecheck/hooks/__init__.py`
- `src/codecheck/hooks/pre_commit.py` — pre-commit hook 逻辑
- `src/codecheck/hooks/install.py` — `codecheck install-hook` 命令
- `tests/hooks/test_pre_commit.py` — Hook 测试

**预期实现要点**：
- `codecheck install-hook`：将 hook 脚本写入 `.git/hooks/pre-commit`
- Hook 脚本内容：调用 `codecheck review --diff --staged --fix`
- 发现问题且无法自动修复 → 阻止提交，展示报告
- 无问题或全部自动修复 → 允许提交
- `codecheck uninstall-hook`：移除 hook 脚本
- Hook 脚本记录自身版本，便于后续更新

**验证步骤**：
1. `codecheck install-hook` → 验证 `.git/hooks/pre-commit` 存在且可执行
2. 在测试 repo 中 `git commit` → 验证 hook 被触发
3. 代码有问题 → 验证 commit 被阻止
4. 代码无问题 → 验证 commit 成功
5. `codecheck uninstall-hook` → 验证 hook 被移除

**依赖**：T11
**可并行**：与 T11 并行

---

## Phase 4: Distribution & CI（分发与持续集成）

### T13: Docker 分发

**目标**：构建 Docker 镜像，确保一键部署运行。

**涉及文件**：
- `Dockerfile` — 多阶段构建
- `.dockerignore` — 排除不必要的文件
- `docker-compose.yml` — 可选，简化本地使用

**预期实现要点**：
- 多阶段构建：builder 阶段安装依赖，runtime 阶段仅包含运行时
- 基础镜像：`python:3.12-slim`
- 容器内安装 Git（系统级依赖）
- Entrypoint: `codecheck`
- 卷挂载：`/workspace`（项目代码）、`/root/.codecheck`（配置和凭据）
- 镜像推送到 GitHub Container Registry（CI 中自动构建）

**验证步骤**：
1. `docker build -t codecheck .` → 构建成功
2. `docker run codecheck --help` → 显示帮助
3. `docker run -v $(pwd):/workspace -v ~/.codecheck:/root/.codecheck codecheck review /workspace` → 运行审查
4. 镜像大小 < 500MB

**依赖**：T11, T12
**可并行**：与 T14, T15 并行

---

### T14: CI/CD（GitHub Actions）

**目标**：配置 GitHub Actions，每次 push 自动运行测试和构建镜像。

**涉及文件**：
- `.github/workflows/ci.yml` — CI 配置

**预期实现要点**：
- **unit-test job**（必做）：
  - 触发条件：push / PR
  - 步骤：checkout → 安装 Python → 安装依赖 → 运行 `pytest`（使用 mock LLM，不需要真实 API Key）
  - 生成测试报告
- **lint job**：
  - 运行 `ruff check`
- **docker-build job**（仅 main 分支）：
  - 构建 Docker 镜像
  - 推送到 GitHub Container Registry
- CI 配置中**不含任何真实凭据**

**验证步骤**：
1. 推送代码 → GitHub Actions 自动运行
2. unit-test job 通过
3. lint job 通过
4. docker-build job 成功构建并推送镜像
5. 最后一次 CI 执行记录为 pass 状态

**依赖**：T13
**可并行**：与 T13, T15 并行

---

### T15: README 与文档

**目标**：编写完整的 README.md，包含项目简介、安装、运行、分发、安全边界。

**涉及文件**：
- `README.md` — 主文档

**预期内容**：
1. 项目简介（CodeCheck 是什么、解决什么问题）
2. 安装方式（Docker、源码安装）
3. 运行命令（CLI 示例、git hook 安装）
4. Key 安全配置方式（首次运行引导、加密存储说明、`.env` 风险说明）
5. 目录结构说明
6. 安全边界说明（不提交真实凭据、护栏限制、已知限制）
7. 已知限制（平台/架构/依赖前提）
8. CI/CD 状态徽章

**验证步骤**：
1. 按 README 步骤在全新机器上操作 → 5 分钟内完成首次审查
2. 所有命令示例可复制粘贴执行

**依赖**：T13, T14
**可并行**：与 T13, T14 并行

---

## Task 执行顺序建议

```
Week 1:
  Day 1-2:  [并行] T1 + T2 + T3 + T4   (Foundation)
  Day 3-4:  [并行] T5 + T6 + T7 + T8   (Core Mechanisms)
  Day 5-7:  T9 → T10                    (Integration: 主循环 + 反馈闭环)

Week 2:
  Day 1-2:  [并行] T11 + T12            (Integration: CLI + Hook)
  Day 3-4:  [并行] T13 + T14 + T15      (Distribution & CI)
  Day 5-7:  冷启动验证 + 修复 + 完善
```

---

## Task 状态追踪

| Task | 状态 | 开始时间 | 完成时间 | Commit Hash |
|------|------|---------|---------|-------------|
| T1: 项目脚手架 | ✅ | 2026-07-07 | 2026-07-07 | `51d9bb2` |
| T2: LLM 抽象层 | ✅ | 2026-07-07 | 2026-07-07 | `51d9bb2` |
| T3: 配置系统 | ✅ | 2026-07-07 | 2026-07-07 | `aea61ed` |
| T4: 凭据安全存储 | ✅ | 2026-07-07 | 2026-07-07 | `442ed8a` |
| T5: 工具系统 | ✅ | 2026-07-07 | 2026-07-07 | `33957ba` |
| T6: 规则引擎 | ✅ | 2026-07-07 | 2026-07-07 | `3d3a89d` |
| T7: 治理护栏 | ✅ | 2026-07-07 | 2026-07-07 | `69fe8e4` |
| T8: 记忆系统 | ✅ | 2026-07-07 | 2026-07-07 | `53bd72c` |
| T9: Agent 主循环 | ✅ | 2026-07-07 | 2026-07-07 | `8de4a85` |
| T10: 反馈闭环 | ✅ | 2026-07-07 | 2026-07-07 | `b554bad` |
| T11: CLI 入口 | ⬜ | - | - | - |
| T12: Git Hook 集成 | ⬜ | - | - | - |
| T13: Docker 分发 | ⬜ | - | - | - |
| T14: CI/CD | ⬜ | - | - | - |
| T15: README 与文档 | ⬜ | - | - | - |