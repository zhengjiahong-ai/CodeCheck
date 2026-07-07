"""Unit tests for governance guardrails — deterministic, no LLM needed."""


from codecheck.guardrails.guard import (
    DEFAULT_PERMISSIONS,
    Action,
    GuardResult,
    PermissionLevel,
    guardrail,
)


class TestPermissionLevel:
    """Test PermissionLevel enum."""

    def test_levels(self):
        assert PermissionLevel.AUTO.value == "auto"
        assert PermissionLevel.CONFIRM.value == "confirm"
        assert PermissionLevel.FORBIDDEN.value == "forbidden"


class TestAutoActions:
    """Test auto-approved actions (read-only)."""

    def test_read_file_auto(self):
        result = guardrail(Action("read_file", {"path": "test.py"}))
        assert result.allowed is True
        assert result.require_confirm is False

    def test_git_diff_auto(self):
        result = guardrail(Action("git_diff"))
        assert result.allowed is True
        assert result.require_confirm is False

    def test_git_log_auto(self):
        result = guardrail(Action("git_log", {"max_count": 5}))
        assert result.allowed is True
        assert result.require_confirm is False

    def test_git_blame_auto(self):
        result = guardrail(Action("git_blame", {"path": "src/main.py"}))
        assert result.allowed is True
        assert result.require_confirm is False


class TestConfirmActions:
    """Test actions that require human confirmation."""

    def test_write_file_confirm(self):
        result = guardrail(Action("write_file", {"path": "x.py", "old_string": "a", "new_string": "b"}))
        assert result.allowed is True
        assert result.require_confirm is True

    def test_run_shell_confirm(self):
        result = guardrail(Action("run_shell", {"command": "ls"}))
        assert result.allowed is True
        assert result.require_confirm is True

    def test_run_test_confirm(self):
        result = guardrail(Action("run_test", {"command": "pytest"}))
        assert result.allowed is True
        assert result.require_confirm is True

    def test_git_commit_confirm(self):
        result = guardrail(Action("git_commit", {"message": "fix"}))
        assert result.allowed is True
        assert result.require_confirm is True


class TestForbiddenActions:
    """Test forbidden actions."""

    def test_git_push_forbidden(self):
        result = guardrail(Action("git_push"))
        assert result.allowed is False
        assert "forbidden" in result.reason.lower()


class TestUnknownActions:
    """Test unknown tools (whitelist principle — deny by default)."""

    def test_unknown_tool_denied(self):
        result = guardrail(Action("unknown_tool_xyz"))
        assert result.allowed is False
        assert "unknown" in result.reason.lower()

    def test_arbitrary_tool_denied(self):
        result = guardrail(Action("rm_rf"))
        assert result.allowed is False


class TestCustomPermissions:
    """Test custom permission overrides."""

    def test_custom_allows_new_tool(self):
        custom = {**DEFAULT_PERMISSIONS, "my_custom_tool": PermissionLevel.AUTO}
        result = guardrail(Action("my_custom_tool"), permissions=custom)
        assert result.allowed is True
        assert result.require_confirm is False

    def test_custom_forbids_tool(self):
        custom = {**DEFAULT_PERMISSIONS, "write_file": PermissionLevel.FORBIDDEN}
        result = guardrail(Action("write_file"), permissions=custom)
        assert result.allowed is False

    def test_custom_empty_permissions(self):
        """Empty permissions → all tools denied."""
        result = guardrail(Action("read_file"), permissions={})
        assert result.allowed is False


class TestGuardResult:
    """Test GuardResult dataclass."""

    def test_auto_result(self):
        result = GuardResult(allowed=True, require_confirm=False, reason="auto")
        assert result.allowed is True
        assert result.require_confirm is False

    def test_confirm_result(self):
        result = GuardResult(allowed=True, require_confirm=True, reason="needs confirm")
        assert result.require_confirm is True

    def test_forbidden_result(self):
        result = GuardResult(allowed=False, reason="forbidden")
        assert result.allowed is False
        assert result.require_confirm is False


class TestAction:
    """Test Action dataclass."""

    def test_action_creation(self):
        action = Action("read_file", {"path": "test.py"})
        assert action.tool_name == "read_file"
        assert action.parameters == {"path": "test.py"}

    def test_action_default_params(self):
        action = Action("git_diff")
        assert action.parameters == {}
