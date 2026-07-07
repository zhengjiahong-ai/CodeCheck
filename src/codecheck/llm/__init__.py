"""LLM abstraction layer for CodeCheck.

Provides a vendor-neutral interface for LLM calls, supporting:
- DeepSeek (real provider via OpenAI-compatible API)
- Mock (rule-driven provider for deterministic unit testing)
"""

from codecheck.llm.deepseek_provider import DeepSeekProvider
from codecheck.llm.exceptions import (
    LLMAuthenticationError,
    LLMContextOverflowError,
    LLMInvalidRequestError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from codecheck.llm.mock_provider import MockProvider, MockRule
from codecheck.llm.provider import LLMProvider, LLMResponse, ToolCall

__all__ = [
    "LLMProvider",
    "LLMResponse",
    "ToolCall",
    "LLMProviderError",
    "LLMAuthenticationError",
    "LLMRateLimitError",
    "LLMInvalidRequestError",
    "LLMTimeoutError",
    "LLMContextOverflowError",
    "DeepSeekProvider",
    "MockProvider",
    "MockRule",
]
