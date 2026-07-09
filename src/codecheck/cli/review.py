"""Review command — run code review with optional auto-fix."""

import json
from pathlib import Path

import click

from codecheck.agent.loop import AgentLoop
from codecheck.config.loader import load_config
from codecheck.credentials.store import get_api_key
from codecheck.feedback.loop import FeedbackLoop
from codecheck.llm.deepseek_provider import DeepSeekProvider
from codecheck.llm.mock_provider import MockProvider
from codecheck.rules.engine import RuleEngine
from codecheck.tools.registry import ToolRegistry


def _collect_files(target_path: str, exclude_patterns: list[str]) -> list[str]:
    """Collect Python source files to review.

    Args:
        target_path: Path to file or directory to scan.
        exclude_patterns: Glob patterns to exclude.

    Returns:
        List of file paths to review.
    """
    target = Path(target_path).resolve()
    if target.is_file():
        return [str(target)]

    # Common source file extensions
    extensions = {".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp", ".h"}
    files: list[str] = []

    for ext in extensions:
        for f in target.rglob(f"*{ext}"):
            path_str = str(f)
            excluded = False
            for pattern in exclude_patterns:
                if f.match(pattern):
                    excluded = True
                    break
            if not excluded:
                files.append(path_str)

    return sorted(files)


def _get_llm_provider(config, api_key: str | None):
    """Create an LLM provider from config and API key.

    If no API key is available, returns a MockProvider for offline/demo use.
    """
    if api_key:
        return DeepSeekProvider(
            api_key=api_key,
            base_url=config.llm.base_url,
            model=config.llm.model,
        )
    # Fallback to mock provider for demo/testing
    return MockProvider()


def _format_issues_for_terminal(issues: list[dict]) -> str:
    """Format issues for colored terminal output.

    Severity colors:
        critical → red
        warning → yellow
        info → blue
    """
    if not issues:
        return ""

    severity_colors = {
        "critical": "red",
        "warning": "yellow",
        "info": "blue",
    }

    lines = ["\nIssues found:"]
    for i, issue in enumerate(issues, 1):
        sev = issue.get("severity", "info")
        color = severity_colors.get(sev, "white")
        rule_id = issue.get("rule_id", "unknown")
        file_path = issue.get("file", "?")
        line_num = issue.get("line", "?")
        message = issue.get("message", "No description")

        header = click.style(
            f"  [{sev.upper()}] {rule_id}", fg=color, bold=True
        )
        location = f"  {file_path}:{line_num}"
        lines.append(f"\n{i}. {header}")
        lines.append(location)
        lines.append(f"     {message}")

    return "\n".join(lines)


def _format_fix_report_for_terminal(fix_report) -> str:
    """Format a FixReport for terminal output."""

    lines = [
        "\nFix Report:",
        f"  Total issues: {fix_report.total_issues}",
        f"  Fixed: {click.style(str(fix_report.fixed), fg='green')}",
        f"  Needs manual: {click.style(str(fix_report.needs_manual), fg='yellow')}",
        f"  Skipped: {fix_report.skipped}",
    ]

    for fix in fix_report.fixes:
        if fix.status == "fixed":
            status = click.style("✓ FIXED", fg="green")
        elif fix.status == "needs_manual":
            status = click.style("⚠ NEEDS MANUAL", fg="yellow")
        else:
            status = click.style("○ SKIPPED", fg="white")
        lines.append(f"  {status} — {fix.issue_id} ({fix.attempts} attempt(s))")

    return "\n".join(lines)


def review_impl(
    path: str,
    diff: bool,
    fix: bool,
    max_rounds: int | None,
    output: str | None,
) -> int:
    """Core implementation of the review command.

    Returns exit code: 0=clean, 1=issues found, 2=needs manual, 3=error.
    """
    # Load configuration
    try:
        config = load_config(path)
    except Exception as e:
        click.echo(click.style(f"Error loading config: {e}", fg="red"), err=True)
        return 3

    # Apply CLI overrides
    if max_rounds is not None:
        config.review.max_fix_rounds = max_rounds
    if diff:
        config.review.diff_only = True

    # Get API key
    try:
        api_key = get_api_key()
    except Exception:
        api_key = None

    if api_key is None:
        click.echo(
            click.style(
                "Note: No API key configured. Running in mock/demo mode.\n"
                "  Set CODE_CHECK_API_KEY or run 'codecheck config --set-key' to use a real LLM.",
                fg="yellow",
            ),
            err=True,
        )

    # Create LLM provider
    llm = _get_llm_provider(config, api_key)

    # Create tool registry
    tool_registry = ToolRegistry()
    tool_registry.register_defaults()

    # Create rule engine
    try:
        rule_engine = RuleEngine(
            rules_path=config.rules.path if Path(config.rules.path).exists() else None,
            llm=llm,
        )
    except Exception as e:
        click.echo(
            click.style(f"Warning: Failed to load rules: {e}\nFalling back to built-in rules.", fg="yellow"),
            err=True,
        )
        rule_engine = RuleEngine(rules_path=None, llm=llm)

    # Collect files to review
    files = _collect_files(path, config.review.exclude_paths)
    if not files:
        click.echo("No files to review.")
        return 0

    click.echo(f"Reviewing {len(files)} file(s)...")

    # Run agent loop
    agent = AgentLoop(
        llm=llm,
        tool_registry=tool_registry,
        rule_engine=rule_engine,
        max_rounds=10,
    )

    # Scan each file via rule engine first, then run agent loop for context
    all_issues: list[dict] = []
    for file_path in files:
        click.echo(f"  Scanning: {file_path}")
        try:
            scan_issues = rule_engine.scan([file_path])
            for issue in scan_issues:
                all_issues.append({
                    "rule_id": issue.rule_id,
                    "file": issue.file,
                    "line": issue.line,
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "dual_confirmed": issue.dual_confirmed,
                })
        except Exception as e:
            click.echo(
                click.style(f"  Error scanning {file_path}: {e}", fg="red"),
                err=True,
            )

    # Run agent loop for richer analysis
    try:
        report = agent.run(path)
        if report.issues:
            for issue in report.issues:
                if issue not in all_issues:
                    all_issues.append(issue)
    except Exception as e:
        click.echo(
            click.style(f"Agent loop error: {e}", fg="red"), err=True
        )

    # Display issues
    if all_issues:
        click.echo(_format_issues_for_terminal(all_issues))
    else:
        click.echo(click.style("\n✓ No issues found.", fg="green"))

    # Auto-fix if requested
    fix_report = None
    if fix and all_issues:
        click.echo("\n--- Auto-fix mode ---")
        fb_loop = FeedbackLoop(
            llm=llm,
            max_rounds=config.review.max_fix_rounds,
            test_command=config.test.command,
        )
        fix_report = fb_loop.process(all_issues)
        click.echo(_format_fix_report_for_terminal(fix_report))

    # Write JSON output if requested
    if output:
        output_data = {
            "status": "complete",
            "total_issues": len(all_issues),
            "issues": all_issues,
        }
        if fix_report:
            output_data["fix_report"] = {
                "total": fix_report.total_issues,
                "fixed": fix_report.fixed,
                "needs_manual": fix_report.needs_manual,
                "skipped": fix_report.skipped,
                "details": [
                    {
                        "issue_id": fr.issue_id,
                        "status": fr.status,
                        "attempts": fr.attempts,
                        "final_diff": fr.final_diff,
                    }
                    for fr in fix_report.fixes
                ],
            }

        try:
            with open(output, "w", encoding="utf-8") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            click.echo(f"\nReport written to: {output}")
        except OSError as e:
            click.echo(
                click.style(f"Error writing output: {e}", fg="red"), err=True
            )
            return 3

    # Determine exit code
    if fix_report and fix_report.needs_manual > 0:
        return 2
    elif all_issues:
        return 1
    else:
        return 0
