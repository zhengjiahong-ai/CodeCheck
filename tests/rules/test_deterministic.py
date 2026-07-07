"""Unit tests for deterministic rule matching."""

from codecheck.rules.deterministic import DeterministicMatcher
from codecheck.rules.models import Rule, Severity

# ── Test fixtures ──────────────────────────────────────────────────────────

DET_RULES = [
    Rule(
        id="no-hardcoded-secret",
        severity=Severity.CRITICAL,
        type="deterministic",
        category="security",
        message="Hardcoded secret detected",
        pattern=r'(api_key|secret|password|token)\s*=\s*[\'"][^\'"]+[\'"]',
    ),
    Rule(
        id="no-bare-except",
        severity=Severity.WARNING,
        type="deterministic",
        category="style",
        message="Avoid bare except",
        pattern=r"except\s*:",
    ),
    Rule(
        id="no-debug-print",
        severity=Severity.INFO,
        type="deterministic",
        category="style",
        message="Debug print found",
        pattern=r"\bprint\s*\(",
    ),
    Rule(
        id="dangerous-eval",
        severity=Severity.CRITICAL,
        type="deterministic",
        category="security",
        message="Dangerous eval/exec usage",
        pattern=r"\b(eval|exec)\s*\(",
    ),
    Rule(
        id="sql-string-concat",
        severity=Severity.CRITICAL,
        type="deterministic",
        category="security",
        message="SQL string concatenation",
        pattern=r"(['\"])\s*(SELECT|INSERT|UPDATE|DELETE)\s",
    ),
]


# ── Tests ──────────────────────────────────────────────────────────────────


class TestDeterministicMatcher:
    """Test deterministic regex-based rule matching."""

    def test_detect_hardcoded_secret(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text('api_key = "sk-1234567890"\n')
        matcher = DeterministicMatcher(DET_RULES)
        issues = matcher.scan_file(test_file)
        assert len(issues) == 1
        assert issues[0].rule_id == "no-hardcoded-secret"
        assert issues[0].line == 1
        assert issues[0].severity == Severity.CRITICAL

    def test_detect_bare_except(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("try:\n    pass\nexcept:\n    pass\n")
        matcher = DeterministicMatcher(DET_RULES)
        issues = matcher.scan_file(test_file)
        assert len(issues) == 1
        assert issues[0].rule_id == "no-bare-except"

    def test_detect_debug_print(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text('print("debug")\n')
        matcher = DeterministicMatcher(DET_RULES)
        issues = matcher.scan_file(test_file)
        assert len(issues) == 1
        assert issues[0].rule_id == "no-debug-print"

    def test_detect_eval(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("eval(user_input)\n")
        matcher = DeterministicMatcher(DET_RULES)
        issues = matcher.scan_file(test_file)
        assert len(issues) == 1
        assert issues[0].rule_id == "dangerous-eval"

    def test_detect_sql_concat(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text('query = "SELECT * FROM users"\n')
        matcher = DeterministicMatcher(DET_RULES)
        issues = matcher.scan_file(test_file)
        assert len(issues) == 1
        assert issues[0].rule_id == "sql-string-concat"

    def test_clean_code_no_issues(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    return 'world'\n")
        matcher = DeterministicMatcher(DET_RULES)
        issues = matcher.scan_file(test_file)
        assert len(issues) == 0

    def test_multiple_issues_in_one_file(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text('api_key = "sk-abc"\nprint("test")\neval("x")\n')
        matcher = DeterministicMatcher(DET_RULES)
        issues = matcher.scan_file(test_file)
        assert len(issues) == 3

    def test_scan_multiple_files(self, tmp_path):
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text('print("a")\n')
        f2.write_text('api_key = "sk-123"\n')
        matcher = DeterministicMatcher(DET_RULES)
        issues = matcher.scan_files([f1, f2])
        assert len(issues) == 2

    def test_skip_non_deterministic_rules(self, tmp_path):
        """LLM-assisted rules should be ignored."""
        llm_rule = Rule(
            id="llm-rule",
            severity=Severity.WARNING,
            type="llm-assisted",
            category="security",
            message="LLM rule",
            prompt="Check for issues",
        )
        test_file = tmp_path / "test.py"
        test_file.write_text('print("hello")\n')
        matcher = DeterministicMatcher([llm_rule])
        assert len(matcher.rules) == 0

    def test_skip_unreadable_file(self, tmp_path):
        """Files that can't be read should be skipped silently."""
        matcher = DeterministicMatcher(DET_RULES)
        issues = matcher.scan_file("/nonexistent/file.py")
        assert len(issues) == 0
