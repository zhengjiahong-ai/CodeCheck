"""Memory store — abstract base class for storing review history."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ReviewRecord:
    """A single review history record.

    Attributes:
        file_path: The file that was reviewed.
        rule_id: The rule that flagged the issue.
        severity: Severity level.
        line_number: Line number where the issue was found.
        issue_description: Description of the issue.
        fix_status: 'fixed', 'needs_manual', 'false_positive', 'unfixed'.
        fix_attempts: Number of fix attempts.
        timestamp: When the review was performed.
    """

    file_path: str
    rule_id: str
    severity: str
    line_number: int
    issue_description: str
    fix_status: str = "unfixed"
    fix_attempts: int = 0
    timestamp: datetime | None = None


@dataclass
class FalsePositiveRecord:
    """A false positive marker.

    Attributes:
        rule_id: The rule that was marked as false positive.
        file_path: The file where the false positive was found.
        line_number: Line number.
        code_snippet_hash: Hash of the code snippet.
        note: Optional user note.
        timestamp: When it was marked.
    """

    rule_id: str
    file_path: str
    line_number: int
    code_snippet_hash: str
    note: str = ""
    timestamp: datetime | None = None


class MemoryStore(ABC):
    """Abstract base class for memory storage.

    Implementations provide persistent storage for review history,
    false positives, and fix strategies.
    """

    @abstractmethod
    def save_review(self, record: ReviewRecord) -> None:
        """Save a review record to persistent storage."""
        ...

    @abstractmethod
    def get_history(
        self, file_path: str | None = None, limit: int = 50
    ) -> list[ReviewRecord]:
        """Retrieve review history, optionally filtered by file path."""
        ...

    @abstractmethod
    def mark_false_positive(
        self, rule_id: str, file_path: str, line_number: int,
        code_snippet_hash: str, note: str = "",
    ) -> None:
        """Mark an issue as false positive."""
        ...

    @abstractmethod
    def is_false_positive(
        self, rule_id: str, file_path: str, line_number: int,
    ) -> bool:
        """Check if an issue at the given location is a known false positive."""
        ...

    @abstractmethod
    def list_false_positives(self) -> list[FalsePositiveRecord]:
        """List all false positive records."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Close the store and release resources."""
        ...
