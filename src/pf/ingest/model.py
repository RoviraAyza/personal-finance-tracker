"""The shapes that move through the import pipeline.

All frozen: a row is read once and never mutated. If a value needs changing,
that is a new row, which keeps the hash in step with the content.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Final, Mapping


class RowError(ValueError):
    """A single row cannot be parsed.

    Carries a machine-readable `reason` so the importer can count categories of
    failure, and a human `detail` for the rejects file. One bad row must never
    abort an import of ten thousand.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class RawRow:
    """One sheet row, as text, before any interpretation."""

    cells: tuple[str, ...]          # every source cell, stripped — the hash input
    by_name: Mapping[str, str]      # header name -> value
    source_row: int                 # 0-based row in the sheet, for messages


@dataclass(frozen=True)
class ParsedRow:
    """One transaction, ready to store."""

    row_hash: str
    account_number: str
    date_op: str                    # ISO YYYY-MM-DD
    date_value: str
    amount_cents: int               # signed; negative = money out
    balance_cents: int | None
    kind: str
    code_common: str
    code_own: str
    description_raw: str
    description_norm: str
    type_label: str | None
    counterparty_ref: str | None


@dataclass(frozen=True)
class Rejection:
    """A row that could not be parsed, kept rather than dropped."""

    source_row: int
    reason: str
    detail: str


@dataclass
class ImportResult:
    """What one import run did. Printed by the CLI, asserted by tests."""

    source_file: str
    rows_read: int = 0
    inserted: int = 0
    skipped: int = 0
    rejected: int = 0
    rejections: list[Rejection] = field(default_factory=list)
    unmapped_kinds: Counter = field(default_factory=Counter)
    date_min: str | None = None
    date_max: str | None = None
    rejects_path: str | None = None

    def add_rejection(self, source_row: int, err: RowError) -> None:
        self.rejected += 1
        self.rejections.append(
            Rejection(source_row=source_row, reason=err.reason, detail=err.detail)
        )


# --------------------------------------------------------------------------
# Column names
# --------------------------------------------------------------------------
#
# Columns are addressed by NAME, never by position. The monthly export leaves
# columns entirely empty that the historical one populates, so a layout
# inferred from which columns carry data would break between files.
#
# Names are held in normalised form (upper-case, accents stripped) so that a
# change in the bank's text encoding cannot stop us finding a column. The
# normaliser used is ingest.normalize.normalize_description.

COL_ACCOUNT: Final = "NUMERO DE COMPTE"
COL_BRANCH: Final = "OFICINA"
COL_CURRENCY: Final = "DIVISA"
COL_DATE_OP: Final = "D. OPERACIO"
COL_DATE_VALUE: Final = "D. VALOR"
COL_INCOME: Final = "INGRES (+)"
COL_EXPENSE: Final = "DESPESA (-)"
COL_BALANCE: Final = "SALDO (+)"
#: Negative balances get their own column, populated on 5 of 10,034 real
#: rows. Ignoring it would record those balances as missing.
COL_BALANCE_NEG: Final = "SALDO (-)"
COL_CODE_COMMON: Final = "CONCEPTE COMU"
COL_CODE_OWN: Final = "CONCEPTE PROPI"
COL_REFERENCE_2: Final = "REFERENCIA 2"
COL_DESCRIPTION: Final = "CONCEPTE COMPLEMENTARI 1"
COL_TYPE_LABEL: Final = "CONCEPTE COMPLEMENTARI 9"

#: Without these the file cannot be interpreted at all, so a missing one is a
#: loud failure rather than a silent empty column.
REQUIRED_COLUMNS: Final[tuple[str, ...]] = (
    COL_ACCOUNT,
    COL_DATE_OP,
    COL_DATE_VALUE,
    COL_INCOME,
    COL_EXPENSE,
    COL_CODE_COMMON,
    COL_CODE_OWN,
    COL_DESCRIPTION,
)


class FileFormatError(Exception):
    """The workbook is not the export we know how to read.

    Raised before any row is processed, so a changed bank format stops the
    import rather than producing a partially-wrong database.
    """
