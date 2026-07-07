"""LLM Provider exception hierarchy.

All exceptions derive from LLMProviderError so that client code
(Agent Loop, Feedback Loop) can catch them uniformly and implement
retry / fallback logic without knowing the vendor details.
"""


class LLMProviderError(Exception):
    """LLM Provider 基础异常。所有 LLM 相关错误的父类。"""

    pass


class LLMAuthenticationError(LLMProviderError):
    """认证失败 — API Key 无效、过期或未配置。"""

    pass


class LLMRateLimitError(LLMProviderError):
    """速率限制 — 请求频率超过 API 限制 (HTTP 429)。"""

    pass


class LLMInvalidRequestError(LLMProviderError):
    """请求参数错误 — 如不支持的模型名称、非法参数。"""

    pass


class LLMTimeoutError(LLMProviderError):
    """请求超时 — API 在指定时间内未响应。"""

    pass


class LLMContextOverflowError(LLMProviderError):
    """上下文窗口溢出 — 消息 token 数超过模型最大上下文。"""

    pass