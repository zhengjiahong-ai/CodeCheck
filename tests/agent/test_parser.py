"""Unit tests for agent response parser."""

import json

import pytest

from codecheck.agent.parser import ParseError, parse_review_report


class TestParseReviewReport:
    """Test parsing LLM review reports."""

    def test_direct_json(self):
        report = json.dumps({
            "status": "complete",
            "issues": [
                {"rule_id": "r1", "file": "a.py", "line": 1,
                 "severity": "critical", "message": "test issue"},
            ],
            "summary": "Found 1 issue",
        })
        result = parse_review_report(report)
        assert result["status"] == "complete"
        assert len(result["issues"]) == 1
        assert result["issues"][0]["rule_id"] == "r1"
        assert result["summary"] == "Found 1 issue"

    def test_json_in_code_block(self):
        report = """Here is my review:
```json
{
  "status": "complete",
  "issues": [
    {"rule_id": "r2", "file": "b.py", "line": 5,
     "severity": "warning", "message": "warning issue"}
  ],
  "summary": "Done"
}
```"""
        result = parse_review_report(report)
        assert len(result["issues"]) == 1
        assert result["issues"][0]["rule_id"] == "r2"

    def test_empty_issues(self):
        result = parse_review_report(json.dumps({
            "status": "complete",
            "issues": [],
            "summary": "No issues",
        }))
        assert result["status"] == "complete"
        assert len(result["issues"]) == 0

    def test_normalizes_severity(self):
        result = parse_review_report(json.dumps({
            "status": "complete",
            "issues": [
                {"rule_id": "r1", "file": "a.py", "line": 1,
                 "severity": "INVALID", "message": "test"},
            ],
            "summary": "test",
        }))
        assert result["issues"][0]["severity"] == "warning"  # default

    def test_normalizes_line_string(self):
        result = parse_review_report(json.dumps({
            "status": "complete",
            "issues": [
                {"rule_id": "r1", "file": "a.py", "line": "42",
                 "severity": "info", "message": "test"},
            ],
            "summary": "test",
        }))
        assert result["issues"][0]["line"] == 42

    def test_invalid_json_raises(self):
        with pytest.raises(ParseError, match="Could not parse"):
            parse_review_report("not valid json at all")

    def test_empty_content_raises(self):
        with pytest.raises(ParseError, match="Empty"):
            parse_review_report("")

    def test_none_content_raises(self):
        with pytest.raises(ParseError):
            parse_review_report(None)

    def test_missing_summary_defaults(self):
        result = parse_review_report(json.dumps({
            "status": "complete",
            "issues": [],
        }))
        assert result["summary"] == ""

    def test_skips_invalid_issue_entries(self):
        result = parse_review_report(json.dumps({
            "status": "complete",
            "issues": [
                "not a dict",
                {"rule_id": "r1", "file": "a.py", "line": 1,
                 "severity": "info", "message": "valid"},
            ],
            "summary": "test",
        }))
        assert len(result["issues"]) == 1
        assert result["issues"][0]["rule_id"] == "r1"
