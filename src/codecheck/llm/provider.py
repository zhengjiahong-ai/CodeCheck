"""LLM Provider abstract base and intermediate representation types."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import tiktoken


@dataclass
class ToolCall:
    """工具调用中间表示，不依赖任何 LLM 供应商格式。

    Attributes:
        id: 工具调用唯一标识符。
        name: 工具名称。
        arguments: 已解析为 dict 的参数。
    """

    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    """LLM 响应中间表示，统一所有供应商的响应格式。

    Attributes:
        content: 文本响应内容（当 finish_reason="stop" 时）。
        tool_calls: 工具调用列表（当 finish_reason="tool_calls" 时）。
        finish_reason: 停止原因 — "stop" | "tool_calls" | "length"。
        usage: Token 用量信息（可选）。
    """

    content: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    usage: dict | None = None


class LLMProvider(ABC):
    """LLM Provider 抽象基类。

    所有 LLM 供应商（DeepSeek、Mock 等）必须实现此接口。
    构造函数接受具体参数，不依赖 CodeCheckConfig 对象，
    以保持与配置系统的解耦。

    Usage:
        provider = DeepSeekProvider(api_key="sk-xxx", model="deepseek-v4-pro")
        response = provider.chat([{"role": "user", "content": "Hello"}])
    """

    # tiktoken encoding for token counting
    _encoding: tiktoken.Encoding | None = None

    @abstractmethod
    def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        """Send messages and return response.

        Args:
            messages: List of {"role": str, "content": str} dicts.
            tools: Optional list of OpenAI function-calling tool definitions.

        Returns:
            LLMResponse with content or tool_calls populated.

        Raises:
            LLMProviderError: Base error for all provider failures.
            LLMAuthenticationError: Authentication failed.
            LLMRateLimitError: Rate limit exceeded.
            LLMTimeoutError: Request timed out.
            LLMContextOverflowError: Context window exceeded.
        """
        ...

    def count_tokens(self, text: str) -> int:
        """Estimate token count using tiktoken cl100k_base.

        Used for context window management — prevents overflow,
        not intended for precise billing.

        Args:
            text: The text to count tokens for.

        Returns:
            Estimated token count.
        """
        if self._encoding is None:
            self._encoding = tiktoken.get_encoding("cl100k_base")
        return len(self._encoding.encode(text))

    def count_messages_tokens(self, messages: list[dict]) -> int:
        """Estimate total tokens for a list of messages.

        Args:
            messages: List of message dicts with 'content' key.

        Returns:
            Total estimated token count.
        """
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self.count_tokens(content)
            elif isinstance(content, list):
                # Multi-modal content (text + images, etc.)
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        total += self.count_tokens(part["text"])
        return total
