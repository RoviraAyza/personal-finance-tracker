"""Build synthetic .xls files shaped exactly like the bank's export.

Real statements can never be committed, so the suite needs files that
reproduce the *structure* of the real export with invented contents. Every
quirk encoded here was measured against the originator's real 9-year file and
is recorded in intent/intent.md section 3:

  * a title block above the header, so the header is not on row 0
  * Catalan column names
  * 25 columns, several of them always empty
  * dates as DD/MM/YYYY text
  * two positive amount columns, never both filled
  * merchant names hard-truncated at 17 characters
  * the bank's own tilde damage ('a-tilde' where 'N-tilde' belongs)
  * a trailing all-empty row
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

import xlwt

#: The real export's headers, in the real order.
HEADERS: tuple[str, ...] = (
    "",
    "Número de compte",
    "Oficina",
    "Divisa",
    "D. Operació",
    "D. Valor",
    "Ingrés (+)",
    "Despesa (-)",
    "Saldo (+)",
    "Saldo (-)",
    "Concepte comú",
    "Concepte propi",
    "Refèrencia 1",
    "Refèrencia 2",
    "Concepte complementari 1",
    "Concepte complementari 2",
    "Concepte complementari 3",
    "Concepte complementari 4",
    "Concepte complementari 5",
    "Concepte complementari 6",
    "Concepte complementari 7",
    "Concepte complementari 8",
    "Concepte complementari 9",
    "Concepte complementari 10",
    "",
)

SHEET_NAME = "Excel simple(1)"
ACCOUNT = "2100 9999 11 2200000000"


def row(
    *,
    date_op: str,
    description: str,
    expense: float | str = "",
    income: float | str = "",
    balance: float | str = "",
    code_common: str = "12",
    code_own: str = "040",
    type_label: str = "COMPRA CON TARJETA",
    account: str = ACCOUNT,
    card: str = "4766640000000000",
    date_value: str | None = None,
    truncate_description: bool = True,
) -> list[object]:
    """One data row in the export's 25-column layout.

    `description` is truncated to 17 characters by default, because that is
    what the bank does to card-purchase merchant names, and it is padded with
    spaces the way the real file pads them.
    """
    desc = description[:17] if truncate_description else description
    padded = f"{' ' * 38}{desc:<38}"

    cells: list[object] = [""] * 25
    cells[1] = account
    cells[2] = "9736"
    cells[3] = "EUR"
    cells[4] = date_op
    cells[5] = date_value if date_value is not None else date_op
    cells[6] = income
    cells[7] = expense
    cells[8] = balance
    cells[10] = code_common
    cells[11] = code_own
    cells[12] = "000000000000"
    cells[13] = card
    cells[14] = padded
    cells[22] = f"{'04000022SIO':<38}{type_label}"
    return cells


def write_xls(
    path: Path,
    rows: Iterable[Sequence[object]],
    *,
    preamble_rows: int = 3,
    headers: Sequence[str] = HEADERS,
    title: str = "MOVIMENTS DES DE : 01/01/2020 FINS: 31/12/2020",
    trailing_blank_row: bool = True,
) -> Path:
    """Write a workbook shaped like the bank's export.

    `preamble_rows` is how many rows sit above the header. The real file uses
    3, but the reader must locate the header rather than assume that, so tests
    vary it.
    """
    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet(SHEET_NAME)

    if preamble_rows > 0:
        sheet.write(min(1, preamble_rows - 1), 1, title)

    for col, name in enumerate(headers):
        sheet.write(preamble_rows, col, name)

    current = preamble_rows + 1
    for data in rows:
        for col, value in enumerate(data):
            if value != "":
                sheet.write(current, col, value)
        current += 1

    if trailing_blank_row:
        # The real export ends with a row that exists but carries nothing
        # usable. Excel discards a cell written as "", so write a single
        # space: the reader strips cells, so this still reads as empty, and
        # the row is present to be rejected -- which is what the real file
        # does, once per export.
        sheet.write(current, 0, " ")

    path.parent.mkdir(parents=True, exist_ok=True)
    book.save(str(path))
    return path


def simple_file(path: Path, **kwargs) -> Path:
    """A small, well-formed export covering the common cases."""
    return write_xls(
        path,
        [
            row(date_op="04/06/2026", description="CAFETERIA EL OLIVO", expense=2.30, balance=978.22),
            # Same day, same amount, same merchant as the row above: a genuine
            # distinct transaction, distinguished only by the balance. 98 such
            # pairs exist in the real data.
            row(date_op="04/06/2026", description="CAFETERIA EL OLIVO", expense=2.30, balance=980.52),
            row(date_op="05/06/2026", description="MERCADONA PLAZA DEL PILAR", expense=62.68, balance=915.54),
            row(date_op="06/06/2026", description="0150-CONSUM PEãIS", expense=14.20, balance=901.34),
            row(
                date_op="07/06/2026",
                description="JOSE EXAMPLE NAME",
                income=800.00,
                balance=1701.34,
                code_common="02",
                code_own="067",
                type_label="TRASPASO PROPIO",
            ),
            row(
                date_op="08/06/2026",
                description="REINT.CAJERO",
                expense=100.00,
                balance=1601.34,
                code_common="11",
                code_own="040",
                type_label="REINT.CAJERO",
            ),
        ],
        **kwargs,
    )
