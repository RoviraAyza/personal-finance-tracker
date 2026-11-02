# CLAUDE.md

Household spending tracker. Imports CaixaBank `.xls` exports, categorises them
with deterministic rules, and reports spend by category for any period.

Read `intent/intent.md` for why, `spec/spec.md` for the design, `plan/` for the
current slice. **Artifacts are approved before the next stage starts; if the
implementation departs from a plan, update the plan in the same commit.**

## Commands

```
python -m pytest                 # the whole suite
python -m pytest -v              # with test names (the review surface)
python -m pytest -m realdata     # opt-in: needs PF_REAL_XLS set
python -m pip install -e .       # once, after cloning

python -m pf.cli init-db
python -m pf.cli import <file.xls> [--dry-run]
python -m pf.cli summary
```

`make` is not installed on this machine. Do not write a Makefile.

## Conventions

- **Money is integer cents, always.** Converted once at the import boundary via
  `Decimal`. A float must never reach a stored amount.
- **Dates are ISO text** in the database, day-first (`DD/MM/YYYY`) in the source.
- **Pure functions stay pure.** `normalize`, `kinds`, `identity` do no I/O and
  read no clock. `importer` is the only module touching both a file and the DB.
- **Columns are addressed by normalised name**, never by position, and never
  inferred from which columns contain data.
- **Nothing is dropped silently.** An unusable row is counted, given a reason,
  and written out. An unmapped code pair is reported.
- **Mappings are data, not branching logic** — see `kinds._CODE_MAP`. Rules
  will follow the same pattern in S2.
- Test names are plain English because they are how the author reviews work in
  a language he does not read. Keep them descriptive sentences.
- Comments say *why*, with the measured number where there is one.

## Architecture

```
.xls --> reader --> parse_row --> SQLite --> (S3) FastAPI --> React
                      |
          normalize / kinds / identity   (pure)
```

The database lives **outside this repo** (`%LOCALAPPDATA%\PersonalFinance`),
because the repo is in a Google Drive folder and Drive sync corrupts SQLite.
Override with `PF_DB_PATH`.

## Things to get right

- **Identity is a hash of the whole row**, minus trailing blanks. There is no
  natural key: `date + amount + merchant` collides 98 times in nine years and
  every collision is a genuine distinct transaction. Never narrow this.
- **Trailing empty columns must not affect the hash.** Excel omits them, so the
  same export can report 24 or 25 columns.
- **Never commit bank data.** Fixtures are synthetic
  (`tests/fixtures/make_xls.py`). No account numbers, card numbers or family
  names in the repo — including in documentation.
- **Own-transfers are not spending.** `transfer_own` is ~€267k in over nine
  years; counting it would wreck every total.
- **The type codes are impure.** `12`/`040` is mostly card purchases but also
  carries `REINT.CAJERO`. Text overrides must be specific: that column holds
  people's *names* on transfers, so a loose pattern matches a surname.
- **`ã` means `Ñ`** — the bank's own damage. Repair before stripping accents,
  or `PEãIS` normalises to `PEAIS` and never matches `PEÑIS`.
- `-q` in pytest `addopts` cancels `-v`. Don't put it back.
