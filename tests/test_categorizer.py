"""The categoriser: pure, deterministic, explainable.

Nothing here touches a file or a database.
"""

from __future__ import annotations

import pytest

from pf.rules.categorizer import Categorizer
from pf.rules.model import Candidate, Category, Rule, RuleError

GROCERIES = Category("Groceries")
EATING_OUT = Category("Eating out")
TRANSFERS = Category("Transfers", kind="transfer")
CATS = [GROCERIES, EATING_OUT, TRANSFERS]


def make(*rules: Rule, categories=None) -> Categorizer:
    """Build a categoriser, assigning ids in the order rules are given."""
    numbered = [r.with_id(i + 1) for i, r in enumerate(rules)]
    return Categorizer(categories or CATS, numbered)


def cand(description: str, kind: str = "card_purchase", cents: int = -1000) -> Candidate:
    return Candidate(description_norm=description, kind=kind, amount_cents=cents)


# --------------------------------------------------------------------------
# Match types
# --------------------------------------------------------------------------


def test_exact_match():
    c = make(Rule("MERCADONA", "exact", "Groceries"))
    assert c.categorize(cand("MERCADONA")).category == "Groceries"
    assert c.categorize(cand("MERCADONA PLAZA D")).category is None


def test_prefix_match_handles_the_banks_truncation():
    # Card-purchase merchant names are cut at 17 characters, so a prefix rule
    # is the natural way to write one. Measured safe: zero genuine merchant
    # collisions among 1,082 strings.
    c = make(Rule("FRUTOS SECOS EL R", "prefix", "Groceries"))
    assert c.categorize(cand("FRUTOS SECOS EL R")).category == "Groceries"


def test_contains_match():
    c = make(Rule("CAFETERIA", "contains", "Eating out"))
    assert c.categorize(cand("CAFETERIA EL OLIV")).category == "Eating out"
    assert c.categorize(cand("BAR CAFETERIA SUR")).category == "Eating out"


def test_regex_match():
    c = make(Rule(r"^CORE(IBERDROLA|ENDESA)", "regex", "Groceries"))
    assert c.categorize(cand("COREIBERDROLA COMER")).category == "Groceries"
    assert c.categorize(cand("OTHER THING")).category is None


def test_unknown_match_type_is_rejected_when_the_rule_is_built():
    with pytest.raises(RuleError) as err:
        Rule("X", "fuzzy", "Groceries")
    assert "fuzzy" in str(err.value)


def test_invalid_regex_fails_at_construction_not_mid_run():
    # A bad pattern must not surface half-way through ten thousand rows.
    with pytest.raises(RuleError) as err:
        make(Rule("[unclosed", "regex", "Groceries"))
    assert "regex" in str(err.value)


# --------------------------------------------------------------------------
# Precedence
# --------------------------------------------------------------------------


def test_lower_priority_number_wins():
    c = make(
        Rule("MERCADONA", "contains", "Eating out", priority=200),
        Rule("MERCADONA", "contains", "Groceries", priority=100),
    )
    assert c.categorize(cand("MERCADONA PLAZA D")).category == "Groceries"


def test_equal_priority_is_broken_by_file_order():
    # Rule ids come from the order they appear in the file, so precedence can
    # be understood by reading the file top to bottom.
    c = make(
        Rule("MERCADONA", "contains", "Groceries"),
        Rule("MERCADONA", "contains", "Eating out"),
    )
    decision = c.categorize(cand("MERCADONA PLAZA D"))
    assert decision.category == "Groceries"
    assert decision.rule_id == 1


def test_first_match_wins_and_names_its_rule():
    c = make(
        Rule("CAFETERIA", "contains", "Eating out"),
        Rule("EL OLIV", "contains", "Groceries"),
    )
    decision = c.categorize(cand("CAFETERIA EL OLIV"))
    assert decision.category == "Eating out"
    assert decision.rule_id == 1
    assert decision.reason == "rule"


def test_rules_are_exposed_in_precedence_order():
    c = make(
        Rule("B", "contains", "Groceries", priority=200),
        Rule("A", "contains", "Groceries", priority=100),
    )
    assert [r.pattern for r in c.rules] == ["A", "B"]


# --------------------------------------------------------------------------
# No match
# --------------------------------------------------------------------------


def test_no_match_is_explicit():
    c = make(Rule("MERCADONA", "contains", "Groceries"))
    decision = c.categorize(cand("SOMETHING ELSE"))
    assert decision.category is None
    assert decision.rule_id is None
    assert decision.reason == "no_match"
    assert decision.categorised is False


def test_empty_description_never_matches_and_does_not_crash():
    # 157 real rows have no description at all.
    c = make(Rule("MERCADONA", "contains", "Groceries"))
    assert c.categorize(cand("")).category is None


def test_no_rules_at_all_is_fine():
    c = Categorizer(CATS, [])
    assert c.categorize(cand("ANYTHING")).category is None


# --------------------------------------------------------------------------
# kind_filter
# --------------------------------------------------------------------------


def test_kind_filter_restricts_a_rule_to_one_transaction_kind():
    # A person's name means a transfer, not a shop. The bank's codes already
    # tell us the kind, so a rule can be scoped to it.
    c = make(Rule("PEYRONA", "contains", "Transfers", kind_filter="transfer_person"))
    assert c.categorize(cand("PEYRONA NAVALLAS", kind="transfer_person")).category == "Transfers"
    assert c.categorize(cand("PEYRONA NAVALLAS", kind="card_purchase")).category is None


def test_a_rule_without_a_kind_filter_applies_to_every_kind():
    c = make(Rule("MERCADONA", "contains", "Groceries"))
    for kind in ["card_purchase", "cash_withdrawal", "transfer_person", "other"]:
        assert c.categorize(cand("MERCADONA PLAZA", kind=kind)).category == "Groceries"


# --------------------------------------------------------------------------
# The `any` match type: structural fallbacks
# --------------------------------------------------------------------------


def test_any_matches_regardless_of_description():
    c = make(Rule("*", "any", "Transfers", priority=900, kind_filter="transfer_person"))
    assert c.categorize(cand("WHATEVER", kind="transfer_person")).category == "Transfers"


def test_any_reaches_rows_with_no_description_at_all():
    # 155 real rows have an empty description. Every other match type gives up
    # on them, so this is the only way they can ever be categorised.
    c = make(Rule("*", "any", "Transfers", priority=900, kind_filter="transfer_person"))
    assert c.categorize(cand("", kind="transfer_person")).category == "Transfers"


def test_any_still_respects_its_kind_filter():
    c = make(Rule("*", "any", "Transfers", priority=900, kind_filter="transfer_person"))
    assert c.categorize(cand("", kind="card_purchase")).category is None


def test_a_merchant_rule_beats_a_structural_fallback():
    # The fallback sits at priority 900 precisely so it never pre-empts a real
    # merchant rule.
    c = make(
        Rule("MERCADONA", "contains", "Groceries", priority=100),
        Rule("*", "any", "Transfers", priority=900),
    )
    assert c.categorize(cand("MERCADONA PLAZA")).category == "Groceries"
    assert c.categorize(cand("ANYTHING ELSE")).category == "Transfers"


# --------------------------------------------------------------------------
# The known hazard, documented rather than wished away
# --------------------------------------------------------------------------


def test_contains_rules_can_over_reach():
    # 'EL ARBOL' also matches 'EL ARBOLITO', which may be a different shop.
    # This is a real hazard of `contains`, recorded here so nobody is
    # surprised by it. S4's rule preview is the mitigation.
    c = make(Rule("EL ARBOL", "contains", "Groceries"))
    assert c.categorize(cand("EL ARBOL 5228")).category == "Groceries"
    assert c.categorize(cand("EL ARBOLITO BAR")).category == "Groceries"   # !


# --------------------------------------------------------------------------
# explain()
# --------------------------------------------------------------------------


def test_explain_returns_every_match_in_precedence_order():
    c = make(
        Rule("CAFETERIA", "contains", "Eating out", priority=100),
        Rule("EL OLIV", "contains", "Groceries", priority=200),
    )
    matched = c.explain(cand("CAFETERIA EL OLIV"))
    assert [r.pattern for r in matched] == ["CAFETERIA", "EL OLIV"]


def test_explain_reveals_a_shadowed_rule():
    # The reason explain() exists: the second rule is the one the user thinks
    # is in charge, and it never fires. Without this the categorisation looks
    # arbitrary.
    c = make(
        Rule("MERCADONA", "contains", "Eating out", priority=50),
        Rule("MERCADONA PLAZA D", "exact", "Groceries", priority=100),
    )
    assert c.categorize(cand("MERCADONA PLAZA D")).category == "Eating out"
    assert len(c.explain(cand("MERCADONA PLAZA D"))) == 2


def test_explain_returns_empty_when_nothing_matches():
    c = make(Rule("MERCADONA", "contains", "Groceries"))
    assert c.explain(cand("NOTHING")) == []


# --------------------------------------------------------------------------
# Rules that do nothing
# --------------------------------------------------------------------------


def test_unused_rules_are_reported():
    # A rule that never fires looks like coverage but is not. Usually a typo.
    c = make(
        Rule("MERCADONA", "contains", "Groceries"),
        Rule("MERCDONA", "contains", "Groceries"),        # typo
    )
    unused = c.unused_rules([cand("MERCADONA PLAZA D"), cand("BON AREA")])
    assert [r.pattern for r in unused] == ["MERCDONA"]


def test_no_unused_rules_when_everything_fires():
    c = make(
        Rule("MERCADONA", "contains", "Groceries"),
        Rule("BON AREA", "contains", "Groceries"),
    )
    assert c.unused_rules([cand("MERCADONA PLAZA"), cand("BON AREA 12")]) == []


def test_shadowed_rules_are_detectable():
    c = make(
        Rule("MERCADONA", "contains", "Groceries", priority=50),
        Rule("MERCADONA PLAZA D", "exact", "Eating out", priority=100),
    )
    pairs = c.shadowed_rules()
    assert len(pairs) == 1
    earlier, later = pairs[0]
    assert earlier.pattern == "MERCADONA"
    assert later.pattern == "MERCADONA PLAZA D"


# --------------------------------------------------------------------------
# Category validation
# --------------------------------------------------------------------------


def test_a_rule_naming_an_unknown_category_is_rejected():
    with pytest.raises(RuleError) as err:
        make(Rule("X", "contains", "Nonexistent"))
    assert "Nonexistent" in str(err.value)


def test_category_kinds_are_validated():
    with pytest.raises(RuleError):
        Category("Weird", kind="sideways")


def test_transfer_categories_do_not_count_as_spending():
    assert TRANSFERS.counts_as_spending is False
    assert GROCERIES.counts_as_spending is True


# --------------------------------------------------------------------------
# Determinism
# --------------------------------------------------------------------------


def test_the_same_candidate_always_gets_the_same_answer():
    c = make(
        Rule("CAFETERIA", "contains", "Eating out"),
        Rule("MERCADONA", "contains", "Groceries"),
    )
    candidate = cand("CAFETERIA EL OLIV")
    answers = {c.categorize(candidate) for _ in range(50)}
    assert len(answers) == 1


def test_a_rule_cannot_see_the_date_or_balance():
    # Candidate carries only description, kind and amount. If a rule could
    # reach the date, categorisation would drift as time passed.
    assert set(Candidate.__dataclass_fields__) == {
        "description_norm",
        "kind",
        "amount_cents",
    }
