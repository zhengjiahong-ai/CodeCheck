"""Tool registry — register, lookup, and dispatch tools."""

from codecheck.tools.base import Tool, ToolResult


class ToolRegistry:
    """Central registry for all CodeCheck tools.

    Tools are registered by name and can be looked up for execution
    or for generating OpenAI function-calling schemas.

    Usage:
        registry = ToolRegistry()
        registry.register(ReadFileTool())
        tool = registry.get("read_file")
        result = registry.execute("read_file", path="src/main.py")
    """

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """Register a tool instance.

        Raises:
            ValueError: If a tool with the same name is already registered.
        """
        if tool.name in self._tools:
            raise ValueError(
                f"Tool '{tool.name}' is already registered. "
                "Use unregister() first to replace it."
            )
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Remove a tool by name. No-op if not registered."""
        self._tools.pop(name, None)

    def get(self, name: str) -> Tool | None:
        """Look up a tool by name. Returns None if not found."""
        return self._tools.get(name)

    def list_all(self) -> list[Tool]:
        """Return all registered tools."""
        return list(self._tools.values())

    def list_names(self) -> list[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    def to_openai_schema(self) -> list[dict]:
        """Return all tools as OpenAI function-calling definitions."""
        return [tool.to_openai_function() for tool in self._tools.values()]

    def execute(self, name: str, **kwargs) -> ToolResult:
        """Look up and execute a tool by name.

        Args:
            name: The tool name to execute.
            **kwargs: Arguments passed to the tool's execute() method.

        Returns:
            ToolResult from the tool execution.

        Raises:
            KeyError: If no tool is registered with the given name.
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: '{name}'. Available tools: {list(self._tools.keys())}",
            )
        try:
            return tool.execute(**kwargs)
        except TypeError as e:
            return ToolResult(
                success=False,
                error=f"Invalid arguments for tool '{name}': {e}",
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Tool '{name}' execution failed: {e}",
            )
