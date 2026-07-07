"""Git tools — diff, log, and blame operations."""

import subprocess

from codecheck.tools.base import Tool, ToolResult


def _run_git(args: list[str], cwd: str | None = None, timeout: int = 30) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            text=True,
        )
        return (result.returncode, result.stdout, result.stderr)
    except subprocess.TimeoutExpired:
        return (-1, "", "git command timed out")
    except FileNotFoundError:
        return (-1, "", "git is not installed or not found in PATH")
    except Exception as e:
        return (-1, "", f"Failed to run git: {e}")


class GitDiffTool(Tool):
    """Get the git diff for the current working tree."""

    name = "git_diff"
    description = (
        "Get the git diff for the current working tree. "
        "Shows changes between the working tree and HEAD (or --staged)."
    )
    parameters = {
        "type": "object",
        "properties": {
            "staged": {
                "type": "boolean",
                "description": "If true, show staged changes only.",
            },
            "target_branch": {
                "type": "string",
                "description": "Compare against this branch instead of HEAD.",
            },
            "path": {
                "type": "string",
                "description": "Limit diff to this file or directory.",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (default: current).",
            },
        },
        "required": [],
    }

    def execute(
        self,
        staged: bool = False,
        target_branch: str | None = None,
        path: str | None = None,
        cwd: str | None = None,
    ) -> ToolResult:
        args = ["diff", "--unified=5"]
        if staged:
            args.append("--staged")
        if target_branch:
            args.append(target_branch)
        if path:
            args.append("--")
            args.append(path)

        returncode, stdout, stderr = _run_git(args, cwd=cwd)

        if returncode != 0 and stderr:
            # Not in a git repo is a common case
            if "not a git repository" in stderr.lower():
                return ToolResult(
                    success=False,
                    error="Not in a git repository. git_diff requires a git workspace.",
                )
            return ToolResult(
                success=False,
                data=stdout or "(no output)",
                error=f"git diff failed: {stderr}",
            )

        if not stdout.strip():
            return ToolResult(success=True, data="No changes (working tree clean).")

        return ToolResult(success=True, data=stdout)


class GitLogTool(Tool):
    """View git commit history."""

    name = "git_log"
    description = "View git commit history for a file or directory."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Limit log to this file or directory.",
            },
            "max_count": {
                "type": "integer",
                "description": "Maximum number of commits to show (default: 10).",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (default: current).",
            },
        },
        "required": [],
    }

    def execute(
        self,
        path: str | None = None,
        max_count: int = 10,
        cwd: str | None = None,
    ) -> ToolResult:
        args = ["log", f"--max-count={max_count}", "--oneline"]
        if path:
            args.append("--")
            args.append(path)

        returncode, stdout, stderr = _run_git(args, cwd=cwd)

        if returncode != 0 and stderr:
            if "not a git repository" in stderr.lower():
                return ToolResult(
                    success=False,
                    error="Not in a git repository.",
                )
            return ToolResult(
                success=False,
                data=stdout or "(no output)",
                error=f"git log failed: {stderr}",
            )

        if not stdout.strip():
            return ToolResult(success=True, data="No commits found.")

        return ToolResult(success=True, data=stdout)


class GitBlameTool(Tool):
    """View line-by-line authorship information."""

    name = "git_blame"
    description = "Show who last modified each line in a file."
    parameters = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the file to blame.",
            },
            "start_line": {
                "type": "integer",
                "description": "First line to show (1-indexed).",
            },
            "end_line": {
                "type": "integer",
                "description": "Last line to show (1-indexed).",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (default: current).",
            },
        },
        "required": ["path"],
    }

    def execute(
        self,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
        cwd: str | None = None,
    ) -> ToolResult:
        args = ["blame"]
        if start_line is not None and end_line is not None:
            args.append(f"-L{start_line},{end_line}")
        elif start_line is not None:
            args.append(f"-L{start_line},")
        args.append("--")
        args.append(path)

        returncode, stdout, stderr = _run_git(args, cwd=cwd)

        if returncode != 0 and stderr:
            if "not a git repository" in stderr.lower():
                return ToolResult(
                    success=False,
                    error="Not in a git repository.",
                )
            return ToolResult(
                success=False,
                data=stdout or "(no output)",
                error=f"git blame failed: {stderr}",
            )

        if not stdout.strip():
            return ToolResult(success=True, data="No blame information available.")

        return ToolResult(success=True, data=stdout)
