"""Unit tests for shell tools (RunShellTool, RunTestTool, RunLintTool)."""

from codecheck.tools.shell_tools import RunLintTool, RunShellTool, RunTestTool


class TestRunShellTool:
    """Test RunShellTool behavior."""

    def test_run_echo(self):
        tool = RunShellTool()
        result = tool.execute(command="echo hello")
        assert result.success
        assert "hello" in result.data

    def test_run_failing_command(self):
        tool = RunShellTool()
        result = tool.execute(command="exit 1")
        assert not result.success
        assert "exited with code" in result.error

    def test_run_command_not_found(self):
        tool = RunShellTool()
        result = tool.execute(command="nonexistent_command_xyz")
        assert not result.success

    def test_run_with_timeout(self):
        tool = RunShellTool()
        result = tool.execute(command="sleep 10", timeout=1)
        assert not result.success
        assert "timed out" in result.error.lower() or "timed out" in result.data.lower()


class TestRunTestTool:
    """Test RunTestTool behavior."""

    def test_run_pytest_help(self):
        """Run pytest --version to verify it works (not a real test suite)."""
        tool = RunTestTool()
        result = tool.execute(command="pytest --version")
        assert result.success
        assert "pytest" in result.data.lower()

    def test_run_failing_test(self):
        """Run a command that fails to test failure handling."""
        tool = RunTestTool()
        result = tool.execute(command="pytest --nonexistent-flag")
        assert not result.success


class TestRunLintTool:
    """Test RunLintTool behavior."""

    def test_run_ruff_version(self):
        tool = RunLintTool()
        result = tool.execute(command="ruff --version")
        assert result.success
        assert "ruff" in result.data.lower()

    def test_run_ruff_check_on_empty_dir(self, tmp_path):
        """Run ruff check on an empty temp directory."""
        tool = RunLintTool()
        result = tool.execute(command="ruff check", path=str(tmp_path))
        assert result.success  # Empty dir has no issues

    def test_run_lint_with_invalid_command(self):
        tool = RunLintTool()
        result = tool.execute(command="nonexistent_linter_xyz")
        assert not result.success
