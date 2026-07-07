"""Rule loader — load rules from YAML files."""

import re
from pathlib import Path

import yaml

from codecheck.rules.models import Rule, Severity


class RuleLoadError(Exception):
    """Raised when a rules file cannot be loaded or parsed."""

    def __init__(self, message: str, file_path: str | None = None):
        self.file_path = file_path
        super().__init__(message)


def load_rules_from_yaml(path: str | Path) -> list[Rule]:
    """Load rules from a YAML rules file.

    Args:
        path: Path to the YAML rules file.

    Returns:
        List of Rule objects.

    Raises:
        RuleLoadError: If the file cannot be read, YAML is invalid, or
                       a rule definition is missing required fields.
    """
    path = Path(path)

    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise RuleLoadError(f"Rules file not found: {path}", file_path=str(path)) from None
    except OSError as e:
        raise RuleLoadError(f"Failed to read rules file: {e}", file_path=str(path)) from e

    try:
        raw = yaml.safe_load(content)
    except yaml.YAMLError as e:
        raise RuleLoadError(f"Invalid YAML in {path}: {e}", file_path=str(path)) from e

    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise RuleLoadError(
            f"Rules file must be a YAML dictionary/mapping, got {type(raw).__name__}",
            file_path=str(path),
        )

    rules_raw = raw.get("rules", [])
    if not isinstance(rules_raw, list):
        raise RuleLoadError(
            "'rules' must be a list, got {type(rules_raw).__name__}",
            file_path=str(path),
        )

    rules = []
    for i, rule_data in enumerate(rules_raw):
        if not isinstance(rule_data, dict):
            raise RuleLoadError(
                f"Rule at index {i} must be a dictionary, got {type(rule_data).__name__}",
                file_path=str(path),
            )

        rule_id = rule_data.get("id")
        if not rule_id:
            raise RuleLoadError(
                f"Rule at index {i} is missing required field 'id'",
                file_path=str(path),
            )

        rule_type = rule_data.get("type", "deterministic")
        if rule_type not in ("deterministic", "llm-assisted"):
            raise RuleLoadError(
                f"Rule '{rule_id}': type must be 'deterministic' or 'llm-assisted'",
                file_path=str(path),
            )

        severity = rule_data.get("severity", "warning")
        try:
            severity = Severity(severity)
        except ValueError:
            raise RuleLoadError(
                f"Rule '{rule_id}': severity must be one of {[s.value for s in Severity]}, "
                f"got '{severity}'",
                file_path=str(path),
            ) from None

        # Validate pattern for deterministic rules
        pattern = rule_data.get("pattern")
        if rule_type == "deterministic" and pattern:
            try:
                re.compile(pattern)
            except re.error as e:
                raise RuleLoadError(
                    f"Rule '{rule_id}': invalid regex pattern: {e}",
                    file_path=str(path),
                ) from e

        rules.append(Rule(
            id=rule_id,
            severity=severity,
            type=rule_type,
            category=rule_data.get("category", "general"),
            message=rule_data.get("message", rule_id),
            pattern=pattern,
            prompt=rule_data.get("prompt"),
        ))

    return rules


def load_builtin_rules() -> list[Rule]:
    """Load the built-in rules from the default rules file.

    Searches for .codecheck/rules.yaml starting from the current directory.
    If not found, raises RuleLoadError.
    """
    # Try current directory first, then parent directories
    current = Path.cwd()
    while True:
        candidate = current / ".codecheck" / "rules.yaml"
        if candidate.is_file():
            return load_rules_from_yaml(candidate)
        parent = current.parent
        if parent == current:
            break
        current = parent

    raise RuleLoadError(
        "Built-in rules file not found. Expected .codecheck/rules.yaml "
        "in the project root or any parent directory."
    )
