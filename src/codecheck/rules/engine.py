"""Rule engine — combine deterministic + LLM-assisted matching with dedup."""

from pathlib import Path

from codecheck.llm.provider import LLMProvider
from codecheck.rules.deterministic import DeterministicMatcher
from codecheck.rules.llm_assisted import LLMAssistedMatcher
from codecheck.rules.loader import RuleLoadError, load_builtin_rules, load_rules_from_yaml
from codecheck.rules.models import Issue, Rule, Severity


class RuleEngine:
    """Main rule engine combining deterministic and LLM-assisted matching.

    Workflow:
        1. Load rules from YAML
        2. Split into deterministic and LLM-assisted
        3. Run deterministic matcher on all source files
        4. Run LLM-assisted matcher (if LLM provider available)
        5. Merge/dedup: same file+line → dual_confirmed
        6. Filter false positives
        7. Return sorted issues (severity desc, then file, then line)

    Usage:
        engine = RuleEngine(rules_path=".codecheck/rules.yaml")
        issues = engine.scan(["src/main.py", "src/utils.py"])
    """

    def __init__(
        self,
        rules_path: str | Path | None = None,
        llm: LLMProvider | None = None,
    ):
        """Initialize the rule engine.

        Args:
            rules_path: Path to a YAML rules file. If None, loads built-in rules.
            llm: LLMProvider for LLM-assisted rules. If None, only deterministic
                 rules are used.
        """
        if rules_path is not None:
            all_rules = load_rules_from_yaml(rules_path)
        else:
            try:
                all_rules = load_builtin_rules()
            except RuleLoadError:
                all_rules = []

        self._det_rules = [r for r in all_rules if r.type == "deterministic"]
        self._llm_rules = [r for r in all_rules if r.type == "llm-assisted"]

        self._det_matcher = DeterministicMatcher(all_rules)
        self._llm_matcher = LLMAssistedMatcher(all_rules, llm=llm)

        # False positive tracking (code_snippet_hash → True)
        self._false_positives: set[str] = set()

    def set_llm(self, llm: LLMProvider) -> None:
        """Set or replace the LLM provider."""
        self._llm_matcher.set_llm(llm)

    def add_false_positive(self, code_snippet_hash: str) -> None:
        """Register a false positive pattern to skip in future scans."""
        self._false_positives.add(code_snippet_hash)

    def scan(self, file_paths: list[str | Path]) -> list[Issue]:
        """Scan all given files with all rules.

        Args:
            file_paths: List of file paths to scan.

        Returns:
            Sorted list of Issues (critical first, then by file/line).
        """
        file_paths_str = [str(p) for p in file_paths]

        # Phase 1: Deterministic matching
        det_issues = self._det_matcher.scan_files(file_paths_str)

        # Phase 2: LLM-assisted matching
        llm_issues = self._llm_matcher.scan_files(file_paths_str)

        # Phase 3: Merge and dedup
        merged = self._merge_and_dedup(det_issues, llm_issues)

        # Phase 4: Filter false positives
        filtered = self._filter_false_positives(merged)

        # Phase 5: Sort by severity (critical first), then file, then line
        severity_order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}
        filtered.sort(key=lambda i: (severity_order.get(i.severity, 99), i.file, i.line))

        return filtered

    def _merge_and_dedup(
        self, det_issues: list[Issue], llm_issues: list[Issue]
    ) -> list[Issue]:
        """Merge deterministic and LLM issues, deduplicating by location.

        When both matchers flag the same (file, line), the result is merged
        into a single issue with dual_confirmed=True.
        """
        # Build a map of location → issues
        location_map: dict[tuple, list[Issue]] = {}
        for issue in det_issues:
            location_map.setdefault(issue.location_key, []).append(issue)
        for issue in llm_issues:
            location_map.setdefault(issue.location_key, []).append(issue)

        merged: list[Issue] = []
        for _location, issues in location_map.items():
            if len(issues) == 1:
                merged.append(issues[0])
            else:
                # Multiple issues at same location — merge
                # Take the first issue, mark as dual_confirmed
                primary = issues[0]
                primary.dual_confirmed = True
                # Use the highest severity
                sev_order = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}
                primary.severity = min(issues, key=lambda i: sev_order.get(i.severity, 99)).severity
                merged.append(primary)

        return merged

    def _filter_false_positives(self, issues: list[Issue]) -> list[Issue]:
        """Filter out known false positives."""
        if not self._false_positives:
            return issues
        return [
            issue for issue in issues
            if f"{issue.file}:{issue.line}:{issue.rule_id}" not in self._false_positives
        ]

    @property
    def deterministic_rules(self) -> list[Rule]:
        return list(self._det_rules)

    @property
    def llm_assisted_rules(self) -> list[Rule]:
        return list(self._llm_rules)
