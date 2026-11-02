"""Pure conversions: text -> normalised text, money -> cents, date -> ISO.

No I/O, no clock, no database. Every function here is a plain input/output
mapping, which is why this is the easiest module in the project to trust.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from decimal import Decimal, InvalidOperation

from pf.ingest.model import RowError

_WHITESPACE = re.compile(r"\s+")

# The bank's own export damages 'N' with a tilde. Measured across 9 years:
# all 22 affected descriptions are this one substitution -- 'PEaIS' for
# 'PENIS(COLA)', 'BAR MAaANA' for 'MANANA', 'DOaA' for 'DONA'. The uppercase
# form is handled defensively; it was not observed.
_MOJIBAKE = {
    "ã": "Ñ",   # a-tilde  -> N-tilde
    "Ã": "Ñ",   # A-tilde  -> N-tilde
}

_DATE_RE = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")


def repair_mojibake(text: str) -> str:
    """Undo the bank's tilde damage.

    This has to happen *before* accents are stripped, and it genuinely matters:
    stripping accents maps 'a-tilde' to 'A' but 'N-tilde' to 'N', so without
    the repair 'PEaIS' would normalise to 'PEAIS' and never match 'PENIS'.
    """
    for bad, good in _MOJIBAKE.items():
        text = text.replace(bad, good)
    return text


def strip_accents(text: str) -> str:
    """Drop combining marks, so 'PENIS' and 'PEÑIS' compare equal."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def normalize_description(raw: str) -> str:
    """Canonical form used for rule matching.

    Order matters: repair, then collapse whitespace, then upper-case, then
    strip accents. Digits are deliberately kept -- 170 of the 1,082 real
    merchant strings carry meaningful ones, such as 'EL ARBOL 5228'.
    """
    text = repair_mojibake(raw)
    text = _WHITESPACE.sub(" ", text).strip()
    text = text.upper()
    text = strip_accents(text)
    return text


def _to_decimal(value: object) -> Decimal | None:
    """A source amount cell -> Decimal, or None when the cell is empty."""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        # Spanish exports have been seen with comma decimals elsewhere; be
        # tolerant, but only when there is no ambiguity with thousands marks.
        if "," in text and "." not in text:
            text = text.replace(",", ".")
        try:
            return Decimal(text)
        except InvalidOperation as exc:
            raise RowError("bad_amount", f"cannot read amount {value!r}") from exc
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    raise RowError("bad_amount", f"unexpected amount type {type(value).__name__}")


def to_cents(income: object, expense: object) -> int:
    """Collapse the export's two positive columns into one signed integer.

    The bank gives 'Ingrés (+)' and 'Despesa (-)' as separate columns, both
    holding positive magnitudes, and never both filled. Verified over 10,034
    real rows: 0 rows with both, 1 row with neither.

    Returns cents, negative for money leaving the account.
    """
    inc = _to_decimal(income)
    exp = _to_decimal(expense)

    if inc is not None and exp is not None:
        raise RowError("both_amounts", "income and expense both populated")
    if inc is None and exp is None:
        raise RowError("no_amount", "neither income nor expense populated")

    magnitude = inc if inc is not None else exp
    assert magnitude is not None  # narrowed by the checks above
    if magnitude < 0:
        raise RowError("negative_magnitude", f"expected a positive figure, got {magnitude}")

    cents = int((magnitude * 100).to_integral_value())
    return cents if inc is not None else -cents


def to_iso_date(text: object) -> str:
    """'DD/MM/YYYY' -> 'YYYY-MM-DD'.

    Day-first, explicitly. All 10,034 real rows match this format; anything
    that does not is rejected rather than guessed at.
    """
    if not isinstance(text, str):
        raise RowError("bad_date", f"expected text date, got {type(text).__name__}")

    match = _DATE_RE.match(text.strip())
    if not match:
        raise RowError("bad_date", f"not DD/MM/YYYY: {text!r}")

    day, month, year = (int(g) for g in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError as exc:
        raise RowError("bad_date", f"not a real date: {text!r}") from exc


def cents_to_text(cents: int) -> str:
    """For display only. Keeps formatting out of the query and storage layers."""
    sign = "-" if cents < 0 else ""
    whole, frac = divmod(abs(cents), 100)
    return f"{sign}{whole:,}.{frac:02d}"
