"""Unit tests for MockProvider and LLM abstraction layer.

All tests are DETERMINISTIC — no network, no real LLM.
"""

import pytest

from codecheck.llm.exceptions import (
    LLMAuthenticationError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from codecheck.llm.mock_provider import MockProvider, MockRule
from codecheck.llm.provider import LLMResponse, ToolCall


class TestToolCall:
    """Test ToolCall intermediate representation."""

    def test_toolcall_creation(self):
        tc = ToolCall(id="1", name="read_file", arguments={"path": "/x"})
        assert tc.id == "1"
        assert tc.name == "read_file"
        assert tc.arguments == {"path": "/x"}

    def test_llmresponse_stop(self):
        resp = LLMResponse(content="hello", finish_reason="stop")
        assert resp.content == "hello"
        assert resp.tool_calls == []
        assert resp.finish_reason == "stop"

    def test_llmresponse_tool_calls(self):
        tc = ToolCall(id="1", name="run_test", arguments={"cmd": "pytest"})
        resp = LLMResponse(
            content=None,
            tool_calls=[tc],
            finish_reason="tool_calls",
        )
        assert resp.content is None
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "run_test"


class TestMockProviderKeyword:
    """Test MockProvider keyword matching."""

    def test_keyword_match(self):
        mock = MockProvider([
            MockRule(keyword="SQL", response_content="Found SQL injection"),
        ])
        resp = mock.chat([{"role": "user", "content": "This code has SQL injection risk"}])
        assert "SQL injection" in resp.content
        assert resp.finish_reason == "stop"

    def test_keyword_no_match_with_default(self):
        mock = MockProvider([
            MockRule(keyword="SQL", response_content="Found issue"),
            MockRule(keyword=None, response_content="No issues", consume=False),
        ])
        resp = mock.chat([{"role": "user", "content": "print('hello')"}])
        assert "No issues" in resp.content

    def test_keyword_no_match_no_default_raises(self):
        mock = MockProvider([
            MockRule(keyword="SQL", response_content="Found issue"),
        ])
        with pytest.raises(RuntimeError, match="no rule matched"):
            mock.chat([{"role": "user", "content": "print('hello')"}])


class TestMockProviderExact:
    """Test MockProvider exact matching."""

    def test_exact_match(self):
        mock = MockProvider([
            MockRule(
                exact="read_file:src/auth.py",
                tool_calls=[ToolCall(id="1", name="read_file", arguments={"path": "src/auth.py"})],
                finish_reason="tool_calls",
            ),
        ])
        resp = mock.chat([{"role": "user", "content": "read_file:src/auth.py"}])
        assert resp.finish_reason == "tool_calls"
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "read_file"

    def test_exact_no_match(self):
        mock = MockProvider([
            MockRule(exact="read_file:src/auth.py", response_content="ok"),
            MockRule(keyword=None, response_content="default", consume=False),
        ])
        resp = mock.chat([{"role": "user", "content": "read_file:src/other.py"}])
        assert resp.content == "default"


class TestMockProviderRegex:
    """Test MockProvider regex matching."""

    def test_regex_match(self):
        mock = MockProvider([
            MockRule(
                regex=r"修复.*sql.*注入",
                response_content="old_string: f-string, new_string: param_query",
            ),
        ])
        resp = mock.chat([{"role": "user", "content": "请修复这段 sql 注入问题"}])
        assert "param_query" in resp.content

    def test_regex_no_match(self):
        mock = MockProvider([
            MockRule(regex=r"修复.*sql", response_content="fix"),
            MockRule(keyword=None, response_content="default", consume=False),
        ])
        resp = mock.chat([{"role": "user", "content": "修复 xss 问题"}])
        assert resp.content == "default"


class TestMockProviderException:
    """Test MockProvider exception simulation."""

    def test_raise_error(self):
        mock = MockProvider([
            MockRule(keyword="timeout", raise_error=LLMTimeoutError("Request timed out")),
            MockRule(keyword=None, response_content="ok", consume=False),
        ])
        with pytest.raises(LLMTimeoutError, match="timed out"):
            mock.chat([{"role": "user", "content": "timeout test"}])

    def test_raise_error_does_not_affect_other_rules(self):
        mock = MockProvider([
            MockRule(keyword="timeout", raise_error=LLMRateLimitError("rate limited")),
            MockRule(keyword="normal", response_content="all good"),
            MockRule(keyword=None, response_content="default", consume=False),
        ])
        # This should raise
        with pytest.raises(LLMRateLimitError):
            mock.chat([{"role": "user", "content": "timeout"}])
        # This should work fine
        resp = mock.chat([{"role": "user", "content": "normal question"}])
        assert resp.content == "all good"


class TestMockProviderConsume:
    """Test MockProvider rule consumption."""

    def test_consume_true_removes_rule(self):
        mock = MockProvider([
            MockRule(keyword="first", response_content="first response", consume=True),
            MockRule(keyword="first", response_content="second response", consume=True),
            MockRule(keyword=None, response_content="default", consume=False),
        ])
        # First call matches first rule, which is consumed
        resp1 = mock.chat([{"role": "user", "content": "first match"}])
        assert resp1.content == "first response"

        # Second call matches second rule (now first in list)
        resp2 = mock.chat([{"role": "user", "content": "first match again"}])
        assert resp2.content == "second response"

        # Third call falls through to default
        resp3 = mock.chat([{"role": "user", "content": "first match again"}])
        assert resp3.content == "default"

    def test_consume_false_persists(self):
        mock = MockProvider([
            MockRule(keyword="persist", response_content="always me", consume=False),
        ])
        for _ in range(5):
            resp = mock.chat([{"role": "user", "content": "persist test"}])
            assert resp.content == "always me"


class TestMockProviderDelay:
    """Test MockProvider simulated delay."""

    def test_delay_is_applied(self):
        mock = MockProvider([
            MockRule(keyword="slow", response_content="done", delay=100),
        ])
        import time

        start = time.time()
        mock.chat([{"role": "user", "content": "slow request"}])
        elapsed = time.time() - start
        assert elapsed >= 0.09  # At least 90ms (100ms with some tolerance)


class TestMockProviderCallTracking:
    """Test MockProvider call history tracking."""

    def test_call_count(self):
        mock = MockProvider([
            MockRule(keyword=None, response_content="ok", consume=False),
        ])
        assert mock.call_count == 0
        mock.chat([{"role": "user", "content": "msg1"}])
        mock.chat([{"role": "user", "content": "msg2"}])
        assert mock.call_count == 2

    def test_last_messages(self):
        mock = MockProvider([
            MockRule(keyword=None, response_content="ok", consume=False),
        ])
        mock.chat([{"role": "user", "content": "first"}])
        mock.chat([{"role": "user", "content": "second"}])
        assert mock.last_messages[0]["content"] == "second"

    def test_reset(self):
        mock = MockProvider([
            MockRule(keyword=None, response_content="ok", consume=False),
        ])
        mock.chat([{"role": "user", "content": "msg"}])
        assert mock.call_count == 1
        mock.reset()
        assert mock.call_count == 0


class TestTokenCounting:
    """Test token counting in LLMProvider."""

    def test_count_tokens_returns_positive(self):
        from codecheck.llm.provider import LLMProvider

        # Create a minimal concrete implementation for testing
        class TestProvider(LLMProvider):
            def chat(self, messages, tools=None):
                return LLMResponse(content="test")

        provider = TestProvider()
        count = provider.count_tokens("Hello, world!")
        assert count > 0
        assert isinstance(count, int)

    def test_count_tokens_empty_string(self):
        from codecheck.llm.provider import LLMProvider

        class TestProvider(LLMProvider):
            def chat(self, messages, tools=None):
                return LLMResponse(content="test")

        provider = TestProvider()
        count = provider.count_tokens("")
        assert count == 0

    def test_count_messages_tokens(self):
        from codecheck.llm.provider import LLMProvider

        class TestProvider(LLMProvider):
            def chat(self, messages, tools=None):
                return LLMResponse(content="test")

        provider = TestProvider()
        messages = [
            {"role": "system", "content": "You are a code reviewer."},
            {"role": "user", "content": "Review this: print('hello')"},
        ]
        total = provider.count_messages_tokens(messages)
        assert total > 0


class TestExceptionHierarchy:
    """Test exception hierarchy correctness."""

    def test_all_are_provider_errors(self):
        assert issubclass(LLMAuthenticationError, LLMProviderError)
        assert issubclass(LLMRateLimitError, LLMProviderError)
        assert issubclass(LLMTimeoutError, LLMProviderError)

    def test_can_catch_all_with_base(self):
        """All LLM exceptions should be catchable as LLMProviderError."""
        try:
            raise LLMRateLimitError("test")
        except LLMProviderError:
            pass  # Should catch
        else:
            pytest.fail("LLMRateLimitError not caught as LLMProviderError")
