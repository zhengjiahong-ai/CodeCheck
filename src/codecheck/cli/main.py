"""CodeCheck CLI — AI-powered code review harness."""

import click


@click.group()
@click.version_option(version="0.1.0", prog_name="codecheck")
def main():
    """CodeCheck — AI-powered code review harness.

    Automatically review code, fix issues, and verify fixes with test feedback.
    """
    pass


@main.command()
@click.argument("path", default=".")
@click.option("--diff", is_flag=True, help="Only review changed files (git diff)")
@click.option("--fix", is_flag=True, help="Auto-fix issues found during review")
@click.option("--max-rounds", type=int, help="Max fix attempts per issue (default: 3)")
@click.option("--output", type=click.Path(), help="Write JSON report to OUTPUT file")
def review(path, diff, fix, max_rounds, output):
    """Run code review on PATH.

    Scans source files for issues using deterministic rules and LLM analysis.
    With --fix, automatically repairs issues and verifies with test suite.
    """
    from codecheck.cli.review import review_impl

    exit_code = review_impl(
        path=path,
        diff=diff,
        fix=fix,
        max_rounds=max_rounds,
        output=output,
    )
    raise SystemExit(exit_code)


@main.command()
@click.option("--status", is_flag=True, help="Show credential status")
@click.option("--set-key", is_flag=True, help="Set API key securely")
@click.option("--clear-key", is_flag=True, help="Clear stored API key")
def config(status, set_key, clear_key):
    """Manage credentials and configuration.

    Store API keys securely using encrypted storage.
    """
    from codecheck.cli.config_cmd import config as config_cmd

    config_cmd(status=status, set_key=set_key, clear_key=clear_key)


@main.command()
def install_hook():
    """Install git pre-commit hook.

    Installs a pre-commit hook that runs CodeCheck on staged changes
    before each commit.
    """
    # T12 实现
    pass


@main.command()
def uninstall_hook():
    """Remove git pre-commit hook installed by CodeCheck."""
    # T12 实现
    pass
