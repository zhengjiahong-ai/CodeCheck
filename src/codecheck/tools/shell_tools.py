"""Shell tools — run tests, shell commands, and lint checks."""

import subprocess

from codecheck.tools.base import Tool, ToolResult

# Maximum output length to prevent context overflow
MAX_OUTPUT_BYTES = 50_000


def _run_command(
    command: str | list[str],
    timeout: int = 120,
    cwd: str | None = None,
) -> tuple[int, str, str]:
    """Run a shell command and return (returncode, stdout, stderr).

    Args:
        command: The command to run (string or list).
        timeout: Timeout in seconds.
        cwd: Working directory for the command.

    Returns:
        Tuple of (returncode, stdout, stderr).
    """
    if isinstance(command, str):
        args = command
        shell = True
    else:
        args = command
        shell = False

    try:
        result = subprocess.run(
            args,
            shell=shell,
            capture_output=True,
            timeout=timeout,
            cwd=cwd,
            text=True,
        )
    except subprocess.TimeoutExpired:
        return (-1, "", f"Command timed out after {timeout}s")
    except FileNotFoundError:
        return (-1, "", f"Command not found: {args[0] if isinstance(args, list) else args.split()[0]}")
    except Exception as e:
        return (-1, "", f"Failed to run command: {e}")

    stdout = result.stdout
    stderr = result.stderr

    # Truncate output to prevent context overflow
    if len(stdout.encode("utf-8")) > MAX_OUTPUT_BYTES:
        stdout = stdout[:MAX_OUTPUT_BYTES] + "\n... [output truncated]"
    if len(stderr.encode("utf-8")) > MAX_OUTPUT_BYTES:
        stderr = stderr[:MAX_OUTPUT_BYTES] + "\n... [output truncated]"

    return (result.returncode, stdout, stderr)


class RunShellTool(Tool):
    """Execute an arbitrary shell command.

    ⚠️ High-risk tool — requires guardrail confirmation.
    """

    name = "run_shell"
    description = (
        "Execute a shell command. Output is captured and truncated if too large. "
        "Commands are run with a timeout to prevent hanging."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 120).",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the command.",
            },
        },
        "required": ["command"],
    }

    def execute(
        self,
        command: str,
        timeout: int = 120,
        cwd: str | None = None,
    ) -> ToolResult:
        returncode, stdout, stderr = _run_command(command, timeout=timeout, cwd=cwd)

        output_parts = []
        if stdout:
            output_parts.append(f"[stdout]\n{stdout}")
        if stderr:
            output_parts.append(f"[stderr]\n{stderr}")

        output = "\n".join(output_parts) if output_parts else "(no output)"

        if returncode == 0:
            return ToolResult(success=True, data=output)
        return ToolResult(
            success=False,
            data=output,
            error=f"Command exited with code {returncode}",
        )


class RunTestTool(Tool):
    """Run the project's test suite."""

    name = "run_test"
    description = (
        "Run the project's test command (e.g., pytest). "
        "Returns the test output and exit code."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The test command to run (default: 'pytest').",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 120).",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory (default: project root).",
            },
        },
        "required": [],
    }

    def execute(
        self,
        command: str = "pytest",
        timeout: int = 120,
        cwd: str | None = None,
    ) -> ToolResult:
        returncode, stdout, stderr = _run_command(command, timeout=timeout, cwd=cwd)

        output_parts = []
        if stdout:
            output_parts.append(f"[stdout]\n{stdout}")
        if stderr:
            output_parts.append(f"[stderr]\n{stderr}")

        output = "\n".join(output_parts) if output_parts else "(no output)"

        if returncode == 0:
            return ToolResult(success=True, data=output)
        return ToolResult(
            success=False,
            data=output,
            error=f"Tests failed with exit code {returncode}",
        )


class RunLintTool(Tool):
    """Run a lint/type check on the project."""

    name = "run_lint"
    description = (
        "Run a linter or type checker on the project. "
        "Default command is 'ruff check'."
    )
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The lint command to run (default: 'ruff check').",
            },
            "path": {
                "type": "string",
                "description": "Path to run lint on (default: entire project).",
            },
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds (default: 120).",
            },
            "cwd": {
                "type": "string",
                "description": "Working directory for the command.",
            },
        },
        "required": [],
    }

    def execute(
        self,
        command: str = "ruff check",
        path: str | None = None,
        timeout: int = 120,
        cwd: str | None = None,
    ) -> ToolResult:
        full_command = f"{command} {path}" if path else command
        returncode, stdout, stderr = _run_command(full_command, timeout=timeout, cwd=cwd)

        output_parts = []
        if stdout:
            output_parts.append(f"[stdout]\n{stdout}")
        if stderr:
            output_parts.append(f"[stderr]\n{stderr}")

        output = "\n".join(output_parts) if output_parts else "(no output)"

        if returncode == 0:
            return ToolResult(success=True, data=output)
        return ToolResult(
            success=False,
            data=output,
            error=f"Lint check failed with exit code {returncode}",
        )
