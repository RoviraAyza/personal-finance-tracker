"""Transaction identity.

The central fact: two rows that look identical in date, amount and merchant
may be two real purchases. 98 such pairs exist in nine years of real data, so
identity must come from the whole row, not a chosen subset.
"""

from __future__ import annotations

from pf.ingest.identity import row_hash

ACCOUNT = "2100 9999 11 2200000000"


def _cells(balance: str = "978.22", desc: str = "CAFETERIA EL OLIV") -> list[str]:
    """A row shaped like the real export's 25 columns."""
    cells = [""] * 25
    cells[1] = ACCOUNT
    cells[4] = "04/06/2026"
    cells[5] = "04/06/2026"
    cells[7] = "2.30"
    cells[8] = balance
    cells[10] = "12"
    cells[11] = "040"
    cells[14] = desc
    return cells


def test_identical_rows_hash_identically():
    assert row_hash(_cells(), ACCOUNT) == row_hash(_cells(), ACCOUNT)


def test_two_identical_looking_purchases_are_distinct():
    # THE important one. Same day, same amount, same bar -- two real coffees,
    # distinguished only by the running balance. A key of
    # (date, amount, merchant) would collapse these into one and silently
    # delete a genuine transaction. This happens 98 times in the real data.
    first = row_hash(_cells(balance="978.22"), ACCOUNT)
    second = row_hash(_cells(balance="980.52"), ACCOUNT)
    assert first != second


def test_a_change_in_any_cell_changes_the_hash():
    baseline = row_hash(_cells(), ACCOUNT)
    for index in range(25):
        mutated = _cells()
        mutated[index] = (mutated[index] or "") + "X"
        assert row_hash(mutated, ACCOUNT) != baseline, f"column {index} ignored"


def test_the_account_participates_in_the_hash():
    # The same figures in two different accounts are two transactions.
    same_cells = _cells()
    assert row_hash(same_cells, ACCOUNT) != row_hash(same_cells, "2100 0000 11 1100000000")


def test_surrounding_whitespace_is_irrelevant():
    # The export pads cells; padding is presentation, not content.
    padded = [f"   {c}   " if c else c for c in _cells()]
    assert row_hash(padded, ACCOUNT) == row_hash(_cells(), ACCOUNT)
    assert row_hash(_cells(), f"  {ACCOUNT}  ") == row_hash(_cells(), ACCOUNT)


def test_trailing_empty_columns_do_not_affect_identity():
    # Excel does not store trailing empty columns, so the same export can
    # report 24 or 25 columns. Without this, one transaction would hash two
    # different ways and import twice.
    short = _cells()
    long = _cells() + ["", "", ""]
    assert row_hash(short, ACCOUNT) == row_hash(long, ACCOUNT)


def test_a_change_in_the_last_meaningful_cell_still_counts():
    # Trimming trailing blanks must not swallow real content at the end.
    baseline = _cells()
    changed = _cells()
    changed[24] = "SOMETHING"
    assert row_hash(changed, ACCOUNT) != row_hash(baseline, ACCOUNT)


def test_cells_cannot_run_together():
    # Joining with a separator matters: without one, ('AB','C') and ('A','BC')
    # would produce the same hash.
    assert row_hash(["AB", "C"], ACCOUNT) != row_hash(["A", "BC"], ACCOUNT)


def test_hash_is_hex_sha256():
    value = row_hash(_cells(), ACCOUNT)
    assert len(value) == 64
    assert all(c in "0123456789abcdef" for c in value)


def test_hash_scheme_is_pinned():
    # A hard-coded expected value, so that ANY future change to how rows are
    # hashed fails here loudly. Without this, changing the scheme would make
    # every already-imported transaction look new on the next import, and the
    # database would silently double.
    assert row_hash(["a", "b"], "ACC") == (
        "277869abdfc50f14f634dfa4babe066a89714658b3c9c21bf611013c6e6835d6"
    )
