"""Writing categories onto transactions.

The promise with no exceptions: a manual decision is never overwritten.
"""

from __future__ import annotations

import pytest

from pf.db.connection import open_initialised
from pf.rules.apply import apply_rules, sync_rule_set
from pf.rules.categorizer import Categorizer
from pf.rules.model import Category, Rule

CATS = [
    Category("Groceries"),
    Category("Eating out"),
    Category("Transfers", kind="transfer"),
    Category("Food"),
]


@pytest.fixture
def con():
    connection = open_initialised(":memory:")
    connection.execute(
        "INSERT INTO accounts (id, account_number, label) VALUES (1, 'ACC', 'ACC')"
    )
    yield connection
    connection.close()


def add(con, row_hash, description, kind="card_purchase", cents=-1000):
    con.execute(
        """INSERT INTO transactions (
               row_hash, account_id, date_op, date_value, amount_cents, kind,
               code_common, code_own, description_raw, description_norm,
               source_file, imported_at
           ) VALUES (?,1,'2026-06-04','2026-06-04',?,?,'12','040',?,?,'f','now')""",
        (row_hash, cents, kind, description, description),
    )


def build(con, *rules):
    numbered = [r.with_id(i + 1) for i, r in enumerate(rules)]
    categorizer = Categorizer(CATS, numbered)
    cat_ids, rule_ids = sync_rule_set(con, CATS, numbered)
    return categorizer, cat_ids, rule_ids


def category_of(con, row_hash):
    row = con.execute(
        """SELECT c.name FROM transactions t
           LEFT JOIN categories c ON c.id = t.category_id
           WHERE t.row_hash = ?""",
        (row_hash,),
    ).fetchone()
    return row["name"]


# --------------------------------------------------------------------------
# The promise
# --------------------------------------------------------------------------


def test_a_manual_decision_is_never_overwritten(con):
    add(con, "h1", "MERCADONA PLAZA")
    categorizer, cat_ids, rule_ids = build(con, Rule("MERCADONA", "contains", "Groceries"))
    con.execute(
        "UPDATE transactions SET category_id = ?, categorized_by = 'manual'",
        (cat_ids["Eating out"],),
    )
    apply_rules(con, categorizer, cat_ids, rule_ids, only_uncategorised=False)
    assert category_of(con, "h1") == "Eating out"


def test_a_manual_decision_survives_even_a_full_reapply(con):
    # --all exists to re-apply after editing rules. It must still not touch
    # anything the user decided himself.
    add(con, "h1", "SOMETHING ODD")
    categorizer, cat_ids, rule_ids = build(con, Rule("SOMETHING", "contains", "Groceries"))
    con.execute(
        "UPDATE transactions SET category_id = ?, categorized_by = 'manual'",
        (cat_ids["Transfers"],),
    )
    result = apply_rules(con, categorizer, cat_ids, rule_ids, only_uncategorised=False)
    assert category_of(con, "h1") == "Transfers"
    assert result.left_alone == 1


# --------------------------------------------------------------------------
# Ordinary application
# --------------------------------------------------------------------------


def test_matching_rows_are_categorised(con):
    add(con, "h1", "MERCADONA PLAZA")
    add(con, "h2", "CAFETERIA SUR")
    categorizer, cat_ids, rule_ids = build(
        con,
        Rule("MERCADONA", "contains", "Groceries"),
        Rule("CAFETERIA", "contains", "Eating out"),
    )
    result = apply_rules(con, categorizer, cat_ids, rule_ids)
    assert result.assigned == 2
    assert category_of(con, "h1") == "Groceries"
    assert category_of(con, "h2") == "Eating out"


def test_rows_matching_nothing_stay_uncategorised(con):
    add(con, "h1", "A SHOP NOBODY KNOWS")
    categorizer, cat_ids, rule_ids = build(con, Rule("MERCADONA", "contains", "Groceries"))
    result = apply_rules(con, categorizer, cat_ids, rule_ids)
    assert result.assigned == 0
    assert result.still_uncategorised == 1
    assert category_of(con, "h1") is None


def test_the_rule_that_decided_is_recorded(con):
    # So the UI can answer "why is this here?" without re-running matching.
    add(con, "h1", "MERCADONA PLAZA")
    categorizer, cat_ids, rule_ids = build(con, Rule("MERCADONA", "contains", "Groceries"))
    apply_rules(con, categorizer, cat_ids, rule_ids)
    row = con.execute(
        "SELECT rule_id, categorized_by FROM transactions WHERE row_hash='h1'"
    ).fetchone()
    assert row["rule_id"] is not None
    assert row["categorized_by"] == "rule"


def test_running_twice_changes_nothing_the_second_time(con):
    add(con, "h1", "MERCADONA PLAZA")
    categorizer, cat_ids, rule_ids = build(con, Rule("MERCADONA", "contains", "Groceries"))
    apply_rules(con, categorizer, cat_ids, rule_ids, only_uncategorised=False)
    second = apply_rules(con, categorizer, cat_ids, rule_ids, only_uncategorised=False)
    assert second.assigned == 0
    assert second.changed == 0
    assert second.unchanged == 1


def test_default_run_only_touches_uncategorised_rows(con):
    add(con, "h1", "MERCADONA PLAZA")
    categorizer, cat_ids, rule_ids = build(con, Rule("MERCADONA", "contains", "Groceries"))
    apply_rules(con, categorizer, cat_ids, rule_ids)
    result = apply_rules(con, categorizer, cat_ids, rule_ids)      # default
    assert result.considered == 0


def test_a_reapply_moves_a_row_when_the_rules_changed(con):
    add(con, "h1", "MERCADONA PLAZA")
    first, cat_ids, rule_ids = build(con, Rule("MERCADONA", "contains", "Groceries"))
    apply_rules(con, first, cat_ids, rule_ids)
    assert category_of(con, "h1") == "Groceries"

    second, cat_ids, rule_ids = build(con, Rule("MERCADONA", "contains", "Eating out"))
    result = apply_rules(con, second, cat_ids, rule_ids, only_uncategorised=False)
    assert result.changed == 1
    assert category_of(con, "h1") == "Eating out"


def test_a_row_becomes_uncategorised_again_when_its_rule_is_deleted(con):
    add(con, "h1", "MERCADONA PLAZA")
    first, cat_ids, rule_ids = build(con, Rule("MERCADONA", "contains", "Groceries"))
    apply_rules(con, first, cat_ids, rule_ids)

    second, cat_ids, rule_ids = build(con, Rule("SOMETHINGELSE", "contains", "Groceries"))
    result = apply_rules(con, second, cat_ids, rule_ids, only_uncategorised=False)
    assert result.cleared == 1
    assert category_of(con, "h1") is None


# --------------------------------------------------------------------------
# Structural fallbacks (the `any` match type)
# --------------------------------------------------------------------------


def test_a_row_with_no_description_can_still_be_categorised(con):
    # 155 real rows have no description at all. Only a kind-based rule can
    # reach them.
    add(con, "h1", "", kind="transfer_person")
    categorizer, cat_ids, rule_ids = build(
        con,
        Rule("*", "any", "Transfers", priority=900, kind_filter="transfer_person"),
    )
    result = apply_rules(con, categorizer, cat_ids, rule_ids)
    assert result.assigned == 1
    assert category_of(con, "h1") == "Transfers"


def test_a_merchant_rule_still_beats_the_structural_fallback(con):
    add(con, "h1", "MERCADONA PLAZA", kind="card_purchase")
    categorizer, cat_ids, rule_ids = build(
        con,
        Rule("MERCADONA", "contains", "Groceries", priority=100),
        Rule("*", "any", "Transfers", priority=900),
    )
    apply_rules(con, categorizer, cat_ids, rule_ids)
    assert category_of(con, "h1") == "Groceries"


# --------------------------------------------------------------------------
# Syncing the files into the database
# --------------------------------------------------------------------------


def test_categories_and_parents_are_synced(con):
    cats = [Category("Food"), Category("Groceries", parent="Food")]
    sync_rule_set(con, cats, [])
    row = con.execute(
        """SELECT c.name, p.name AS parent FROM categories c
           LEFT JOIN categories p ON p.id = c.parent_id
           WHERE c.name = 'Groceries'"""
    ).fetchone()
    assert row["parent"] == "Food"


def test_parent_order_in_the_file_does_not_matter(con):
    # The child is listed before its parent.
    cats = [Category("Groceries", parent="Food"), Category("Food")]
    sync_rule_set(con, cats, [])
    row = con.execute(
        """SELECT p.name AS parent FROM categories c
           LEFT JOIN categories p ON p.id = c.parent_id
           WHERE c.name = 'Groceries'"""
    ).fetchone()
    assert row["parent"] == "Food"


def test_a_rule_removed_from_the_file_disappears_from_the_database(con):
    # The file is the authority. A deleted rule must not linger.
    build(con, Rule("A", "contains", "Groceries"), Rule("B", "contains", "Groceries"))
    assert con.execute("SELECT COUNT(*) AS n FROM rules").fetchone()["n"] == 2
    build(con, Rule("A", "contains", "Groceries"))
    assert con.execute("SELECT COUNT(*) AS n FROM rules").fetchone()["n"] == 1


def test_syncing_twice_does_not_duplicate_categories(con):
    sync_rule_set(con, CATS, [])
    sync_rule_set(con, CATS, [])
    assert con.execute("SELECT COUNT(*) AS n FROM categories").fetchone()["n"] == len(CATS)
