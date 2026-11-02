"""Recomputing kinds without re-importing.

This works only because the raw source codes are stored alongside the derived
kind. These tests are the guarantee that the derivation stays correctable.
"""

from __future__ import annotations

import pytest

from pf.db.connection import open_initialised
from pf.ingest import kinds
from pf.ingest.reclassify import reclassify


@pytest.fixture
def con():
    connection = open_initialised(":memory:")
    connection.execute(
        "INSERT INTO accounts (id, account_number, label) VALUES (1, 'ACC', 'ACC')"
    )
    yield connection
    connection.close()


def add(con, row_hash, kind, common, own, label=""):
    con.execute(
        """INSERT INTO transactions (
               row_hash, account_id, date_op, date_value, amount_cents,
               kind, code_common, code_own, type_label,
               description_raw, description_norm, source_file, imported_at
           ) VALUES (?,1,'2026-06-04','2026-06-04',-1000,?,?,?,?,'D','D','f','now')""",
        (row_hash, kind, common, own, label),
    )


def kind_of(con, row_hash):
    return con.execute(
        "SELECT kind FROM transactions WHERE row_hash = ?", (row_hash,)
    ).fetchone()["kind"]


def test_a_stale_kind_is_corrected(con):
    # A direct debit stored under the old, wrong classification.
    add(con, "h1", "transfer_person", "03", "038", "SOME NAME")
    result = reclassify(con)
    assert result.changed == 1
    assert kind_of(con, "h1") == kinds.DIRECT_DEBIT


def test_correct_kinds_are_left_alone(con):
    add(con, "h1", "card_purchase", "12", "040", "COMPRA CON TARJETA")
    result = reclassify(con)
    assert result.changed == 0
    assert result.unchanged == 1
    assert kind_of(con, "h1") == kinds.CARD_PURCHASE


def test_transitions_are_reported_so_a_change_can_be_reviewed(con):
    add(con, "h1", "transfer_person", "03", "038")
    add(con, "h2", "transfer_person", "03", "005")
    add(con, "h3", "other", "17", "036", "MANTENIMIENTO")
    result = reclassify(con)
    assert result.transitions[("transfer_person", "direct_debit")] == 2
    assert result.transitions[("other", "fee")] == 1


def test_dry_run_reports_without_writing(con):
    add(con, "h1", "transfer_person", "03", "038")
    result = reclassify(con, dry_run=True)
    assert result.changed == 1
    assert kind_of(con, "h1") == "transfer_person"       # untouched


def test_running_twice_changes_nothing_the_second_time(con):
    add(con, "h1", "transfer_person", "03", "038")
    assert reclassify(con).changed == 1
    assert reclassify(con).changed == 0


def test_unmapped_codes_are_still_reported(con):
    add(con, "h1", "other", "77", "999", "WHO KNOWS")
    result = reclassify(con)
    assert result.unmapped == 1
    assert result.unmapped_codes[("77", "999")] == 1
    assert result.changed == 0                           # already 'other'


def test_an_empty_database_is_fine(con):
    result = reclassify(con)
    assert result.considered == 0
    assert result.changed == 0


def test_the_label_override_still_wins_on_reclassify(con):
    # A cash withdrawal filed under the card-purchase code.
    add(con, "h1", "card_purchase", "12", "040", "04000001TOC REINT.CAJERO")
    reclassify(con)
    assert kind_of(con, "h1") == kinds.CASH_WITHDRAWAL


def test_categories_are_not_disturbed(con):
    # Reclassifying kinds must not touch categorisation: they are separate
    # decisions, and one is the user's.
    con.execute("INSERT INTO categories (id, name) VALUES (1, 'Groceries')")
    add(con, "h1", "transfer_person", "03", "038")
    con.execute(
        "UPDATE transactions SET category_id = 1, categorized_by = 'manual'"
    )
    reclassify(con)
    row = con.execute(
        "SELECT category_id, categorized_by, kind FROM transactions"
    ).fetchone()
    assert row["category_id"] == 1
    assert row["categorized_by"] == "manual"
    assert row["kind"] == kinds.DIRECT_DEBIT
