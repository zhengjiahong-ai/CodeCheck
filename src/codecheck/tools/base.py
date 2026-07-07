"""Tool system — abstract base classes and result types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ToolResult:
    """Standardized result from any tool execution.

    Attributes:
        success: Whether the tool call succeeded.
        data: The output data on success (e.g., file content, stdout).
        error: Error message on failure.
    """

    success: bool
    data: str | None = None
    error: str | None = None


class Tool(ABC):
    """Abstract base class for all CodeCheck tools.

    Each tool declares its name, description, and a JSON Schema
    for its parameters. The execute() method performs the actual work.

    Subclasses must set name, description, and parameters as class
    attributes or instance attributes in __init__.
    """

    name: str
    description: str
    parameters: dict  # JSON Schema for the tool's arguments

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with the given keyword arguments.

        Args:
            **kwargs: Tool-specific arguments matching the JSON Schema.

        Returns:
            ToolResult indicating success or failure.
        """
        ...

    def to_openai_function(self) -> dict:
        """Return the tool definition in OpenAI function-calling format."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
