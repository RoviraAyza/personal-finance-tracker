"""Deciding which category a transaction belongs to.

Pure: rules in, decision out. No I/O, no clock, no database. The same
candidate and rule set always produce the same decision, which is what makes
this testable exhaustively and lets the UI preview a rule's effect before
anything is saved.

Matching is deliberately dumb. Rules are tried in order -- `priority`
ascending, then `id` -- and the first one that matches wins. No scoring, no
fuzzy ranking, no tie-breaking cleverness. A surprising categorisation can
always be explained by pointing at one rule.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

from pf.rules.model import (
    CONTAINS,
    EXACT,
    NO_MATCH,
    PREFIX,
    REGEX,
    Candidate,
    Category,
    Decision,
    Rule,
    RuleError,
)


class Categorizer:
    """Applies a rule set to candidates."""

    def __init__(
        self, categories: Sequence[Category], rules: Sequence[Rule]
    ) -> None:
        self._categories = {c.name: c for c in categories}

        unknown = sorted({r.category for r in rules} - set(self._categories))
        if unknown:
            raise RuleError(
                "rules reference categories that do not exist: "
                + ", ".join(repr(u) for u in unknown)
            )

        # Precedence is fixed here, once, so every lookup sees the same order.
        self._rules: tuple[Rule, ...] = tuple(
            sorted(rules, key=lambda r: (r.priority, r.id))
        )

        # Regexes are compiled up front: a bad pattern must fail immediately,
        # not part-way through ten thousand rows.
        self._compiled: dict[int, re.Pattern[str]] = {}
        for rule in self._rules:
            if rule.match == REGEX:
                try:
                    self._compiled[rule.id] = re.compile(rule.pattern)
                except re.error as exc:
                    raise RuleError(
                        f"rule {rule.pattern!r} is not a valid regex: {exc}"
                    ) from exc

    # ----------------------------------------------------------------------
    # Reading the rule set
    # ----------------------------------------------------------------------

    @property
    def rules(self) -> tuple[Rule, ...]:
        """The rules, in the precedence order they are applied in."""
        return self._rules

    @property
    def categories(self) -> dict[str, Category]:
        return dict(self._categories)

    # ----------------------------------------------------------------------
    # Matching
    # ----------------------------------------------------------------------

    def _matches(self, rule: Rule, candidate: Candidate) -> bool:
        if rule.kind_filter is not None and rule.kind_filter != candidate.kind:
            return False

        text = candidate.description_norm
        if not text:
            return False

        if rule.match == EXACT:
            return text == rule.pattern
        if rule.match == PREFIX:
            return text.startswith(rule.pattern)
        if rule.match == CONTAINS:
            return rule.pattern in text
        if rule.match == REGEX:
            return self._compiled[rule.id].search(text) is not None
        return False      # unreachable: the match type is validated on Rule

    def categorize(self, candidate: Candidate) -> Decision:
        """The first matching rule wins."""
        for rule in self._rules:
            if self._matches(rule, candidate):
                return Decision(
                    category=rule.category, rule_id=rule.id, reason="rule"
                )
        return NO_MATCH

    def explain(self, candidate: Candidate) -> list[Rule]:
        """Every rule that matches, in precedence order.

        Not a debugging extra. This is how a wrong rule gets found: the user
        drills into a category, sees something that does not belong, and the
        immediate next question is "why is this here?" -- which this answers,
        including showing a rule that was shadowed by a higher-priority one.
        """
        return [rule for rule in self._rules if self._matches(rule, candidate)]

    def unused_rules(self, candidates: Iterable[Candidate]) -> list[Rule]:
        """Rules that matched nothing at all.

        Almost always a typo in the pattern. Reported rather than tolerated,
        because a rule that never fires is indistinguishable from a rule that
        was never written -- except that it looks like coverage.
        """
        used: set[int] = set()
        for candidate in candidates:
            for rule in self._rules:
                if self._matches(rule, candidate):
                    used.add(rule.id)
        return [rule for rule in self._rules if rule.id not in used]

    def shadowed_rules(self) -> list[tuple[Rule, Rule]]:
        """Pairs where an earlier rule makes a later one unreachable.

        Only detects the clear cases -- an earlier `contains` or `prefix` whose
        pattern is contained in a later rule's pattern, with no kind filter
        separating them. Cheap to compute and catches the common mistake of
        adding a specific rule below a general one.
        """
        found: list[tuple[Rule, Rule]] = []
        for index, later in enumerate(self._rules):
            for earlier in self._rules[:index]:
                if earlier.kind_filter not in (None, later.kind_filter):
                    continue
                if earlier.match == CONTAINS and earlier.pattern in later.pattern:
                    found.append((earlier, later))
                elif earlier.match == PREFIX and later.pattern.startswith(
                    earlier.pattern
                ):
                    found.append((earlier, later))
        return found
