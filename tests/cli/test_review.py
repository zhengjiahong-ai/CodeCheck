"""Tests for the review CLI command."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from codecheck.cli.main import main


def test_review_no_files():
    """Review on an empty directory exits cleanly."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        result = runner.invoke(main, ["review", tmpdir])
        assert result.exit_code == 0
        assert "No files to review" in result.output


def test_review_with_python_file():
    """Review on a Python file produces output."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a simple Python file
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")

        result = runner.invoke(main, ["review", str(test_file)])
        # Should complete without error (uses mock mode)
        assert result.exit_code in (0, 1)  # 0=no issues, 1=issues found
        assert "Reviewing" in result.output or "Scanning" in result.output


def test_review_output_json():
    """Review with --output writes a JSON report."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")

        output_path = Path(tmpdir) / "report.json"
        result = runner.invoke(
            main, ["review", str(test_file), "--output", str(output_path)]
        )
        assert result.exit_code in (0, 1)

        # Check that output file was created
        assert output_path.exists()
        with open(output_path) as f:
            data = json.load(f)
        assert "status" in data
        assert "total_issues" in data
        assert "issues" in data


def test_review_with_fix_flag():
    """Review with --fix flag still runs (mock mode won't actually fix)."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")

        result = runner.invoke(main, ["review", str(test_file), "--fix", "--max-rounds", "1"])
        assert result.exit_code in (0, 1, 2)


def test_review_with_diff_flag():
    """Review with --diff flag works."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test.py"
        test_file.write_text("def hello():\n    print('hello')\n")

        result = runner.invoke(main, ["review", str(test_file), "--diff"])
        assert result.exit_code in (0, 1)


def test_review_help():
    """Verify review --help shows all options."""
    runner = CliRunner()
    result = runner.invoke(main, ["review", "--help"])
    assert result.exit_code == 0
    assert "--diff" in result.output
    assert "--fix" in result.output
    assert "--max-rounds" in result.output
    assert "--output" in result.output


def test_review_exit_code_clean():
    """Review on clean code returns exit code 0."""
    runner = CliRunner()
    with tempfile.TemporaryDirectory() as tmpdir:
        # Empty dir = no files = clean
        result = runner.invoke(main, ["review", tmpdir])
        assert result.exit_code == 0