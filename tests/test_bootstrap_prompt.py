"""The bootstrap payload.

This is the only data that leaves the machine, so these tests are the
guarantee behind that. They assert what is absent as carefully as what is
present.
"""

from __future__ import annotations

import re

import pytest

from pf.bootstrap.prompt import build_prompt, collect_merchants, write_payload
from pf.db.connection import open_initialised

ACCOUNT = "2100 9999 11 2200536981"


@pytest.fixture
def con():
    connection = open_initialised(":memory:")
    connection.execute(
        "INSERT INTO accounts (id, account_number, label) VALUES (1, ?, ?)",
        (ACCOUNT, ACCOUNT),
    )
    yield connection
    connection.close()


def add(con, description, kind="card_purchase", cents=-1000, date="2026-06-04", balance=50000):
    con.execute(
        """INSERT INTO transactions (
               row_hash, account_id, date_op, date_value, amount_cents,
               balance_cents, kind, code_common, code_own,
               description_raw, description_norm, source_file, imported_at
           ) VALUES (?,1,?,?,?,?,?,'12','040',?,?,'f.xls','now')""",
        (
            f"h{description}{kind}{cents}{date}{balance}",
            date, date, cents, balance, kind, description, description,
        ),
    )


# --------------------------------------------------------------------------
# What is included
# --------------------------------------------------------------------------


def test_collects_distinct_merchant_strings(con):
    add(con, "MERCADONA PLAZA D")
    add(con, "MERCADONA PLAZA D", cents=-2000)
    add(con, "BON AREA")
    payload = collect_merchants(con)
    assert payload.merchants == ("BON AREA", "MERCADONA PLAZA D")
    assert payload.count == 2


def test_the_list_is_sorted_so_the_file_is_stable_between_runs(con):
    for name in ["ZARA", "BON AREA", "MERCADONA"]:
        add(con, name)
    assert list(collect_merchants(con).merchants) == ["BON AREA", "MERCADONA", "ZARA"]


def test_empty_descriptions_are_skipped(con):
    add(con, "MERCADONA")
    add(con, "")
    add(con, "   ")
    assert collect_merchants(con).count == 1


# --------------------------------------------------------------------------
# What is held back
# --------------------------------------------------------------------------


def test_descriptions_only_ever_on_transfer_rows_are_excluded(con):
    # This is where the family's names live. The bank's type codes already
    # identify these rows, so the name contributes nothing to categorisation.
    add(con, "A FAMILY MEMBER NAME", kind="transfer_person")
    add(con, "A FAMILY MEMBER NAME", kind="transfer_person", cents=-5000)
    add(con, "ANOTHER NAME", kind="transfer_own")
    add(con, "MERCADONA")
    payload = collect_merchants(con)
    assert payload.merchants == ("MERCADONA",)
    assert payload.excluded_transfer_only == 2
    assert payload.total_distinct == 3


def test_a_description_seen_on_both_kinds_is_kept(con):
    # If it ever appears as a real purchase, the model should see it.
    add(con, "AMBIGUOUS NAME", kind="transfer_person")
    add(con, "AMBIGUOUS NAME", kind="card_purchase", cents=-2500)
    assert collect_merchants(con).merchants == ("AMBIGUOUS NAME",)


def test_the_payload_contains_no_amounts_dates_or_account_numbers(con, tmp_path):
    # The guarantee, asserted rather than promised.
    add(con, "MERCADONA PLAZA D", cents=-6268, date="2026-06-04", balance=91554)
    add(con, "BON AREA", cents=-123456, date="2017-09-11", balance=1)
    _, merchants_path, _ = write_payload(con, tmp_path)
    body = merchants_path.read_text(encoding="utf-8")

    assert ACCOUNT not in body
    assert "2200536981" not in body          # the account, unspaced
    assert "62.68" not in body and "6268" not in body
    assert "2026-06-04" not in body
    assert "04/06/2026" not in body
    assert "915.54" not in body
    assert body.strip().splitlines() == ["BON AREA", "MERCADONA PLAZA D"]


def test_merchant_digits_are_preserved_even_though_amounts_are_not(con, tmp_path):
    # 'EL ARBOL 5228' is a branch number and part of the name. Stripping all
    # digits to be safe would destroy real merchant identities.
    add(con, "EL ARBOL 5228")
    _, merchants_path, _ = write_payload(con, tmp_path)
    assert "EL ARBOL 5228" in merchants_path.read_text(encoding="utf-8")


def test_no_card_numbers_reach_the_payload(con, tmp_path):
    # Card numbers live in counterparty_ref, which is never consulted here.
    add(con, "MERCADONA")
    con.execute("UPDATE transactions SET counterparty_ref = '4766645938385471'")
    _, merchants_path, _ = write_payload(con, tmp_path)
    assert "4766645938385471" not in merchants_path.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# The prompt itself
# --------------------------------------------------------------------------


def test_the_prompt_states_how_many_strings_accompany_it(con):
    for name in ["MERCADONA", "BON AREA", "ZARA"]:
        add(con, name)
    text = build_prompt(collect_merchants(con))
    assert "3 distinct merchant description" in text


def test_the_prompt_asks_for_both_json_shapes(con):
    text = build_prompt(collect_merchants(con))
    assert "categories.json" in text
    assert "rules.json" in text
    for match_type in ["exact", "prefix", "contains", "regex"]:
        assert match_type in text


def test_the_prompt_warns_about_the_17_character_truncation(con):
    # Otherwise the model writes patterns for full merchant names that never
    # appear in the data.
    text = build_prompt(collect_merchants(con))
    assert "17 characters" in text


def test_the_prompt_tells_the_model_to_leave_doubtful_merchants_alone(con):
    # The most important instruction: a wrong rule is invisible and corrupts a
    # total, while an uncategorised row is honest and gets reviewed.
    text = build_prompt(collect_merchants(con))
    assert "leave it without a" in text.lower()


def test_the_prompt_contains_no_merchant_data_itself(con):
    # The strings go in their own file, so the prompt can be reviewed on its
    # own and the data reviewed separately.
    add(con, "MERCADONA PLAZA D")
    text = build_prompt(collect_merchants(con))
    assert "MERCADONA PLAZA D" not in text


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------


def test_write_payload_creates_both_files(con, tmp_path):
    add(con, "MERCADONA")
    prompt_path, merchants_path, payload = write_payload(con, tmp_path / "out")
    assert prompt_path.exists() and prompt_path.name == "prompt.md"
    assert merchants_path.exists() and merchants_path.name == "merchants.txt"
    assert payload.count == 1


def test_write_payload_is_repeatable(con, tmp_path):
    add(con, "MERCADONA")
    add(con, "BON AREA")
    first = write_payload(con, tmp_path / "a")[1].read_text(encoding="utf-8")
    second = write_payload(con, tmp_path / "b")[1].read_text(encoding="utf-8")
    assert first == second


def test_an_empty_database_produces_an_empty_list_not_a_crash(con, tmp_path):
    _, merchants_path, payload = write_payload(con, tmp_path)
    assert payload.count == 0
    assert merchants_path.read_text(encoding="utf-8").strip() == ""
