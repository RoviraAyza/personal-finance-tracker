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
from pf.ingest.reclassify import reclassify
from pf.rules import coverage as coverage_mod
from pf.rules.apply import apply_rules, sync_rule_set
from pf.rules.categorizer import Categorizer
from pf.rules.loader import load_rule_set
from pf.rules.model import Candidate, RuleError


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


def cmd_reclassify(args: argparse.Namespace) -> int:
    """Re-derive every transaction's kind from its stored source codes."""
    path = config.db_path()
    if not path.exists():
        print(f"no database at {path}", file=sys.stderr)
        return 2

    con = open_initialised(path)
    try:
        result = reclassify(con, dry_run=args.dry_run)
    finally:
        con.close()

    label = "would change" if args.dry_run else "changed"
    print(f"  considered   {result.considered:>7,}")
    print(f"  {label:<12} {result.changed:>7,}")
    print(f"  unchanged    {result.unchanged:>7,}")

    if result.transitions:
        print()
        print("  reclassifications:")
        for (old, new), count in result.transitions.most_common():
            print(f"    {count:>6,}  {old}  ->  {new}")

    print()
    if result.unmapped_codes:
        print(f"  still unmapped ({result.unmapped:,} rows):")
        for (common, own), count in result.unmapped_codes.most_common(10):
            print(f"    {count:>6,}  codes {common}/{own}")
    else:
        print("  no unmapped code pairs remain")
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


def _load_categorizer():
    categories, rules = load_rule_set()
    return categories, rules, Categorizer(categories, rules)


def cmd_rules_check(args: argparse.Namespace) -> int:
    """Validate the rule set and report rules that do nothing."""
    try:
        categories, rules, categorizer = _load_categorizer()
    except RuleError as err:
        print("rule set is not usable:", file=sys.stderr)
        print(f"  {err}", file=sys.stderr)
        return 3

    print(f"  categories  {len(categories)}")
    print(f"  rules       {len(rules)}")

    shadowed = categorizer.shadowed_rules()
    print(f"  shadowed    {len(shadowed)}")
    for earlier, later in shadowed[:10]:
        print(
            f"    {earlier.pattern!r} (p{earlier.priority}) hides "
            f"{later.pattern!r} (p{later.priority})"
        )

    path = config.db_path()
    if not path.exists():
        print("  (no database, so unused rules cannot be checked)")
        return 0

    con = open_initialised(path)
    try:
        candidates = [
            Candidate(
                description_norm=row["description_norm"],
                kind=row["kind"],
                amount_cents=row["amount_cents"],
            )
            for row in con.execute(
                "SELECT description_norm, kind, amount_cents FROM transactions"
            )
        ]
    finally:
        con.close()

    unused = categorizer.unused_rules(candidates)
    print(f"  unused      {len(unused)}   (a rule matching nothing is usually a typo)")
    for rule in unused[:20]:
        print(f"    {rule.pattern!r} ({rule.match}) -> {rule.category}")
    return 0


def cmd_categorize(args: argparse.Namespace) -> int:
    """Apply the rule set to stored transactions."""
    path = config.db_path()
    if not path.exists():
        print(f"no database at {path}", file=sys.stderr)
        return 2
    try:
        categories, rules, categorizer = _load_categorizer()
    except RuleError as err:
        print("rule set is not usable:", file=sys.stderr)
        print(f"  {err}", file=sys.stderr)
        return 3

    con = open_initialised(path)
    try:
        cat_ids, rule_ids = sync_rule_set(con, categories, rules)
        result = apply_rules(
            con, categorizer, cat_ids, rule_ids, only_uncategorised=not args.all
        )
    finally:
        con.close()

    print(f"  considered          {result.considered:>7,}")
    print(f"  newly categorised   {result.assigned:>7,}")
    print(f"  moved               {result.changed:>7,}")
    print(f"  cleared             {result.cleared:>7,}   (rule no longer exists)")
    print(f"  unchanged           {result.unchanged:>7,}")
    print(f"  manual, untouched   {result.left_alone:>7,}")
    print(f"  still uncategorised {result.still_uncategorised:>7,}")
    return 0


def cmd_coverage(args: argparse.Namespace) -> int:
    """How much of the spending the rules explain."""
    path = config.db_path()
    if not path.exists():
        print(f"no database at {path}", file=sys.stderr)
        return 2

    con = open_initialised(path)
    try:
        if args.holdout:
            train, test = coverage_mod.measure_holdout(
                con, train_to=args.train_to, test_from=args.test_from
            )
            print(
                f"  rules fitted on data up to {args.train_to}, "
                f"measured on {args.test_from} onwards"
            )
            print(
                f"    fitted period  {train.rows_pct:5.1f}% rows  "
                f"{train.value_pct:5.1f}% value   ({train.rows_total:,} rows)"
            )
            print(
                f"    held out       {test.rows_pct:5.1f}% rows  "
                f"{test.value_pct:5.1f}% value   ({test.rows_total:,} rows)"
            )
            return 0

        if args.by_month:
            print("  month     unknown / rows")
            for month, unknown, total in coverage_mod.monthly_uncategorised(con):
                print(f"  {month}   {unknown:>7,} / {total:>5,}")
            return 0

        m = coverage_mod.measure(con)
        print("  outgoing transactions, excluding transfers between own accounts")
        print(
            f"    rows   {m.rows_categorised:>7,} / {m.rows_total:>7,}   "
            f"{m.rows_pct:5.1f}%"
        )
        print(
            f"    value  {cents_to_text(m.value_categorised_cents):>12} / "
            f"{cents_to_text(m.value_total_cents):>12}   {m.value_pct:5.1f}%"
        )
        print()
        print("  by category")
        for name, n, value in m.by_category:
            print(f"    {name:<28} {n:>6,} rows  {cents_to_text(value):>12}")
        print()
        print("  biggest uncategorised, by value -- the ones worth a rule")
        for description, n, value in m.worst_uncategorised:
            print(f"    {cents_to_text(value):>11}  {n:>4}x  {description[:38]}")
        return 0
    finally:
        con.close()


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

    recl = subs.add_parser(
        "reclassify",
        help="re-derive transaction kinds after the mapping has been corrected",
    )
    recl.add_argument(
        "--dry-run", action="store_true", help="report without writing"
    )
    recl.set_defaults(func=cmd_reclassify)

    boot = subs.add_parser(
        "bootstrap-prompt",
        help="write the categorisation prompt and merchant list to files",
    )
    boot.add_argument(
        "--out", default="bootstrap", help="directory to write into (default: bootstrap)"
    )
    boot.set_defaults(func=cmd_bootstrap_prompt)

    check = subs.add_parser("rules", help="validate the rule set")
    check.add_argument("subcommand", nargs="?", default="check", choices=["check"])
    check.set_defaults(func=cmd_rules_check)

    categ = subs.add_parser("categorize", help="apply the rule set to transactions")
    categ.add_argument(
        "--all",
        action="store_true",
        help="re-apply to rows already categorised by rule (never to manual ones)",
    )
    categ.set_defaults(func=cmd_categorize)

    covp = subs.add_parser("coverage", help="how much of the spending is explained")
    covp.add_argument("--by-month", action="store_true", help="unknowns per month")
    covp.add_argument(
        "--holdout",
        action="store_true",
        help="measure rules against data they were not derived from",
    )
    covp.add_argument("--train-to", default="2024-12-31")
    covp.add_argument("--test-from", default="2025-01-01")
    covp.set_defaults(func=cmd_coverage)

    summary = subs.add_parser("summary", help="what is in the database")
    summary.set_defaults(func=cmd_summary)

    return parser


def main(argv: list[str] | None = None) -> int:
    _force_utf8_output()
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
