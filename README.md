# CodeCheck — AI-Powered Code Review Harness

[![CI](https://github.com/nju-ai4se/codecheck/actions/workflows/ci.yml/badge.svg)](https://github.com/nju-ai4se/codecheck/actions/workflows/ci.yml)

**CodeCheck** is a coding agent harness that implements the core loop of an AI-powered code review system: **review → fix → verify → retry → converge**. It's built as a demonstration of the "Agent = LLM + Harness" principle — the LLM decides what to do, but the harness (governance, feedback, context, tool dispatch) is all deterministic, testable code.

## What It Does

- **Scans** source code with deterministic regex rules (hardcoded secrets, bare except, debug print, eval, SQL injection)
- **Analyzes** code with LLM-assisted semantic rules (logic errors, unhandled errors, SQL injection risks)
- **Auto-fixes** detected issues and verifies each fix by running tests and lint
- **Rolls back** failed fixes and retries with failure context fed back to the LLM
- **Blocks** dangerous operations with a code-based guardrail system
- **Tracks** review history, false positives, and fix patterns across sessions

## Quick Start

### 1. Install

```bash
# From source
git clone https://github.com/nju-ai4se/codecheck.git
cd codecheck
pip install -e ".[dev]"

# Or via Docker
docker pull ghcr.io/nju-ai4se/codecheck:latest
```

### 2. Configure API Key

```bash
# Interactive setup (recommended - encrypted storage)
codecheck config --set-key

# Or via environment variable (less secure)
export CODE_CHECK_API_KEY=sk-your-key-here
```

### 3. Run a Review

```bash
# Review current directory
codecheck review .

# Review with auto-fix
codecheck review . --fix

# Review specific file
codecheck review src/main.py

# Review only staged changes
codecheck review --diff

# Save report to JSON
codecheck review . --output report.json
```

### 4. Install Git Hook

```bash
# Block commits with unfixed issues
codecheck install-hook

# Remove the hook
codecheck uninstall-hook
```

## Docker Usage

```bash
# Build
docker build -t codecheck .

# Run
docker run -v $(pwd):/workspace -v ~/.codecheck:/root/.codecheck codecheck review /workspace

# With docker-compose
docker-compose run --rm codecheck review /workspace
```

## Key Security Configuration

CodeCheck talks to LLM APIs — it needs an API key. Here's how to keep it safe:

| Method | Security | Notes |
|--------|----------|-------|
| `codecheck config --set-key` | **Best** | Encrypted with Fernet (AES-128-CBC + HMAC) + PBKDF2 master password. Key never leaves disk in plaintext. |
| `CODE_CHECK_API_KEY` env var | **OK** | Plaintext in process environment. Use `.env` file (not `export`). Never commit `.env`. |
| Hardcoded in source | **Never** | Will be rejected by deterministic rules. Never do this. |

**Threat model**: An attacker with filesystem access to `~/.codecheck/credentials.enc` cannot decrypt the key without the master password. The master password is never stored. Environment variables are visible to any process running as the same user.

## Project Structure

```
codecheck/
├── src/codecheck/
│   ├── agent/          # Agent main loop + context builder
│   ├── cli/            # CLI commands (review, config, hooks)
│   ├── config/         # .codecheck.yaml loader + schema
│   ├── credentials/    # Encrypted API key storage
│   ├── feedback/       # Fix → test → rollback → retry loop
│   ├── guardrails/     # Deterministic action gate (HITL)
│   ├── hooks/          # Git pre-commit hook integration
│   ├── llm/            # LLM abstraction (DeepSeek + Mock)
│   ├── memory/         # Review history + false positive tracking
│   ├── rules/          # Deterministic + LLM-assisted rule engine
│   └── tools/          # File, shell, git tools
├── tests/              # 268 tests (all runnable without real LLM)
├── .codecheck/         # Built-in rules (rules.yaml)
├── Dockerfile          # Multi-stage Docker build
├── docker-compose.yml  # Simplified local Docker usage
└── .github/workflows/  # CI/CD (tests + lint + Docker build)
```

## Architecture

CodeCheck implements a full coding agent harness with six dimensions:

| Dimension | Implementation | Deterministic? |
|-----------|---------------|----------------|
| **Decision** | Agent main loop: context → LLM → parse → dispatch → loop | Yes (loop logic is code) |
| **Tools** | Read/write files, run shell, git operations, test/lint runners | Yes (all tools are code) |
| **Memory** | SQLite for review history, false positive tracking | Yes (storage is code) |
| **Governance** | Permission matrix + HITL confirmation for dangerous ops | Yes (guardrail is code) |
| **Feedback** | Fix → test → rollback → retry → converge loop | Yes (loop is code) |
| **Configuration** | `.codecheck.yaml` with rules, exclusions, test commands | Yes (parsing is code) |

**The "deep dimension"** is the feedback loop — it's not just a prompt telling the LLM to "fix it", but deterministic code that:
1. Backs up the file before each fix attempt
2. Applies the fix, runs tests and lint
3. If either fails, restores the backup and feeds the failure output back to the LLM
4. Repeats up to `max_fix_rounds` times
5. Marks issues as "needs manual" if all rounds fail

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
make test
# or: pytest --tb=short -v

# Run lint
make lint
# or: ruff check src/ tests/

# Run a specific test
pytest tests/cli/test_review.py -v
```

## Testing Philosophy

- **268 tests** pass without any network or real LLM
- All core mechanisms (guardrails, feedback loop, tool dispatch, memory) are tested with mock LLMs
- 16 hook tests, 17 CLI tests, 10 config tests, plus agent, rules, tools, feedback, guardrails, and memory tests
- CI runs on Python 3.10 and 3.12
- Only 5 tests require `CODE_CHECK_TEST_LIVE=1` (DeepSeek integration)

## Known Limitations

- **Platform**: Linux/macOS primary. Windows support via Docker.
- **LLM Provider**: DeepSeek API by default. OpenAI-compatible providers work via config.
- **File types**: Python, JavaScript, TypeScript, Java, Go, Rust, C/C++.
- **Fix verification**: Requires the project to have a test command configured (defaults to `pytest`).
- **No real sandboxing**: Shell commands run with the user's permissions. The guardrail is a gate, not a container.
- **Memory**: SQLite-based. ChromaDB vector search is planned but not yet implemented.

## Security Boundaries

CodeCheck is designed to run on your development machine. It:

- **Does NOT** send your code to any external service without your API key
- **Does NOT** store your API key in plaintext on disk
- **Does NOT** execute shell commands without guardrail checks
- **Does** allow you to review and confirm dangerous operations (HITL)
- **Does** run your test suite as configured — tests have full access to your system

**Never commit your API key or `.env` file**. The built-in `no-hardcoded-secret` rule will catch obvious leaks, but it's not a substitute for good security hygiene.

## License

MIT — see [LICENSE](LICENSE) file.

---

Built with [Superpowers](https://github.com/obra/superpowers) methodology: spec-driven, subagent-built, human-owned.