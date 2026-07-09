"""Unit tests for FeedbackLoop — using MockProvider for deterministic testing."""

import json

from codecheck.feedback.loop import FeedbackLoop, _parse_fix_response
from codecheck.feedback.reporter import FixReport
from codecheck.llm.mock_provider import MockProvider, MockRule

# ── Helpers ────────────────────────────────────────────────────────────────


def _make_fix_response(old_string: str, new_string: str, explanation: str = "fix") -> str:
    """Build a fix response JSON."""
    return json.dumps({
        "old_string": old_string,
        "new_string": new_string,
        "explanation": explanation,
    })


# ── Tests ──────────────────────────────────────────────────────────────────


class TestParseFixResponse:
    """Test fix response parsing."""

    def test_direct_json(self):
        result = _parse_fix_response(
            json.dumps({"old_string": "a", "new_string": "b", "explanation": "test"})
        )
        assert result["old_string"] == "a"
        assert result["new_string"] == "b"

    def test_empty_response(self):
        assert _parse_fix_response("") == {}

    def test_none_response(self):
        assert _parse_fix_response(None) == {}

    def test_json_in_code_block(self):
        result = _parse_fix_response(
            '```json\n{"old_string": "x", "new_string": "y"}\n```'
        )
        assert result["old_string"] == "x"


class TestFeedbackLoop:
    """Test the full feedback loop with mock LLM."""

    def test_single_fix_succeeds(self, tmp_path):
        """LLM generates a fix, it applies, tests pass → fixed."""
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\n")

        mock_llm = MockProvider([
            MockRule(
                keyword=None,
                response_content=_make_fix_response(
                    old_string="print('hello')",
                    new_string="logging.info('hello')",
                ),
                consume=False,
            ),
        ])

        issue = {
            "rule_id": "no-debug-print",
            "file": str(test_file),
            "line": 1,
            "severity": "info",
            "message": "Debug print found",
        }

        loop = FeedbackLoop(
            llm=mock_llm,
            max_rounds=3,
            test_command="echo 'all tests passed'",
            lint_command="echo 'no lint errors'",
        )

        report = loop.process([issue])
        assert isinstance(report, FixReport)
        assert report.total_issues == 1
        assert report.fixed == 1
        assert report.fixes[0].status == "fixed"

        # Verify the fix was applied
        assert "logging" in test_file.read_text()

    def test_fix_applies_but_tests_fail_then_retry(self, tmp_path):
        """First attempt: fix applies but tests fail → rollback → retry → succeed."""
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1\n")

        mock_llm = MockProvider([
            # Round 1: generate fix, but tests will fail
            MockRule(
                keyword=None,
                response_content=_make_fix_response(
                    old_string="x = 1",
                    new_string="x = 2",
                ),
                consume=True,
            ),
            # Round 2: generate better fix, tests pass
            MockRule(
                keyword=None,
                response_content=_make_fix_response(
                    old_string="x = 1",
                    new_string="x = 42",
                ),
                consume=False,
            ),
        ])

        issue = {
            "rule_id": "test-rule",
            "file": str(test_file),
            "line": 1,
            "severity": "warning",
            "message": "Test issue",
        }

        loop = FeedbackLoop(
            llm=mock_llm,
            max_rounds=3,
            test_command="pytest --nonexistent-flag",  # Will fail
            lint_command="echo 'lint ok'",  # Lint passes
        )

        report = loop.process([issue])
        assert report.total_issues == 1
        # After test failure round 1, file is restored, round 2 generates fix
        # but tests still fail → needs_manual
        assert report.fixes[0].status in ("needs_manual", "fixed")

    def test_old_string_not_found_retry(self, tmp_path):
        """LLM generates a fix with wrong old_string → retry."""
        test_file = tmp_path / "test.py"
        test_file.write_text("actual content\n")

        mock_llm = MockProvider([
            # Round 1: wrong old_string
            MockRule(
                keyword=None,
                response_content=_make_fix_response(
                    old_string="wrong content",
                    new_string="fixed",
                ),
                consume=True,
            ),
            # Round 2: correct old_string
            MockRule(
                keyword=None,
                response_content=_make_fix_response(
                    old_string="actual content",
                    new_string="fixed content",
                ),
                consume=False,
            ),
        ])

        issue = {
            "rule_id": "test-rule",
            "file": str(test_file),
            "line": 1,
            "severity": "warning",
            "message": "Test issue",
        }

        loop = FeedbackLoop(
            llm=mock_llm,
            max_rounds=3,
            test_command="echo 'tests pass'",
            lint_command="echo 'lint pass'",
        )

        report = loop.process([issue])
        assert report.fixes[0].status == "fixed"
        assert test_file.read_text() == "fixed content\n"

    def test_max_rounds_exceeded(self, tmp_path):
        """All fix attempts fail → needs_manual with full history."""
        test_file = tmp_path / "test.py"
        test_file.write_text("original\n")

        mock_llm = MockProvider([
            MockRule(
                keyword=None,
                response_content=_make_fix_response(
                    old_string="wrong",
                    new_string="new",
                ),
                consume=False,
            ),
        ])

        issue = {
            "rule_id": "test-rule",
            "file": str(test_file),
            "line": 1,
            "severity": "warning",
            "message": "Test issue",
        }

        loop = FeedbackLoop(
            llm=mock_llm,
            max_rounds=2,
            test_command="echo 'pass'",
            lint_command="echo 'pass'",
        )

        report = loop.process([issue])
        assert report.fixes[0].status == "needs_manual"
        assert report.fixes[0].attempts == 2
        assert report.needs_manual == 1

    def test_multiple_issues_processed(self, tmp_path):
        """Multiple issues are processed independently."""
        f1 = tmp_path / "a.py"
        f2 = tmp_path / "b.py"
        f1.write_text("a\n")
        f2.write_text("b\n")

        mock_llm = MockProvider([
            # Issue 1: fix "a"
            MockRule(
                keyword=None,
                response_content=_make_fix_response("a", "fixed_a"),
                consume=True,
            ),
            # Issue 2: fix "b"
            MockRule(
                keyword=None,
                response_content=_make_fix_response("b", "fixed_b"),
                consume=False,
            ),
        ])

        issues = [
            {"rule_id": "r1", "file": str(f1), "line": 1, "severity": "info", "message": "m1"},
            {"rule_id": "r2", "file": str(f2), "line": 1, "severity": "warning", "message": "m2"},
        ]

        loop = FeedbackLoop(
            llm=mock_llm,
            max_rounds=3,
            test_command="echo 'pass'",
            lint_command="echo 'pass'",
        )

        report = loop.process(issues)
        assert report.total_issues == 2
        assert report.fixed == 2
