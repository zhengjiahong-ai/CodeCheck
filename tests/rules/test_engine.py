"""Unit tests for RuleEngine integration (deterministic + LLM-assisted + dedup)."""

import json
from pathlib import Path

import yaml

from codecheck.llm.mock_provider import MockProvider, MockRule
from codecheck.rules.engine import RuleEngine
from codecheck.rules.loader import RuleLoadError, load_rules_from_yaml

# ── Helpers ────────────────────────────────────────────────────────────────


def _write_rules_yaml(path: Path, rules: list[dict]) -> None:
    path.write_text(yaml.dump({"rules": rules}), encoding="utf-8")


def _write_code_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


# ── Tests ──────────────────────────────────────────────────────────────────


class TestRuleEngineDeterministic:
    """Test RuleEngine with only deterministic rules."""

    def test_det_only_scan(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        _write_rules_yaml(rules_file, [
            {
                "id": "no-debug-print",
                "severity": "info",
                "type": "deterministic",
                "category": "style",
                "message": "Debug print",
                "pattern": r"\bprint\s*\(",
            },
        ])
        code_file = tmp_path / "test.py"
        _write_code_file(code_file, 'print("hello")\n')

        engine = RuleEngine(rules_path=rules_file)
        issues = engine.scan([code_file])
        assert len(issues) == 1
        assert issues[0].rule_id == "no-debug-print"

    def test_clean_code_no_issues(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        _write_rules_yaml(rules_file, [
            {
                "id": "no-debug-print",
                "severity": "info",
                "type": "deterministic",
                "category": "style",
                "message": "Debug print",
                "pattern": r"\bprint\s*\(",
            },
        ])
        code_file = tmp_path / "test.py"
        _write_code_file(code_file, "x = 1\n")

        engine = RuleEngine(rules_path=rules_file)
        issues = engine.scan([code_file])
        assert len(issues) == 0

    def test_sorted_by_severity(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        _write_rules_yaml(rules_file, [
            {
                "id": "info-rule",
                "severity": "info",
                "type": "deterministic",
                "category": "style",
                "message": "Info",
                "pattern": r"info_marker",
            },
            {
                "id": "critical-rule",
                "severity": "critical",
                "type": "deterministic",
                "category": "security",
                "message": "Critical",
                "pattern": r"critical_marker",
            },
        ])
        code_file = tmp_path / "test.py"
        _write_code_file(code_file, "info_marker\ncritical_marker\n")

        engine = RuleEngine(rules_path=rules_file)
        issues = engine.scan([code_file])
        assert len(issues) == 2
        # Critical should come first
        assert issues[0].severity.value == "critical"
        assert issues[1].severity.value == "info"


class TestRuleEngineLLM:
    """Test RuleEngine with LLM-assisted rules (using MockProvider)."""

    def test_llm_and_det_combined(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        _write_rules_yaml(rules_file, [
            {
                "id": "no-debug-print",
                "severity": "info",
                "type": "deterministic",
                "category": "style",
                "message": "Debug print",
                "pattern": r"\bprint\s*\(",
            },
            {
                "id": "sql-injection",
                "severity": "critical",
                "type": "llm-assisted",
                "category": "security",
                "message": "SQL injection risk",
                "prompt": "Check for SQL injection",
            },
        ])
        code_file = tmp_path / "test.py"
        _write_code_file(code_file, 'print("test")\n')

        mock = MockProvider([
            MockRule(
                keyword=None,
                response_content=json.dumps([
                    {"line": 1, "severity": "warning", "message": "print found"},
                ]),
                consume=False,
            ),
        ])

        engine = RuleEngine(rules_path=rules_file, llm=mock)
        issues = engine.scan([code_file])

        # Both det and LLM hit line 1 → dual_confirmed
        assert len(issues) == 1
        assert issues[0].dual_confirmed is True


class TestRuleEngineDedup:
    """Test issue deduplication in RuleEngine."""

    def test_different_lines_not_merged(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        _write_rules_yaml(rules_file, [
            {
                "id": "rule-a",
                "severity": "warning",
                "type": "deterministic",
                "category": "style",
                "message": "Rule A",
                "pattern": r"marker_a",
            },
            {
                "id": "rule-b",
                "severity": "warning",
                "type": "deterministic",
                "category": "style",
                "message": "Rule B",
                "pattern": r"marker_b",
            },
        ])
        code_file = tmp_path / "test.py"
        _write_code_file(code_file, "marker_a\nmarker_b\n")

        engine = RuleEngine(rules_path=rules_file)
        issues = engine.scan([code_file])
        assert len(issues) == 2  # Different lines → not merged

    def test_same_line_merged_with_dual_confirmed(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        _write_rules_yaml(rules_file, [
            {
                "id": "rule-a",
                "severity": "warning",
                "type": "deterministic",
                "category": "style",
                "message": "Rule A",
                "pattern": r"same_line",
            },
            {
                "id": "rule-b",
                "severity": "info",
                "type": "deterministic",
                "category": "style",
                "message": "Rule B",
                "pattern": r"same_line",
            },
        ])
        code_file = tmp_path / "test.py"
        _write_code_file(code_file, "same_line\n")

        engine = RuleEngine(rules_path=rules_file)
        issues = engine.scan([code_file])
        assert len(issues) == 1
        assert issues[0].dual_confirmed is True
        # Highest severity (warning) should win
        assert issues[0].severity.value == "warning"


class TestRuleEngineFalsePositive:
    """Test false positive filtering."""

    def test_false_positive_filtered(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        _write_rules_yaml(rules_file, [
            {
                "id": "no-print",
                "severity": "info",
                "type": "deterministic",
                "category": "style",
                "message": "Print found",
                "pattern": r"\bprint\s*\(",
            },
        ])
        code_file = tmp_path / "test.py"
        _write_code_file(code_file, 'print("known false positive")\n')

        engine = RuleEngine(rules_path=rules_file)
        engine.add_false_positive(f"{code_file}:1:no-print")

        issues = engine.scan([code_file])
        assert len(issues) == 0


class TestRuleLoader:
    """Test YAML rule loading."""

    def test_load_valid_rules(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        _write_rules_yaml(rules_file, [
            {
                "id": "test-rule",
                "severity": "critical",
                "type": "deterministic",
                "category": "security",
                "message": "Test rule",
                "pattern": r"test",
            },
        ])
        rules = load_rules_from_yaml(rules_file)
        assert len(rules) == 1
        assert rules[0].id == "test-rule"

    def test_load_empty_file(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        rules_file.write_text("# no rules\n")
        rules = load_rules_from_yaml(rules_file)
        assert len(rules) == 0

    def test_load_missing_file(self, tmp_path):
        with __import__("pytest").raises(RuleLoadError, match="not found"):
            load_rules_from_yaml(tmp_path / "nonexistent.yaml")

    def test_load_invalid_yaml(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        rules_file.write_text(": invalid yaml\n")
        with __import__("pytest").raises(RuleLoadError, match="Invalid YAML"):
            load_rules_from_yaml(rules_file)

    def test_load_missing_id(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        _write_rules_yaml(rules_file, [
            {"severity": "warning", "type": "deterministic", "message": "No ID"},
        ])
        with __import__("pytest").raises(RuleLoadError, match="missing required field 'id'"):
            load_rules_from_yaml(rules_file)

    def test_load_invalid_type(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        _write_rules_yaml(rules_file, [
            {
                "id": "bad-rule",
                "severity": "warning",
                "type": "invalid-type",
                "message": "Bad type",
            },
        ])
        with __import__("pytest").raises(RuleLoadError, match="type must be"):
            load_rules_from_yaml(rules_file)

    def test_load_invalid_severity(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        _write_rules_yaml(rules_file, [
            {
                "id": "bad-severity",
                "severity": "fatal",
                "type": "deterministic",
                "message": "Bad severity",
            },
        ])
        with __import__("pytest").raises(RuleLoadError, match="severity must be"):
            load_rules_from_yaml(rules_file)

    def test_load_invalid_regex(self, tmp_path):
        rules_file = tmp_path / "rules.yaml"
        _write_rules_yaml(rules_file, [
            {
                "id": "bad-regex",
                "severity": "warning",
                "type": "deterministic",
                "message": "Bad regex",
                "pattern": "[invalid",
            },
        ])
        with __import__("pytest").raises(RuleLoadError, match="invalid regex"):
            load_rules_from_yaml(rules_file)
