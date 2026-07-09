"""Verifier — run tests and lint checks to validate fixes."""

import subprocess
from dataclasses import dataclass


@dataclass
class TestResult:
    """Result of running a test command."""

    passed: bool
    returncode: int
    stdout: str
    stderr: str
    command: str


@dataclass
class LintResult:
    """Result of running a lint command."""

    passed: bool
    returncode: int
    stdout: str
    stderr: str
    command: str


def run_tests(command: str = "pytest", timeout: int = 120, cwd: str | None = None) -> TestResult:
    """Run the project's test suite.

    Args:
        command: The test command to run.
        timeout: Timeout in seconds.
        cwd: Working directory.

    Returns:
        TestResult with pass/fail status and output.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            text=True,
        )
        return TestResult(
            passed=(result.returncode == 0),
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            command=command,
        )
    except subprocess.TimeoutExpired:
        return TestResult(
            passed=False,
            returncode=-1,
            stdout="",
            stderr=f"Test command timed out after {timeout}s",
            command=command,
        )
    except Exception as e:
        return TestResult(
            passed=False,
            returncode=-1,
            stdout="",
            stderr=f"Failed to run test command: {e}",
            command=command,
        )


def run_lint(command: str = "ruff check", timeout: int = 120, cwd: str | None = None) -> LintResult:
    """Run a lint/type check on the project.

    Args:
        command: The lint command to run.
        timeout: Timeout in seconds.
        cwd: Working directory.

    Returns:
        LintResult with pass/fail status and output.
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            text=True,
        )
        return LintResult(
            passed=(result.returncode == 0),
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            command=command,
        )
    except subprocess.TimeoutExpired:
        return LintResult(
            passed=False,
            returncode=-1,
            stdout="",
            stderr=f"Lint command timed out after {timeout}s",
            command=command,
        )
    except Exception as e:
        return LintResult(
            passed=False,
            returncode=-1,
            stdout="",
            stderr=f"Failed to run lint command: {e}",
            command=command,
        )
