"""Agent context builder — system prompt, tools, target code, memory."""

from codecheck.llm.provider import LLMProvider
from codecheck.rules.engine import RuleEngine
from codecheck.tools.registry import ToolRegistry

SYSTEM_PROMPT_TEMPLATE = """You are CodeCheck, an AI-powered code reviewer. Your job is to review source code for bugs, security issues, style violations, and other problems.

## Available Tools

You have the following tools available to inspect the codebase:

{tools}

## Review Rules

The following rules are enabled for this review:

{rules}

## Instructions

1. First, use tools (read_file, git_diff, git_log, etc.) to gather information about the code.
2. Then, output your review findings as a JSON report.

## Output Format

When you are done reviewing, output a JSON object with the following structure:

```json
{{
  "status": "complete",
  "issues": [
    {{
      "rule_id": "rule-name",
      "file": "path/to/file.py",
      "line": 42,
      "severity": "critical",
      "message": "Description of the issue"
    }}
  ],
  "summary": "Brief summary of the review"
}}
```

If no issues are found, output an empty issues array.

## Important

- Only use tools that are listed above.
- Never make up file paths — use tools to discover them.
- Focus on the review rules provided. Do not report issues that don't match a rule.
- Be thorough but concise."""


class ContextBuilder:
    """Build the initial context (system prompt + tool list) for the Agent loop.

    Usage:
        builder = ContextBuilder(tool_registry, rule_engine)
        messages = builder.build_initial_messages(target_path)
    """

    def __init__(
        self,
        tool_registry: ToolRegistry,
        rule_engine: RuleEngine,
        llm: LLMProvider | None = None,
    ):
        self._tool_registry = tool_registry
        self._rule_engine = rule_engine
        self._llm = llm

    def build_system_prompt(self) -> str:
        """Build the system prompt with tool and rule descriptions."""
        tool_descriptions = []
        for tool in self._tool_registry.list_all():
            tool_descriptions.append(f"- **{tool.name}**: {tool.description}")

        rule_descriptions = []
        for rule in self._rule_engine.deterministic_rules:
            rule_descriptions.append(
                f"- [{rule.severity.value}] **{rule.id}**: {rule.message}"
            )
        for rule in self._rule_engine.llm_assisted_rules:
            rule_descriptions.append(
                f"- [{rule.severity.value}] **{rule.id}** (LLM-assisted): {rule.message}"
            )

        return SYSTEM_PROMPT_TEMPLATE.format(
            tools="\n".join(tool_descriptions),
            rules="\n".join(rule_descriptions) if rule_descriptions else "No rules configured.",
        )

    def build_initial_messages(self, target_path: str = ".") -> list[dict]:
        """Build the initial messages for the LLM conversation.

        Args:
            target_path: The path to review.

        Returns:
            A list of message dicts: [system_prompt, user_message].
        """
        system_prompt = self.build_system_prompt()

        user_message = (
            f"Please review the code in: {target_path}\n\n"
            "Start by reading the relevant files to understand the codebase, "
            "then provide your review findings."
        )

        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]

    def get_tool_schemas(self) -> list[dict]:
        """Return tool schemas in OpenAI function-calling format."""
        return self._tool_registry.to_openai_schema()
