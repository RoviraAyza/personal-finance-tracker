"""Measuring coverage.

These numbers are the slice's verdict, so what they include and exclude
matters more than usual.
"""

from __future__ import annotations

import pytest

from pf.db.connection import open_initialised
from pf.rules import coverage as cov


@pytest.fixture
def con():
    connection = open_initialised(":memory:")
    connection.execute(
        "INSERT INTO accounts (id, account_number, label) VALUES (1, 'ACC', 'ACC')"
    )
    connection.execute("INSERT INTO categories (id, name, kind) VALUES (1, 'Groceries', 'spending')")
    connection.execute("INSERT INTO categories (id, name, kind) VALUES (2, 'Transfers', 'transfer')")
    yield connection
    connection.close()


def add(con, row_hash, cents, *, category=None, kind="card_purchase",
        date="2026-06-04", description="A SHOP"):
    con.execute(
        """INSERT INTO transactions (
               row_hash, account_id, date_op, date_value, amount_cents, kind,
               code_common, code_own, description_raw, description_norm,
               category_id, categorized_by, source_file, imported_at
           ) VALUES (?,1,?,?,?,?,'12','040',?,?,?,?,'f','now')""",
        (row_hash, date, date, cents, kind, description, description,
         category, "rule" if category else "none"),
    )


# --------------------------------------------------------------------------
# The arithmetic
# --------------------------------------------------------------------------


def test_percentages_are_computed_for_rows_and_value(con):
    add(con, "h1", -1000, category=1)
    add(con, "h2", -3000, category=1)
    add(con, "h3", -6000)                       # uncategorised
    m = cov.measure(con)
    assert m.rows_total == 3
    assert m.rows_categorised == 2
    assert round(m.rows_pct, 1) == 66.7
    assert m.value_total_cents == 10000
    assert m.value_categorised_cents == 4000
    assert m.value_pct == 40.0


def test_value_is_the_stricter_measure(con):
    # Two thirds of rows categorised, but only a small fraction of the money.
    # This is why both are reported: a rule set can look good by row count
    # while leaving the expensive things unexplained.
    add(con, "h1", -100, category=1)
    add(con, "h2", -100, category=1)
    add(con, "h3", -9800)
    m = cov.measure(con)
    assert round(m.rows_pct) == 67
    assert round(m.value_pct) == 2


def test_incoming_money_is_not_counted(con):
    # Coverage is about spending. Income and refunds are not spending.
    add(con, "h1", -1000, category=1)
    add(con, "h2", 50000, kind="transfer_in")
    m = cov.measure(con)
    assert m.rows_total == 1
    assert m.value_total_cents == 1000


def test_own_transfers_are_excluded_entirely(con):
    # Moving money between the household's own accounts is not spending, and
    # counting it would both inflate the denominator and flatter the result.
    add(con, "h1", -1000, category=1)
    add(con, "h2", -500000, kind="transfer_own", category=2)
    m = cov.measure(con)
    assert m.rows_total == 1
    assert m.value_total_cents == 1000


def test_an_empty_database_reports_zero_not_an_error(con):
    m = cov.measure(con)
    assert m.rows_total == 0
    assert m.rows_pct == 0.0
    assert m.value_pct == 0.0


def test_uncategorised_figures_are_derived_consistently(con):
    add(con, "h1", -1000, category=1)
    add(con, "h2", -4000)
    m = cov.measure(con)
    assert m.rows_uncategorised == 1
    assert m.value_uncategorised_cents == 4000


# --------------------------------------------------------------------------
# What it reports
# --------------------------------------------------------------------------


def test_breakdown_by_category_includes_an_uncategorised_bucket(con):
    add(con, "h1", -1000, category=1)
    add(con, "h2", -4000)
    names = dict((name, (n, v)) for name, n, v in cov.measure(con).by_category)
    assert names["Groceries"] == (1, 1000)
    assert names["(uncategorised)"] == (1, 4000)


def test_worst_uncategorised_is_ranked_by_value_not_count(con):
    # One 400 EUR unknown matters more than ten 2 EUR ones, and it is the one
    # worth writing a rule for.
    for i in range(10):
        add(con, f"small{i}", -200, description="TINY SHOP")
    add(con, "big", -40000, description="EXPENSIVE SHOP")
    worst = cov.measure(con).worst_uncategorised
    assert worst[0][0] == "EXPENSIVE SHOP"
    assert worst[1][0] == "TINY SHOP"


def test_a_date_window_narrows_the_measurement(con):
    add(con, "h1", -1000, category=1, date="2024-05-01")
    add(con, "h2", -2000, date="2026-05-01")
    assert cov.measure(con, date_from="2025-01-01").rows_total == 1
    assert cov.measure(con, date_to="2024-12-31").rows_total == 1
    assert cov.measure(con).rows_total == 2


# --------------------------------------------------------------------------
# The holdout
# --------------------------------------------------------------------------


def test_the_holdout_split_respects_the_boundary_in_both_directions(con):
    add(con, "old1", -1000, category=1, date="2023-01-01")
    add(con, "old2", -1000, category=1, date="2024-12-31")
    add(con, "new1", -1000, date="2025-01-01")
    add(con, "new2", -1000, date="2026-10-31")
    train, test = cov.measure_holdout(con, train_to="2024-12-31", test_from="2025-01-01")
    assert train.rows_total == 2 and train.rows_pct == 100.0
    assert test.rows_total == 2 and test.rows_pct == 0.0


# --------------------------------------------------------------------------
# Monthly burden
# --------------------------------------------------------------------------


def test_monthly_report_counts_unknowns_per_month(con):
    add(con, "a", -1000, category=1, date="2026-05-04")
    add(con, "b", -1000, date="2026-05-20")
    add(con, "c", -1000, category=1, date="2026-06-01")
    months = dict((m, (unknown, total)) for m, unknown, total in cov.monthly_uncategorised(con))
    assert months["2026-05"] == (1, 2)
    assert months["2026-06"] == (0, 1)
