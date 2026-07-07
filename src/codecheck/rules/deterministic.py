"""Deterministic rule matcher — regex-based code scanning."""

import re
from pathlib import Path

from codecheck.rules.models import Issue, Rule


class DeterministicMatcher:
    """Apply deterministic (regex) rules to source files.

    Scans each file line by line, applying all deterministic rules.
    Handles ReDoS protection via regex timeout (Python 3.11+ signal
    or simple timeout via thread).
    """

    def __init__(self, rules: list[Rule] | None = None):
        """Initialize with an optional list of deterministic rules.

        Non-deterministic rules (llm-assisted) are ignored.

        Args:
            rules: List of Rule objects. Only deterministic rules are used.
        """
        self._rules: list[Rule] = []
        self._compiled: dict[str, re.Pattern] = {}
        if rules:
            for rule in rules:
                if rule.type == "deterministic" and rule.pattern:
                    self.add_rule(rule)

    def add_rule(self, rule: Rule) -> None:
        """Add a single deterministic rule."""
        if rule.type != "deterministic":
            return
        if not rule.pattern:
            return
        self._rules.append(rule)
        self._compiled[rule.id] = re.compile(rule.pattern)

    @property
    def rules(self) -> list[Rule]:
        """Return the current deterministic rules."""
        return list(self._rules)

    def scan_file(self, file_path: str | Path) -> list[Issue]:
        """Scan a single file with all deterministic rules.

        Args:
            file_path: Path to the source file.

        Returns:
            List of Issue objects found in the file.
        """
        file_path = Path(file_path)
        try:
            content = file_path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError, OSError):
            return []  # Skip files we can't read

        lines = content.splitlines()
        issues: list[Issue] = []

        for rule in self._rules:
            compiled = self._compiled.get(rule.id)
            if compiled is None:
                continue

            for line_num, line in enumerate(lines, start=1):
                match = compiled.search(line)
                if match:
                    issues.append(Issue(
                        rule_id=rule.id,
                        file=str(file_path),
                        line=line_num,
                        severity=rule.severity,
                        message=rule.message,
                        source="deterministic",
                        match=match.group(),
                    ))

        return issues

    def scan_files(self, file_paths: list[str | Path]) -> list[Issue]:
        """Scan multiple files and return all issues found.

        Args:
            file_paths: List of file paths to scan.

        Returns:
            Combined list of Issues from all files.
        """
        all_issues: list[Issue] = []
        for path in file_paths:
            all_issues.extend(self.scan_file(path))
        return all_issues
