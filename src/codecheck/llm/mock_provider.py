"""Mock LLM provider — rule-driven, deterministic responses for testing."""

import re
import time
from dataclasses import dataclass

from codecheck.llm.exceptions import LLMProviderError
from codecheck.llm.provider import LLMProvider, LLMResponse, ToolCall


@dataclass
class MockRule:
    """A single matching rule for MockProvider.

    Each rule has a trigger condition (keyword/regex/exact) and a response.
    Rules are checked in registration order. The first match wins.

    Attributes:
        keyword: Match if the concatenated message content contains this string.
        regex: Match if the concatenated message content matches this regex.
        exact: Match if the last user message content equals this string.
        response_content: Text content to return (for 'stop' finish).
        tool_calls: Tool calls to return (for 'tool_calls' finish).
        finish_reason: "stop" or "tool_calls".
        consume: If True, the rule is removed after first match (one-shot).
                 If False, it can match unlimited times (good for defaults).
        delay: Simulated latency in milliseconds.
        raise_error: If set, raise this exception instead of returning.
    """

    keyword: str | None = None
    regex: str | None = None
    exact: str | None = None

    response_content: str | None = None
    tool_calls: list[ToolCall] | None = None
    finish_reason: str = "stop"

    consume: bool = True
    delay: int = 0
    raise_error: LLMProviderError | None = None

    def matches(self, messages: list[dict]) -> bool:
        """Check if this rule matches the given messages.

        A rule with all trigger conditions set to None is a catch-all default.
        """
        if self.keyword is None and self.regex is None and self.exact is None:
            return True  # Catch-all default rule

        # Get the last user message for exact matching
        last_user_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                last_user_content = msg.get("content", "")
                break

        # Concatenate all message content for keyword/regex matching
        all_content = " ".join(
            msg.get("content", "")
            for msg in messages
            if isinstance(msg.get("content"), str)
        )

        if self.exact is not None:
            return last_user_content == self.exact

        if self.keyword is not None:
            return self.keyword in all_content

        if self.regex is not None:
            return bool(re.search(self.regex, all_content))

        return False


class MockProvider(LLMProvider):
    """Rule-driven mock LLM provider for deterministic unit testing.

    Rules are checked in registration order. The first matching rule wins.
    A rule with all trigger conditions set to None acts as a catch-all default.

    Usage:
        mock = MockProvider(rules=[
            MockRule(keyword="SQL", response_content="Found SQL injection"),
            MockRule(keyword=None, response_content="No issues", consume=False),
        ])
        response = mock.chat([{"role": "user", "content": "SELECT * FROM users"}])
        assert "SQL injection" in response.content
    """

    def __init__(self, rules: list[MockRule] | None = None):
        """Initialize with an optional list of rules.

        Args:
            rules: Ordered list of MockRule objects. Checked in order.
        """
        self._rules: list[MockRule] = list(rules) if rules else []
        self._call_history: list[dict] = []  # Record of all chat() calls

    @property
    def rules(self) -> list[MockRule]:
        """Return current rules (for inspection in tests)."""
        return self._rules

    @property
    def call_count(self) -> int:
        """Number of times chat() was called."""
        return len(self._call_history)

    @property
    def last_messages(self) -> list[dict] | None:
        """The messages from the most recent chat() call."""
        return self._call_history[-1] if self._call_history else None

    def add_rule(self, rule: MockRule) -> None:
        """Add a rule to the end of the matching chain."""
        self._rules.append(rule)

    def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        """Process messages through the rule chain.

        Args:
            messages: The chat messages to match against.
            tools: Ignored in mock (rules determine response format).

        Returns:
            LLMResponse according to the first matching rule.

        Raises:
            LLMProviderError: If the matched rule has raise_error set.
            RuntimeError: If no rule matches and no catch-all rule exists.
        """
        self._call_history.append(messages)

        for i, rule in enumerate(self._rules):
            if rule.matches(messages):
                # Simulate delay
                if rule.delay > 0:
                    time.sleep(rule.delay / 1000.0)

                # Remove consumed rules
                if rule.consume:
                    self._rules.pop(i)

                # Raise error if configured
                if rule.raise_error is not None:
                    raise rule.raise_error

                # Return response
                return LLMResponse(
                    content=rule.response_content,
                    tool_calls=list(rule.tool_calls) if rule.tool_calls else [],
                    finish_reason=rule.finish_reason,
                )

        # No rule matched
        raise RuntimeError(
            "MockProvider: no rule matched and no catch-all rule configured. "
            "Add a MockRule with all triggers set to None as a fallback."
        )

    def reset(self) -> None:
        """Clear call history (for test isolation)."""
        self._call_history = []
