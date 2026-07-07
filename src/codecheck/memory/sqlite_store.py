"""SQLite memory store — persistent review history and false positive tracking."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from codecheck.memory.store import (
    FalsePositiveRecord,
    MemoryStore,
    ReviewRecord,
)


class SQLiteStore(MemoryStore):
    """SQLite-backed memory store for review history and false positives.

    Creates three tables: review_history, false_positives, fix_history.
    Automatically initializes the database on first use.

    Usage:
        store = SQLiteStore("~/.codecheck/memory.db")
        store.save_review(ReviewRecord(...))
        history = store.get_history(file_path="src/main.py")
    """

    def __init__(self, db_path: str | Path = "~/.codecheck/memory.db"):
        """Initialize the SQLite store.

        Args:
            db_path: Path to the SQLite database file.
                     Defaults to ~/.codecheck/memory.db
        """
        self._db_path = Path(db_path).expanduser().resolve()
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    @property
    def path(self) -> Path:
        """Return the database file path."""
        return self._db_path

    def _get_conn(self) -> sqlite3.Connection:
        """Get or create a database connection."""
        if self._conn is None:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self._db_path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
        return self._conn

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS review_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                file_path TEXT NOT NULL,
                rule_id TEXT NOT NULL,
                severity TEXT NOT NULL,
                line_number INTEGER,
                issue_description TEXT,
                fix_status TEXT DEFAULT 'unfixed',
                fix_attempts INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS false_positives (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                rule_id TEXT NOT NULL,
                file_path TEXT NOT NULL,
                line_number INTEGER,
                code_snippet_hash TEXT NOT NULL,
                note TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS fix_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                rule_id TEXT NOT NULL,
                original_code_hash TEXT,
                fix_diff TEXT,
                success BOOLEAN,
                test_output TEXT,
                attempts_taken INTEGER DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_review_history_file
                ON review_history(file_path);
            CREATE INDEX IF NOT EXISTS idx_review_history_rule
                ON review_history(rule_id);
            CREATE INDEX IF NOT EXISTS idx_false_positives_hash
                ON false_positives(code_snippet_hash);
            CREATE INDEX IF NOT EXISTS idx_false_positives_rule
                ON false_positives(rule_id);
        """)
        conn.commit()

    def save_review(self, record: ReviewRecord) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO review_history
               (file_path, rule_id, severity, line_number,
                issue_description, fix_status, fix_attempts)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                record.file_path,
                record.rule_id,
                record.severity,
                record.line_number,
                record.issue_description,
                record.fix_status,
                record.fix_attempts,
            ),
        )
        conn.commit()

    def get_history(
        self, file_path: str | None = None, limit: int = 50
    ) -> list[ReviewRecord]:
        conn = self._get_conn()
        if file_path:
            rows = conn.execute(
                """SELECT * FROM review_history
                   WHERE file_path = ?
                   ORDER BY timestamp DESC LIMIT ?""",
                (file_path, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM review_history ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()

        return [ReviewRecord(
            file_path=row["file_path"],
            rule_id=row["rule_id"],
            severity=row["severity"],
            line_number=row["line_number"],
            issue_description=row["issue_description"],
            fix_status=row["fix_status"],
            fix_attempts=row["fix_attempts"],
            timestamp=_parse_timestamp(row["timestamp"]),
        ) for row in rows]

    def mark_false_positive(
        self,
        rule_id: str,
        file_path: str,
        line_number: int,
        code_snippet_hash: str,
        note: str = "",
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO false_positives
               (rule_id, file_path, line_number, code_snippet_hash, note)
               VALUES (?, ?, ?, ?, ?)""",
            (rule_id, file_path, line_number, code_snippet_hash, note),
        )
        conn.commit()

    def is_false_positive(
        self, rule_id: str, file_path: str, line_number: int
    ) -> bool:
        conn = self._get_conn()
        row = conn.execute(
            """SELECT 1 FROM false_positives
               WHERE rule_id = ? AND file_path = ? AND line_number = ?
               LIMIT 1""",
            (rule_id, file_path, line_number),
        ).fetchone()
        return row is not None

    def list_false_positives(self) -> list[FalsePositiveRecord]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM false_positives ORDER BY timestamp DESC"
        ).fetchall()
        return [FalsePositiveRecord(
            rule_id=row["rule_id"],
            file_path=row["file_path"],
            line_number=row["line_number"],
            code_snippet_hash=row["code_snippet_hash"],
            note=row["note"],
            timestamp=_parse_timestamp(row["timestamp"]),
        ) for row in rows]

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _parse_timestamp(ts: str | None) -> datetime | None:
    """Parse a SQLite timestamp string to datetime."""
    if ts is None:
        return None
    try:
        # SQLite CURRENT_TIMESTAMP format: "YYYY-MM-DD HH:MM:SS"
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=timezone.utc
        )
    except (ValueError, TypeError):
        return None
