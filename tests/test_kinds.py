"""Classifying what sort of movement each row is.

The code combinations below are the ones actually observed in nine years of
real statements; the row counts in kinds.py record how often each occurred.
"""

from __future__ import annotations

import pytest

from pf.ingest import kinds
from pf.ingest.kinds import derive_kind, is_spending


@pytest.mark.parametrize(
    "common,own,expected",
    [
        ("12", "040", kinds.CARD_PURCHASE),
        ("02", "067", kinds.TRANSFER_OWN),
        ("11", "040", kinds.CASH_WITHDRAWAL),
        ("04", "002", kinds.TRANSFER_PERSON),
        ("03", "038", kinds.DIRECT_DEBIT),
        ("04", "067", kinds.TRANSFER_OWN),
        ("02", "040", kinds.REFUND),
    ],
)
def test_known_code_pairs_are_classified(common, own, expected):
    kind, mapped = derive_kind(common, own)
    assert kind == expected
    assert mapped is True


def test_unknown_code_pair_becomes_other_and_is_reported():
    # The whole point of returning a flag: an unmapped combination is a gap in
    # what we know about the bank's format, and must be visible.
    kind, mapped = derive_kind("77", "999")
    assert kind == kinds.OTHER
    assert mapped is False


def test_label_overrides_the_code_table():
    # The measured impurity: ('12','040') is overwhelmingly card purchases,
    # but its second most common label in the real data is a cash withdrawal.
    kind, mapped = derive_kind("12", "040", "04000001TOC    REINT.CAJERO")
    assert kind == kinds.CASH_WITHDRAWAL
    assert mapped is True


def test_card_purchase_label_is_respected():
    kind, _ = derive_kind("12", "040", "04000022SIO    COMPRA CON TARJETA")
    assert kind == kinds.CARD_PURCHASE


def test_cash_deposit_is_not_mistaken_for_a_withdrawal():
    # 'INGRESO CAJERO' is money going IN at an ATM. Matching loosely on
    # 'CAJERO' would have classified it as a withdrawal.
    kind, _ = derive_kind("11", "040", "INGRESO CAJERO")
    assert kind == kinds.CASH_DEPOSIT


def test_refund_label_is_recognised():
    kind, _ = derive_kind("02", "040", "04000023SIO    DEVOLUCION COMPRA")
    assert kind == kinds.REFUND


def test_card_fee_is_recognised():
    kind, _ = derive_kind("12", "040", "04000004TCV    CUOTA TARJETA")
    assert kind == kinds.FEE


def test_direct_debits_are_not_mistaken_for_person_transfers():
    # CORRECTED 2026-11-02. Codes 03/xxx carry a person's name in the label --
    # but that person is the account holder being DEBITED, not the payee. The
    # payee is the company in the description. 296 real rows, 20,572 EUR:
    # school catering, electricity, council tax, language classes.
    for own in ["038", "005", "033", "034", "006"]:
        kind, mapped = derive_kind("03", own, "MEN OLAYA PEYRONA NAVALLAS")
        assert kind == kinds.DIRECT_DEBIT, f"03/{own}"
        assert mapped is True


def test_bank_charges_are_fees():
    assert derive_kind("17", "036", "MANTENIMIENTO")[0] == kinds.FEE
    assert derive_kind("17", "040", "COSTE USO CAJERO")[0] == kinds.FEE


def test_incoming_third_party_transfers_have_their_own_kind():
    assert derive_kind("02", "002")[0] == kinds.TRANSFER_IN
    assert derive_kind("02", "048")[0] == kinds.TRANSFER_IN


def test_council_tax_and_card_products_are_direct_debits():
    assert derive_kind("17", "016")[0] == kinds.DIRECT_DEBIT
    assert derive_kind("12", "044", "MEN OLAYA PEYRONA")[0] == kinds.DIRECT_DEBIT


def test_a_persons_name_in_the_label_does_not_trigger_an_override():
    # On person-to-person transfers this column holds a name, not a type.
    # The overrides must be specific enough not to match a surname.
    kind, mapped = derive_kind("04", "002", "Gabriel;Peyrona;Navallas")
    assert kind == kinds.TRANSFER_PERSON
    assert mapped is True


def test_label_matching_survives_accents_and_case():
    # The label goes through the same normaliser as descriptions.
    kind, _ = derive_kind("12", "040", "devolucion compra")
    assert kind == kinds.REFUND


def test_codes_are_stripped_before_lookup():
    kind, mapped = derive_kind(" 12 ", " 040 ")
    assert kind == kinds.CARD_PURCHASE
    assert mapped is True


def test_missing_label_falls_back_to_the_code_table():
    kind, mapped = derive_kind("12", "040", "")
    assert kind == kinds.CARD_PURCHASE
    assert mapped is True


# --------------------------------------------------------------------------
# What counts as spending
# --------------------------------------------------------------------------


def test_own_transfers_are_not_spending():
    # 267,342 EUR in / 11,004 EUR out over nine years. Counting these as
    # spending or income is the single largest distortion available.
    assert is_spending(kinds.TRANSFER_OWN) is False


def test_cash_deposits_are_not_spending():
    assert is_spending(kinds.CASH_DEPOSIT) is False


@pytest.mark.parametrize(
    "kind",
    [
        kinds.CARD_PURCHASE,
        kinds.DIRECT_DEBIT,
        kinds.CASH_WITHDRAWAL,
        kinds.TRANSFER_PERSON,
        kinds.TRANSFER_IN,
        kinds.REFUND,
        kinds.FEE,
        kinds.OTHER,
    ],
)
def test_everything_else_counts_as_spending(kind):
    # Cash withdrawn is money genuinely leaving the household, even though
    # where it then goes is unknowable. It counts, in its own category.
    assert is_spending(kind) is True


def test_the_vocabulary_is_exactly_these_kinds():
    # Pinned, so adding a kind is a deliberate act that updates this list.
    assert kinds.ALL_KINDS == {
        "card_purchase",
        "direct_debit",
        "transfer_in",
        "cash_withdrawal",
        "cash_deposit",
        "transfer_own",
        "transfer_person",
        "refund",
        "fee",
        "other",
    }


def test_code_table_only_produces_known_kinds():
    for kind in kinds._CODE_MAP.values():
        assert kind in kinds.ALL_KINDS
    for _, kind in kinds._TEXT_OVERRIDES:
        assert kind in kinds.ALL_KINDS
