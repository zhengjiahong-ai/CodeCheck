"""Unit tests for SQLite memory store."""

import sqlite3

from codecheck.memory.sqlite_store import SQLiteStore
from codecheck.memory.store import ReviewRecord


class TestSQLiteStore:
    """Test SQLite-backed memory store."""

    def test_init_creates_database(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = SQLiteStore(db_path)
        assert db_path.is_file()
        store.close()

    def test_save_and_retrieve_review(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = SQLiteStore(db_path)
        record = ReviewRecord(
            file_path="src/main.py",
            rule_id="no-hardcoded-secret",
            severity="critical",
            line_number=12,
            issue_description="API key hardcoded",
        )
        store.save_review(record)
        history = store.get_history()
        assert len(history) == 1
        assert history[0].file_path == "src/main.py"
        assert history[0].rule_id == "no-hardcoded-secret"
        store.close()

    def test_get_history_filtered_by_file(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = SQLiteStore(db_path)
        store.save_review(ReviewRecord(
            file_path="src/a.py", rule_id="r1", severity="info",
            line_number=1, issue_description="issue a",
        ))
        store.save_review(ReviewRecord(
            file_path="src/b.py", rule_id="r2", severity="warning",
            line_number=2, issue_description="issue b",
        ))
        history = store.get_history(file_path="src/a.py")
        assert len(history) == 1
        assert history[0].file_path == "src/a.py"
        store.close()

    def test_get_history_respects_limit(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = SQLiteStore(db_path)
        for i in range(10):
            store.save_review(ReviewRecord(
                file_path=f"src/{i}.py", rule_id="r1", severity="info",
                line_number=i, issue_description=f"issue {i}",
            ))
        history = store.get_history(limit=3)
        assert len(history) == 3
        store.close()

    def test_mark_and_check_false_positive(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = SQLiteStore(db_path)
        store.mark_false_positive(
            rule_id="no-print",
            file_path="src/main.py",
            line_number=5,
            code_snippet_hash="abc123",
            note="This is intentional",
        )
        assert store.is_false_positive("no-print", "src/main.py", 5) is True
        assert store.is_false_positive("no-print", "src/main.py", 6) is False
        assert store.is_false_positive("other-rule", "src/main.py", 5) is False
        store.close()

    def test_list_false_positives(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = SQLiteStore(db_path)
        store.mark_false_positive(
            rule_id="r1", file_path="a.py", line_number=1,
            code_snippet_hash="h1",
        )
        store.mark_false_positive(
            rule_id="r2", file_path="b.py", line_number=2,
            code_snippet_hash="h2", note="user note",
        )
        fps = store.list_false_positives()
        assert len(fps) == 2
        store.close()

    def test_empty_history(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = SQLiteStore(db_path)
        history = store.get_history()
        assert len(history) == 0
        store.close()

    def test_multiple_reviews_same_file(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = SQLiteStore(db_path)
        for i in range(5):
            store.save_review(ReviewRecord(
                file_path="src/main.py", rule_id=f"r{i}", severity="warning",
                line_number=i, issue_description=f"issue {i}",
            ))
        history = store.get_history(file_path="src/main.py")
        assert len(history) == 5
        store.close()

    def test_context_manager(self, tmp_path):
        db_path = tmp_path / "test.db"
        with SQLiteStore(db_path) as store:
            store.save_review(ReviewRecord(
                file_path="src/main.py", rule_id="r1", severity="info",
                line_number=1, issue_description="test",
            ))
        # After exit, connection should be closed
        assert store._conn is None

    def test_tables_created(self, tmp_path):
        db_path = tmp_path / "test.db"
        store = SQLiteStore(db_path)
        conn = sqlite3.connect(str(db_path))
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "review_history" in table_names
        assert "false_positives" in table_names
        assert "fix_history" in table_names
        conn.close()
        store.close()

    def test_empty_db_path_creates_default(self, tmp_path, monkeypatch):
        # Set HOME so Path.expanduser() works
        monkeypatch.setenv("HOME", str(tmp_path / "custom_home"))
        store = SQLiteStore()  # Default path
        assert store.path.is_file()
        store.close()
