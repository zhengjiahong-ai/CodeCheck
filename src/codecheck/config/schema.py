"""Configuration data structures for CodeCheck.

All config fields are defined as dataclasses with defaults,
so the system works without any .codecheck.yaml file present.
"""

from dataclasses import dataclass, field


@dataclass
class LLMConfig:
    """LLM provider configuration."""

    provider: str = "deepseek"
    model: str = "deepseek-v4-pro"
    base_url: str = "https://api.deepseek.com"


@dataclass
class ReviewConfig:
    """Review behavior configuration."""

    max_fix_rounds: int = 3
    diff_only: bool = True
    exclude_paths: list[str] = field(
        default_factory=lambda: ["node_modules/", "*.min.js", "vendor/"]
    )


@dataclass
class TestRunnerConfig:
    """Test execution configuration.

    (Named with 'Test' prefix intentionally — pytest ignores it
    because it has __init__ from @dataclass.)
    """

    command: str = "pytest"
    timeout_seconds: int = 120


@dataclass
class RulesConfig:
    """Rules file configuration."""

    path: str = ".codecheck/rules.yaml"


@dataclass
class MemoryConfig:
    """Memory storage configuration."""

    db_path: str = "~/.codecheck/memory.db"
    vector_path: str = "~/.codecheck/vectors/"


@dataclass
class CodeCheckConfig:
    """Top-level CodeCheck configuration.

    All fields have sensible defaults — the system is fully functional
    without any .codecheck.yaml file present.
    """

    version: str = "1.0"
    llm: LLMConfig = field(default_factory=LLMConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    test: TestRunnerConfig = field(default_factory=TestRunnerConfig)
    rules: RulesConfig = field(default_factory=RulesConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
