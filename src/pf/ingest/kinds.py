"""What sort of movement a row represents.

Not every row is spending. Counting a transfer between the household's own
accounts as spending would add 267,342 EUR of phantom money over nine years,
so the kind has to be derived before anything is totalled.

The derivation is a lookup table plus a short list of text overrides, kept as
data rather than branching logic so that it can be read, tested and corrected
without touching the flow. Combinations that are not in the table become
'other' AND are reported, so the long tail surfaces instead of hiding.
"""

from __future__ import annotations

from typing import Final

from pf.ingest.normalize import normalize_description

# --------------------------------------------------------------------------
# The vocabulary
# --------------------------------------------------------------------------

CARD_PURCHASE: Final = "card_purchase"
DIRECT_DEBIT: Final = "direct_debit"
TRANSFER_IN: Final = "transfer_in"
CASH_WITHDRAWAL: Final = "cash_withdrawal"
CASH_DEPOSIT: Final = "cash_deposit"
TRANSFER_OWN: Final = "transfer_own"
TRANSFER_PERSON: Final = "transfer_person"
REFUND: Final = "refund"
FEE: Final = "fee"
OTHER: Final = "other"

ALL_KINDS: Final = frozenset(
    {
        CARD_PURCHASE,
        DIRECT_DEBIT,
        TRANSFER_IN,
        CASH_WITHDRAWAL,
        CASH_DEPOSIT,
        TRANSFER_OWN,
        TRANSFER_PERSON,
        REFUND,
        FEE,
        OTHER,
    }
)

#: Kinds that are movements of the household's own money rather than spending.
#: Excluded from spend analysis by default. See spec section 5.
NON_SPENDING_KINDS: Final = frozenset({TRANSFER_OWN, CASH_DEPOSIT})


# --------------------------------------------------------------------------
# Code table
# --------------------------------------------------------------------------

# (Concepte comu, Concepte propi) -> kind.
# Row counts are from the real 9-year export and are the evidence for each
# entry; anything rarer than this is deliberately left unmapped.
_CODE_MAP: Final[dict[tuple[str, str], str]] = {
    ("12", "040"): CARD_PURCHASE,     # 8,125 rows -- COMPRA CON TARJETA
    ("02", "067"): TRANSFER_OWN,      #   630 rows -- TRASPASO PROPIO / TRASPASO
    ("11", "040"): CASH_WITHDRAWAL,   #   369 rows -- REINT.CAJERO / CAJERO AJENO
    ("04", "002"): TRANSFER_PERSON,   #   267 rows -- Bizum; 'Name;Surname;Surname'
    ("04", "067"): TRANSFER_OWN,      #   138 rows -- TRASPASO PROPIO
    ("02", "040"): REFUND,            #   126 rows -- DEVOLUCION COMPRA

    # Direct debits (domiciliaciones). CORRECTED 2026-11-02: these were
    # originally read as person-to-person transfers because the type-label
    # column holds a PERSON'S NAME -- but that person is the account holder
    # being debited, not the payee. The payee is in the description, with the
    # bank's 'CORE' prefix: school catering, electricity, council tax,
    # language classes. 296 rows, 20,572 EUR over nine years.
    ("03", "038"): DIRECT_DEBIT,      #   158 rows
    ("03", "005"): DIRECT_DEBIT,      #    67 rows
    ("03", "033"): DIRECT_DEBIT,      #    28 rows
    ("03", "034"): DIRECT_DEBIT,      #    23 rows
    ("03", "006"): DIRECT_DEBIT,      #     8 rows -- a mobile operator
    ("12", "044"): DIRECT_DEBIT,      #     8 rows -- a card product
    ("17", "016"): DIRECT_DEBIT,      #     7 rows -- council vehicle tax

    # Bank's own charges.
    ("17", "036"): FEE,               #    13 rows -- overdraft, maintenance
    ("17", "040"): FEE,               #     1 row  -- COSTE USO CAJERO

    # Money arriving from a third party (company, club, refund of a fee).
    ("02", "002"): TRANSFER_IN,       #    17 rows, all incoming
    ("02", "048"): TRANSFER_IN,       #     1 row
    ("02", "036"): REFUND,            #     7 rows -- COND. MANTENIMIENTO
    ("98", "040"): REFUND,            #     1 row  -- ANUL.OPERACION TARJ
    ("02", "032"): TRANSFER_IN,       #    24 rows -- all incoming, via a
                                      #               payment processor
                                      #               (proceeds of selling
                                      #               second-hand items)
    ("99", "067"): TRANSFER_OWN,      #    23 rows -- all outgoing, 20 of them
                                      #               to the household's own or
                                      #               the spouse's accounts.
                                      #               KNOWN IMPRECISION: two of
                                      #               the 23 are not own
                                      #               transfers (a phone top-up
                                      #               and a generic transfer),
                                      #               so they are excluded from
                                      #               spend when they should
                                      #               not be. Two rows in
                                      #               10,161; recorded rather
                                      #               than contorting the map.
}


# --------------------------------------------------------------------------
# Text overrides
# --------------------------------------------------------------------------

# The codes are not perfectly clean: ('12','040') is overwhelmingly card
# purchases, but its second most common label in the real data is
# REINT.CAJERO -- a cash withdrawal. Where the label states the type
# unambiguously, it wins over the code.
#
# These are matched as substrings of the NORMALISED label, so they must be
# specific: on person-to-person transfers this column holds somebody's name
# rather than a type, and a loose pattern would match a surname.
_TEXT_OVERRIDES: Final[tuple[tuple[str, str], ...]] = (
    ("REINT.CAJERO", CASH_WITHDRAWAL),
    ("CAJERO AJENO", CASH_WITHDRAWAL),
    ("INGRESO CAJERO", CASH_DEPOSIT),      # a deposit, NOT a withdrawal
    ("DEVOLUCION COMPRA", REFUND),
    ("TRASPASO PROPIO", TRANSFER_OWN),
    ("TRASP. PROPIO", TRANSFER_OWN),
    ("CUOTA TARJETA", FEE),
    ("COSTE USO CAJERO", FEE),
    ("CANCELAC.PRESTAMO", OTHER),
    ("COMPRA CON TARJETA", CARD_PURCHASE),
)


def derive_kind(
    code_common: str, code_own: str, type_label: str = ""
) -> tuple[str, bool]:
    """Classify one row.

    Returns ``(kind, was_mapped)``. ``was_mapped`` is False when the row fell
    through to 'other', which the importer counts and reports -- an unmapped
    code combination is a gap in our knowledge of the bank's format, and
    should be visible rather than quietly absorbed.

    The label overrides the code table when it names a type unambiguously,
    because the codes are measurably impure.
    """
    label = normalize_description(type_label or "")
    for needle, kind in _TEXT_OVERRIDES:
        if needle in label:
            return kind, True

    key = (code_common.strip(), code_own.strip())
    if key in _CODE_MAP:
        return _CODE_MAP[key], True

    return OTHER, False


def is_spending(kind: str) -> bool:
    """Whether rows of this kind should count towards spend totals."""
    return kind not in NON_SPENDING_KINDS
