"""Turning read rows into stored transactions.

The only module that touches both a file and the database. Everything it
relies on -- normalising, classifying, hashing -- is a pure function tested
elsewhere, so what is left here is orchestration and the rules about what
happens to a row that cannot be used.

Two behaviours matter more than the rest:

  * **Re-import is a no-op.** The bank's export is a date-range query, so
    overlapping ranges will be requested by accident. Identity is the row
    hash, and inserts ignore conflicts, so importing the same file twice
    changes nothing.
  * **Nothing is dropped silently.** A row that cannot be parsed is counted,
    given a reason, and written out for inspection.
"""

from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from pf import config
from pf.ingest import kinds
from pf.ingest.identity import file_hash, row_hash
from pf.ingest.model import (
    COL_ACCOUNT,
    COL_BALANCE,
    COL_BALANCE_NEG,
    COL_CODE_COMMON,
    COL_CODE_OWN,
    COL_DATE_OP,
    COL_DATE_VALUE,
    COL_DESCRIPTION,
    COL_EXPENSE,
    COL_INCOME,
    COL_REFERENCE_2,
    COL_TYPE_LABEL,
    ImportResult,
    ParsedRow,
    RawRow,
    RowError,
)
from pf.ingest.normalize import normalize_description, to_cents, to_iso_date
from pf.ingest.reader import read_rows


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _balance_cents(raw: RawRow) -> int | None:
    """The running balance, which may be positive, negative, or absent."""
    positive = raw.by_name.get(COL_BALANCE, "").strip()
    negative = raw.by_name.get(COL_BALANCE_NEG, "").strip()
    try:
        if positive:
            return to_cents(positive, "")
        if negative:
            return -to_cents(negative, "")
    except RowError:
        # A balance we cannot read is not worth rejecting the transaction
        # over: it is informational, and identity does not depend on it.
        return None
    return None


def parse_row(raw: RawRow) -> ParsedRow:
    """One read row -> one storable transaction. Raises RowError if unusable."""
    if not any(cell.strip() for cell in raw.cells):
        raise RowError("empty_row", "row has no content")

    account = raw.by_name.get(COL_ACCOUNT, "").strip()
    if not account:
        raise RowError("no_account", "no account number on the row")

    date_op = to_iso_date(raw.by_name.get(COL_DATE_OP, ""))
    raw_value_date = raw.by_name.get(COL_DATE_VALUE, "").strip()
    date_value = to_iso_date(raw_value_date) if raw_value_date else date_op

    amount_cents = to_cents(
        raw.by_name.get(COL_INCOME, ""), raw.by_name.get(COL_EXPENSE, "")
    )

    code_common = raw.by_name.get(COL_CODE_COMMON, "").strip()
    code_own = raw.by_name.get(COL_CODE_OWN, "").strip()
    type_label = raw.by_name.get(COL_TYPE_LABEL, "").strip()
    kind, _mapped = kinds.derive_kind(code_common, code_own, type_label)

    description_raw = raw.by_name.get(COL_DESCRIPTION, "")

    return ParsedRow(
        row_hash=row_hash(raw.cells, account),
        account_number=account,
        date_op=date_op,
        date_value=date_value,
        amount_cents=amount_cents,
        balance_cents=_balance_cents(raw),
        kind=kind,
        code_common=code_common,
        code_own=code_own,
        description_raw=description_raw,
        description_norm=normalize_description(description_raw),
        type_label=type_label or None,
        counterparty_ref=raw.by_name.get(COL_REFERENCE_2, "").strip() or None,
    )


def _account_id(con: sqlite3.Connection, account_number: str) -> int:
    """Find the account, creating it on first sight."""
    found = con.execute(
        "SELECT id FROM accounts WHERE account_number = ?", (account_number,)
    ).fetchone()
    if found:
        return found["id"]
    cur = con.execute(
        "INSERT INTO accounts (account_number, label) VALUES (?, ?)",
        (account_number, account_number),
    )
    return int(cur.lastrowid)


_INSERT = """
INSERT OR IGNORE INTO transactions (
    row_hash, account_id, date_op, date_value, amount_cents, balance_cents,
    currency, kind, code_common, code_own, description_raw, description_norm,
    type_label, counterparty_ref, categorized_by, source_file, imported_at
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,'none',?,?)
"""


def import_file(
    path: Path | str,
    con: sqlite3.Connection,
    *,
    dry_run: bool = False,
    rejects_dir: Path | None = None,
) -> ImportResult:
    """Import one export. Safe to run twice on the same file."""
    path = Path(path)
    started = _now()
    result = ImportResult(source_file=str(path))
    imported_at = _now()

    accounts: dict[str, int] = {}
    parsed: list[ParsedRow] = []

    for raw in read_rows(path):
        result.rows_read += 1
        try:
            row = parse_row(raw)
        except RowError as err:
            result.add_rejection(raw.source_row, err)
            continue

        _, mapped = kinds.derive_kind(row.code_common, row.code_own, row.type_label or "")
        if not mapped:
            result.unmapped_kinds[(row.code_common, row.code_own)] += 1

        parsed.append(row)
        if result.date_min is None or row.date_op < result.date_min:
            result.date_min = row.date_op
        if result.date_max is None or row.date_op > result.date_max:
            result.date_max = row.date_op

    for row in parsed:
        if dry_run:
            exists = con.execute(
                "SELECT 1 FROM transactions WHERE row_hash = ?", (row.row_hash,)
            ).fetchone()
            if exists:
                result.skipped += 1
            else:
                result.inserted += 1
            continue

        if row.account_number not in accounts:
            accounts[row.account_number] = _account_id(con, row.account_number)

        before = con.total_changes
        con.execute(
            _INSERT,
            (
                row.row_hash,
                accounts[row.account_number],
                row.date_op,
                row.date_value,
                row.amount_cents,
                row.balance_cents,
                "EUR",
                row.kind,
                row.code_common,
                row.code_own,
                row.description_raw,
                row.description_norm,
                row.type_label,
                row.counterparty_ref,
                str(path),
                imported_at,
            ),
        )
        if con.total_changes > before:
            result.inserted += 1
        else:
            result.skipped += 1

    if not dry_run:
        con.execute(
            """INSERT INTO import_runs (
                   source_file, file_sha256, rows_read, rows_inserted,
                   rows_skipped, rows_rejected, started_at, finished_at
               ) VALUES (?,?,?,?,?,?,?,?)""",
            (
                str(path),
                file_hash(path),
                result.rows_read,
                result.inserted,
                result.skipped,
                result.rejected,
                started,
                _now(),
            ),
        )
        con.commit()
        if result.rejections:
            result.rejects_path = str(_write_rejects(result, rejects_dir))

    return result


def _write_rejects(result: ImportResult, rejects_dir: Path | None) -> Path:
    """Write rejected rows out, so they can be looked at rather than guessed about."""
    target_dir = rejects_dir or config.rejects_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    target = target_dir / f"rejects-{stamp}.csv"
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["source_row", "reason", "detail", "source_file"])
        for rejection in result.rejections:
            writer.writerow(
                [rejection.source_row, rejection.reason, rejection.detail, result.source_file]
            )
    return target
