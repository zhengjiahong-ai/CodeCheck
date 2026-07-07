# CodeCheck — Coding Agent Harness 设计规约

> **Spec-Driven, Subagent-Built, Human-Owned.**
>
> 本文件与《AI4SE 期末项目 · 通用要求》及《AI4SE 期末项目 · A · Coding Agent Harness》拼装阅读。
> 本文档涵盖通用要求 §4.2 的 SPEC 全部内容 + A.5 的领域与机制设计。

---

## 一、问题陈述

### 1.1 要解决的问题

代码审查（Code Review）是软件工程质量保障的关键环节，但在实际项目中面临三个痛点：

1. **审查滞后**：人工审查依赖 reviewer 的时间窗口，往往在代码提交后数小时甚至数天才完成，反馈周期过长导致修复成本上升。
2. **规则一致性差**：同一团队不同 reviewer 对同一规则的执行标准不一；大量机械性检查（如硬编码密钥、裸 except、SQL 注入风险）占用 reviewer 精力。
3. **修复闭环断裂**：传统审查产出"问题列表"后，修复仍由开发者手动完成，审查 → 修复 → 验证的闭环没有自动化。

### 1.2 目标用户

- 个人开发者 / 小型团队：在 CI 资源有限的情况下，希望每次 commit 都有基础的自动化审查。
- 开源项目维护者：面对大量 PR 时，需要自动化的第一轮筛查，将人力集中在复杂逻辑审查上。

### 1.3 为什么值得做

代码审查是 agentic coding 的天然切入点：它的反馈信号（测试结果、lint 输出、类型检查）是**客观的、可编程的、可回灌的**，符合 harness 对"确定性反馈闭环"的核心要求。同时，它在工程深度上足够有挑战——规则系统、修复-验证循环、记忆与误报学习——而不仅仅是"调用 LLM 写一段 prompt"。

---

## 二、用户故事

遵循 INVEST 原则（Independent, Negotiable, Valuable, Estimable, Small, Testable）。

| 编号 | 用户故事 | 优先级 | 验收标准 |
|------|---------|--------|---------|
| US-1 | 作为开发者，我可以通过 CLI 对指定目录触发代码审查，以便在提交前快速发现问题 | P0 (MVP) | `codecheck review ./src/` 运行后输出问题列表，包含文件路径、行号、严重级别、问题描述、规则 ID |
| US-2 | 作为开发者，我提交代码时自动触发审查（git hook），以便在问题进入仓库前拦截 | P0 (MVP) | `git commit` 时自动运行审查，发现问题则阻止提交并展示报告 |
| US-3 | 作为开发者，审查发现的问题应被自动修复并验证，以便减少手动修复工作量 | P0 (MVP) | 发现问题后自动生成修复 → 应用 → 运行测试 → 测试通过则保留修复，失败则回滚文件并重试 |
| US-4 | 作为开发者，多次修复失败的问题应被标记为"需人工介入"并给出完整尝试历史，以便我了解情况并手动处理 | P1 | 超过 N 轮（默认 3）修复失败后，输出所有尝试过的修复 diff 和对应的测试失败原因 |
| US-5 | 作为开发者，我可以定义项目级审查规则（YAML），以便审查符合团队约定 | P1 | `.codecheck/rules.yaml` 中的自定义规则被加载并参与审查 |
| US-6 | 作为开发者，被我标记为"误报"的 pattern 不应再次出现在后续审查中 | P1 | 标记误报后，相同 pattern 在后续审查中被跳过，并记录在 SQLite 中 |
| US-7 | 作为开发者，审查仅针对我的变更（git diff），而非全量扫描整个仓库 | P1 | 仅审查已变更的代码行及其上下文，输出中标注变更 vs 已有代码 |
| US-8 | 作为运维人员，我可以通过 Docker 一键部署 CodeCheck，并在全新机器上安全配置 API key | P2 | `docker pull` + `docker run` 即可启动，首次运行引导录入 key |

---

## 三、功能规约

### 3.1 模块划分

```
CodeCheck
├── 模块 A：主循环（Agent Loop）
├── 模块 B：工具系统（Tool System）
├── 模块 C：规则引擎（Rule Engine）
├── 模块 D：反馈闭环（Feedback Loop）
├── 模块 E：治理护栏（Governance Guardrails）
├── 模块 F：记忆系统（Memory System）
└── 模块 G：配置与分发（Config & Distribution）
```

### 3.2 模块 A：主循环（Agent Loop）

**职责**：组织上下文 → 调用 LLM → 解析动作 → 分发执行 → 回灌结果 → 停机判断。

**输入**：
- 触发方式（CLI 参数 `review` 或 git hook）
- 目标路径（目录或文件）
- 是否增量（`--diff` 标志）

**行为**：
```
1. 加载配置（.codecheck.yaml）
2. 获取审查目标：
   - 增量模式：执行 git diff，获取变更文件列表及 diff 内容
   - 全量模式：遍历目标目录，收集所有源代码文件
3. 构建初始上下文：
   - 系统提示（角色定义、规则说明、工具列表）
   - 审查目标代码
   - 相关记忆（该文件的审查历史、误报记录）
4. LLM 调用 → 解析响应：
   - 若响应为"工具调用"→ 分发到工具系统执行 → 结果回灌 → 回到步骤 4
   - 若响应为"审查结论"→ 进入反馈闭环（模块 D）
5. 停机条件：
   - 审查完成且无待修复问题
   - 修复超过 N 轮上限
   - 用户主动中断
```

**输出**：审查报告（JSON 格式，包含问题列表、修复记录、最终状态）。

**边界条件**：
- 目标目录为空 → 输出"无文件可审查"
- 无 git 仓库时 `--diff` 模式 → 降级为全量审查并给出警告
- LLM 返回无法解析的响应 → 重试一次，仍失败则报错退出

**错误处理**：
- LLM API 超时 → 重试 2 次，仍失败则终止并输出已完成的审查结果
- 文件读取失败（权限/编码）→ 跳过该文件并在报告中标注

### 3.3 模块 B：工具系统（Tool System）

**职责**：让 agent 作用于外部世界，并提供工具注册、分发、执行、结果回灌的通用框架。

**Agent 可用工具清单**：

| 工具名 | 描述 | 参数 | 风险等级 | 护栏要求 |
|--------|------|------|---------|---------|
| `read_file` | 读取文件内容 | path, start_line?, end_line? | 低 | 无 |
| `search_code` | 搜索代码（grep/正则） | pattern, path?, glob? | 低 | 无 |
| `write_file` | 修改文件（精确替换） | path, old_string, new_string | 中 | 首次修改需确认 |
| `run_test` | 运行测试命令 | command | 中 | 需确认 |
| `run_shell` | 执行 shell 命令 | command, timeout? | 高 | 每次需确认 |
| `git_diff` | 获取 git diff | staged?, target_branch? | 中 | 无（只读） |
| `git_log` | 查看提交历史 | path?, max_count? | 低 | 无 |
| `git_blame` | 查看行归属 | path, start_line, end_line | 低 | 无 |
| `run_lint` | 运行 linter/类型检查 | tool, path? | 中 | 需确认 |

**输入/行为/输出**：
- 每个工具接收标准化参数，返回标准化结果 `{success: bool, data: any, error?: string}`
- 工具执行前经过护栏（模块 E）检查
- 执行结果回灌给主循环 LLM 上下文

**边界条件**：
- 工具调用超时 → 返回超时错误
- 工具参数非法 → 返回参数错误描述

### 3.4 模块 C：规则引擎（Rule Engine）

**职责**：混合模式（确定性 + LLM 辅助）的代码审查规则匹配。

**输入**：源代码文件内容、规则定义文件（`.codecheck/rules.yaml`）。

**行为**：
```
1. 加载规则文件（内置规则 + 项目自定义规则）
2. 确定性规则扫描（正则/AST 匹配）：
   - 遍历所有 source 文件
   - 对每个文件应用所有 type=deterministic 的规则
   - 产出：问题列表（文件、行号、规则 ID、严重级别）
3. LLM 辅助规则扫描：
   - 将 source 代码 + LLM 规则描述提交给 LLM
   - LLM 返回语义层面的问题判断
   - 产出：问题列表（同上格式）
4. 合并去重：
   - 同一位置（文件+行号）由两种规则同时命中 → 合并为一条，标注"双重确认"
   - 不同位置的问题 → 合并列表
5. 与误报库比对：
   - 查询记忆系统（模块 F）中的误报记录
   - 匹配的 pattern 被过滤，不进入最终报告
```

**输出**：合并后的问题列表 `[{file, line, severity, rule_id, message, source}]`。

**规则文件格式**（`.codecheck/rules.yaml`）：

```yaml
rules:
  - id: "no-hardcoded-secret"
    severity: critical
    type: deterministic
    pattern: '(api_key|secret|password|token)\s*=\s*[''"][^''""]+['''"]'
    message: "禁止硬编码密钥/密码/Token"
    category: security

  - id: "no-bare-except"
    severity: warning
    type: deterministic
    pattern: 'except\s*:'
    message: "避免裸 except，请指定具体异常类型"
    category: style

  - id: "sql-injection-risk"
    severity: critical
    type: llm-assisted
    description: "检测 SQL 注入风险，如字符串拼接构造 SQL 语句"
    prompt: "检查以下代码是否存在 SQL 注入风险。关注：字符串拼接构造 SQL、未使用参数化查询、动态表名/列名未经校验。"
    category: security

  - id: "unhandled-error"
    severity: warning
    type: llm-assisted
    description: "检测未处理的异常/错误"
    prompt: "检查以下代码是否存在未处理的错误路径。关注：调用可能失败的函数但未检查返回值、空值未判空直接使用。"
    category: reliability
```

**边界条件**：
- 规则文件为空或不存在 → 仅使用内置规则
- 规则 pattern 为正则语法错误 → 加载时报错并跳过该规则
- LLM 辅助规则在 LLM 不可用时 → 降级为仅确定性规则

**错误处理**：
- YAML 解析失败 → 报错退出，提示用户修复规则文件
- 确定性规则正则匹配超时（ReDoS）→ 跳过该规则对该文件的应用，记录警告

### 3.5 模块 D：反馈闭环（Feedback Loop）—— 重点维度

**职责**：审查发现问题后的自动修复 → 验证 → 回滚/收敛循环。这是 CodeCheck 的**核心深度维度**。

**输入**：问题列表（来自模块 C）、源代码文件、项目测试命令。

**行为**：

```
对每个问题（按严重级别降序）：
  1. 生成修复：
     - 将问题描述 + 问题所在代码 + 上下文提交给 LLM
     - LLM 生成修复方案（old_string → new_string）
  2. 备份文件：
     - 将目标文件复制到 .codecheck/backups/{timestamp}/{filename}
  3. 应用修复：
     - 调用 write_file 工具应用修复
  4. 运行验证：
     - 执行项目测试命令（从 .codecheck.yaml 读取）
     - 执行相关 lint 检查
  5. 判断结果：
     - 测试通过 + lint 通过 → 修复成功，保留修改，记录到修复历史
     - 测试失败 或 lint 失败 → 从备份恢复文件，将失败信息回灌给 LLM
  6. 重试循环：
     - 将失败信息（测试输出、lint 输出）作为额外上下文反馈给 LLM
     - LLM 基于失败信息调整修复策略，重新生成修复
     - 重复步骤 2-5
     - 超过 N 轮（默认 3，可配置）→ 标记为"需人工介入"
  7. 继续下一个问题
```

**输出**：
```json
{
  "total_issues": 5,
  "fixed": 3,
  "needs_manual": 1,
  "false_positive": 1,
  "fixes": [
    {
      "issue_id": "no-hardcoded-secret:src/auth.py:12",
      "status": "fixed",
      "attempts": 1,
      "diff": "...",
      "test_result": "passed"
    },
    {
      "issue_id": "sql-injection-risk:src/db.py:45",
      "status": "needs_manual",
      "attempts": 3,
      "attempts_detail": [
        {"round": 1, "diff": "...", "failure_reason": "test_auth failed: ..."},
        {"round": 2, "diff": "...", "failure_reason": "lint: E501 line too long"},
        {"round": 3, "diff": "...", "failure_reason": "test_db failed: ..."}
      ]
    }
  ]
}
```

**边界条件**：
- 项目无测试命令 → 跳过测试验证，仅运行 lint，并在报告中标注
- 多个问题在同一文件 → 逐个修复，每次修复后运行全量测试（确保不相互影响）
- 文件备份失败（磁盘满）→ 终止修复，不执行任何修改
- 恢复失败 → 输出错误信息，建议用户手动 `git checkout`

**错误处理**：
- LLM 生成的修复无法应用（old_string 不匹配）→ 回灌错误，让 LLM 重新生成
- 测试命令执行超时 → 视为测试失败，进入重试循环

### 3.6 模块 E：治理护栏（Governance Guardrails）

**职责**：识别危险操作，在 LLM 生成的动作执行前拦截，必要时请求人工确认。

**权限矩阵**：

| 操作 | 自动执行 | 需确认 | 禁止 | 说明 |
|------|---------|--------|------|------|
| `read_file` | ✓ | | | 只读操作，无风险 |
| `search_code` | ✓ | | | 只读操作 |
| `git_diff` | ✓ | | | 只读操作 |
| `git_log` | ✓ | | | 只读操作 |
| `git_blame` | ✓ | | | 只读操作 |
| `write_file` | | ✓（首次） | | 首次修改文件需确认，同一会话后续修改可自动 |
| `run_test` | | ✓ | | 每次需确认命令内容 |
| `run_shell` | | ✓ | | 每次需确认命令内容 |
| `run_lint` | | ✓ | | 每次需确认 |
| `git_commit` | | ✓ | | 每次需确认 |
| `git_push` | | | ✗ | 绝对禁止 |
| `install_deps` | | ✓ | | 每次需确认 |
| `delete_file` | | ✓ | | 每次需确认 |

**实现**：
- `guardrail(action) -> {allowed: bool, reason: string, require_confirm: bool}`
- 确定性代码实现，不依赖 LLM 判断
- 可通过 mock 进行确定性单元测试：`guardrail(Action(tool="git_push"))` → `{allowed: false}`

**输入**：工具调用动作（tool name + parameters）。

**行为**：
```
1. 解析动作的工具名
2. 查表：
   - 禁止列表中 → 返回 {allowed: false, reason: "该操作被禁止: ..."}
   - 需确认列表中 → 返回 {allowed: true, require_confirm: true, reason: "需要确认: ..."}
   - 自动列表中 → 返回 {allowed: true, require_confirm: false}
3. 需确认时：
   - 展示操作内容给用户
   - 等待用户 y/n 输入
   - 超时（默认 60s）→ 视为拒绝
```

**边界条件**：
- 未知工具名 → 默认拒绝（白名单原则）
- 用户在确认超时后 → 返回拒绝，agent 需寻找替代方案

### 3.7 模块 F：记忆系统（Memory System）

**职责**：跨会话存储和检索审查历史、误报记录、项目规则约定。

**三层次存储**：

| 层次 | 存储 | 内容 | 检索方式 |
|------|------|------|---------|
| 结构化 | SQLite (`~/.codecheck/memory.db`) | 审查历史（文件、时间、问题、修复状态）、误报记录（pattern hash、标记时间、用户备注） | SQL 查询（按文件路径、时间范围、规则 ID） |
| 配置化 | YAML (`.codecheck/rules.yaml`) | 项目级自定义规则、审查排除路径、N 轮上限 | 文件加载，随项目版本控制 |
| 语义化 | 向量数据库 (ChromaDB, `~/.codecheck/vectors/`) | 误报 pattern 的向量嵌入、修复策略的语义索引 | 语义相似度检索（cosine similarity） |

**输入**：
- 存储：问题对象、用户标记的误报、修复成功/失败记录
- 检索：当前审查的代码片段、文件路径、规则 ID

**行为**：
```
存储（审查完成后）：
  1. 将每个问题写入 SQLite review_history 表
  2. 若用户标记为误报：
     - 计算代码片段的向量嵌入
     - 写入 SQLite false_positives 表
     - 写入 ChromaDB 向量集合
  3. 若修复成功：记录修复策略（diff）到 SQLite fix_history

检索（审查开始时）：
  1. 从 SQLite 查询当前文件的审查历史
  2. 从 SQLite 查询当前规则 ID 的误报记录
  3. 对每个待审查代码片段：
     - 计算向量嵌入
     - 在 ChromaDB 中检索相似片段（threshold: cosine > 0.85）
     - 若命中误报库 → 跳过该问题
```

**输出**：过滤后的问题列表（已排除已知误报）、相关历史上下文（供 LLM 参考）。

**边界条件**：
- 首次运行（无数据库）→ 自动初始化，无历史返回
- ChromaDB 不可用 → 降级为仅 SQLite 精确匹配
- 向量维度不匹配 → 重建向量集合

### 3.8 模块 G：配置与分发（Config & Distribution）

**配置**：`.codecheck.yaml` 位于项目根目录。

```yaml
# CodeCheck 项目配置
version: "1.0"

# LLM 配置
llm:
  provider: deepseek
  model: deepseek-v4-pro
  base_url: https://api.deepseek.com
  # api_key 不从配置文件读取，通过安全存储获取

# 审查配置
review:
  max_fix_rounds: 3
  diff_only: true
  exclude_paths:
    - "node_modules/"
    - "*.min.js"
    - "vendor/"

# 测试配置
test:
  command: "pytest"
  timeout_seconds: 120

# 规则配置
rules:
  path: ".codecheck/rules.yaml"  # 相对于项目根目录

# 记忆配置
memory:
  db_path: "~/.codecheck/memory.db"
  vector_path: "~/.codecheck/vectors/"
```

**触发方式**：
- CLI：`codecheck review [path] [--diff] [--fix] [--max-rounds N]`
- Git hook：`.git/hooks/pre-commit` 中调用 `codecheck review --diff --staged`

---

## 四、非功能性需求

### 4.1 性能

- 确定性规则扫描：1000 行代码 < 1 秒
- LLM 辅助审查：单文件（< 500 行）< 30 秒
- 修复闭环：单问题 < 3 分钟（含 3 轮测试）
- 整个审查流程：10 文件以内 < 10 分钟

### 4.2 安全性（含凭据威胁模型）

**威胁模型**：

| 威胁 | 风险等级 | 对策 |
|------|---------|------|
| API Key 硬编码泄露 | 高 | 绝不硬编码；使用 OS keychain（Linux Secret Service）或加密文件存储；`.env` 仅作为来源之一，不提交 Git |
| LLM 生成恶意代码 | 中 | 护栏阻止危险 shell 命令执行；`write_file` 需确认；`git_push` 绝对禁止 |
| 审查过程引入新漏洞 | 中 | 修复后必须通过测试 + lint 验证；多轮重试失败则标记人工介入 |
| 记忆数据库泄露 | 低 | 记忆仅存储代码片段 hash 和 pattern，不存储完整源代码 |
| 配置文件被篡改 | 低 | 配置文件仅控制行为参数，不包含密钥 |

**凭据安全存储**（§3.1 必做）：

- 方案：加密文件 + 主密码（`~/.codecheck/credentials.enc`）
- 首次运行：
  1. 提示用户输入 API Key（隐藏输入，不回显）
  2. 提示用户设置主密码
  3. 使用主密码加密 API Key 并写入 `~/.codecheck/credentials.enc`
- 后续运行：
  1. 提示输入主密码
  2. 解密读取 API Key 到内存（不写入日志/终端/文件）
- 查看状态：仅显示"已配置 / 未配置"，绝不回显明文
- 更新/清除：`codecheck config --set-key` / `codecheck config --clear-key`

**环境变量风险说明**：`.env` 文件为明文，进程环境变量可见。若用户选择通过 `.env` 提供 key，需在文档中明确风险。

### 4.3 可用性

- 首次运行成功率：在新机器上按照 README 操作，应在 5 分钟内完成首次审查
- 错误信息：所有错误信息应包含原因和建议操作
- CLI 帮助：`codecheck --help` 提供完整命令说明

### 4.4 可观测性

- 日志：`~/.codecheck/logs/` 按日期记录运行日志（不含 API Key）
- 进度：CLI 输出当前审查进度（文件 N/M、修复轮次）
- 报告：审查结束后输出结构化报告（JSON 格式，可重定向到文件）

---

## 五、系统架构

### 5.1 组件图

```
┌─────────────────────────────────────────────────────────┐
│                      用户界面层                           │
│  ┌──────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ CLI 入口  │  │ Git Hook 入口 │  │ 审查报告（终端/JSON）│  │
│  └────┬─────┘  └──────┬───────┘  └────────▲──────────┘  │
└───────┼───────────────┼───────────────────┼─────────────┘
        │               │                   │
┌───────┴───────────────┴───────────────────┴─────────────┐
│                     主循环层 (Agent Loop)                  │
│  ┌─────────────────────────────────────────────────────┐ │
│  │  上下文构建 → LLM 调用 → 响应解析 → 动作分发 → 回灌   │ │
│  └──────────────────────┬──────────────────────────────┘ │
└─────────────────────────┼────────────────────────────────┘
                          │
        ┌─────────────────┼─────────────────┐
        ▼                 ▼                  ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   规则引擎    │  │   工具系统    │  │   反馈闭环    │
│  (Rule Engine)│  │(Tool System) │  │(Feedback Loop)│
│              │  │              │  │              │
│ 确定性规则匹配 │  │ read_file    │  │ 修复生成      │
│ LLM 辅助规则  │  │ write_file   │  │ 备份/应用     │
│ 去重合并      │  │ run_test     │  │ 测试验证      │
│ 误报过滤      │  │ git_diff ... │  │ 回滚/重试     │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                  │
       └────────┬────────┴────────┬─────────┘
                ▼                 ▼
        ┌──────────────┐  ┌──────────────┐
        │   治理护栏    │  │   记忆系统    │
        │ (Guardrails) │  │(Memory System)│
        │              │  │              │
        │ 权限矩阵      │  │ SQLite       │
        │ 危险操作拦截  │  │ YAML 规则    │
        │ HITL 确认    │  │ ChromaDB     │
        └──────────────┘  └──────────────┘
                │                 │
                ▼                 ▼
        ┌──────────────────────────────────┐
        │           基础层                  │
        │  ┌────────┐  ┌──────────────────┐│
        │  │Mock LLM│  │DeepSeek API (真实)││
        │  └────────┘  └──────────────────┘│
        │  ┌────────┐  ┌──────────────────┐│
        │  │ 配置   │  │  凭据安全存储     ││
        │  └────────┘  └──────────────────┘│
        └──────────────────────────────────┘
```

### 5.2 数据流

```
用户触发
  │
  ▼
加载配置 (.codecheck.yaml)
  │
  ▼
获取审查目标 (git diff 或目录遍历)
  │
  ▼
检索记忆 (审查历史 + 误报库)
  │
  ▼
规则引擎：确定性规则匹配 ──→ 问题列表 A
  │                           │
  ▼                           │
规则引擎：LLM 辅助规则 ──→ 问题列表 B
  │                           │
  ▼                           ▼
合并去重 + 误报过滤 ──→ 最终问题列表
  │
  ▼
反馈闭环：对每个问题
  │
  ├── LLM 生成修复
  ├── 护栏检查
  ├── 备份文件
  ├── 应用修复
  ├── 运行测试
  │   ├── 通过 → 保留修复，记录到记忆
  │   └── 失败 → 恢复备份，反馈给 LLM → 重试
  │       └── 超过 N 轮 → 标记"需人工介入"
  │
  ▼
输出审查报告
  │
  ▼
存储审查历史到记忆系统
```

### 5.3 外部依赖

| 依赖 | 用途 | 备注 |
|------|------|------|
| DeepSeek API | LLM 推理（审查分析、修复生成） | 通过 mock 抽象层可替换为其他供应商 |
| ChromaDB | 向量存储与语义检索 | 本地运行，无需外部服务 |
| Git | 版本控制（diff、log、blame） | 系统级依赖 |
| Python 3.10+ | 运行环境 | — |

---

## 六、数据模型

### 6.1 SQLite 表结构

```sql
-- 审查历史
CREATE TABLE review_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    file_path TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    line_number INTEGER,
    issue_description TEXT,
    fix_status TEXT,  -- 'fixed', 'needs_manual', 'false_positive', 'unfixed'
    fix_attempts INTEGER DEFAULT 0,
    fix_diff TEXT,
    commit_hash TEXT
);

-- 误报记录
CREATE TABLE false_positives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    rule_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line_number INTEGER,
    code_snippet_hash TEXT NOT NULL,
    vector_id TEXT,  -- 对应的 ChromaDB 向量 ID
    marked_by TEXT DEFAULT 'user',
    note TEXT
);

-- 修复策略
CREATE TABLE fix_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    rule_id TEXT NOT NULL,
    original_code_hash TEXT,
    fix_diff TEXT,
    success BOOLEAN,
    test_output TEXT,
    attempts_taken INTEGER
);

CREATE INDEX idx_review_history_file ON review_history(file_path);
CREATE INDEX idx_review_history_rule ON review_history(rule_id);
CREATE INDEX idx_false_positives_hash ON false_positives(code_snippet_hash);
CREATE INDEX idx_false_positives_rule ON false_positives(rule_id);
```

### 6.2 ChromaDB 集合

```
collection: false_positive_patterns
  - id: UUID
  - embedding: float[] (维度取决于所用 embedding 模型)
  - metadata: {rule_id, file_path, code_snippet_hash, timestamp}

collection: fix_strategies  
  - id: UUID
  - embedding: float[]
  - metadata: {rule_id, success, attempts_taken}
```

### 6.3 核心实体关系

```
审查任务 (ReviewTask)
  ├── 1:N → 审查问题 (Issue)
  │           ├── rule_id
  │           ├── file_path, line_number
  │           └── severity, description
  │
  ├── 1:N → 修复尝试 (FixAttempt)
  │           ├── issue_id
  │           ├── round_number
  │           ├── diff
  │           └── test_result
  │
  └── 1:1 → 审查报告 (ReviewReport)
              ├── total_issues
              ├── fixed_count
              ├── needs_manual_count
              └── false_positive_count
```

---

## 七、凭据与分发设计

### 7.1 凭据安全存储

- **方案**：AES-256 加密文件 + 主密码（通过 Python `cryptography` 库）
- **存储位置**：`~/.codecheck/credentials.enc`
- **工作流**：
  1. 首次运行 → 引导录入 API Key（`getpass` 隐藏输入）→ 设置主密码 → 加密写入
  2. 后续运行 → 输入主密码 → 解密到内存变量 → 仅用于 API 调用
  3. 查看状态 → `codecheck config --status` → 输出"已配置 / 未配置"
  4. 更新 → `codecheck config --set-key` → 重新录入
  5. 清除 → `codecheck config --clear-key` → 删除加密文件
- **安全约束**：
  - API Key 绝不写入日志、终端输出、配置文件
  - 加密文件权限设为 600（仅 owner 可读写）
  - `.env` 文件明确说明风险（明文存储、进程可见），可选支持但不推荐

### 7.2 分发

- **主方案**：Docker 镜像
  - `docker build -t codecheck .`
  - `docker run -v $(pwd):/workspace -v ~/.codecheck:/root/.codecheck -it codecheck review /workspace`
  - 镜像推送到公开 registry（Docker Hub / GitHub Container Registry）
- **备选方案**：PyPI 包（`pip install codecheck`），后续迭代实现
- **README 说明**：获取方式、运行命令、Key 在目标机器上的安全配置方式、已知限制（需要 Python 3.10+、Git、Docker）

---

## 八、技术选型与理由

| 选项 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.10+ | 生态成熟（cryptography、ChromaDB、click、pytest）；LLM SDK 支持好；开发效率高 |
| LLM 供应商 | DeepSeek | 用户已配置的供应商；API 兼容 OpenAI SDK |
| LLM 抽象层 | 自定义 `LLMProvider` 抽象类 | 满足 mock 注入要求；可替换供应商 |
| 规则引擎 | 自定义（re + YAML） | 确定性规则需自己实现正则匹配和 AST 分析 |
| 向量数据库 | ChromaDB | 轻量、本地运行、Python 原生支持、无需外部服务 |
| 结构化存储 | SQLite | 零配置、单文件、Python 标准库支持 |
| CLI 框架 | Click | Python 最成熟的 CLI 库 |
| 测试框架 | pytest | Python 标准测试框架 |
| 加密 | cryptography | Python 最成熟的加密库 |
| 分发 | Docker | 消除环境差异；用户无需安装 Python 依赖 |
| 前端 | 豁免 | 纯 CLI 项目，无需 Open Design |

---

## 九、验收标准

每个用户故事的客观判定标准，见 §二 用户故事表中的"验收标准"列。

**跨故事验收标准**：

1. **Mock LLM 确定性测试**：移除真实 LLM 后，所有核心机制（护栏、规则引擎、反馈闭环、记忆读写）均能通过单元测试验证。
2. **一键运行测试**：`make test` 或 `pytest` 覆盖核心功能。
3. **CI 通过**：最后一次 CI 执行 `unit-test` job 为 pass 状态。
4. **新机器验证**：在一台全新机器上按照 README 操作，能在 5 分钟内完成首次审查。
5. **无凭据泄露**：仓库中无任何真实 API Key（含 Git 历史、配置、日志、`.env`）。

---

## 十、领域与机制设计（A.5 额外要求）

### 10.1 领域分析：Coding 场景的四类机制

| 机制 | 在 Coding 领域的具体化 |
|------|----------------------|
| **动作/工具** | 读写文件、执行 shell、运行测试、Git 操作、lint 检查 |
| **客观反馈信号** | 测试结果（pass/fail + output）、lint 输出、类型检查结果——客观、确定、可回灌 |
| **危险动作** | 删除文件、强制推送、安装依赖、执行未审查的 shell 命令 |
| **记忆需求** | 审查历史、误报 pattern、项目约定、修复策略有效性 |

### 10.2 重点维度：反馈闭环

选择反馈闭环作为 CodeCheck 的**主要贡献维度**。理由：

1. **天然由代码构成**：反馈闭环的每个环节（备份、应用、测试执行、结果解析、回滚、重试计数）都是确定性代码，完美符合 §A.4 (B) "机制必须是代码"的要求。
2. **可独立测试**：注入 mock LLM（规则驱动：给定输入 X 返回修复 Y），整个闭环可以在无网络、无真实 LLM 的情况下用确定性单元测试验证。
3. **工程深度空间大**：从简单的"修复-测试"循环，到多轮策略调整、失败分类、收敛判断，有充足的深度挖掘空间。
4. **最能回答课程命题**："当 LLM 能完成大部分编码工作时，工程师的价值在哪里"——闭环中的护栏、回滚、重试策略、收敛判断，正是工程师需要编码实现的工程层。

### 10.3 各机制编码实现策略

| 机制 | 实现方式 | Mock 测试策略 |
|------|---------|-------------|
| 主循环 | 自定义 `AgentLoop` 类：`build_context()` → `call_llm()` → `parse_response()` → `dispatch_action()` → `check_stop()` | 注入 mock LLM，验证循环在收到"停止"响应后正确退出 |
| 工具系统 | `ToolRegistry` + 各工具类实现 `execute()` 方法 | 注入 mock 文件系统/mock subprocess，验证工具调用和结果回灌 |
| 规则引擎 | 确定性规则：`re` 模块正则匹配；LLM 辅助规则：提交给 LLM Provider | 确定性规则：构造代码片段，断言匹配/不匹配；LLM 规则：注入 mock LLM 返回预定义结果 |
| 反馈闭环 | `FeedbackLoop` 类：`generate_fix()` → `backup()` → `apply()` → `verify()` → `rollback_or_retry()` | 注入 mock LLM（返回修复方案）+ mock test runner（返回 pass/fail），验证完整的修复-重试-回滚流程 |
| 治理护栏 | `guardrail(action)` 函数，白名单查表 | 直接传入各种 Action，断言返回值 |
| 记忆系统 | `MemoryStore` 抽象类，SQLite + ChromaDB 实现 | 注入 mock store，验证读写和检索逻辑 |
| 配置 | YAML 解析 + `getpass` 隐藏输入 | 标准配置测试，无需 mock |

---

## 十一、风险与未决问题

### 11.1 已识别风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM 生成的修复引入新 bug | 中 | 修复后必须通过测试；多轮失败则标记人工介入；仅修改问题所在区域 |
| 对同一文件的多个修复相互冲突 | 中 | 逐个修复，每次修复后运行全量测试，确保独立性 |
| 测试覆盖率不足导致"通过测试"不代表修复正确 | 高 | 在报告中明确标注"测试通过不代表修复完全正确"；建议用户提升测试覆盖率 |
| ChromaDB 向量维度变更 | 低 | 启动时校验维度，不匹配则重建集合 |
| LLM 上下文窗口溢出（大量文件审查） | 中 | 分批次处理文件；增量模式降低上下文量 |
| 误报标记的语义匹配不准确 | 中 | 设置较高的 cosine 相似度阈值（0.85）；提供"精确匹配"降级选项 |

### 11.2 未决问题

1. **Embedding 模型选择**：用于 ChromaDB 向量化，需选择轻量且效果好的模型（如 `all-MiniLM-L6-v2` 或 DeepSeek embedding API）。后续在 PLAN 阶段确定。
2. **多文件修复的依赖顺序**：如果问题 A 在 `auth.py`，问题 B 在 `db.py`，且 B 依赖 A 的接口，修复顺序可能影响结果。MVP 阶段按严重级别排序，后续迭代可加入依赖分析。
3. **LLM 输出格式稳定性**：DeepSeek 是否能稳定输出结构化（JSON）的审查结果和修复方案？需要 prompt engineering 和 retry 机制保障。

---

## 十二、附录

### A. 术语表

| 术语 | 定义 |
|------|------|
| Harness | 将 LLM 封装为稳定、可靠工作系统的工程层 |
| 确定性规则 | 由正则表达式/AST 模式匹配的代码审查规则，不依赖 LLM |
| LLM 辅助规则 | 需要 LLM 语义理解才能判断的审查规则 |
| 反馈闭环 | 审查 → 修复 → 测试验证 → 失败回滚重试 → 收敛的循环 |
| 误报 | 被规则/LLM 标记为问题，但开发者认为不是问题的发现 |
| HITL | Human-in-the-Loop，人工确认环节 |
| 护栏 | 在危险操作执行前拦截的确定性代码机制 |

### B. 参考

- [Superpowers](https://github.com/obra/superpowers) — 编码智能体技能框架
- [ChromaDB](https://www.trychroma.com/) — 开源向量数据库
- [Click](https://click.palletsprojects.com/) — Python CLI 框架
- [cryptography](https://cryptography.io/) — Python 加密库