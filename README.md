# Personal Finance Tracker

Categorise and report household spending from bank exports.

My bank holds every transaction but is bad at the one thing I care about: it
won't let me define my own categories, and it won't let me save a filter — so
every time I want to know where the money went, I rebuild the same query from
scratch. This fixes that.

**Status:** slice S1 of 6 complete — import works, categorisation is next.

---

## What it does today

Imports a CaixaBank "Excel simple" export into a local SQLite database,
idempotently, and tells you what it found. Nine years of statements (10,034
transactions) load in a couple of seconds, and re-importing the same file —
or an overlapping date range — changes nothing.

## What it will do

Categorise automatically from rules bootstrapped out of the existing history,
surface only what it can't categorise, and answer *"how much did I spend in
this period, and in which categories?"* for any period — with drill-down,
comparison against a reference period, and filters you can save. Then the same
answers on a phone (see `intent/intent.md`).

---

## Setup

Requires Python 3.12+.

```bash
python -m pip install -e .          # the package and its one runtime dependency
python -m pip install -e ".[dev]"   # plus pytest and the fixture writer
```

## Use

```bash
python -m pf.cli init-db                        # create the database
python -m pf.cli import statement.xls --dry-run # look before you leap
python -m pf.cli import statement.xls           # import it
python -m pf.cli summary                        # what's in there
```

The database lives in `%LOCALAPPDATA%\PersonalFinance\finance.db`, **not** in
this repository. That is deliberate: this folder is inside Google Drive, and
Drive syncs files while they are open, which corrupts SQLite. Override the
location with `PF_DB_PATH`.

Rows that cannot be parsed are never dropped silently — they are counted, given
a reason, and written to a CSV the importer names.

## Tests

```bash
python -m pytest -v        # 99 tests, names included
```

All fixtures are **synthetic**: `tests/fixtures/make_xls.py` generates `.xls`
files reproducing the real export's structure — title block above the header,
Catalan column names, split amount columns, merchant names truncated at 17
characters, the bank's own `ã`-for-`Ñ` damage — with invented merchants and
amounts. The suite needs no bank data and none is in this repository.

To additionally check the parser against a real statement:

```bash
PF_REAL_XLS=/path/to/export.xls python -m pytest -m realdata
```

Those tests skip when the variable is unset.

---

## How this is built

Following Anthropic's [AI-native SDLC
playbook](https://claude.com/resources/articles/the-ai-native-sdlc-playbook),
adapted for one person:

| | |
|---|---|
| `intent/intent.md` | Why this exists, what it must do, every decision and its reasoning |
| `spec/spec.md` | Requirements and design: schema, interfaces, thresholds |
| `plan/` | One implementation plan per slice, updated when reality departs from it |
| `CLAUDE.md` | What a coding agent needs to know before touching this |

Each artifact is reviewed and approved before the next begins. Decisions are
recorded with their rationale — including the ones that were later reversed.

## Privacy

Everything runs locally. No bank API, no server, no account. The one network
call in the design is a single offline step that derives categorisation rules
from the *deduplicated list of merchant names* — no amounts, dates, balances,
account numbers or card numbers. Bank data is gitignored and never committed.
