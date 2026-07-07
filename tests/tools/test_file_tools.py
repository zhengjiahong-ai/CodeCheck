"""Unit tests for file tools (ReadFileTool, WriteFileTool)."""

from codecheck.tools.file_tools import ReadFileTool, WriteFileTool


class TestReadFileTool:
    """Test ReadFileTool behavior."""

    def test_read_existing_file(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("line 1\nline 2\nline 3\n")
        tool = ReadFileTool()
        result = tool.execute(path=str(test_file))
        assert result.success
        assert "line 1" in result.data
        assert "line 2" in result.data

    def test_read_file_not_found(self):
        tool = ReadFileTool()
        result = tool.execute(path="/nonexistent/file.txt")
        assert not result.success
        assert "not found" in result.error

    def test_read_with_line_range(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("a\nb\nc\nd\ne\n")
        tool = ReadFileTool()
        result = tool.execute(path=str(test_file), start_line=2, end_line=4)
        assert result.success
        assert "b" in result.data
        assert "c" in result.data
        assert "d" in result.data
        assert "a" not in result.data
        assert "e" not in result.data

    def test_read_start_line_past_end(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("a\nb\n")
        tool = ReadFileTool()
        result = tool.execute(path=str(test_file), start_line=10)
        assert not result.success
        assert "exceeds" in result.error

    def test_read_with_line_numbers(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("hello\nworld\n")
        tool = ReadFileTool()
        result = tool.execute(path=str(test_file))
        assert result.success
        assert "1|" in result.data
        assert "2|" in result.data


class TestWriteFileTool:
    """Test WriteFileTool behavior."""

    def test_write_single_replacement(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1\n")
        tool = WriteFileTool()
        result = tool.execute(
            path=str(test_file),
            old_string="x = 1",
            new_string="x = 2",
        )
        assert result.success
        assert test_file.read_text() == "x = 2\n"

    def test_write_old_string_not_found(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("x = 1\n")
        tool = WriteFileTool()
        result = tool.execute(
            path=str(test_file),
            old_string="not in file",
            new_string="replacement",
        )
        assert not result.success
        assert "not found" in result.error
        # File should be unchanged
        assert test_file.read_text() == "x = 1\n"

    def test_write_duplicate_old_string(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("dup\nmiddle\ndup\n")
        tool = WriteFileTool()
        result = tool.execute(
            path=str(test_file),
            old_string="dup",
            new_string="new",
        )
        assert not result.success
        assert "appears 2 times" in result.error
        # File should be unchanged
        assert test_file.read_text() == "dup\nmiddle\ndup\n"

    def test_write_file_not_found(self, tmp_path):
        tool = WriteFileTool()
        result = tool.execute(
            path=str(tmp_path / "nonexistent.py"),
            old_string="a",
            new_string="b",
        )
        assert not result.success
        assert "not found" in result.error

    def test_write_unicode_content(self, tmp_path):
        test_file = tmp_path / "test.py"
        test_file.write_text("# 中文注释\n")
        tool = WriteFileTool()
        result = tool.execute(
            path=str(test_file),
            old_string="# 中文注释",
            new_string="# English comment",
        )
        assert result.success
        assert "English comment" in test_file.read_text()
