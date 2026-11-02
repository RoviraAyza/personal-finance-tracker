# Plan — S1: Parse → SQLite

**Status:** 🟢 **APPROVED** 2026-11-02 — in progress
**Slice:** S1 of 6 (see [`spec/spec.md`](../spec/spec.md) §13)
**Author:** Claude (agent-written), for review by Jose
**Date:** 2026-11-02
**Derives from:** `spec/spec.md` (approved 2026-11-02)

> **Convention.** One plan per slice, in `plan/`. If implementation departs
> from the plan, **this file is updated in the same commit** (playbook Play 3a).

---

## 1. Goal

Turn a CaixaBank `.xls` export into queryable rows in SQLite, idempotently,
with a CLI that reports what happened. **No categorization** (that is S2) and
**no UI** (that is S3).

### Done when

| #   | Criterion                                                   | How it is checked        |
| --- | ----------------------------------------------------------- | ------------------------ |
| D1  | The 9-year file imports as **10,034 rows, 1 rejected**      | `pf import` output       |
| D2  | Re-importing the same file inserts **0**, skips **10,034**  | run it twice             |
| D3  | The October file then imports **127 new** rows              | `pf import` output       |
| D4  | `pf summary` reports counts, date range and totals per kind | eyeball                  |
| D5  | `python -m pytest` passes                                   | one command (see note)   |
| D6  | Every trap in spec §12 that belongs to S1 has a test        | review the list in §5    |

### Explicitly not in S1

Categorization, rules, `rules.json`, the LLM bootstrap, FastAPI, React,
coverage thresholds, the second account, snapshot export.

---

## 2. Dependencies

⚠️ **Deviation from the approved plan (2026-11-02).** The plan said two
dependencies. It is three — but still **one at runtime**:

```
xlrd==2.0.1     # runtime: reads legacy BIFF8; verified against the real file
pytest>=8       # dev only
xlwt>=1.3       # dev only: WRITES .xls, for synthetic fixtures
```

`xlwt` was missed when planning: `xlrd` only *reads*, so there was no way to
produce the `.xls` test fixtures the plan calls for in step 4. Verified that
`xlwt` writes a file `xlrd` reads back correctly, including the sheet name.
Dev-only, so nothing ships with it.

No ORM — the schema is six tables and the queries are simple; `sqlite3` from
the standard library is less to learn and less to go wrong. No `pandas`: it
would be the largest dependency in the project for work that is a loop.
No CLI framework — `argparse` is stdlib.

⚠️ **Deviation 2: no Makefile.** `make` is not installed on the originator's
Windows machine, so a `Makefile` would be a file he cannot run. The single
command is **`python -m pytest`**, with the CLI invoked directly. The README
documents both. Dropping the Makefile from the file list in §3.

---

## 3. Files

New files only; the repo currently has no code.

```
pyproject.toml                   project metadata + pytest config
.env.example                     documents PF_DB_PATH
README.md                        how to run it

src/pf/__init__.py
src/pf/config.py                 paths; PF_DB_PATH; default %LOCALAPPDATA%
src/pf/cli.py                    argparse entry: import, summary, init-db

src/pf/db/__init__.py
src/pf/db/schema.sql             the DDL from spec §3, verbatim
src/pf/db/connection.py          connect(), init_schema(), WAL, foreign_keys

src/pf/ingest/__init__.py
src/pf/ingest/model.py           RawRow, ParsedRow, Rejection  (frozen dataclasses)
src/pf/ingest/reader.py          .xls -> Iterator[RawRow]   (header location, column map)
src/pf/ingest/normalize.py       description normalization; money; dates
src/pf/ingest/kinds.py           (code_common, code_own) -> kind, + text overrides
src/pf/ingest/identity.py        row_hash
src/pf/ingest/importer.py        orchestration; insert-or-skip; import_runs; rejects

tests/conftest.py
tests/fixtures/make_xls.py       synthetic .xls generator (structure, fake data)
tests/test_normalize.py
tests/test_kinds.py
tests/test_identity.py
tests/test_reader.py
tests/test_importer.py
tests/test_real_corpus.py        skipped unless PF_REAL_XLS is set
```

### Module boundaries

`reader` knows about Excel and nothing about the database.
`normalize`, `kinds`, `identity` are **pure functions** — no I/O, no clock.
`importer` is the only module that touches both a file and the database.
`cli` contains no logic, only argument wiring and output formatting.

This matters for testing: everything interesting is pure and testable without
a file or a database.

---

## 4. Work order

Pure functions first, I/O last, so each step is verifiable when written.

| #   | Step                                           | Why here                                                                                                       |
| --- | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| 1 | `pyproject.toml`, package skeleton | the test command must work before there is anything to test |
| 2   | `config.py`                                    | Everything else needs the DB path                                                                              |
| 3   | `db/schema.sql` + `connection.py`              | Lift the DDL verbatim from the approved spec                                                                   |
| 4   | **`tests/fixtures/make_xls.py`**               | **Before the reader.** Tests need input, and a generator forces the real file's quirks to be stated explicitly |
| 5   | `normalize.py` + tests                         | Pure, self-contained, highest trap density                                                                     |
| 6   | `kinds.py` + tests                             | Pure, table-driven                                                                                             |
| 7   | `identity.py` + tests                          | Pure, one function                                                                                             |
| 8   | `reader.py` + tests                            | Needs fixtures from step 4                                                                                     |
| 9   | `importer.py` + tests                          | Integration; needs all the above                                                                               |
| 10  | `cli.py`                                       | Thin wiring over a working importer                                                                            |
| 11  | Run against the **real** files; confirm D1–D4  | The acceptance moment                                                                                          |
| 12  | `README.md`; draft `CLAUDE.md`                 | Written once there is a codebase to describe                                                                   |

Step 4 before step 8 is the important ordering choice. Writing the generator
first means every quirk measured in `intent.md` §3 gets encoded as something a
test can produce, rather than being remembered later.

---

## 5. Tests

From spec §12, the subset that belongs to S1. Each maps to a measured fact.

### `test_normalize.py`
- `ã` → `Ñ`: `'0150-CONSUM PEãIS'` → contains `PEÑIS`; all 22 real cases are this one substitution
- accent stripping: `PEÑIS` and `PENIS` normalize equal
- internal whitespace collapsed (28 real values have doubles)
- case folded to upper (110 real values are mixed case)
- **digits preserved** — `EL ARBOL 5228` keeps `5228` (170 real values carry meaningful digits)
- leading/trailing padding stripped (card rows are space-padded)
- idempotent: `norm(norm(x)) == norm(x)`

### Money and dates (also `test_normalize.py`)
- `7.66` → `766` cents; `-` sign applied from which column was filled
- expense → negative, income → positive
- both filled → `Rejection`; neither filled → `Rejection`
- `'11/09/2026'` → `'2026-09-11'` (day-first, not month-first)
- `'31/10/2026'` → `'2026-10-31'` — a date that would be invalid month-first
- unparseable date → `Rejection`, never coerced
- no float arithmetic reaches a stored amount

### `test_kinds.py`
- `('12','040')` → `card_purchase`
- `('02','067')` → `transfer_own`
- `('11','040')` → `cash_withdrawal`
- `('04','002')` → `transfer_person`
- `('02','040')` → `refund`
- unmapped `('77','999')` → `other` **and** is reported, not swallowed
- text override: `('12','040')` with label `REINT.CAJERO` → `cash_withdrawal`,
  not `card_purchase` *(the measured impurity in the codes)*

### `test_identity.py`
- identical rows hash identically
- a change in **any** of the 25 cells changes the hash
- **two same-day, same-amount, same-merchant rows hash differently** when
  their balances differ — the 98 real cases that a narrower key would destroy
- the account number participates in the hash

### `test_reader.py`
- header found with a 2-, 3- and 5-row preamble *(not hardcoded to row 3)*
- missing a required header → raises, with the missing name in the message
- columns mapped **by name**: a fixture with reordered columns still parses
- a column empty throughout is fine *(the monthly file leaves two empty)*
- trailing all-empty row → `Rejection`, not a crash
- the account number is read from column 1

### `test_importer.py`
- fresh DB: N rows in → N inserted
- same file again → 0 inserted, N skipped **(D2)**
- overlapping date ranges → only genuinely new rows inserted
- rejections counted and written, not silently dropped
- `import_runs` records a row per run with accurate counts
- an unknown account number creates an `accounts` row
- `category_id` is NULL and `categorized_by` is `'none'` — S1 does not categorize

### `test_real_corpus.py` — skipped unless `PF_REAL_XLS` is set
- the 9-year file yields exactly **10,034** rows and **1** rejection
- all dates parse; zero date rejections
- `row_hash` is unique across all rows *(0 collisions, as measured)*
- `transfer_own` totals ≈ **€205,219 in / €5,773 out** *(the distortion guard)*
- `card_purchase` outflow ≈ **€186,823**, total outflow ≈ **€270,760**
- 1,082 distinct `description_norm` values

The real-data test never ships data — it reads a path from the environment and
skips when absent, so the suite is green on a machine without the statements.

---

## 6. Interfaces worth agreeing now

```python
# config.py
def db_path() -> Path: ...          # PF_DB_PATH, else %LOCALAPPDATA%/PersonalFinance/finance.db

# ingest/model.py
@dataclass(frozen=True)
class RawRow:
    cells: tuple[str, ...]          # all 25, stripped, as text — the hash input
    by_name: Mapping[str, str]      # header name -> value
    source_row: int                 # 0-based sheet row, for error messages

@dataclass(frozen=True)
class ParsedRow:
    row_hash: str
    account_number: str
    date_op: str                    # ISO
    date_value: str
    amount_cents: int               # signed
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
    source_row: int
    reason: str                     # machine-readable, e.g. 'no_amount'
    detail: str

# ingest/reader.py
def read_rows(path: Path) -> Iterator[RawRow]: ...

# ingest/normalize.py
def normalize_description(raw: str) -> str: ...
def to_cents(income: str | float, expense: str | float) -> int: ...   # raises RowError
def to_iso_date(text: str) -> str: ...                                 # raises RowError

# ingest/kinds.py
def derive_kind(code_common: str, code_own: str, type_label: str) -> tuple[str, bool]:
    """Returns (kind, was_mapped). was_mapped=False means it fell through to
    'other' and should be reported."""

# ingest/identity.py
def row_hash(cells: Sequence[str], account_number: str) -> str: ...

# ingest/importer.py
@dataclass(frozen=True)
class ImportResult:
    rows_read: int
    inserted: int
    skipped: int
    rejected: int
    rejections: list[Rejection]
    unmapped_kinds: Counter[tuple[str, str]]

def import_file(path: Path, con: Connection) -> ImportResult: ...
```

`derive_kind` returning `(kind, was_mapped)` is deliberate: the spec requires
unmapped code combinations to be **reported**, and a bare string return would
make that impossible without a second lookup.

---

## 7. CLI

```
pf init-db                     create the database and schema
pf import <file.xls>           import; print the result
pf import <file.xls> --dry-run parse and report, write nothing
pf summary                     counts, date range, totals per kind
```

`--dry-run` is worth having in S1: it lets a new export be inspected before it
touches the database, which is exactly what you want the first time the bank
changes something.

Expected output shape:

```
$ pf import TT120926.075.XLS
  read      10,035 rows
  inserted  10,034
  skipped        0
  rejected       1   -> rejects/2026-11-02T18-14-02.csv
  unmapped kinds: none
  date range 2017-09-11 .. 2026-09-11
```

⚠️ **Windows console encoding.** Printing Catalan/Spanish text to the Windows
console produced mojibake during investigation. The CLI must force UTF-8 on
stdout (`reconfigure(encoding='utf-8')`) or the output will be unreadable
exactly where it matters.

---

## 8. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **DB in Google Drive corrupts SQLite** | High if defaulted wrong | Default outside the synced folder (spec §2); `pf summary` prints the path so it is visible |
| Windows console mangles accented output | **Already observed** | Force UTF-8 on stdout; a test asserts the normalizer's output, not the console's |
| `xlrd` breaks on a future export | Low | Verified on two real files; `--dry-run` and loud header validation catch it before data is touched |
| Header/layout changes at the bank | Low, eventually certain | Locate header by marker, map by name, fail loudly with the missing header named |
| Date parsed month-first | Low | Explicit day-first parse; a test uses `31/10/2026`, impossible month-first |
| Float cents drift | Medium if careless | Convert once at the boundary; a test asserts integer-only arithmetic |
| `%LOCALAPPDATA%` missing/unwritable | Low | Create on demand; clear error naming the path |
| Over-building S1 | **Medium — the real risk** | The "not in S1" list in §1 is the guard; categorization is S2 |

---

## 9. What this slice does *not* prove

Honest limits, so the next slice starts from the truth:

- **Nothing about whether categorization will work.** S1 ends with 10,034
  uncategorized rows. The coverage thresholds are S2's problem.
- **Nothing about the UI or React** — the learning payload starts at S3.
- **Nothing about the monthly ritual being pleasant.** S1 makes it *possible*,
  S4 makes it *quick*.
- The real-corpus test proves the parser against **one account at one bank**.

---

## 10. Review checklist

- [ ] Scope of S1 is right — nothing missing, nothing that belongs to S2
- [ ] Two dependencies is the right call (no pandas, no ORM, no CLI framework)
- [ ] File layout and module boundaries make sense
- [ ] Work order agreed — in particular, the fixture generator before the reader
- [ ] The interfaces in §6 are ones he'd want to maintain
- [ ] `--dry-run` worth having in S1
- [ ] Test list covers the traps
- [ ] **Approved → implement S1**

---

## 11. Progress log

Updated as implementation proceeds, per the convention at the top of this file.

| Step | State | Notes |
|---|---|---|
| 1 — scaffolding | ✅ done | `pyproject.toml`; src layout; no Makefile (deviation 2) |
| 2 — `config.py` | ✅ done | `PF_DB_PATH`, default `%LOCALAPPDATA%/PersonalFinance` |
| 3 — schema + connection | ✅ done | DDL from spec §3, tables reordered so FK targets precede referrers; WAL + `foreign_keys=ON` |
| 4 — fixture generator | ✅ done | `tests/fixtures/make_xls.py`; needed `xlwt` (deviation 1) |
| 5 — `normalize.py` | ✅ done | **27 tests passing** |
| 6 — `kinds.py` | ✅ done | code table + text overrides as data; **18 tests** |
| 7 — `identity.py` | ✅ done | full-row sha256; hash scheme pinned by test; **17 tests** |
| 8 — `reader.py` | ✅ done | header located not assumed; columns by normalised name; **19 tests**. Verified on both real files: 10,035/128 rows, 0 hash collisions |
| 9 — `importer.py` | ✅ done | insert-or-ignore on row hash; rejections written out; **18 tests** |
| 10 — `cli.py` | ✅ done | `init-db`, `import`, `import --dry-run`, `summary`; UTF-8 forced on stdout |
| 11 — real-file acceptance | ✅ **D1–D4 met** | 10,034 inserted + 1 rejected; re-import 0/10,034; October +127; **totals reconcile to the cent against the raw files** |
| 12 — README, `CLAUDE.md` | ⏳ next | |

### Deviations from the approved plan

1. **`xlwt` added** as a dev dependency — `xlrd` cannot write, so fixtures
   were impossible as planned. Runtime dependencies unchanged (one).
2. **No Makefile** — `make` is not installed on the target machine. The single
   test command is `python -m pytest`.
3. **Schema table order changed** from the spec's listing so each foreign-key
   target is created before the table referencing it. No column changes; the
   spec's DDL is otherwise verbatim.
4. **Row identity ignores trailing empty columns.** Found while building the
   fixtures: Excel does not store trailing empty columns, so the same export
   can report 24 or 25 columns. Hashing all cells blindly would make an
   identical transaction hash two different ways between such files and import
   twice. Trailing blanks are now trimmed before hashing — safe, since two
   rows differing only in trailing blanks are the same row. The spec's
   "hash over all 25 source cells" (§4.3) should be read as "over all
   meaningful cells".

### Acceptance evidence (2026-11-02)

Independent reconciliation, reading the raw spreadsheets without going through
the importer:

| | rows | in | out |
|---|---|---|---|
| Raw spreadsheets | 10,161 | €274,613.03 | €273,968.64 |
| Database | 10,161 | €274,613.03 | €273,968.64 |
| **Difference** | **0** | **+0.00** | **+0.00** |

Two findings from the acceptance run:

1. **`transfer_own` is €267,342 in, not the €205,219 quoted during Stage 1.**
   The earlier figure counted only rows whose label literally read
   `TRASPASO PROPIO`. Code pair `02/067` also carries plain `TRASPASO`, and
   the descriptions show 95 of those 113 rows come from the spouse and 18 from
   the originator — household funding, correctly classified as own-transfers.
   Only 3 rows (€105) remain genuinely ambiguous. The classification is more
   correct than the original hand measurement; `intent.md` §3 should be read
   with that correction.
2. **The cash-withdrawal override fires 27 times**, lifting withdrawals from
   the 369 that carry the withdrawal code to 396. Those 27 sat under the
   card-purchase code with a `REINT.CAJERO` label — precisely the measured
   impurity the override exists for.

64 rows (0.6%) fall through to kind `other` across 10 unmapped code pairs, and
are reported by the importer rather than absorbed.
