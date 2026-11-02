"""Reading the bank's .xls into plain rows.

Knows about Excel and nothing about the database. Its whole job is to turn a
workbook into a stream of RawRow, and to fail loudly if the workbook is not
the export we recognise.

Two rules here come from measuring the real files, and both exist to survive
the bank changing something:

  1. The header row is FOUND, not assumed. The real export has a three-row
     title block above it, but that is the bank's choice and not a contract.
  2. Columns are addressed BY NAME. The monthly export leaves two columns
     entirely empty that the nine-year export populates, so any layout
     inferred from the data would be wrong half the time.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

import xlrd

from pf.ingest.model import (
    COL_DATE_OP,
    REQUIRED_COLUMNS,
    FileFormatError,
    RawRow,
)
from pf.ingest.normalize import normalize_description

#: How far down to look for the header before giving up. The real file uses
#: row 3; this allows a generous margin without scanning a whole sheet.
_MAX_HEADER_SEARCH_ROWS = 20


def _cell_text(value: object) -> str:
    """One cell as canonical text.

    Everything is stringified the same way on every read, because these
    strings are what the row hash is computed from: an inconsistency here
    would make the same transaction hash differently on a later import and
    silently duplicate it.
    """
    if value is None:
        return ""
    if isinstance(value, float):
        # xlrd returns every number as a float. Render whole numbers without
        # a trailing '.0' so that 800 and 800.0 cannot diverge.
        if value.is_integer():
            return str(int(value))
        return repr(value)
    return str(value).strip()


def _find_header_row(sheet) -> int:
    """Locate the header by looking for a column we know must exist."""
    limit = min(sheet.nrows, _MAX_HEADER_SEARCH_ROWS)
    for row in range(limit):
        for col in range(sheet.ncols):
            text = normalize_description(_cell_text(sheet.cell_value(row, col)))
            if text.startswith(COL_DATE_OP):
                return row
    raise FileFormatError(
        f"no header row found in the first {limit} rows: expected a column "
        f"named like {COL_DATE_OP!r}. Is this the 'Excel simple' export?"
    )


def _column_map(sheet, header_row: int) -> dict[str, int]:
    """Normalised header name -> column index."""
    mapping: dict[str, int] = {}
    for col in range(sheet.ncols):
        name = normalize_description(_cell_text(sheet.cell_value(header_row, col)))
        if name and name not in mapping:
            mapping[name] = col

    missing = [name for name in REQUIRED_COLUMNS if name not in mapping]
    if missing:
        raise FileFormatError(
            "export is missing required column(s): "
            + ", ".join(repr(m) for m in missing)
            + f". Found: {sorted(mapping)!r}"
        )
    return mapping


def read_rows(path: Path | str) -> Iterator[RawRow]:
    """Yield every data row below the header.

    Rows are yielded as they are -- including blank ones. Deciding that a row
    is unusable is the importer's job, so that rejections are counted and
    reported rather than disappearing here.
    """
    book = xlrd.open_workbook(str(path))
    sheet = book.sheet_by_index(0)

    header_row = _find_header_row(sheet)
    mapping = _column_map(sheet, header_row)

    for row in range(header_row + 1, sheet.nrows):
        cells = tuple(
            _cell_text(sheet.cell_value(row, col)) for col in range(sheet.ncols)
        )
        by_name = {name: cells[col] for name, col in mapping.items() if col < len(cells)}
        yield RawRow(cells=cells, by_name=by_name, source_row=row)


def describe(path: Path | str) -> dict[str, object]:
    """Summarise a workbook without importing it. Used by `pf import --dry-run`."""
    book = xlrd.open_workbook(str(path))
    sheet = book.sheet_by_index(0)
    header_row = _find_header_row(sheet)
    mapping = _column_map(sheet, header_row)
    return {
        "sheet": sheet.name,
        "rows": sheet.nrows,
        "cols": sheet.ncols,
        "header_row": header_row,
        "data_rows": max(0, sheet.nrows - header_row - 1),
        "columns": sorted(mapping),
    }
