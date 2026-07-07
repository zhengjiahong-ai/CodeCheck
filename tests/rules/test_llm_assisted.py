"""Unit tests for LLM-assisted rule matching (using MockProvider)."""

import json

from codecheck.llm.mock_provider import MockProvider, MockRule
from codecheck.rules.llm_assisted import LLMAssistedMatcher, _extract_json
from codecheck.rules.models import Rule, Severity

# ── Test fixtures ──────────────────────────────────────────────────────────

LLM_RULES = [
    Rule(
        id="sql-injection-risk",
        severity=Severity.CRITICAL,
        type="llm-assisted",
        category="security",
        message="Potential SQL injection",
        prompt="Check for SQL injection risks",
    ),
    Rule(
        id="unhandled-error",
        severity=Severity.WARNING,
        type="llm-assisted",
        category="reliability",
        message="Unhandled error path",
        prompt="Check for unhandled errors",
    ),
]


# ── Tests ──────────────────────────────────────────────────────────────────


class TestExtractJSON:
    """Test JSON extraction from LLM responses."""

    def test_direct_json_array(self):
        response = '[{"line": 1, "severity": "critical", "message": "test"}]'
        result = _extract_json(response)
        assert len(result) == 1
        assert result[0]["line"] == 1

    def test_empty_array(self):
        assert _extract_json("[]") == []

    def test_json_in_code_block(self):
        response = '```json\n[{"line": 5, "severity": "warning", "message": "test"}]\n```'
        result = _extract_json(response)
        assert len(result) == 1
        assert result[0]["line"] == 5

    def test_invalid_json(self):
        assert _extract_json("not json at all") == []

    def test_json_with_surrounding_text(self):
        response = 'Here are findings: [{"line": 3, "severity": "info", "message": "ok"}]'
        result = _extract_json(response)
        assert len(result) == 1
        assert result[0]["line"] == 3


class TestLLMAssistedMatcher:
    """Test LLM-assisted rule matching with mock LLM."""

    def test_no_llm_returns_empty(self, tmp_path):
        """Without an LLM provider, scan should return empty."""
        matcher = LLMAssistedMatcher(LLM_RULES, llm=None)
        test_file = tmp_path / "test.py"
        test_file.write_text("SELECT * FROM users\n")
        issues = matcher.scan_file(str(test_file))
        assert len(issues) == 0

    def test_llm_finds_issues(self, tmp_path):
        """Mock LLM returns findings → parsed correctly."""
        findings = json.dumps([
            {"line": 1, "severity": "critical", "message": "SQL injection detected"},
        ])
        mock = MockProvider([
            MockRule(keyword=None, response_content=findings, consume=False),
        ])
        matcher = LLMAssistedMatcher(LLM_RULES, llm=mock)
        test_file = tmp_path / "test.py"
        test_file.write_text("query = 'SELECT * FROM users'\n")
        issues = matcher.scan_file(str(test_file))
        # Two rules × one finding each = 2 issues
        assert len(issues) == 2
        assert issues[0].rule_id == "sql-injection-risk"
        assert issues[0].severity == Severity.CRITICAL

    def test_llm_finds_no_issues(self, tmp_path):
        """Mock LLM returns empty array → no issues."""
        mock = MockProvider([
            MockRule(keyword=None, response_content="[]", consume=False),
        ])
        matcher = LLMAssistedMatcher(LLM_RULES, llm=mock)
        test_file = tmp_path / "test.py"
        test_file.write_text("safe code\n")
        issues = matcher.scan_file(str(test_file))
        assert len(issues) == 0

    def test_llm_error_graceful(self, tmp_path):
        """LLM call raises exception → gracefully return empty."""
        from codecheck.llm.exceptions import LLMProviderError

        mock = MockProvider([
            MockRule(
                keyword=None,
                raise_error=LLMProviderError("LLM down"),
            ),
        ])
        matcher = LLMAssistedMatcher(LLM_RULES, llm=mock)
        test_file = tmp_path / "test.py"
        test_file.write_text("code\n")
        issues = matcher.scan_file(str(test_file))
        assert len(issues) == 0  # Graceful degradation

    def test_two_rules_both_find_issues(self, tmp_path):
        """Both LLM rules fire and return findings."""
        findings = json.dumps([
            {"line": 1, "severity": "critical", "message": "SQL injection"},
            {"line": 3, "severity": "warning", "message": "Unhandled error"},
        ])
        mock = MockProvider([
            MockRule(keyword=None, response_content=findings, consume=False),
        ])
        matcher = LLMAssistedMatcher(LLM_RULES, llm=mock)
        test_file = tmp_path / "test.py"
        test_file.write_text("line1\nline2\nline3\n")
        issues = matcher.scan_file(str(test_file))
        assert len(issues) == 4  # 2 findings × 2 rules

    def test_scan_multiple_files(self, tmp_path):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("code a\n")
        f2.write_text("code b\n")
        mock = MockProvider([
            MockRule(keyword=None, response_content="[]", consume=False),
        ])
        matcher = LLMAssistedMatcher(LLM_RULES, llm=mock)
        issues = matcher.scan_files([str(f1), str(f2)])
        assert len(issues) == 0
