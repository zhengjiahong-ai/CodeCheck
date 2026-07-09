"""Unit tests for file backup and restore."""

import pytest

from codecheck.feedback.backup import (
    backup_file,
    backup_file_with_metadata,
    restore_file,
)


class TestBackupRestore:
    """Test file backup and restore operations."""

    def test_backup_creates_file(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("original content\n")

        backup_path = backup_file(str(test_file))
        assert backup_path != str(test_file)
        assert open(backup_path).read() == "original content\n"

    def test_backup_preserves_content(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line 1\nline 2\nline 3\n")

        backup_path = backup_file(str(test_file))
        assert open(backup_path).read() == "line 1\nline 2\nline 3\n"

    def test_restore_after_modification(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("original\n")

        backup_path = backup_file_with_metadata(str(test_file))

        # Modify the file
        test_file.write_text("modified\n")
        assert test_file.read_text() == "modified\n"

        # Restore
        restore_file(backup_path)
        assert test_file.read_text() == "original\n"

    def test_backup_nonexistent_file_raises(self):
        with pytest.raises(FileNotFoundError):
            backup_file("/nonexistent/file.txt")

    def test_restore_nonexistent_backup_raises(self):
        with pytest.raises(FileNotFoundError):
            restore_file("/nonexistent/backup.txt")

    def test_backup_with_metadata_writes_origin(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("content\n")

        backup_path = backup_file_with_metadata(str(test_file))
        # The .origin file should exist in the backup directory
        backup_dir = __import__("pathlib").Path(backup_path).parent
        origin_file = backup_dir / ".test.py.origin"
        assert origin_file.is_file()
        assert origin_file.read_text() == str(test_file.resolve())
