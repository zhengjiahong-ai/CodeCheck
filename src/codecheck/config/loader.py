"""Configuration loader — find, parse, validate, and merge .codecheck.yaml.

Key behaviors:
- Walk up from the target path to find .codecheck.yaml (like .gitignore)
- Return sensible defaults when no config file exists
- Validate types and required fields, with clear error messages
- Support CLI argument overrides (e.g. --max-rounds overrides max_fix_rounds)
"""

from pathlib import Path
from typing import Any

import yaml

from codecheck.config.schema import (
    CodeCheckConfig,
    LLMConfig,
    MemoryConfig,
    ReviewConfig,
    RulesConfig,
    TestRunnerConfig,
)


class ConfigError(Exception):
    """Raised when .codecheck.yaml is invalid."""

    def __init__(self, message: str, file_path: str | None = None):
        self.file_path = file_path
        super().__init__(message)


def get_default_config() -> CodeCheckConfig:
    """Return a CodeCheckConfig with all defaults."""
    return CodeCheckConfig()


def find_config_file(start_path: str | Path = ".") -> str | None:
    """Walk up from start_path to find a .codecheck.yaml file.

    Stops at filesystem root. Returns the absolute path, or None.
    """
    current = Path(start_path).resolve()
    if current.is_file():
        current = current.parent

    while True:
        candidate = current / ".codecheck.yaml"
        if candidate.is_file():
            return str(candidate)
        parent = current.parent
        if parent == current:  # Reached filesystem root
            return None
        current = parent


def _validate_string(data: dict, key: str, path: str) -> None:
    """Validate that data[key] is a string if present."""
    if key in data and not isinstance(data[key], str):
        raise ConfigError(
            f"{path}.{key}: expected string, got {type(data[key]).__name__}"
        )


def _validate_int(data: dict, key: str, path: str, min_value: int = 1) -> None:
    """Validate that data[key] is a positive int if present."""
    if key in data:
        if not isinstance(data[key], int) or isinstance(data[key], bool):
            raise ConfigError(
                f"{path}.{key}: expected integer, got {type(data[key]).__name__}"
            )
        if data[key] < min_value:
            raise ConfigError(
                f"{path}.{key}: must be >= {min_value}, got {data[key]}"
            )


def _validate_bool(data: dict, key: str, path: str) -> None:
    """Validate that data[key] is a bool if present."""
    if key in data and not isinstance(data[key], bool):
        raise ConfigError(
            f"{path}.{key}: expected boolean, got {type(data[key]).__name__}"
        )


def _validate_list_of_strings(data: dict, key: str, path: str) -> None:
    """Validate that data[key] is a list of strings if present."""
    if key not in data:
        return
    if not isinstance(data[key], list):
        raise ConfigError(
            f"{path}.{key}: expected list, got {type(data[key]).__name__}"
        )
    for i, item in enumerate(data[key]):
        if not isinstance(item, str):
            raise ConfigError(
                f"{path}.{key}[{i}]: expected string, got {type(item).__name__}"
            )


def _parse_llm_config(raw: dict | None) -> LLMConfig:
    """Parse and validate LLM configuration section."""
    if raw is None:
        return LLMConfig()
    _validate_string(raw, "provider", "llm")
    _validate_string(raw, "model", "llm")
    _validate_string(raw, "base_url", "llm")
    return LLMConfig(
        provider=raw.get("provider", "deepseek"),
        model=raw.get("model", "deepseek-v4-pro"),
        base_url=raw.get("base_url", "https://api.deepseek.com"),
    )


def _parse_review_config(raw: dict | None) -> ReviewConfig:
    """Parse and validate review configuration section."""
    if raw is None:
        return ReviewConfig()
    _validate_int(raw, "max_fix_rounds", "review", min_value=1)
    _validate_bool(raw, "diff_only", "review")
    _validate_list_of_strings(raw, "exclude_paths", "review")
    return ReviewConfig(
        max_fix_rounds=raw.get("max_fix_rounds", 3),
        diff_only=raw.get("diff_only", True),
        exclude_paths=raw.get("exclude_paths", ["node_modules/", "*.min.js", "vendor/"]),
    )


def _parse_test_config(raw: dict | None) -> TestRunnerConfig:
    """Parse and validate test configuration section."""
    if raw is None:
        return TestRunnerConfig()
    _validate_string(raw, "command", "test")
    _validate_int(raw, "timeout_seconds", "test", min_value=1)
    return TestRunnerConfig(
        command=raw.get("command", "pytest"),
        timeout_seconds=raw.get("timeout_seconds", 120),
    )


def _parse_rules_config(raw: dict | None) -> RulesConfig:
    """Parse and validate rules configuration section."""
    if raw is None:
        return RulesConfig()
    _validate_string(raw, "path", "rules")
    return RulesConfig(path=raw.get("path", ".codecheck/rules.yaml"))


def _parse_memory_config(raw: dict | None) -> MemoryConfig:
    """Parse and validate memory configuration section."""
    if raw is None:
        return MemoryConfig()
    _validate_string(raw, "db_path", "memory")
    _validate_string(raw, "vector_path", "memory")
    return MemoryConfig(
        db_path=raw.get("db_path", "~/.codecheck/memory.db"),
        vector_path=raw.get("vector_path", "~/.codecheck/vectors/"),
    )


def parse_config(raw: dict) -> CodeCheckConfig:
    """Parse a raw YAML dict into a validated CodeCheckConfig.

    Args:
        raw: The parsed YAML dictionary.

    Returns:
        A fully populated CodeCheckConfig with defaults filled in.

    Raises:
        ConfigError: If any field fails validation.
    """
    if not isinstance(raw, dict):
        raise ConfigError("Configuration must be a YAML dictionary/mapping")

    # Validate version
    if "version" in raw:
        _validate_string(raw, "version", "<root>")

    # Parse each section independently — each handles None gracefully
    return CodeCheckConfig(
        version=raw.get("version", "1.0"),
        llm=_parse_llm_config(raw.get("llm")),
        review=_parse_review_config(raw.get("review")),
        test=_parse_test_config(raw.get("test")),
        rules=_parse_rules_config(raw.get("rules")),
        memory=_parse_memory_config(raw.get("memory")),
    )


def load_config(
    start_path: str | Path = ".",
    cli_overrides: dict[str, Any] | None = None,
) -> CodeCheckConfig:
    """Load CodeCheck configuration from a .codecheck.yaml file.

    Searches upward from start_path until a .codecheck.yaml is found.
    If no file is found, returns a config with all defaults.

    Args:
        start_path: Where to start searching for .codecheck.yaml.
        cli_overrides: Optional dict of CLI arguments to override config values.
                       Supported keys: max_fix_rounds, diff_only.

    Returns:
        A fully populated and validated CodeCheckConfig.

    Raises:
        ConfigError: If the config file exists but is invalid.
    """
    config_path = find_config_file(start_path)

    if config_path is None:
        config = get_default_config()
    else:
        try:
            with open(config_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(
                f"Failed to parse YAML in {config_path}: {e}",
                file_path=config_path,
            ) from e
        except OSError as e:
            raise ConfigError(
                f"Failed to read config file {config_path}: {e}",
                file_path=config_path,
            ) from e

        if raw is None:
            # Empty YAML file (just comments or blank)
            config = get_default_config()
        else:
            config = parse_config(raw)

    # Apply CLI overrides
    if cli_overrides:
        config = apply_cli_overrides(config, cli_overrides)

    return config


def apply_cli_overrides(
    config: CodeCheckConfig, overrides: dict[str, Any]
) -> CodeCheckConfig:
    """Apply CLI argument overrides to an existing config.

    Only overrides fields that are explicitly provided (not None).
    Returns the same config object if no overrides are applicable.

    Supported override keys:
        max_fix_rounds: int — overrides review.max_fix_rounds
        diff_only: bool — overrides review.diff_only
    """
    if "max_fix_rounds" in overrides and overrides["max_fix_rounds"] is not None:
        config.review.max_fix_rounds = overrides["max_fix_rounds"]

    if "diff_only" in overrides and overrides["diff_only"] is not None:
        config.review.diff_only = overrides["diff_only"]

    return config
