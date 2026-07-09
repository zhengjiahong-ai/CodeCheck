"""Unit tests for test/lint verifier."""

from codecheck.feedback.verifier import run_lint, run_tests


class TestRunTests:
    """Test test execution verification."""

    def test_run_pytest_version(self):
        result = run_tests(command="pytest --version")
        assert result.passed
        assert "pytest" in result.stdout.lower()

    def test_run_failing_command(self):
        result = run_tests(command="pytest --nonexistent-flag")
        assert not result.passed

    def test_run_timeout(self):
        result = run_tests(command="sleep 10", timeout=1)
        assert not result.passed
        assert "timed out" in result.stderr.lower()

    def test_result_has_command(self):
        result = run_tests(command="echo test")
        assert result.command == "echo test"


class TestRunLint:
    """Test lint execution verification."""

    def test_run_ruff_version(self):
        result = run_lint(command="ruff --version")
        assert result.passed
        assert "ruff" in result.stdout.lower()

    def test_run_failing_lint(self):
        result = run_lint(command="ruff --nonexistent-flag")
        assert not result.passed

    def test_lint_timeout(self):
        result = run_lint(command="sleep 10", timeout=1)
        assert not result.passed
        assert "timed out" in result.stderr.lower()
