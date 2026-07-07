"""Unit tests for ToolRegistry."""

import pytest

from codecheck.tools.base import Tool, ToolResult
from codecheck.tools.registry import ToolRegistry


class _FakeTool(Tool):
    """A simple tool for testing the registry."""

    name = "fake_tool"
    description = "A fake tool for testing."
    parameters = {
        "type": "object",
        "properties": {
            "value": {"type": "string"},
        },
        "required": ["value"],
    }

    def execute(self, **kwargs):
        return ToolResult(success=True, data=f"got: {kwargs.get('value', '')}")


class _FailingTool(Tool):
    """A tool that always fails."""

    name = "failing_tool"
    description = "Always fails."
    parameters = {"type": "object", "properties": {}, "required": []}

    def execute(self, **kwargs):
        raise RuntimeError("intentional failure")


class TestRegistry:
    """Test ToolRegistry core operations."""

    def test_register_and_get(self):
        registry = ToolRegistry()
        tool = _FakeTool()
        registry.register(tool)
        assert registry.get("fake_tool") is tool

    def test_get_nonexistent(self):
        registry = ToolRegistry()
        assert registry.get("nonexistent") is None

    def test_register_duplicate_raises(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        with pytest.raises(ValueError, match="already registered"):
            registry.register(_FakeTool())

    def test_unregister(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        registry.unregister("fake_tool")
        assert registry.get("fake_tool") is None

    def test_unregister_nonexistent_noop(self):
        registry = ToolRegistry()
        registry.unregister("nonexistent")  # should not raise

    def test_list_all(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        registry.register(_FailingTool())
        names = [t.name for t in registry.list_all()]
        assert "fake_tool" in names
        assert "failing_tool" in names

    def test_list_names(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        assert registry.list_names() == ["fake_tool"]

    def test_execute_success(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        result = registry.execute("fake_tool", value="hello")
        assert result.success
        assert "hello" in result.data

    def test_execute_unknown_tool(self):
        registry = ToolRegistry()
        result = registry.execute("nonexistent")
        assert not result.success
        assert "Unknown tool" in result.error

    def test_execute_tool_error(self):
        registry = ToolRegistry()
        registry.register(_FailingTool())
        result = registry.execute("failing_tool")
        assert not result.success
        assert "intentional failure" in result.error

    def test_to_openai_schema(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        schemas = registry.to_openai_schema()
        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "fake_tool"

    def test_to_openai_schema_multiple(self):
        registry = ToolRegistry()
        registry.register(_FakeTool())
        registry.register(_FailingTool())
        schemas = registry.to_openai_schema()
        assert len(schemas) == 2
