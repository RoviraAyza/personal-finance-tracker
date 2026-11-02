"""Importing into the database.

The behaviour these tests protect: importing twice must change nothing, and
nothing unusable may disappear quietly.
"""

from __future__ import annotations

import pytest

from pf.db.connection import open_initialised
from pf.ingest import kinds
from pf.ingest.importer import import_file, parse_row
from pf.ingest.model import RowError
from pf.ingest.reader import read_rows
from tests.fixtures.make_xls import row, simple_file, write_xls


@pytest.fixture
def con():
    connection = open_initialised(":memory:")
    yield connection
    connection.close()


def _count(con) -> int:
    return con.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()["n"]


# --------------------------------------------------------------------------
# The core promise: idempotency
# --------------------------------------------------------------------------


def test_imports_every_usable_row(con, tmp_path):
    path = simple_file(tmp_path / "a.xls")
    result = import_file(path, con)
    assert result.rows_read == 7          # 6 data rows + the trailing blank
    assert result.inserted == 6
    assert result.rejected == 1           # the blank
    assert _count(con) == 6


def test_importing_the_same_file_twice_changes_nothing(con, tmp_path):
    # The export is a date-range query, so overlapping requests will happen
    # by accident. This is the behaviour that makes that harmless.
    path = simple_file(tmp_path / "a.xls")
    first = import_file(path, con)
    second = import_file(path, con)
    assert first.inserted == 6
    assert second.inserted == 0
    assert second.skipped == 6
    assert _count(con) == 6


def test_overlapping_ranges_insert_only_the_new_rows(con, tmp_path):
    shared = row(date_op="04/06/2026", description="MERCADONA", expense=10.0, balance=100.0)
    only_in_first = row(date_op="03/06/2026", description="BON AREA", expense=5.0, balance=110.0)
    only_in_second = row(date_op="05/06/2026", description="ZARA", expense=20.0, balance=80.0)

    first = write_xls(tmp_path / "first.xls", [only_in_first, shared], trailing_blank_row=False)
    second = write_xls(tmp_path / "second.xls", [shared, only_in_second], trailing_blank_row=False)

    assert import_file(first, con).inserted == 2
    result = import_file(second, con)
    assert result.inserted == 1            # only ZARA is new
    assert result.skipped == 1             # MERCADONA was already there
    assert _count(con) == 3


def test_two_identical_looking_purchases_both_survive(con, tmp_path):
    # Same day, same amount, same merchant, different balance: two real
    # coffees. 98 such pairs exist in nine years of real statements.
    path = simple_file(tmp_path / "a.xls")
    import_file(path, con)
    found = con.execute(
        """SELECT COUNT(*) AS n FROM transactions
           WHERE date_op = '2026-06-04' AND amount_cents = -230"""
    ).fetchone()["n"]
    assert found == 2


# --------------------------------------------------------------------------
# Nothing disappears quietly
# --------------------------------------------------------------------------


def test_a_blank_trailing_row_alone_writes_no_rejects_file(con, tmp_path):
    # Every export ends with one blank row. Writing a CSV for that alone would
    # litter a useless file after every single import.
    rejects = tmp_path / "rejects"
    path = simple_file(tmp_path / "a.xls")
    result = import_file(path, con, rejects_dir=rejects)
    assert result.rejected == 1
    assert result.rejections[0].reason == "empty_row"
    assert result.rejects_path is None
    assert not rejects.exists()


def test_real_rejections_are_counted_and_written(con, tmp_path):
    # Anything rejected for a reason worth investigating does get written out.
    rejects = tmp_path / "rejects"
    path = write_xls(
        tmp_path / "bad.xls",
        [
            row(date_op="04/06/2026", description="GOOD", expense=1.0, balance=10.0),
            row(date_op="not-a-date", description="BAD", expense=1.0, balance=9.0),
        ],
    )
    result = import_file(path, con, rejects_dir=rejects)
    assert result.rejected == 2                 # the bad date and the blank row
    assert result.rejects_path is not None
    written = list(rejects.glob("rejects-*.csv"))
    assert len(written) == 1
    body = written[0].read_text(encoding="utf-8")
    assert "bad_date" in body
    assert "empty_row" in body                  # still listed, just not alone


def test_a_row_with_no_amount_is_rejected_not_stored(con, tmp_path):
    path = write_xls(
        tmp_path / "noamount.xls",
        [row(date_op="04/06/2026", description="MYSTERY", balance=100.0)],
        trailing_blank_row=False,
    )
    result = import_file(path, con)
    assert result.inserted == 0
    assert result.rejected == 1
    assert result.rejections[0].reason == "no_amount"


def test_one_bad_row_does_not_abort_the_import(con, tmp_path):
    good = row(date_op="04/06/2026", description="MERCADONA", expense=10.0, balance=100.0)
    bad = row(date_op="not-a-date", description="BROKEN", expense=1.0, balance=99.0)
    also_good = row(date_op="05/06/2026", description="ZARA", expense=20.0, balance=79.0)
    path = write_xls(tmp_path / "mixed.xls", [good, bad, also_good], trailing_blank_row=False)
    result = import_file(path, con)
    assert result.inserted == 2
    assert result.rejected == 1
    assert result.rejections[0].reason == "bad_date"


def test_unmapped_kinds_are_reported(con, tmp_path):
    path = write_xls(
        tmp_path / "weird.xls",
        [
            row(
                date_op="04/06/2026",
                description="SOMETHING NEW",
                expense=10.0,
                balance=100.0,
                code_common="77",
                code_own="999",
                type_label="UNKNOWN THING",
            )
        ],
        trailing_blank_row=False,
    )
    result = import_file(path, con)
    assert result.inserted == 1
    assert result.unmapped_kinds[("77", "999")] == 1


# --------------------------------------------------------------------------
# What gets stored
# --------------------------------------------------------------------------


def test_accounts_are_created_on_first_sight(con, tmp_path):
    path = simple_file(tmp_path / "a.xls")
    import_file(path, con)
    accounts = con.execute("SELECT account_number FROM accounts").fetchall()
    assert len(accounts) == 1
    assert accounts[0]["account_number"] == "2100 9999 11 2200000000"


def test_nothing_is_categorised_by_s1(con, tmp_path):
    # Categorisation is S2. S1 must leave every row uncategorised, so that
    # the coverage measurement in S2 starts from an honest zero.
    path = simple_file(tmp_path / "a.xls")
    import_file(path, con)
    rows = con.execute(
        "SELECT category_id, categorized_by, rule_id FROM transactions"
    ).fetchall()
    assert all(r["category_id"] is None for r in rows)
    assert all(r["rule_id"] is None for r in rows)
    assert all(r["categorized_by"] == "none" for r in rows)


def test_amounts_are_signed_by_direction(con, tmp_path):
    path = simple_file(tmp_path / "a.xls")
    import_file(path, con)
    outgoing = con.execute(
        "SELECT amount_cents FROM transactions WHERE description_norm LIKE 'MERCADONA%'"
    ).fetchone()["amount_cents"]
    incoming = con.execute(
        "SELECT amount_cents FROM transactions WHERE kind = ?", (kinds.TRANSFER_OWN,)
    ).fetchone()["amount_cents"]
    assert outgoing == -6268
    assert incoming == 80000


def test_the_banks_tilde_damage_is_repaired_in_storage(con, tmp_path):
    path = simple_file(tmp_path / "a.xls")
    import_file(path, con)
    stored = con.execute(
        "SELECT description_raw, description_norm FROM transactions "
        "WHERE description_norm LIKE '%CONSUM%'"
    ).fetchone()
    assert "ã" in stored["description_raw"]        # original kept as-is
    assert stored["description_norm"] == "0150-CONSUM PENIS"


def test_import_runs_are_recorded(con, tmp_path):
    path = simple_file(tmp_path / "a.xls")
    import_file(path, con)
    import_file(path, con)
    runs = con.execute("SELECT * FROM import_runs ORDER BY id").fetchall()
    assert len(runs) == 2
    assert runs[0]["rows_inserted"] == 6
    assert runs[1]["rows_inserted"] == 0
    assert runs[1]["rows_skipped"] == 6
    assert runs[0]["file_sha256"] == runs[1]["file_sha256"]


def test_date_range_is_reported(con, tmp_path):
    path = simple_file(tmp_path / "a.xls")
    result = import_file(path, con)
    assert result.date_min == "2026-06-04"
    assert result.date_max == "2026-06-08"


# --------------------------------------------------------------------------
# Dry run
# --------------------------------------------------------------------------


def test_dry_run_writes_nothing(con, tmp_path):
    path = simple_file(tmp_path / "a.xls")
    result = import_file(path, con, dry_run=True)
    assert result.inserted == 6            # what it WOULD insert
    assert _count(con) == 0                # but nothing was written
    assert con.execute("SELECT COUNT(*) AS n FROM import_runs").fetchone()["n"] == 0


def test_dry_run_distinguishes_new_rows_from_known_ones(con, tmp_path):
    path = simple_file(tmp_path / "a.xls")
    import_file(path, con)
    result = import_file(path, con, dry_run=True)
    assert result.inserted == 0
    assert result.skipped == 6


# --------------------------------------------------------------------------
# parse_row directly
# --------------------------------------------------------------------------


def test_missing_value_date_falls_back_to_operation_date(tmp_path):
    path = write_xls(
        tmp_path / "novalue.xls",
        [row(date_op="04/06/2026", description="X", expense=1.0, date_value="")],
        trailing_blank_row=False,
    )
    parsed = parse_row(next(iter(read_rows(path))))
    assert parsed.date_value == parsed.date_op == "2026-06-04"


def test_empty_row_raises_empty_row(tmp_path):
    path = simple_file(tmp_path / "a.xls")
    blank = list(read_rows(path))[-1]
    with pytest.raises(RowError) as err:
        parse_row(blank)
    assert err.value.reason == "empty_row"
