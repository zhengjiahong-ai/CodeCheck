"""Smoke tests for CLI entry point."""

from click.testing import CliRunner
from codecheck.cli.main import main


def test_cli_help():
    """Verify CLI --help works and shows all subcommands."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "CodeCheck" in result.output
    assert "review" in result.output
    assert "config" in result.output
    assert "install-hook" in result.output
    assert "uninstall-hook" in result.output


def test_cli_version():
    """Verify --version flag works."""
    runner = CliRunner()
    result = runner.invoke(main, ["--version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_review_help():
    """Verify review subcommand has help."""
    runner = CliRunner()
    result = runner.invoke(main, ["review", "--help"])
    assert result.exit_code == 0
    assert "--diff" in result.output
    assert "--fix" in result.output
    assert "--max-rounds" in result.output
    assert "--output" in result.output


def test_config_help():
    """Verify config subcommand has help."""
    runner = CliRunner()
    result = runner.invoke(main, ["config", "--help"])
    assert result.exit_code == 0
    assert "--status" in result.output
    assert "--set-key" in result.output
    assert "--clear-key" in result.output


def test_review_empty_dir():
    """Verify review on empty path returns without crashing."""
    runner = CliRunner()
    result = runner.invoke(main, ["review", "."])
    assert result.exit_code == 0