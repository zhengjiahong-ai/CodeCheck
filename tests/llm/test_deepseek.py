"""Integration tests for DeepSeekProvider.

These tests are SKIPPED by default and only run when
CODE_CHECK_TEST_LIVE=1 is set, because they require a real API key.
"""

import os

import pytest

from codecheck.llm.deepseek_provider import DeepSeekProvider
from codecheck.llm.exceptions import LLMAuthenticationError

# Skip all tests in this module unless CODE_CHECK_TEST_LIVE=1
pytestmark = pytest.mark.skipif(
    os.getenv("CODE_CHECK_TEST_LIVE") != "1",
    reason="Set CODE_CHECK_TEST_LIVE=1 to run live DeepSeek tests",
)


class TestDeepSeekProviderLive:
    """Live integration tests — require real API key and network."""

    def test_no_api_key_raises(self, monkeypatch):
        """Verify authentication error when no key is configured."""
        monkeypatch.delenv("CODE_CHECK_API_KEY", raising=False)
        with pytest.raises(LLMAuthenticationError, match="API Key"):
            DeepSeekProvider(api_key=None)

    def test_simple_chat(self):
        """Basic chat completion with DeepSeek."""
        provider = DeepSeekProvider()
        response = provider.chat([
            {"role": "user", "content": "Reply with exactly: OK"},
        ])
        assert response.content is not None
        assert len(response.content) > 0
        assert response.finish_reason == "stop"

    def test_chat_with_tools(self):
        """Chat completion with function-calling tools."""
        provider = DeepSeekProvider()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path"},
                        },
                        "required": ["path"],
                    },
                },
            }
        ]
        response = provider.chat(
            [
                {"role": "user", "content": "Read the file at /tmp/test.txt"},
            ],
            tools=tools,
        )
        # Should either return a tool call or a text response
        assert response.finish_reason in ("stop", "tool_calls")

    def test_token_counting(self):
        """Verify token counting is consistent."""
        provider = DeepSeekProvider()
        count = provider.count_tokens("Hello, world!")
        assert count > 0
        assert isinstance(count, int)

    def test_messages_with_system_prompt(self):
        """Verify multi-turn conversation works."""
        provider = DeepSeekProvider()
        messages = [
            {"role": "system", "content": "You are a code reviewer. Be brief."},
            {"role": "user", "content": "What is the issue with: eval('1+1')?"},
        ]
        response = provider.chat(messages)
        assert response.content is not None
        assert "eval" in response.content.lower() or "dangerous" in response.content.lower()
