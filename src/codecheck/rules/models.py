"""Rule engine data models — Rule, Issue, Severity."""

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    """Issue severity levels."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class Rule:
    """A single code review rule.

    Attributes:
        id: Unique rule identifier (e.g., "no-hardcoded-secret").
        severity: Severity level.
        type: "deterministic" (regex) or "llm-assisted" (LLM).
        category: Category (security, style, reliability, etc.).
        message: Human-readable description of the issue.
        pattern: Regex pattern for deterministic rules.
        prompt: LLM prompt for llm-assisted rules.
    """

    id: str
    severity: Severity
    type: str  # "deterministic" or "llm-assisted"
    category: str
    message: str
    pattern: str | None = None
    prompt: str | None = None

    def __post_init__(self):
        if isinstance(self.severity, str):
            self.severity = Severity(self.severity)
        if self.type not in ("deterministic", "llm-assisted"):
            raise ValueError(
                f"Rule type must be 'deterministic' or 'llm-assisted', got '{self.type}'"
            )


@dataclass
class Issue:
    """A single code review issue found by the rule engine.

    Attributes:
        rule_id: The rule that produced this issue.
        file: File path where the issue was found.
        line: Line number (1-indexed).
        severity: Severity level.
        message: Human-readable description.
        source: How the issue was found ("deterministic" or "llm-assisted").
        dual_confirmed: True if both deterministic and LLM rules flagged this.
        match: The actual text that matched (for deterministic rules).
    """

    rule_id: str
    file: str
    line: int
    severity: Severity
    message: str
    source: str  # "deterministic" or "llm-assisted"
    dual_confirmed: bool = False
    match: str | None = None

    def __post_init__(self):
        if isinstance(self.severity, str):
            self.severity = Severity(self.severity)

    @property
    def location_key(self) -> tuple:
        """Return a dedup key — (file, line) tuple."""
        return (self.file, self.line)
