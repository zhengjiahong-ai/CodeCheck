"""Feedback loop — the deep dimension of CodeCheck.

Review → Fix → Test → Rollback → Retry → Converge.

This is the core mechanism that makes CodeCheck a harness, not just a prompt.
The entire loop is deterministic code — LLM is only used for fix generation.
"""

from codecheck.feedback.backup import backup_file_with_metadata, restore_file
from codecheck.feedback.reporter import FixAttempt, FixReport, SingleFixResult
from codecheck.feedback.verifier import run_lint, run_tests
from codecheck.llm.provider import LLMProvider
from codecheck.tools.file_tools import WriteFileTool

FIX_PROMPT_TEMPLATE = """You are fixing a code review issue. Here is the issue:

Rule: {rule_id}
Severity: {severity}
Message: {message}
File: {file_path}
Line: {line_number}

The code at this location:
```{language}
{code_context}
```

{failure_context}

Please provide a fix. Your response must be a JSON object with:
- "old_string": the exact code to replace
- "new_string": the replacement code
- "explanation": a brief explanation of the fix

Respond ONLY with the JSON object, no other text."""


class FeedbackLoop:
    """The feedback loop — auto-fix, verify, rollback, retry.

    This implements the deep dimension of CodeCheck:
    review → fix → test → rollback → retry → converge.

    Usage:
        loop = FeedbackLoop(llm, max_rounds=3)
        report = loop.process(issues, test_command="pytest")
    """

    def __init__(
        self,
        llm: LLMProvider,
        max_rounds: int = 3,
        test_command: str = "pytest",
        lint_command: str = "ruff check",
    ):
        """Initialize the feedback loop.

        Args:
            llm: LLM provider for generating fixes.
            max_rounds: Maximum fix attempts per issue.
            test_command: Command to run for test verification.
            lint_command: Command to run for lint verification.
        """
        self._llm = llm
        self._max_rounds = max_rounds
        self._test_command = test_command
        self._lint_command = lint_command
        self._write_tool = WriteFileTool()

    def process(self, issues: list[dict]) -> FixReport:
        """Process a list of issues through the feedback loop.

        Args:
            issues: List of issue dicts from the review report.
                    Each must have: rule_id, file, line, severity, message.

        Returns:
            FixReport with per-issue results.
        """
        report = FixReport(total_issues=len(issues))

        for issue in issues:
            result = self._process_single_issue(issue)
            report.fixes.append(result)

            if result.status == "fixed":
                report.fixed += 1
            elif result.status == "needs_manual":
                report.needs_manual += 1
            else:
                report.skipped += 1

        return report

    def _process_single_issue(self, issue: dict) -> SingleFixResult:
        """Process a single issue through fix attempts.

        Args:
            issue: Issue dict with rule_id, file, line, severity, message.

        Returns:
            SingleFixResult with the fix outcome.
        """
        issue_id = f"{issue['rule_id']}:{issue['file']}:{issue['line']}"
        result = SingleFixResult(issue_id=issue_id, status="skipped")

        file_path = issue.get("file", "")
        line_number = issue.get("line", 1)

        # Read the current file content
        try:
            with open(file_path, encoding="utf-8") as f:
                current_content = f.read()
        except (FileNotFoundError, PermissionError, OSError):
            result.status = "failed"
            return result

        # Get context around the issue line
        lines = current_content.splitlines()
        start = max(0, line_number - 5)
        end = min(len(lines), line_number + 4)
        code_context = "\n".join(lines[start:end])

        failure_context = ""
        previous_failures: list[FixAttempt] = []

        for attempt_round in range(1, self._max_rounds + 1):
            result.attempts = attempt_round

            # Generate fix via LLM
            fix_prompt = FIX_PROMPT_TEMPLATE.format(
                rule_id=issue.get("rule_id", "unknown"),
                severity=issue.get("severity", "warning"),
                message=issue.get("message", ""),
                file_path=file_path,
                line_number=line_number,
                language=_guess_language(file_path),
                code_context=code_context,
                failure_context=failure_context,
            )

            try:
                response = self._llm.chat([{"role": "user", "content": fix_prompt}])
                fix_data = _parse_fix_response(response.content)
            except Exception:
                continue

            old_string = fix_data.get("old_string", "")
            new_string = fix_data.get("new_string", "")

            if not old_string:
                continue

            # Backup the file
            try:
                backup_path = backup_file_with_metadata(file_path)
            except (FileNotFoundError, OSError):
                continue

            # Apply the fix
            apply_result = self._write_tool.execute(
                path=file_path, old_string=old_string, new_string=new_string
            )

            if not apply_result.success:
                # Fix application failed — old_string didn't match
                failure_context = (
                    "\nPrevious attempt failed to apply: old_string not found in file.\n"
                    "Re-read the file and regenerate the fix.\n"
                )
                continue

            # Verify with tests
            test_result = run_tests(command=self._test_command)
            lint_result = run_lint(command=self._lint_command)

            fix_attempt = FixAttempt(
                round=attempt_round,
                diff=f"{old_string} → {new_string}",
                test_result=test_result.stdout[:500] if test_result.stdout else test_result.stderr[:500],
                lint_result=lint_result.stdout[:500] if lint_result.stdout else lint_result.stderr[:500],
            )

            if test_result.passed and lint_result.passed:
                fix_attempt.success = True
                result.attempts_detail.append(fix_attempt)
                result.status = "fixed"
                result.final_diff = fix_attempt.diff
                return result

            # Fix failed — restore the file
            fix_attempt.failure_reason = (
                f"Tests: {'PASSED' if test_result.passed else 'FAILED'}, "
                f"Lint: {'PASSED' if lint_result.passed else 'FAILED'}"
            )
            result.attempts_detail.append(fix_attempt)
            previous_failures.append(fix_attempt)

            try:
                restore_file(backup_path)
            except (FileNotFoundError, OSError):
                pass

            # Build failure context for next attempt
            failure_parts = ["\nPrevious attempts failed:"]
            for pf in previous_failures:
                failure_parts.append(
                    f"- Round {pf.round}: {pf.failure_reason}\n"
                    f"  Test output: {pf.test_result[:200]}\n"
                    f"  Lint output: {pf.lint_result[:200]}"
                )
            failure_context = "\n".join(failure_parts)

        # Max rounds reached
        result.status = "needs_manual"
        return result


def _parse_fix_response(content: str | None) -> dict:
    """Parse a fix response from the LLM into a dict with old_string/new_string.

    Tries direct JSON parse, then code block extraction, then bracket matching.
    """
    import json
    import re

    if not content:
        return {}

    content = content.strip()

    # Try direct JSON
    try:
        result = json.loads(content)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # Try code block
    json_block = re.search(r"```(?:json)?\s*([\s\S]*?)```", content)
    if json_block:
        try:
            result = json.loads(json_block.group(1).strip())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    # Try bracket pattern
    obj_match = re.search(r"\{[\s\S]*\}", content)
    if obj_match:
        try:
            result = json.loads(obj_match.group())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    return {}


def _guess_language(file_path: str) -> str:
    """Guess the programming language from a file extension."""
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    mapping = {
        "py": "python", "js": "javascript", "ts": "typescript",
        "java": "java", "go": "go", "rs": "rust", "c": "c", "cpp": "c++",
        "h": "c", "rb": "ruby", "sh": "bash", "yaml": "yaml", "yml": "yaml",
        "toml": "toml", "json": "json",
    }
    return mapping.get(ext, "")
