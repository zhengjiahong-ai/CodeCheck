"""Agent response parser — extract review reports from LLM output."""

import json
import re

from codecheck.rules.models import Severity


class ParseError(Exception):
    """Raised when the LLM response cannot be parsed."""


def parse_review_report(content: str | None) -> dict:
    """Parse an LLM review report from text content.

    Tries multiple strategies to extract structured JSON from the LLM output:
    1. Direct JSON parse of the full content
    2. JSON inside ```json ... ``` code block
    3. JSON object pattern { ... }

    Args:
        content: The content string from the LLM response.

    Returns:
        A dict with keys: status, issues (list), summary.

    Raises:
        ParseError: If no valid JSON report can be extracted.
    """
    if not content:
        raise ParseError("Empty LLM response")

    content = content.strip()

    # Strategy 1: Direct JSON parse
    try:
        result = json.loads(content)
        if isinstance(result, dict):
            return _normalize_report(result)
    except json.JSONDecodeError:
        pass

    # Strategy 2: JSON inside code block
    json_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if json_block:
        try:
            result = json.loads(json_block.group(1).strip())
            if isinstance(result, dict):
                return _normalize_report(result)
        except json.JSONDecodeError:
            pass

    # Strategy 3: JSON object pattern
    obj_match = re.search(r"\{[\s\S]*\}", content)
    if obj_match:
        try:
            result = json.loads(obj_match.group())
            if isinstance(result, dict):
                return _normalize_report(result)
        except json.JSONDecodeError:
            pass

    raise ParseError(f"Could not parse review report from LLM response: {content[:200]}...")


def _normalize_report(raw: dict) -> dict:
    """Normalize a parsed report dict to the expected format."""
    status = raw.get("status", "complete")
    issues = raw.get("issues", [])
    summary = raw.get("summary", "")

    # Normalize each issue
    normalized_issues = []
    for issue_data in issues:
        if not isinstance(issue_data, dict):
            continue

        severity_str = issue_data.get("severity", "warning")
        try:
            severity = Severity(severity_str)
        except ValueError:
            severity = Severity.WARNING

        line = issue_data.get("line", 1)
        if isinstance(line, str):
            try:
                line = int(line)
            except ValueError:
                line = 1

        normalized_issues.append({
            "rule_id": issue_data.get("rule_id", "unknown"),
            "file": issue_data.get("file", ""),
            "line": line,
            "severity": severity.value,
            "message": issue_data.get("message", ""),
        })

    return {
        "status": status,
        "issues": normalized_issues,
        "summary": summary,
    }
