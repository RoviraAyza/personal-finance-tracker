"""The bootstrap payload.

This is the only data that leaves the machine, so these tests are the
guarantee behind that. They assert what is absent as carefully as what is
present.
"""

from __future__ import annotations

import re

import pytest

from pf.bootstrap.prompt import (
    build_prompt,
    collect_merchants,
    redact,
    write_payload,
)
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


def test_incoming_transfers_also_count_as_transfers_for_exclusion(con):
    # A real near-miss: `transfer_in` was added as a kind and left out of the
    # exclusion list. One single incoming transfer was then enough to expose a
    # family member's name in a payload of a thousand strings. Any new
    # transfer-shaped kind must be added to _TRANSFER_KINDS.
    add(con, "A FAMILY NAME", kind="transfer_person")
    add(con, "A FAMILY NAME", kind="transfer_in", cents=5000)
    add(con, "MERCADONA")
    payload = collect_merchants(con)
    assert payload.merchants == ("MERCADONA",)


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
# Redaction of personal identifiers
#
# Every case below was found by READING the generated payload, which is the
# reason the payload is written to a file and reviewed before being sent.
# --------------------------------------------------------------------------


def test_a_dni_is_stripped_from_a_description():
    # Spanish national identity number: 8-9 digits plus a control letter.
    assert redact("ANA EXAMPLE SURNAME 029119795R") == "ANA EXAMPLE SURNAME"
    assert redact("SOME NAME 73388291Y") == "SOME NAME"


def test_an_nie_is_stripped():
    # The foreigner equivalent: X/Y/Z, 7 digits, a letter.
    assert redact("SOMEONE X1234567L") == "SOMEONE"


def test_a_phone_number_is_stripped():
    assert redact("TELEFONO NUM: 645350001 REC. ORANGE BD") == "TELEFONO NUM: REC. ORANGE BD"


def test_a_company_tax_id_is_kept():
    # A CIF identifies a business, is public register data, and helps the model
    # recognise the company. Deliberately not redacted.
    assert redact("DX COMPUTER SL B50514470") == "DX COMPUTER SL B50514470"
    assert redact("BASKET CLUB EXAMPLE G12324737") == "BASKET CLUB EXAMPLE G12324737"


def test_branch_numbers_in_shop_names_are_kept():
    # 'EL ARBOL 5228' -- the number is part of the merchant identity.
    assert redact("EL ARBOL 5228") == "EL ARBOL 5228"
    assert redact("DIA 6438") == "DIA 6438"


def test_ordinary_merchant_names_are_untouched():
    for name in ["MERCADONA PLAZA D", "BON AREA", "CAFETERIA EL OLIV"]:
        assert redact(name) == name


def test_redaction_only_removes_so_patterns_still_match():
    # A rule written against the redacted form must still match the stored
    # description with `contains` or `prefix`.
    original = "ANA EXAMPLE SURNAME 029119795R"
    assert redact(original) in original


def test_redactions_are_counted(con, tmp_path):
    add(con, "SOME NAME 73388291Y")
    add(con, "MERCADONA")
    payload = collect_merchants(con)
    assert payload.redacted == 1
    assert "SOME NAME" in payload.merchants


def test_identifiers_do_not_reach_the_written_payload(con, tmp_path):
    add(con, "ANA EXAMPLE SURNAME 029119795R")
    add(con, "TELEFONO NUM: 645350001 REC. ORANGE BD")
    _, merchants_path, _ = write_payload(con, tmp_path)
    body = merchants_path.read_text(encoding="utf-8")
    assert "029119795R" not in body
    assert "645350001" not in body


def test_redaction_can_merge_two_descriptions_into_one(con):
    # 'NAME 1234567A' and 'NAME 7654321B' both redact to 'NAME'. Deduplicating
    # after redaction is correct: the model should see one string, not two.
    add(con, "SAME NAME 12345678A")
    add(con, "SAME NAME 87654321B")
    payload = collect_merchants(con)
    assert payload.merchants == ("SAME NAME",)


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
