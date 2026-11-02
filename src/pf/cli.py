"""Command line entry point.

No logic lives here -- only argument parsing and formatting. Anything worth
testing belongs in the modules this calls.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pf import config
from pf.db.connection import open_initialised
from pf.ingest.importer import import_file
from pf.ingest.model import FileFormatError, ImportResult
from pf.ingest.normalize import cents_to_text
from pf.ingest.reader import describe
from pf.bootstrap.prompt import write_payload


def _force_utf8_output() -> None:
    """Make accented output readable on the Windows console.

    Without this, 'Concepte comú' and every Spanish merchant name prints as
    mojibake -- which matters most in exactly the messages a person needs to
    read, like a rejection detail.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_init_db(args: argparse.Namespace) -> int:
    path = config.db_path()
    con = open_initialised(path)
    tables = [
        r["name"]
        for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    ]
    con.close()
    print(f"database ready at {path}")
    print(f"  tables: {', '.join(tables)}")
    return 0


def _print_result(result: ImportResult, *, dry_run: bool) -> None:
    verb = "would insert" if dry_run else "inserted"
    print(f"  read       {result.rows_read:>8,} rows")
    print(f"  {verb:<10} {result.inserted:>8,}")
    print(f"  skipped    {result.skipped:>8,}   (already present)")
    print(f"  rejected   {result.rejected:>8,}", end="")
    if result.rejects_path:
        print(f"   -> {result.rejects_path}")
    else:
        print()

    if result.rejected:
        reasons: dict[str, int] = {}
        for rejection in result.rejections:
            reasons[rejection.reason] = reasons.get(rejection.reason, 0) + 1
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print(f"               {count:>5,}  {reason}")

    if result.unmapped_kinds:
        print("  unmapped transaction kinds (worth a look):")
        for (common, own), count in result.unmapped_kinds.most_common(10):
            print(f"               {count:>5,}  codes {common}/{own}")
    else:
        print("  unmapped kinds: none")

    if result.date_min:
        print(f"  dates      {result.date_min} .. {result.date_max}")


def cmd_import(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.exists():
        print(f"no such file: {path}", file=sys.stderr)
        return 2

    if args.dry_run:
        info = describe(path)
        print(f"{path.name}  (dry run -- nothing will be written)")
        print(f"  sheet      {info['sheet']!r}")
        print(f"  header row {info['header_row']}")
        print(f"  data rows  {info['data_rows']:,}")
    else:
        print(f"{path.name}")

    con = open_initialised(config.db_path())
    try:
        result = import_file(path, con, dry_run=args.dry_run)
    except FileFormatError as err:
        print(f"\n  NOT the export we know how to read:\n    {err}", file=sys.stderr)
        return 3
    finally:
        con.close()

    _print_result(result, dry_run=args.dry_run)
    return 0


def cmd_bootstrap_prompt(args: argparse.Namespace) -> int:
    """Write the bootstrap payload to files. Sends nothing anywhere."""
    path = config.db_path()
    if not path.exists():
        print(f"no database at {path}", file=sys.stderr)
        print("run: pf init-db", file=sys.stderr)
        return 2

    out = Path(args.out)
    con = open_initialised(path)
    try:
        prompt_path, merchants_path, payload = write_payload(con, out)
    finally:
        con.close()

    print("nothing has been sent anywhere. two files were written:")
    print(f"  {prompt_path}")
    print(f"  {merchants_path}")
    print()
    print(f"  distinct descriptions in the database : {payload.total_distinct:,}")
    print(f"  excluded (transfer rows only)         : {payload.excluded_transfer_only:,}")
    print(f"  merchant strings in the payload       : {payload.count:,}")
    print()
    print("read merchants.txt before sending it. it contains merchant names")
    print("only: no amounts, dates, balances, account or card numbers.")
    return 0


def cmd_summary(args: argparse.Namespace) -> int:
    path = config.db_path()
    if not path.exists() and str(path) != ":memory:":
        print(f"no database yet at {path}\nrun: pf init-db", file=sys.stderr)
        return 2

    con = open_initialised(path)
    total = con.execute("SELECT COUNT(*) AS n FROM transactions").fetchone()["n"]
    print(f"database   {path}")
    print(f"transactions {total:,}")

    if not total:
        con.close()
        return 0

    span = con.execute(
        "SELECT MIN(date_op) AS lo, MAX(date_op) AS hi FROM transactions"
    ).fetchone()
    print(f"date range   {span['lo']} .. {span['hi']}")

    print("\naccounts")
    for acct in con.execute(
        """SELECT a.label, COUNT(t.row_hash) AS n
           FROM accounts a LEFT JOIN transactions t ON t.account_id = a.id
           GROUP BY a.id ORDER BY n DESC"""
    ):
        print(f"  {acct['n']:>8,}  {acct['label']}")

    print("\nby kind                     rows            in            out")
    for kind in con.execute(
        """SELECT kind,
                  COUNT(*) AS n,
                  COALESCE(SUM(CASE WHEN amount_cents > 0 THEN amount_cents END), 0) AS cr,
                  COALESCE(SUM(CASE WHEN amount_cents < 0 THEN -amount_cents END), 0) AS db
           FROM transactions GROUP BY kind ORDER BY n DESC"""
    ):
        print(
            f"  {kind['kind']:<22} {kind['n']:>7,}  "
            f"{cents_to_text(kind['cr']):>12}  {cents_to_text(kind['db']):>13}"
        )

    uncategorised = con.execute(
        "SELECT COUNT(*) AS n FROM transactions WHERE categorized_by = 'none'"
    ).fetchone()["n"]
    print(f"\nuncategorised {uncategorised:,} of {total:,}")
    if uncategorised == total:
        print("  (categorisation is slice S2 -- nothing is categorised yet)")

    runs = con.execute(
        "SELECT COUNT(*) AS n FROM import_runs"
    ).fetchone()["n"]
    print(f"import runs  {runs}")
    con.close()
    return 0


# --------------------------------------------------------------------------
# Wiring
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pf", description="Categorise and report household spending."
    )
    subs = parser.add_subparsers(dest="command", required=True)

    init = subs.add_parser("init-db", help="create the database and its schema")
    init.set_defaults(func=cmd_init_db)

    imp = subs.add_parser("import", help="import a bank export (.xls)")
    imp.add_argument("file", help="path to the export")
    imp.add_argument(
        "--dry-run",
        action="store_true",
        help="parse and report without writing anything",
    )
    imp.set_defaults(func=cmd_import)

    boot = subs.add_parser(
        "bootstrap-prompt",
        help="write the categorisation prompt and merchant list to files",
    )
    boot.add_argument(
        "--out", default="bootstrap", help="directory to write into (default: bootstrap)"
    )
    boot.set_defaults(func=cmd_bootstrap_prompt)

    summary = subs.add_parser("summary", help="what is in the database")
    summary.set_defaults(func=cmd_summary)

    return parser


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
