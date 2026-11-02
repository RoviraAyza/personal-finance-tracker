"""Normalisation, money and dates.

Each test here maps to something measured in the real 9-year export; the
comments say which, so a future reader knows the test is guarding a real
observation rather than an imagined one.
"""

from __future__ import annotations

import pytest

from pf.ingest.model import RowError
from pf.ingest.normalize import (
    cents_to_text,
    normalize_description,
    repair_mojibake,
    strip_accents,
    to_cents,
    to_iso_date,
)

# --------------------------------------------------------------------------
# Description normalisation
# --------------------------------------------------------------------------


def test_repairs_the_banks_tilde_damage():
    # 22 real descriptions carry this damage, all of it this one substitution.
    assert repair_mojibake("0150-CONSUM PEãIS") == "0150-CONSUM PEÑIS"
    assert repair_mojibake("BAR MAãANA") == "BAR MAÑANA"
    assert repair_mojibake("DOãA HIPOLITA") == "DOÑA HIPOLITA"


def test_damaged_and_clean_spellings_normalise_the_same():
    # This is the point of the repair. Stripping accents maps a-tilde to 'A'
    # but N-tilde to 'N', so without repairing first these would never match.
    assert normalize_description("CONSUM PEãIS") == normalize_description("CONSUM PEÑIS")
    assert normalize_description("CONSUM PEãIS") == "CONSUM PENIS"


def test_accents_are_stripped():
    assert strip_accents("PEÑIS") == "PENIS"
    assert normalize_description("Café Martín") == "CAFE MARTIN"


def test_internal_whitespace_is_collapsed():
    # 28 of 1,082 real descriptions contain runs of spaces.
    assert normalize_description("BAR   CAMPO  DE EL E") == "BAR CAMPO DE EL E"


def test_padding_is_stripped():
    # Card rows arrive space-padded on both sides in the real file.
    assert normalize_description("      MERCADONA PLAZA D       ") == "MERCADONA PLAZA D"


def test_case_is_folded_to_upper():
    # 110 real descriptions are mixed case, e.g. 'Amazon.es', 'AMZN Mktp ES'.
    assert normalize_description("Amazon.es") == "AMAZON.ES"
    assert normalize_description("AMZN Mktp ES") == "AMZN MKTP ES"


def test_digits_are_preserved():
    # 170 real descriptions carry meaningful digits; stripping them would
    # merge 'EL ARBOL 5228' with every other 'EL ARBOL' branch.
    assert normalize_description("EL ARBOL 5228") == "EL ARBOL 5228"
    assert normalize_description("DIA 6438") == "DIA 6438"


def test_normalisation_is_idempotent():
    for raw in ["  Café  Martín ", "0150-CONSUM PEãIS", "EL ARBOL 5228"]:
        once = normalize_description(raw)
        assert normalize_description(once) == once


def test_empty_description_survives():
    # 157 real rows (1.6%) have no description at all.
    assert normalize_description("") == ""
    assert normalize_description("     ") == ""


# --------------------------------------------------------------------------
# Money
# --------------------------------------------------------------------------


def test_expense_becomes_negative_cents():
    assert to_cents("", 7.66) == -766


def test_income_becomes_positive_cents():
    assert to_cents(800.0, "") == 80000


def test_both_columns_filled_is_rejected():
    # Never observed in 10,034 rows, but guarded: silently picking one would
    # be a wrong number rather than a loud failure.
    with pytest.raises(RowError) as err:
        to_cents(10.0, 5.0)
    assert err.value.reason == "both_amounts"


def test_neither_column_filled_is_rejected():
    # Exactly 1 real row per file: the trailing blank.
    with pytest.raises(RowError) as err:
        to_cents("", "")
    assert err.value.reason == "no_amount"


@pytest.mark.parametrize(
    "value,expected",
    [(0.1, 10), (0.07, 7), (2.3, 230), (5783.34, 578334), (0.09, 9), (1234.56, 123456)],
)
def test_awkward_floats_convert_exactly(value, expected):
    # 7.66 * 100 is 765.99999... in binary floating point. Going through
    # Decimal(str(value)) is what keeps every one of these exact.
    assert to_cents("", value) == -expected


def test_amounts_are_always_whole_cents():
    for value in [0.01, 0.1, 3.33, 99.99, 5783.34]:
        assert isinstance(to_cents("", value), int)


def test_text_amounts_are_accepted():
    assert to_cents("", "7.66") == -766
    assert to_cents("", "7,66") == -766   # comma decimal, seen in Spanish exports


def test_negative_magnitude_is_rejected():
    # The export's columns are magnitudes; a negative one means a changed
    # format, which should stop us rather than flip a sign silently.
    with pytest.raises(RowError) as err:
        to_cents("", -5.0)
    assert err.value.reason == "negative_magnitude"


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------


def test_dates_are_parsed_day_first():
    assert to_iso_date("11/09/2026") == "2026-09-11"


def test_day_first_is_unambiguous_for_high_days():
    # 31/10/2026 is impossible read month-first, so this test fails loudly if
    # anyone ever "fixes" the parser to US order.
    assert to_iso_date("31/10/2026") == "2026-10-31"
    assert to_iso_date("28/02/2024") == "2024-02-28"


def test_malformed_dates_are_rejected_not_guessed():
    for bad in ["2026-09-11", "11-09-2026", "1/9/2026", "", "   ", "31/13/2026", "32/01/2026"]:
        with pytest.raises(RowError) as err:
            to_iso_date(bad)
        assert err.value.reason == "bad_date"


def test_non_text_date_is_rejected():
    with pytest.raises(RowError):
        to_iso_date(45000.0)


# --------------------------------------------------------------------------
# Display
# --------------------------------------------------------------------------


def test_cents_render_for_humans():
    assert cents_to_text(-766) == "-7.66"
    assert cents_to_text(80000) == "800.00"
    assert cents_to_text(20521930) == "205,219.30"
    assert cents_to_text(0) == "0.00"
    assert cents_to_text(-9) == "-0.09"
