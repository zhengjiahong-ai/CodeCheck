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
@click.option("--force", is_flag=True, help="Overwrite existing hook even if not CodeCheck's")
def install_hook(force):
    """Install git pre-commit hook.

    Installs a pre-commit hook that runs CodeCheck on staged changes
    before each commit. The hook will block commits with issues that
    cannot be auto-fixed.
    """
    import click

    from codecheck.hooks.pre_commit import install_hook as do_install

    try:
        path = do_install(force=force)
        click.echo(click.style(f"✓ Pre-commit hook installed at: {path}", fg="green"))
        click.echo("  CodeCheck will now run automatically before each commit.")
    except FileNotFoundError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        raise SystemExit(1) from e
    except FileExistsError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        raise SystemExit(1) from e


@main.command()
def uninstall_hook():
    """Remove git pre-commit hook installed by CodeCheck."""
    import click

    from codecheck.hooks.pre_commit import (
        is_hook_installed,
    )
    from codecheck.hooks.pre_commit import (
        uninstall_hook as do_uninstall,
    )

    if not is_hook_installed():
        click.echo(click.style("No CodeCheck pre-commit hook is installed.", fg="yellow"))
        return

    removed = do_uninstall()
    if removed:
        click.echo(click.style("✓ Pre-commit hook removed.", fg="green"))
    else:
        click.echo(click.style("Error: Failed to remove hook.", fg="red"), err=True)
        raise SystemExit(1)
