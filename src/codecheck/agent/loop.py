"""Agent main loop — orchestrate context, LLM calls, tool dispatch, and stop."""

import json
from dataclasses import dataclass, field

from codecheck.agent.context import ContextBuilder
from codecheck.agent.parser import ParseError, parse_review_report
from codecheck.guardrails.guard import Action, guardrail
from codecheck.llm.provider import LLMProvider
from codecheck.rules.engine import RuleEngine
from codecheck.tools.registry import ToolRegistry


@dataclass
class ReviewReport:
    """Final output of an AgentLoop run.

    Attributes:
        status: "complete" | "max_rounds" | "error"
        issues: List of issues found (normalized dicts).
        summary: Human-readable summary.
        rounds: Number of LLM rounds executed.
        tool_calls: Total number of tool calls made.
        errors: List of error messages encountered.
    """

    status: str = "complete"
    issues: list[dict] = field(default_factory=list)
    summary: str = ""
    rounds: int = 0
    tool_calls: int = 0
    errors: list[str] = field(default_factory=list)


class AgentLoop:
    """Main agent loop for CodeCheck.

    Orchestrates the review process:
    1. Build initial context (system prompt + target path)
    2. Call LLM → parse response
    3. If tool calls: check guardrail → execute → feed back → loop
    4. If text content: parse review report → stop
    5. Stop conditions: max rounds, LLM says stop, parse error

    Usage:
        loop = AgentLoop(llm, tool_registry, rule_engine)
        report = loop.run("src/")
    """

    def __init__(
        self,
        llm: LLMProvider,
        tool_registry: ToolRegistry,
        rule_engine: RuleEngine,
        max_rounds: int = 10,
    ):
        """Initialize the agent loop.

        Args:
            llm: LLM provider for making calls.
            tool_registry: Tool registry for dispatching tool calls.
            rule_engine: Rule engine (for rule descriptions in context).
            max_rounds: Maximum LLM rounds before forced stop.
        """
        self._llm = llm
        self._tool_registry = tool_registry
        self._rule_engine = rule_engine
        self._max_rounds = max_rounds

        self._context = ContextBuilder(tool_registry, rule_engine, llm)
        self._report = ReviewReport()

    def run(self, target_path: str = ".") -> ReviewReport:
        """Run the review loop on the given target path.

        Args:
            target_path: Path to the file or directory to review.

        Returns:
            A ReviewReport with the review results.
        """
        self._report = ReviewReport()
        messages = self._context.build_initial_messages(target_path)
        tool_schemas = self._context.get_tool_schemas()

        while self._report.rounds < self._max_rounds:
            self._report.rounds += 1

            # Call LLM
            try:
                response = self._llm.chat(messages, tools=tool_schemas if tool_schemas else None)
            except Exception as e:
                self._report.errors.append(f"LLM call failed: {e}")
                self._report.status = "error"
                return self._report

            # Check if LLM wants to call tools
            if response.tool_calls:
                for tc in response.tool_calls:
                    self._report.tool_calls += 1

                    # Guardrail check
                    action = Action(tc.name, tc.arguments)
                    guard_result = guardrail(action)

                    if not guard_result.allowed:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": f"ERROR: {guard_result.reason}",
                        })
                        continue

                    # Execute tool
                    result = self._tool_registry.execute(tc.name, **tc.arguments)

                    # Build tool result message
                    content = result.data if result.success else f"ERROR: {result.error}"
                    if result.data:
                        content = result.data

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": content,
                    })

                # Add assistant message with tool calls
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in response.tool_calls
                    ],
                })

            else:
                # LLM returned text content — parse review report
                try:
                    report = parse_review_report(response.content)
                    self._report.status = report.get("status", "complete")
                    self._report.issues = report.get("issues", [])
                    self._report.summary = report.get("summary", "")
                    return self._report
                except ParseError as e:
                    self._report.errors.append(str(e))
                    self._report.status = "error"
                    return self._report

        # Max rounds reached
        self._report.status = "max_rounds"
        self._report.summary = "Review stopped: maximum rounds reached without a final report."
        return self._report

    @property
    def report(self) -> ReviewReport:
        """Return the current report (updated during the loop)."""
        return self._report
