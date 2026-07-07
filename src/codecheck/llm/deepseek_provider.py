"""DeepSeek LLM provider — wraps OpenAI-compatible API."""

import os
import time

from openai import APIError, AuthenticationError, OpenAI, RateLimitError

from codecheck.llm.exceptions import (
    LLMAuthenticationError,
    LLMContextOverflowError,
    LLMInvalidRequestError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from codecheck.llm.provider import LLMProvider, LLMResponse, ToolCall


class DeepSeekProvider(LLMProvider):
    """DeepSeek LLM provider via OpenAI-compatible API.

    Constructor accepts specific parameters (not CodeCheckConfig),
    keeping the provider decoupled from the configuration system.

    Args:
        api_key: DeepSeek API key. If None, reads from CODE_CHECK_API_KEY env var.
        base_url: API base URL. Defaults to DeepSeek endpoint.
        model: Model name. Defaults to 'deepseek-v4-pro'.
        timeout: Request timeout in seconds. Defaults to 120.
        max_retries: Max retries on transient errors. Defaults to 2.
    """

    # Default DeepSeek API endpoint
    DEFAULT_BASE_URL = "https://api.deepseek.com"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "deepseek-v4-pro",
        timeout: int = 120,
        max_retries: int = 2,
    ):
        self._api_key = api_key or os.getenv("CODE_CHECK_API_KEY")
        if not self._api_key:
            raise LLMAuthenticationError(
                "API Key 未配置。请运行 'codecheck config --set-key' "
                "或设置环境变量 CODE_CHECK_API_KEY"
            )

        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries

        self._client = OpenAI(
            api_key=self._api_key,
            base_url=base_url or self.DEFAULT_BASE_URL,
            timeout=timeout,
            max_retries=0,  # We handle retries ourselves
        )

    @property
    def model(self) -> str:
        return self._model

    def chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        """Send chat completion request to DeepSeek.

        Args:
            messages: List of message dicts.
            tools: Optional list of function-calling tool definitions.

        Returns:
            LLMResponse with content or tool_calls.

        Raises:
            Various LLMProviderError subclasses on failure.
        """
        last_error: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                return self._do_chat(messages, tools)
            except (LLMAuthenticationError, LLMInvalidRequestError):
                # Non-retryable errors — re-raise immediately
                raise
            except (LLMRateLimitError, LLMTimeoutError, LLMProviderError) as e:
                last_error = e
                if attempt < self._max_retries:
                    wait = 2**attempt  # Exponential backoff: 1s, 2s
                    time.sleep(wait)
                    continue
                raise
            except Exception as e:
                last_error = LLMProviderError(f"Unexpected error: {e}")
                if attempt < self._max_retries:
                    time.sleep(2**attempt)
                    continue
                raise last_error from e

        # Should not reach here, but satisfy type checker
        raise last_error  # type: ignore[misc]

    def _do_chat(
        self, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse:
        """Execute a single chat completion call.

        Maps OpenAI SDK exceptions to our internal exception hierarchy.
        """
        try:
            kwargs: dict = {
                "model": self._model,
                "messages": messages,
            }
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            completion = self._client.chat.completions.create(**kwargs)
            choice = completion.choices[0]

            # Parse tool calls into IR
            tool_calls: list[ToolCall] = []
            if choice.message.tool_calls:
                import json

                for tc in choice.message.tool_calls:
                    try:
                        arguments = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                    tool_calls.append(
                        ToolCall(
                            id=tc.id or "",
                            name=tc.function.name,
                            arguments=arguments,
                        )
                    )

            return LLMResponse(
                content=choice.message.content,
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason or "stop",
                usage={
                    "prompt_tokens": completion.usage.prompt_tokens if completion.usage else 0,
                    "completion_tokens": completion.usage.completion_tokens if completion.usage else 0,
                    "total_tokens": completion.usage.total_tokens if completion.usage else 0,
                },
            )

        except AuthenticationError as e:
            raise LLMAuthenticationError(
                "API Key 无效或已过期。请运行 'codecheck config --set-key' 更新凭据。"
            ) from e
        except RateLimitError as e:
            raise LLMRateLimitError(
                "API 速率限制，请稍后重试。"
            ) from e
        except APIError as e:
            if e.status_code == 400:
                if "context" in str(e.body).lower() or "token" in str(e.body).lower():
                    raise LLMContextOverflowError(
                        "上下文窗口溢出，请缩减审查范围或使用 --diff 增量模式。"
                    ) from e
                raise LLMInvalidRequestError(
                    f"请求参数错误: {e.body}"
                ) from e
            raise LLMProviderError(f"API 错误 (HTTP {e.status_code}): {e.body}") from e