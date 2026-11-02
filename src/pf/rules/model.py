"""The shapes the categoriser works with.

Rules are data. Nothing in this module reads a file, a database or a clock --
that is the whole point. A rule set can be built in a test in two lines, and
the same objects come out of `loader.py` when read from JSON.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

# --------------------------------------------------------------------------
# Match types
# --------------------------------------------------------------------------

EXACT: Final = "exact"
PREFIX: Final = "prefix"
CONTAINS: Final = "contains"
REGEX: Final = "regex"

MATCH_TYPES: Final = frozenset({EXACT, PREFIX, CONTAINS, REGEX})

# --------------------------------------------------------------------------
# Category kinds
# --------------------------------------------------------------------------

SPENDING: Final = "spending"
INCOME: Final = "income"
TRANSFER: Final = "transfer"
EXCLUDED: Final = "excluded"

CATEGORY_KINDS: Final = frozenset({SPENDING, INCOME, TRANSFER, EXCLUDED})

#: Category kinds left out of spend analysis unless explicitly asked for.
NON_SPEND_CATEGORY_KINDS: Final = frozenset({TRANSFER, EXCLUDED})


class RuleError(ValueError):
    """A rule set is not usable. Raised at load time, never mid-run."""


@dataclass(frozen=True)
class Category:
    """A bucket Jose defined. Named, because names are what he edits."""

    name: str
    kind: str = SPENDING
    parent: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise RuleError("a category needs a name")
        if self.kind not in CATEGORY_KINDS:
            raise RuleError(
                f"category {self.name!r}: unknown kind {self.kind!r}; "
                f"expected one of {sorted(CATEGORY_KINDS)}"
            )

    @property
    def counts_as_spending(self) -> bool:
        return self.kind not in NON_SPEND_CATEGORY_KINDS


@dataclass(frozen=True)
class Rule:
    """One pattern -> one category.

    `priority` orders rules, lower first; `id` breaks ties and is assigned from
    the order rules appear in the file, so precedence is reviewable by reading
    the file top to bottom.
    """

    pattern: str
    match: str
    category: str
    priority: int = 100
    kind_filter: str | None = None
    note: str | None = None
    id: int = 0

    def __post_init__(self) -> None:
        if not self.pattern:
            raise RuleError("a rule needs a pattern")
        if self.match not in MATCH_TYPES:
            raise RuleError(
                f"rule {self.pattern!r}: unknown match type {self.match!r}; "
                f"expected one of {sorted(MATCH_TYPES)}"
            )
        if not self.category.strip():
            raise RuleError(f"rule {self.pattern!r}: no category")

    @property
    def key(self) -> tuple[str, str, str | None]:
        """Identity for duplicate detection."""
        return (self.pattern, self.match, self.kind_filter)

    def with_id(self, value: int) -> "Rule":
        return replace(self, id=value)


@dataclass(frozen=True)
class Candidate:
    """Everything a rule is allowed to see about a transaction.

    Deliberately narrow: a rule cannot reach the date, the balance or the
    account, so categorisation cannot drift with time or depend on import
    order. Same candidate, same answer, forever.
    """

    description_norm: str
    kind: str = ""
    amount_cents: int = 0


@dataclass(frozen=True)
class Decision:
    """What the categoriser concluded, and which rule is responsible."""

    category: str | None
    rule_id: int | None = None
    reason: str = "no_match"      # 'rule' | 'no_match'

    @property
    def categorised(self) -> bool:
        return self.category is not None


#: A decision meaning "nothing matched". A singleton so callers can compare.
NO_MATCH: Final = Decision(category=None, rule_id=None, reason="no_match")
