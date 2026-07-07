"""Unit tests for configuration loading, validation, and CLI overrides."""

from pathlib import Path

import pytest

from codecheck.config.loader import (
    ConfigError,
    apply_cli_overrides,
    find_config_file,
    get_default_config,
    load_config,
)
from codecheck.config.schema import (
    CodeCheckConfig,
    LLMConfig,
    ReviewConfig,
)

# ── Fixtures ──────────────────────────────────────────────────────────────

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ── Default configuration ─────────────────────────────────────────────────


class TestDefaultConfig:
    """Test that get_default_config() returns sensible defaults."""

    def test_default_config_is_populated(self):
        config = get_default_config()
        assert isinstance(config, CodeCheckConfig)
        assert config.version == "1.0"

    def test_default_llm_config(self):
        config = get_default_config()
        assert config.llm.provider == "deepseek"
        assert config.llm.model == "deepseek-v4-pro"
        assert config.llm.base_url == "https://api.deepseek.com"

    def test_default_review_config(self):
        config = get_default_config()
        assert config.review.max_fix_rounds == 3
        assert config.review.diff_only is True
        assert "node_modules/" in config.review.exclude_paths
        assert "*.min.js" in config.review.exclude_paths
        assert "vendor/" in config.review.exclude_paths

    def test_default_test_config(self):
        config = get_default_config()
        assert config.test.command == "pytest"
        assert config.test.timeout_seconds == 120

    def test_default_rules_config(self):
        config = get_default_config()
        assert config.rules.path == ".codecheck/rules.yaml"

    def test_default_memory_config(self):
        config = get_default_config()
        assert config.memory.db_path == "~/.codecheck/memory.db"
        assert config.memory.vector_path == "~/.codecheck/vectors/"


# ── Loading valid config file ─────────────────────────────────────────────


class TestLoadValidConfig:
    """Test loading a valid .codecheck.yaml from disk."""

    def test_load_valid_config(self, tmp_path):
        """Load a full config file and verify all fields are parsed correctly."""
        # Copy the fixture content to a .codecheck.yaml in tmp_path
        fixture_content = (FIXTURES_DIR / "valid_config.yaml").read_text()
        (tmp_path / ".codecheck.yaml").write_text(fixture_content)
        config = load_config(tmp_path)
        assert config.version == "1.0"
        assert config.llm.provider == "deepseek"
        assert config.review.max_fix_rounds == 5
        assert config.review.diff_only is False
        assert "build/" in config.review.exclude_paths
        assert config.test.command == "pytest --tb=short"
        assert config.test.timeout_seconds == 180

    def test_load_config_when_not_found_returns_defaults(self, tmp_path):
        """No .codecheck.yaml in an empty directory → defaults."""
        config = load_config(tmp_path)
        assert config.review.max_fix_rounds == 3
        assert config.review.diff_only is True

    def test_find_config_file_walks_up(self, tmp_path):
        """find_config_file should walk up from a subdirectory."""
        (tmp_path / ".codecheck.yaml").write_text("version: '1.0'\n")
        sub = tmp_path / "a" / "b" / "c"
        sub.mkdir(parents=True)
        found = find_config_file(sub)
        assert found == str(tmp_path / ".codecheck.yaml")

    def test_find_config_file_returns_none_at_root(self, tmp_path):
        """find_config_file returns None when no file exists up to root."""
        # Create a temp directory with no .codecheck.yaml
        found = find_config_file(tmp_path)
        assert found is None

    def test_load_empty_yaml_returns_defaults(self, tmp_path):
        """Empty YAML file (just comments) → defaults."""
        config_path = tmp_path / ".codecheck.yaml"
        config_path.write_text("# just a comment\n")
        config = load_config(tmp_path)
        assert config.review.max_fix_rounds == 3

    def test_load_partial_config_fills_defaults(self, tmp_path):
        """Only some sections defined → defaults for the rest."""
        config_path = tmp_path / ".codecheck.yaml"
        config_path.write_text("version: '1.0'\nreview:\n  max_fix_rounds: 10\n")
        config = load_config(tmp_path)
        assert config.review.max_fix_rounds == 10
        # Unspecified sections use defaults
        assert config.llm.provider == "deepseek"
        assert config.test.command == "pytest"
        assert config.review.diff_only is True  # Not set, use default


# ── Invalid config handling ────────────────────────────────────────────────


class TestLoadInvalidConfig:
    """Test that invalid config files produce clear errors."""

    def test_invalid_yaml_syntax(self, tmp_path):
        """Malformed YAML should raise ConfigError."""
        config_path = tmp_path / ".codecheck.yaml"
        config_path.write_text("version: '1.0'\n  - bad\nindent: oops\n")
        with pytest.raises(ConfigError, match="Failed to parse YAML"):
            load_config(tmp_path)

    def test_max_fix_rounds_not_int(self, tmp_path):
        config_path = tmp_path / ".codecheck.yaml"
        config_path.write_text("review:\n  max_fix_rounds: 'abc'\n")
        with pytest.raises(ConfigError, match="max_fix_rounds"):
            load_config(tmp_path)

    def test_diff_only_not_bool(self, tmp_path):
        config_path = tmp_path / ".codecheck.yaml"
        config_path.write_text("review:\n  diff_only: 'yes'\n")
        with pytest.raises(ConfigError, match="diff_only"):
            load_config(tmp_path)

    def test_max_fix_rounds_below_minimum(self, tmp_path):
        config_path = tmp_path / ".codecheck.yaml"
        config_path.write_text("review:\n  max_fix_rounds: 0\n")
        with pytest.raises(ConfigError, match=">= 1"):
            load_config(tmp_path)

    def test_exclude_paths_not_list(self, tmp_path):
        config_path = tmp_path / ".codecheck.yaml"
        config_path.write_text("review:\n  exclude_paths: 'not-a-list'\n")
        with pytest.raises(ConfigError, match="exclude_paths"):
            load_config(tmp_path)

    def test_exclude_paths_contains_non_string(self, tmp_path):
        config_path = tmp_path / ".codecheck.yaml"
        config_path.write_text("review:\n  exclude_paths:\n    - 123\n")
        with pytest.raises(ConfigError, match="exclude_paths\\[0\\]"):
            load_config(tmp_path)

    def test_timeout_not_int(self, tmp_path):
        config_path = tmp_path / ".codecheck.yaml"
        config_path.write_text("test:\n  timeout_seconds: 1.5\n")
        with pytest.raises(ConfigError, match="timeout_seconds"):
            load_config(tmp_path)

    def test_config_is_list_not_dict(self, tmp_path):
        config_path = tmp_path / ".codecheck.yaml"
        config_path.write_text("- item1\n- item2\n")
        with pytest.raises(ConfigError, match="mapping"):
            load_config(tmp_path)


# ── CLI overrides ──────────────────────────────────────────────────────────


class TestCLIOverrides:
    """Test that CLI arguments override config values."""

    def test_override_max_fix_rounds(self):
        config = get_default_config()
        assert config.review.max_fix_rounds == 3
        apply_cli_overrides(config, {"max_fix_rounds": 7})
        assert config.review.max_fix_rounds == 7

    def test_override_diff_only(self):
        config = get_default_config()
        assert config.review.diff_only is True
        apply_cli_overrides(config, {"diff_only": False})
        assert config.review.diff_only is False

    def test_override_none_is_ignored(self):
        """CLI options that are None (not provided) should not override."""
        config = get_default_config()
        apply_cli_overrides(config, {"max_fix_rounds": None, "diff_only": None})
        assert config.review.max_fix_rounds == 3
        assert config.review.diff_only is True

    def test_override_unknown_key_is_ignored(self):
        """Unknown keys in overrides should be silently ignored."""
        config = get_default_config()
        apply_cli_overrides(config, {"unknown_option": 123})
        assert config.review.max_fix_rounds == 3  # unchanged

    def test_load_config_with_overrides(self, tmp_path):
        """load_config should accept and apply CLI overrides."""
        config_path = tmp_path / ".codecheck.yaml"
        config_path.write_text("review:\n  max_fix_rounds: 2\n")
        config = load_config(tmp_path, cli_overrides={"max_fix_rounds": 10})
        assert config.review.max_fix_rounds == 10  # CLI wins

    def test_load_config_defaults_with_overrides(self, tmp_path):
        """CLI overrides work even when no config file exists."""
        config = load_config(tmp_path, cli_overrides={"max_fix_rounds": 8})
        assert config.review.max_fix_rounds == 8


# ── Schema dataclass immutability ──────────────────────────────────────────


class TestSchemaDataclasses:
    """Test that individual config dataclasses work correctly."""

    def test_llm_config_custom(self):
        llm = LLMConfig(provider="openai", model="gpt-4")
        assert llm.provider == "openai"
        assert llm.model == "gpt-4"
        assert llm.base_url == "https://api.deepseek.com"  # default

    def test_review_config_custom(self):
        review = ReviewConfig(
            max_fix_rounds=10, exclude_paths=["dist/", "*.pyc"]
        )
        assert review.max_fix_rounds == 10
        assert "dist/" in review.exclude_paths

    def test_codecheck_config_nested(self):
        config = CodeCheckConfig(
            llm=LLMConfig(model="custom-model"),
            review=ReviewConfig(max_fix_rounds=7),
        )
        assert config.llm.model == "custom-model"
        assert config.review.max_fix_rounds == 7
        # Defaults for unset sub-configs
        assert config.test.command == "pytest"
