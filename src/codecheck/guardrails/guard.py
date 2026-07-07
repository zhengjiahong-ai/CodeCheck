"""Governance guardrails — permission matrix and HITL confirmation.

The guardrail is a deterministic code mechanism — it does not rely on LLM
judgment. Every tool action is checked against a permission matrix before
execution.

Design (from SPEC §3.6):
    - AUTO: read_file, search_code, git_diff, git_log, git_blame
    - CONFIRM: write_file, run_test, run_shell, run_lint, git_commit, delete_file
    - FORBIDDEN: git_push, install_deps
    - Unknown tools → FORBIDDEN (whitelist principle)
"""

from dataclasses import dataclass, field
from enum import Enum


class PermissionLevel(str, Enum):
    """Permission level for a tool action."""

    AUTO = "auto"  # Execute without confirmation
    CONFIRM = "confirm"  # Require human confirmation
    FORBIDDEN = "forbidden"  # Never allowed


@dataclass
class Action:
    """A tool action to be checked by the guardrail.

    Attributes:
        tool_name: The name of the tool being invoked.
        parameters: The tool's parameters dict.
    """

    tool_name: str
    parameters: dict = field(default_factory=dict)


@dataclass
class GuardResult:
    """Result of a guardrail check.

    Attributes:
        allowed: Whether the action can proceed.
        require_confirm: Whether human confirmation is needed.
        reason: Human-readable explanation.
    """

    allowed: bool
    require_confirm: bool = False
    reason: str = ""


# ── Permission Matrix ──────────────────────────────────────────────────────

# Default permission matrix per SPEC §3.6
DEFAULT_PERMISSIONS: dict[str, PermissionLevel] = {
    # Read-only — auto
    "read_file": PermissionLevel.AUTO,
    "search_code": PermissionLevel.AUTO,
    "git_diff": PermissionLevel.AUTO,
    "git_log": PermissionLevel.AUTO,
    "git_blame": PermissionLevel.AUTO,
    # Write/shell — confirm
    "write_file": PermissionLevel.CONFIRM,
    "run_test": PermissionLevel.CONFIRM,
    "run_shell": PermissionLevel.CONFIRM,
    "run_lint": PermissionLevel.CONFIRM,
    "git_commit": PermissionLevel.CONFIRM,
    "delete_file": PermissionLevel.CONFIRM,
    "install_deps": PermissionLevel.CONFIRM,
    # Push — forbidden
    "git_push": PermissionLevel.FORBIDDEN,
}


def guardrail(action: Action, permissions: dict | None = None) -> GuardResult:
    """Check an action against the permission matrix.

    This is a deterministic function — no LLM, no network, no randomness.
    Unknown tools are denied by default (whitelist principle).

    Args:
        action: The Action to check.
        permissions: Optional custom permission matrix. Uses DEFAULT_PERMISSIONS
                     if not provided.

    Returns:
        GuardResult with allowed/require_confirm/reason.
    """
    if permissions is None:
        permissions = DEFAULT_PERMISSIONS

    level = permissions.get(action.tool_name)

    if level is None:
        # Unknown tool — deny by default (whitelist principle)
        return GuardResult(
            allowed=False,
            reason=f"Unknown tool '{action.tool_name}' is not in the permission matrix. "
            "All tool actions must be explicitly registered.",
        )

    if level == PermissionLevel.FORBIDDEN:
        return GuardResult(
            allowed=False,
            reason=f"Action '{action.tool_name}' is forbidden by policy.",
        )

    if level == PermissionLevel.CONFIRM:
        return GuardResult(
            allowed=True,
            require_confirm=True,
            reason=f"Action '{action.tool_name}' requires human confirmation.",
        )

    # AUTO
    return GuardResult(
        allowed=True,
        require_confirm=False,
        reason=f"Action '{action.tool_name}' is auto-approved.",
    )
