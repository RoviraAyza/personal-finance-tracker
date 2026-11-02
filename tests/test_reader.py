"""Reading the bank's .xls.

Every fixture here is synthetic, built by tests/fixtures/make_xls.py to the
same shape as the real export. No bank data is needed to run these.
"""

from __future__ import annotations

import pytest

from pf.ingest.model import COL_DATE_OP, COL_DESCRIPTION, FileFormatError
from pf.ingest.reader import describe, read_rows
from tests.fixtures.make_xls import HEADERS, row, simple_file, write_xls


def test_reads_every_data_row(tmp_path):
    path = simple_file(tmp_path / "simple.xls")
    rows = list(read_rows(path))
    # 6 data rows plus the trailing blank the real export also carries.
    assert len(rows) == 7


@pytest.mark.parametrize("preamble", [0, 1, 2, 3, 5, 8])
def test_header_is_found_not_assumed(tmp_path, preamble):
    # The real file puts the header on row 3, but that is the bank's choice.
    # Hardcoding it would work until the day the preamble changes.
    path = simple_file(tmp_path / f"pre{preamble}.xls", preamble_rows=preamble)
    rows = list(read_rows(path))
    assert len(rows) == 7
    assert rows[0].by_name[COL_DATE_OP] == "04/06/2026"


def test_columns_are_addressed_by_name_not_position(tmp_path):
    # Reverse the column order entirely. If anything indexed by position,
    # this breaks.
    reordered = tuple(reversed(HEADERS))
    original = row(date_op="04/06/2026", description="MERCADONA", expense=10.0)
    path = write_xls(
        tmp_path / "reordered.xls",
        [list(reversed(original))],
        headers=reordered,
        trailing_blank_row=False,
    )
    rows = list(read_rows(path))
    assert rows[0].by_name[COL_DATE_OP] == "04/06/2026"
    assert "MERCADONA" in rows[0].by_name[COL_DESCRIPTION]


def test_a_column_empty_throughout_is_fine(tmp_path):
    # The monthly export leaves two columns entirely empty that the nine-year
    # export populates. Neither file is malformed, and the empty one must
    # simply read as empty rather than shifting everything along.
    path = simple_file(tmp_path / "sparse.xls")
    rows = list(read_rows(path))
    assert len(rows) == 7
    data_rows = rows[:-1]                      # last is the trailing blank
    assert all(r.by_name.get("SALDO (-)", "") == "" for r in data_rows)
    # ...while a populated column is still read correctly.
    assert all(r.by_name["DIVISA"] == "EUR" for r in data_rows)


def test_missing_required_column_fails_loudly(tmp_path):
    headers = list(HEADERS)
    headers[4] = ""          # remove 'D. Operació'
    headers[5] = ""          # and 'D. Valor', so the header is unfindable
    path = write_xls(
        tmp_path / "broken.xls",
        [row(date_op="04/06/2026", description="X", expense=1.0)],
        headers=headers,
    )
    with pytest.raises(FileFormatError):
        list(read_rows(path))


def test_missing_one_required_column_names_it(tmp_path):
    headers = list(HEADERS)
    headers[7] = ""          # remove 'Despesa (-)'
    path = write_xls(
        tmp_path / "nodespesa.xls",
        [row(date_op="04/06/2026", description="X", expense=1.0)],
        headers=headers,
    )
    with pytest.raises(FileFormatError) as err:
        list(read_rows(path))
    assert "DESPESA" in str(err.value)


def test_unrecognisable_file_is_rejected_before_any_row(tmp_path):
    path = write_xls(
        tmp_path / "nothing.xls",
        [],
        headers=["Alpha", "Beta", "Gamma"],
        preamble_rows=1,
    )
    with pytest.raises(FileFormatError) as err:
        list(read_rows(path))
    assert "Excel simple" in str(err.value)


def test_blank_trailing_row_is_yielded_not_dropped(tmp_path):
    # The reader does not decide a row is unusable -- the importer does, so
    # that rejections get counted instead of vanishing here.
    path = simple_file(tmp_path / "blank.xls")
    rows = list(read_rows(path))
    assert all(not c for c in rows[-1].cells)


def test_whole_numbers_do_not_acquire_a_decimal_tail(tmp_path):
    # xlrd returns every number as a float. If 800 rendered as '800.0' in one
    # file and '800' in another, the same transaction would hash differently
    # and import twice.
    path = write_xls(
        tmp_path / "whole.xls",
        [row(date_op="07/06/2026", description="TRANSFER", income=800.0, balance=1701.0)],
        trailing_blank_row=False,
    )
    rows = list(read_rows(path))
    assert rows[0].by_name["INGRES (+)"] == "800"
    assert rows[0].by_name["SALDO (+)"] == "1701"


def test_fractional_amounts_keep_their_cents(tmp_path):
    path = simple_file(tmp_path / "frac.xls")
    rows = list(read_rows(path))
    assert rows[0].by_name["DESPESA (-)"] == "2.3"


def test_source_row_number_is_reported(tmp_path):
    # Needed so a rejection can point at a row in the actual spreadsheet.
    path = simple_file(tmp_path / "rows.xls", preamble_rows=3)
    rows = list(read_rows(path))
    assert rows[0].source_row == 4          # header on row 3, data from row 4
    assert rows[1].source_row == 5


def test_describe_summarises_without_importing(tmp_path):
    path = simple_file(tmp_path / "desc.xls")
    info = describe(path)
    assert info["sheet"] == "Excel simple(1)"
    assert info["header_row"] == 3
    assert info["data_rows"] == 7
    assert COL_DESCRIPTION in info["columns"]
