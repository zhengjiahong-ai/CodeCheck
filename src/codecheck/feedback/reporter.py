"""Fix report — data structures for the feedback loop output."""

from dataclasses import dataclass, field


@dataclass
class FixAttempt:
    """A single fix attempt.

    Attributes:
        round: The attempt number (1-indexed).
        diff: The fix diff (old_string → new_string).
        test_result: The test output after applying the fix.
        lint_result: The lint output after applying the fix.
        success: Whether this attempt succeeded.
        failure_reason: If failed, why.
    """

    round: int
    diff: str = ""
    test_result: str = ""
    lint_result: str = ""
    success: bool = False
    failure_reason: str = ""


@dataclass
class SingleFixResult:
    """Result for a single issue fix.

    Attributes:
        issue_id: The issue identifier (rule_id:file:line).
        status: "fixed", "needs_manual", "failed", "skipped".
        attempts: Number of fix attempts.
        attempts_detail: Details of each attempt.
        final_diff: The diff that finally worked (if fixed).
    """

    issue_id: str
    status: str  # "fixed" | "needs_manual" | "failed" | "skipped"
    attempts: int = 0
    attempts_detail: list[FixAttempt] = field(default_factory=list)
    final_diff: str = ""


@dataclass
class FixReport:
    """Complete fix report for all issues.

    Attributes:
        total_issues: Total number of issues processed.
        fixed: Number of issues successfully fixed.
        needs_manual: Number of issues that need human intervention.
        skipped: Number of issues skipped (no fix attempted).
        fixes: Per-issue fix results.
    """

    total_issues: int = 0
    fixed: int = 0
    needs_manual: int = 0
    skipped: int = 0
    fixes: list[SingleFixResult] = field(default_factory=list)
