"""Unit tests for AgentLoop — using MockProvider for deterministic testing."""

import json

from codecheck.agent.loop import AgentLoop
from codecheck.llm.mock_provider import MockProvider, MockRule
from codecheck.llm.provider import ToolCall
from codecheck.rules.engine import RuleEngine
from codecheck.rules.loader import RuleLoadError
from codecheck.tools.base import Tool, ToolResult
from codecheck.tools.registry import ToolRegistry

# ── Test tools ─────────────────────────────────────────────────────────────


class _EchoTool(Tool):
    """A simple tool for testing the agent loop."""

    name = "echo"
    description = "Echo a message back."
    parameters = {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    }

    def execute(self, **kwargs):
        return ToolResult(success=True, data=f"echo: {kwargs.get('message', '')}")


class _ReadTool(Tool):
    """Simulates reading a file."""

    name = "read_file"
    description = "Read a file."
    parameters = {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    }

    def execute(self, **kwargs):
        return ToolResult(success=True, data=f"content of {kwargs.get('path', '')}")


# ── Helpers ────────────────────────────────────────────────────────────────


def _build_review_report(issues: list[dict] | None = None, status: str = "complete") -> str:
    """Build a review report JSON string."""
    report = {
        "status": status,
        "issues": issues or [],
        "summary": "Review complete",
    }
    return json.dumps(report)


def _make_rule_engine():
    """Create a RuleEngine with no rules (we don't need rules for loop tests)."""
    try:
        return RuleEngine()
    except RuleLoadError:
        return RuleEngine(rules_path=None)


# ── Tests ──────────────────────────────────────────────────────────────────


class TestAgentLoopBasic:
    """Test basic AgentLoop behavior."""

    def test_llm_returns_report_immediately(self):
        """LLM returns a review report on first call → loop exits."""
        mock = MockProvider([
            MockRule(
                keyword=None,
                response_content=_build_review_report([
                    {"rule_id": "no-print", "file": "a.py", "line": 1,
                     "severity": "info", "message": "print found"},
                ]),
                consume=False,
            ),
        ])
        registry = ToolRegistry()
        engine = _make_rule_engine()

        loop = AgentLoop(mock, registry, engine)
        report = loop.run("test/")

        assert report.status == "complete"
        assert len(report.issues) == 1
        assert report.issues[0]["rule_id"] == "no-print"
        assert report.rounds == 1

    def test_llm_returns_no_issues(self):
        """LLM reports no issues."""
        mock = MockProvider([
            MockRule(
                keyword=None,
                response_content=_build_review_report([]),
                consume=False,
            ),
        ])
        registry = ToolRegistry()
        engine = _make_rule_engine()

        loop = AgentLoop(mock, registry, engine)
        report = loop.run("test/")

        assert report.status == "complete"
        assert len(report.issues) == 0

    def test_max_rounds_reached(self):
        """LLM keeps calling tools → max rounds hit."""
        mock = MockProvider([
            MockRule(
                keyword=None,
                tool_calls=[
                    ToolCall(id="1", name="echo", arguments={"message": "hello"}),
                ],
                finish_reason="tool_calls",
                consume=False,
            ),
        ])
        registry = ToolRegistry()
        registry.register(_EchoTool())
        engine = _make_rule_engine()

        loop = AgentLoop(mock, registry, engine, max_rounds=3)
        report = loop.run("test/")

        assert report.status == "max_rounds"
        assert report.rounds == 3


class TestAgentLoopToolDispatch:
    """Test agent loop tool call dispatch."""

    def test_tool_call_and_feedback(self):
        """LLM calls tool, then returns report → tool was executed, feedback fed back."""
        mock = MockProvider([
            # Round 1: call a tool
            MockRule(
                keyword=None,
                tool_calls=[
                    ToolCall(id="1", name="echo", arguments={"message": "test"}),
                ],
                finish_reason="tool_calls",
                consume=True,
            ),
            # Round 2: return report
            MockRule(
                keyword=None,
                response_content=_build_review_report([
                    {"rule_id": "r1", "file": "x.py", "line": 1,
                     "severity": "warning", "message": "issue"},
                ]),
                consume=False,
            ),
        ])
        registry = ToolRegistry()
        registry.register(_EchoTool())
        engine = _make_rule_engine()

        loop = AgentLoop(mock, registry, engine)
        report = loop.run("test/")

        assert report.status == "complete"
        assert report.rounds == 2
        assert report.tool_calls == 1
        assert len(report.issues) == 1

    def test_multiple_tool_calls(self):
        """LLM calls multiple tools in one response."""
        mock = MockProvider([
            # Round 1: call two tools
            MockRule(
                keyword=None,
                tool_calls=[
                    ToolCall(id="1", name="echo", arguments={"message": "a"}),
                    ToolCall(id="2", name="echo", arguments={"message": "b"}),
                ],
                finish_reason="tool_calls",
                consume=True,
            ),
            # Round 2: return report
            MockRule(
                keyword=None,
                response_content=_build_review_report([]),
                consume=False,
            ),
        ])
        registry = ToolRegistry()
        registry.register(_EchoTool())
        engine = _make_rule_engine()

        loop = AgentLoop(mock, registry, engine)
        report = loop.run("test/")

        assert report.status == "complete"
        assert report.tool_calls == 2

    def test_forbidden_tool_blocked(self):
        """Guardrail blocks a forbidden tool → error fed back to LLM."""
        mock = MockProvider([
            # Attempt to use git_push (forbidden)
            MockRule(
                keyword=None,
                tool_calls=[
                    ToolCall(id="1", name="git_push", arguments={}),
                ],
                finish_reason="tool_calls",
                consume=True,
            ),
            # After blocked, return report
            MockRule(
                keyword=None,
                response_content=_build_review_report([]),
                consume=False,
            ),
        ])
        registry = ToolRegistry()
        engine = _make_rule_engine()

        loop = AgentLoop(mock, registry, engine)
        report = loop.run("test/")

        assert report.status == "complete"
        # Tool was blocked, so no tool was actually executed
        assert report.rounds == 2

    def test_llm_error_handled(self):
        """LLM throws an exception → error status returned."""
        from codecheck.llm.exceptions import LLMProviderError

        mock = MockProvider([
            MockRule(
                keyword=None,
                raise_error=LLMProviderError("Service unavailable"),
            ),
        ])
        registry = ToolRegistry()
        engine = _make_rule_engine()

        loop = AgentLoop(mock, registry, engine)
        report = loop.run("test/")

        assert report.status == "error"
        assert len(report.errors) > 0


class TestAgentLoopContext:
    """Test that context is built correctly."""

    def test_context_includes_tools(self):
        """Context builder should include registered tools."""
        from codecheck.agent.context import ContextBuilder

        registry = ToolRegistry()
        registry.register(_EchoTool())
        registry.register(_ReadTool())
        engine = _make_rule_engine()

        builder = ContextBuilder(registry, engine)
        messages = builder.build_initial_messages("src/")

        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "echo" in messages[0]["content"]
        assert "read_file" in messages[0]["content"]
        assert "src/" in messages[1]["content"]

    def test_tool_schemas_in_openai_format(self):
        from codecheck.agent.context import ContextBuilder

        registry = ToolRegistry()
        registry.register(_EchoTool())
        engine = _make_rule_engine()

        builder = ContextBuilder(registry, engine)
        schemas = builder.get_tool_schemas()

        assert len(schemas) == 1
        assert schemas[0]["type"] == "function"
        assert schemas[0]["function"]["name"] == "echo"
