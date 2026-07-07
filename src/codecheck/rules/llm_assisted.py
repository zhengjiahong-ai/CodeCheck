"""LLM-assisted rule matcher — semantic code analysis via LLM."""

import json
import re

from codecheck.llm.provider import LLMProvider
from codecheck.rules.models import Issue, Rule, Severity

# The LLM is expected to return a JSON array of issues.
# We use a prompt template to instruct the LLM on the format.
LLM_ISSUE_PROMPT_TEMPLATE = """You are a code reviewer. Analyze the following code for "{rule_description}".

Rule: {rule_message}
Category: {category}

Return your findings as a JSON array. Each finding should have these fields:
- "line": the line number where the issue is found (integer)
- "severity": "critical", "warning", or "info"
- "message": a brief description of the issue

If no issues are found, return an empty JSON array: []

Code to analyze:
```{language}
{code}
```

Respond ONLY with the JSON array, no other text."""


def _extract_json(response: str) -> list[dict]:
    """Extract a JSON array from an LLM response.

    Tries direct JSON parse first, then falls back to extracting
    from markdown code blocks or raw brackets.
    """
    # Try direct parse
    try:
        result = json.loads(response.strip())
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass

    # Try to extract from ```json ... ``` block
    json_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", response)
    if json_block:
        try:
            result = json.loads(json_block.group(1).strip())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    # Try to extract from [...] pattern
    bracket_match = re.search(r"\[[\s\S]*\]", response)
    if bracket_match:
        try:
            result = json.loads(bracket_match.group())
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

    return []


def _guess_language(file_path: str) -> str:
    """Guess the programming language from a file extension."""
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    mapping = {
        "py": "python",
        "js": "javascript",
        "ts": "typescript",
        "java": "java",
        "go": "go",
        "rs": "rust",
        "c": "c",
        "cpp": "c++",
        "h": "c",
        "rb": "ruby",
        "sh": "bash",
        "yaml": "yaml",
        "yml": "yaml",
        "toml": "toml",
        "json": "json",
    }
    return mapping.get(ext, "")


class LLMAssistedMatcher:
    """Use an LLM Provider to apply semantic review rules.

    Each LLM-assisted rule is applied by sending the code + rule prompt
    to the LLM and parsing the structured JSON response.
    """

    # Maximum characters to send per LLM request
    MAX_CODE_LENGTH = 8000

    def __init__(self, rules: list[Rule] | None = None, llm: LLMProvider | None = None):
        """Initialize with LLM-assisted rules and an LLM provider.

        Args:
            rules: List of Rule objects. Only llm-assisted rules are used.
            llm: An LLMProvider instance for making LLM calls.
        """
        self._rules: list[Rule] = []
        if rules:
            for rule in rules:
                if rule.type == "llm-assisted":
                    self._rules.append(rule)
        self._llm: LLMProvider | None = llm

    @property
    def rules(self) -> list[Rule]:
        return list(self._rules)

    def set_llm(self, llm: LLMProvider) -> None:
        """Set the LLM provider."""
        self._llm = llm

    def scan_file(self, file_path: str) -> list[Issue]:
        """Scan a single file with LLM-assisted rules.

        Args:
            file_path: Path to the source file.

        Returns:
            List of Issue objects found by the LLM.
        """
        if not self._llm:
            return []

        try:
            with open(file_path, encoding="utf-8") as f:
                code = f.read()
        except (UnicodeDecodeError, PermissionError, OSError):
            return []

        # Truncate if too long
        if len(code) > self.MAX_CODE_LENGTH:
            code = code[:self.MAX_CODE_LENGTH] + "\n... [code truncated]"

        language = _guess_language(file_path)
        issues: list[Issue] = []

        for rule in self._rules:
            if not rule.prompt:
                continue

            prompt = LLM_ISSUE_PROMPT_TEMPLATE.format(
                rule_description=rule.prompt,
                rule_message=rule.message,
                category=rule.category,
                language=language,
                code=code,
            )

            try:
                response = self._llm.chat([{"role": "user", "content": prompt}])
                findings = _extract_json(response.content or "")
            except Exception:
                continue  # LLM call failed, skip this rule

            for finding in findings:
                line = finding.get("line", 1)
                if isinstance(line, str):
                    try:
                        line = int(line)
                    except ValueError:
                        line = 1

                severity_str = finding.get("severity", "warning")
                try:
                    severity = Severity(severity_str)
                except ValueError:
                    severity = Severity.WARNING

                issues.append(Issue(
                    rule_id=rule.id,
                    file=file_path,
                    line=line,
                    severity=severity,
                    message=finding.get("message", rule.message),
                    source="llm-assisted",
                ))

        return issues

    def scan_files(self, file_paths: list[str]) -> list[Issue]:
        """Scan multiple files with LLM-assisted rules."""
        all_issues: list[Issue] = []
        for path in file_paths:
            all_issues.extend(self.scan_file(path))
        return all_issues
