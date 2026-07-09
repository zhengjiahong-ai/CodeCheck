"""CodeCheck feedback loop — auto-fix, verify, rollback, retry, converge."""

from codecheck.feedback.backup import backup_file, backup_file_with_metadata, restore_file
from codecheck.feedback.loop import FeedbackLoop
from codecheck.feedback.reporter import FixAttempt, FixReport, SingleFixResult
from codecheck.feedback.verifier import LintResult, TestResult, run_lint, run_tests

__all__ = [
    "FeedbackLoop",
    "FixAttempt",
    "FixReport",
    "LintResult",
    "SingleFixResult",
    "TestResult",
    "backup_file",
    "backup_file_with_metadata",
    "restore_file",
    "run_lint",
    "run_tests",
]
