# Spec: Personal Finance Tracker — Step 1 (Desktop)

**Status:** 🟡 Draft — awaiting review
**Author:** Claude (agent-written), for review and correction by Jose
**Date:** 2026-11-02
**Derives from:** [`intent/intent.md`](../intent/intent.md) (approved 2026-11-02)

> **Scope of this document.** Step 1 only: the working desktop tool. Step 2
> (the Expo iPhone app) is designed later, against a foundation that already
> works. Where a step‑1 decision exists to keep step 2 cheap, it says so.
>
> Every quantitative claim here was measured against the originator's real
> 9‑year export (10,034 rows) and October 2026 monthly export (127 rows).

---

## 1. What step 1 delivers

A locally-run desktop tool that answers **"how much did I spend in this
period, and in which categories?"** — with drill-down, saveable filters, and a
monthly import that takes minutes rather than an evening.

### In scope

| # | Capability | Why |
|---|---|---|
| R1 | Import a CaixaBank `.xls` export, idempotently | The monthly ritual |
| R2 | Categorize automatically via deterministic rules | The core failure of the bank's app |
| R3 | Surface what *couldn't* be categorized, and turn a decision into a rule | Keeps the ritual short, improves by exception |
| R4 | Spend by category for an arbitrary period | The dominant query |
| R5 | Drill from a category into its transactions | A total invites "on what?" |
| R6 | Compare a period against a reference | A bare total is not actionable |
| R7 | Create and **save** filters | "The work is never banked" |
| R8 | User-defined categories | The bank's list isn't his |

### Out of scope for step 1

Bank APIs · the iPhone app · budgeting/forecasting · multi-user · auth ·
a hosted backend · writing from a phone · loading a second account ·
per-person attribution · packaging as an installer (Tauri/Electron).

### Definition of done

1. All 10,034 historical rows import cleanly, and a re-import of the same file
   adds nothing.
2. Rule coverage meets the thresholds in §9.
3. The October 2026 file imports as a monthly top-up with no special casing.
4. `make test` (or equivalent single command) passes, and the test suite
   includes the traps named in §5.
5. The dominant query returns in well under a second.

---

## 2. Architecture

```
  CaixaBank .xls  ──▶  importer  ──▶  SQLite  ──▶  FastAPI  ──▶  React UI
   (manual                                │                      (browser,
    download)                             │                       localhost)
                                          │
                             rules.json ──┘  (data, version-controlled)
                                   ▲
                                   │  one-off, offline
                          bootstrap script (LLM)
```

**Stack**

| Layer | Choice | Rationale |
|---|---|---|
| Parsing | Python + `xlrd` 2.0.1 | Already verified against the real file |
| Store | SQLite | Single user, single machine, zero setup |
| API | FastAPI + Pydantic | Typed request/response; the typing will feel familiar coming from ABAP |
| UI | React + TypeScript (Vite) | The learning payload; carries into React Native for step 2 |
| Tests | pytest + Vitest | One command per side |

**No packaging.** One command starts the API and serves the UI; the "app" is a
browser tab at `localhost`. Tauri can wrap the same React later (intent §4).

### ⚠️ Flagged concern 1 — the database must not live in Google Drive

The repo is at `C:\Users\rovir\Mi unidad\Projects\…`, which is **Google
Drive**. Google Drive syncs files while they are open, and **SQLite databases
are corrupted by file-level sync** — Drive copies a half-written database and
its separate write-ahead log out of step with each other.

✅ **Decision: code in the repo, data outside it.**

- Database: `%LOCALAPPDATA%\PersonalFinance\finance.db` (not synced, not in git)
- Path configurable via env var, with that as the default
- Backup is an explicit, atomic export command — not ambient cloud sync

This also keeps nine years of financial history out of a Google data centre.

---

## 3. Data model

Money is stored as **integer cents**, never floating point. The source gives
floats (`7.66`); the importer multiplies by 100 and rounds once, at the
boundary.

```sql
CREATE TABLE accounts (
    id              INTEGER PRIMARY KEY,
    account_number  TEXT NOT NULL UNIQUE,   -- as it appears in column 1
    label           TEXT NOT NULL,          -- e.g. 'Común (household)'
    is_active       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE categories (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    parent_id   INTEGER REFERENCES categories(id),
    kind        TEXT NOT NULL DEFAULT 'spending'
                -- 'spending' | 'income' | 'transfer' | 'excluded'
                -- 'transfer' and 'excluded' are omitted from spend analysis
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE transactions (
    row_hash        TEXT PRIMARY KEY,        -- see §4.3; identity
    account_id      INTEGER NOT NULL REFERENCES accounts(id),

    date_op         TEXT NOT NULL,           -- ISO 'YYYY-MM-DD'
    date_value      TEXT NOT NULL,

    amount_cents    INTEGER NOT NULL,        -- signed: negative = money out
    balance_cents   INTEGER,                 -- running balance, nullable
    currency        TEXT NOT NULL DEFAULT 'EUR',

    kind            TEXT NOT NULL,           -- see §5; derived enum
    code_common     TEXT NOT NULL,           -- 'Concepte comú', kept raw
    code_own        TEXT NOT NULL,           -- 'Concepte propi', kept raw

    description_raw   TEXT NOT NULL,         -- exactly as exported
    description_norm  TEXT NOT NULL,         -- normalized; what rules match
    type_label        TEXT,                  -- e.g. 'COMPRA CON TARJETA'
    counterparty_ref  TEXT,                  -- card no. / origin ref, raw

    category_id     INTEGER REFERENCES categories(id),
    rule_id         INTEGER REFERENCES rules(id),   -- which rule assigned it
    categorized_by  TEXT NOT NULL DEFAULT 'none',
                    -- 'none' | 'rule' | 'manual'

    source_file     TEXT NOT NULL,
    imported_at     TEXT NOT NULL
);

CREATE INDEX ix_tx_date     ON transactions(date_op);
CREATE INDEX ix_tx_cat_date ON transactions(category_id, date_op);
CREATE INDEX ix_tx_acct     ON transactions(account_id, date_op);
CREATE INDEX ix_tx_uncat    ON transactions(categorized_by) WHERE categorized_by = 'none';

CREATE TABLE rules (
    id           INTEGER PRIMARY KEY,
    pattern      TEXT NOT NULL,
    match_type   TEXT NOT NULL,       -- 'exact' | 'prefix' | 'contains' | 'regex'
    field        TEXT NOT NULL DEFAULT 'description_norm',
    category_id  INTEGER NOT NULL REFERENCES categories(id),
    priority     INTEGER NOT NULL DEFAULT 100,   -- lower wins
    kind_filter  TEXT,                -- optional: only apply to this kind
    origin       TEXT NOT NULL,       -- 'bootstrap' | 'manual'
    note         TEXT,
    created_at   TEXT NOT NULL,
    UNIQUE(pattern, match_type, field, kind_filter)
);

CREATE TABLE saved_filters (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    definition  TEXT NOT NULL,        -- JSON, see §10.3
    created_at  TEXT NOT NULL
);

CREATE TABLE import_runs (
    id            INTEGER PRIMARY KEY,
    source_file   TEXT NOT NULL,
    file_sha256   TEXT NOT NULL,
    rows_read     INTEGER NOT NULL,
    rows_inserted INTEGER NOT NULL,
    rows_skipped  INTEGER NOT NULL,   -- already present
    rows_rejected INTEGER NOT NULL,   -- unparseable; see §4.5
    started_at    TEXT NOT NULL,
    finished_at   TEXT NOT NULL
);
```

### Notes on deliberate choices

- **`rules` lives in the database *and* in a version-controlled
  `rules.json`.** The file is the source of truth and is loaded on start; edits
  made in the UI write back to the file. This keeps the ABAP "customizing
  table" model while giving a readable git diff per rule change
  (intent §2 — rules are data, not code).
- **`description_raw` is never discarded.** Normalization is lossy and the
  normalizer will change; the raw value makes re-normalization possible.
- **`code_common`/`code_own` are kept raw**, not just the derived `kind`. The
  derivation in §5 is imperfect and will be revised.
- **No `raw_json` blob of all 25 columns.** Six source columns are entirely
  empty and the rest are captured above; storing the full row would be
  dead weight. The `row_hash` still covers every column, so nothing is lost
  for identity purposes.

---

## 4. Import pipeline

### 4.1 Stages

```
 read .xls ─▶ locate header ─▶ map columns ─▶ per row:
     normalize ─▶ derive amount ─▶ derive kind ─▶ hash ─▶ insert-or-skip
```

### 4.2 Locating the header — measured facts

- Rows 0–2 are a title block (`MOVIMENTS DES DE : … FINS: …`); **the header is
  row 3**, data from row 4. Verified identical in both files.
- ⚠️ **The header row must be located by searching for a known marker**
  (a cell starting `D. Operaci`), not hardcoded to index 3. Hardcoding works
  until the bank changes its preamble.
- ⚠️ **Columns must be mapped by header name, never by position, and never
  inferred from which columns contain data.** The monthly file leaves
  `Saldo (-)` and `Concepte complementari 7` entirely empty while the 9-year
  file populates them. A schema inferred from one month would break on another.
- Reject the file if any required header is missing — loudly, not silently.

Required headers (Catalan, as exported):
`Número de compte`, `D. Operació`, `D. Valor`, `Ingrés (+)`, `Despesa (-)`,
`Saldo (+)`, `Concepte comú`, `Concepte propi`, `Concepte complementari 1`,
`Concepte complementari 9`, `Refèrencia 2`.

### 4.3 Identity and idempotency

✅ **`row_hash = sha256` over all 25 source cells**, each stripped and joined
with `\x1f`, plus the account number.

Measured justification (intent §3): `date + amount + merchant` collides **98
times** in nine years, and those collisions are *genuine distinct
transactions* — two coffees at the same bar, same day, same price. Any
narrower key silently deletes real spending. The full-row hash has **zero
collisions across 10,034 rows**.

Import is therefore `INSERT … ON CONFLICT(row_hash) DO NOTHING`, making
re-import of an overlapping date range a no-op. The export is a date-range
query, so overlapping requests are expected, not exceptional.

### 4.4 Field derivation

**Amount.** `Ingrés (+)` and `Despesa (-)` are two columns, both positive, and
mutually exclusive (verified: 0 rows with both, 1 row with neither).

```
income  present  ->  amount_cents = +round(income * 100)
expense present  ->  amount_cents = -round(expense * 100)
neither          ->  reject the row (§4.5)
both             ->  reject the row  (never observed; guard anyway)
```

**Dates.** `DD/MM/YYYY` text → ISO `YYYY-MM-DD`. All 10,034 rows parse
cleanly; zero malformed. Anything that fails to parse is rejected, not coerced.

**Description normalization** (`description_norm`), in order:

1. Strip, then collapse runs of internal whitespace to one space
   *(28 of 1,082 unique values contain double spaces)*
2. **Repair the bank's encoding damage: `ã` → `Ñ`.** All 22 affected values are
   this single substitution (`PEãIS`→`PEÑIS`, `BAR MAãANA`→`MAÑANA`,
   `DOãA`→`DOÑA`, `COMPAãIA`→`COMPAÑIA`). Applied before case folding.
3. Uppercase *(110 values are mixed case)*
4. Strip combining accents via NFD *(38 values are accented)* — so `PEÑIS` and
   `PENIS` match the same rule regardless of which the bank sent

`description_raw` keeps the original. Digits are **not** stripped: 170 values
contain meaningful ones (`EL ARBOL 5228`, `DIA 6438`).

### 4.5 Rejections

A row that cannot be parsed is **recorded, counted and reported** — never
silently dropped. The importer prints a summary and writes rejects to
`rejects/<import-id>.csv` for inspection. Known rejects in the real data: one
trailing all-empty row per file.

---

## 5. Transaction kinds

Needed because **not all rows are spending**, and counting them as such
distorts every total.

Derived from `(Concepte comú, Concepte propi)` with the type label as a
secondary signal. Measured distribution over 9 years:

| Codes | n | Dominant label | `kind` |
|---|---|---|---|
| `12`/`040` | 8,125 | `COMPRA CON TARJETA` | `card_purchase` |
| `02`/`067` | 630 | `TRASPASO PROPIO` | `transfer_own` |
| `11`/`040` | 369 | `REINT.CAJERO` | `cash_withdrawal` |
| `04`/`002` | 267 | *(person names)* | `transfer_person` |
| `03`/`038` | 157 | *(person names)* | `transfer_person` |
| `04`/`067` | 138 | `TRASPASO PROPIO` | `transfer_own` |
| `02`/`040` | 126 | `DEVOLUCION COMPRA` | `refund` |
| others | ~220 | mixed | `other` |

### ⚠️ Flagged concern 2 — the codes are not perfectly clean

`12`/`040` is dominated by card purchases but its second-most-common label is
`REINT.CAJERO` (a cash withdrawal). So **codes alone are insufficient** and
the text label alone is worse — `Concepte complementari 9` holds a *person's
name* instead of a type on transfer rows.

✅ **Decision: derive `kind` from a code→kind table, then let an explicit text
override correct known exceptions.** The mapping table and overrides live in
one small, unit-tested, data-driven module — not scattered `if` statements.
Unmapped combinations become `other` and are **reported**, so the long tail
surfaces instead of hiding.

### ⚠️ Flagged concern 3 — own-transfers must be excluded from spend

`transfer_own` totals **€205,219 in against €5,773 out** over nine years. This
is the household account being funded from the spouses' personal accounts
(intent §3), not income. Once a second account is loaded, each such transfer
appears twice — once leaving, once arriving.

✅ `transfer_own` maps to a category of `kind='transfer'` and is **excluded
from spend analysis by default**, with a UI toggle to reveal it.

### Cash is a known blind spot

`cash_withdrawal` (369 rows) is money leaving the account to be spent
*somewhere unknowable*. It cannot be categorized by merchant because there is
no merchant. ✅ It gets its own category (`Cash withdrawn`) and is reported as
such — honest about the gap rather than silently miscounted.

### Card purchases are only 69% of outflow

Measured: `card_purchase` = €186,823 out; everything else = €83,937 out.
**Categorization cannot be card-only** — direct debits (utilities, insurance),
Bizum payments to people and cash all matter. The rule engine therefore runs
over all kinds, not just card rows.

---

## 6. The categorizer

The encapsulated unit from intent §2 — the ABAP instinct, kept.

```python
# One interface. Rules are data passed in; nothing here reads a file or a DB.

@dataclass(frozen=True)
class Candidate:                 # the subset of a transaction rules may see
    description_norm: str
    kind: str
    amount_cents: int

@dataclass(frozen=True)
class Decision:
    category_id: int | None      # None => uncategorized
    rule_id: int | None          # which rule fired
    reason: str                  # 'rule' | 'no_match' | 'ambiguous'

class Categorizer:
    def __init__(self, rules: Sequence[Rule]) -> None: ...

    def categorize(self, c: Candidate) -> Decision: ...

    def explain(self, c: Candidate) -> list[Rule]:
        """Every rule that matches, in precedence order. For debugging a
        surprising categorization — and for the UI's 'why this category?'."""
```

**Properties this interface buys**

- **Pure and deterministic.** No I/O, no clock, no network. The same candidate
  and rule set always give the same decision — so it is trivially testable and
  the UI can preview the effect of a rule before saving it.
- **Swappable.** Rule matching could later become something smarter without any
  caller changing.
- **`explain()` is a first-class requirement, not a debug afterthought.** The
  main way a wrong rule gets noticed is drilling into a category and seeing
  something odd; the next question is immediately "why is it here?"

### 6.1 Rule format

`rules.json`, version-controlled, is the source of truth:

```json
{
  "version": 1,
  "rules": [
    { "pattern": "MERCADONA",   "match": "contains", "category": "Groceries",     "priority": 100 },
    { "pattern": "BON AREA",    "match": "contains", "category": "Groceries",     "priority": 100 },
    { "pattern": "FRUTOS SECOS EL R", "match": "prefix", "category": "Groceries", "priority": 100 },
    { "pattern": "CAFETERIA",   "match": "contains", "category": "Eating out",    "priority": 200 },
    { "pattern": "^COREIBERDROLA", "match": "regex", "category": "Utilities",     "priority": 100 }
  ]
}
```

### 6.2 Matching and precedence

- Matching runs against `description_norm` (§4.4), so patterns are written
  uppercase and accent-free.
- **Order: `priority` ascending, then rule `id` ascending. First match wins.**
  Deterministic and explainable; no scoring, no fuzzy ranking.
- **Prefix matching is safe.** Measured: of 1,082 unique descriptions, only 5
  share a 17-character prefix with another, and all 5 are the *same entity* at
  different lengths (`COREDIGI SPAIN TELECOM SA` / `…SL`). **Zero genuine
  merchant collisions**, so truncated names can be matched directly.
- `kind_filter` lets a rule apply only to one kind — e.g. a person's name
  meaning `transfer_person`, not a shop.
- A rule that matches **nothing** in the historical corpus is reported as
  suspicious: almost always a typo in the pattern.

### ⚠️ Flagged concern 4 — `contains` rules can over-reach

`CAFETERIA` as a `contains` rule catches every café, which is usually wanted —
but `EL ARBOL` would also match `EL ARBOLITO`, a different shop. Mitigation:
the UI shows **how many historical transactions a rule would newly capture,
and samples them, before the rule is saved.** Cheap to compute over 10k rows
and it turns an invisible mistake into an obvious one.

---

## 7. Rule bootstrap (one-off)

A script, run once, not part of the running app (intent §4 — deterministic at
runtime).

1. Extract **unique `description_norm` values** from the imported history —
   measured at **1,082** across nine years.
2. Send only that deduplicated list of strings to the model. ✅ **No amounts,
   no dates, no balances, no account or card numbers, no running totals.**
   Roughly 1,000 short strings: one call, cents of tokens, minimal exposure.
3. The model proposes (a) a category set and (b) a pattern→category rule per
   description, preferring the shortest unambiguous pattern.
4. Output is written as `rules.json` **plus a review report** — rules grouped
   by proposed category, with the historical transaction count and total spend
   each would capture.
5. **Jose reviews and edits before anything is committed.** The model proposes;
   the human decides (intent §6 Q3).
6. Re-runnable: new unknown descriptions can be bootstrapped later the same
   way, without touching existing rules.

### ⚠️ Flagged concern 5 — some "merchants" are family members

Several of the most frequent descriptions are people's names, not shops. The
bootstrap prompt must be told so, and those should become
`kind='transfer'`/`excluded` categories rather than spending ones. Left
unhandled, the top of the spending chart becomes family members.

---

## 8. Categories

- Seeded from the bootstrap proposal, then edited by Jose.
- **One level of nesting allowed** (`parent_id`), because `Groceries` and
  `Eating out` plausibly roll up to `Food` — but the default view shows leaves.
- Renaming or merging categories must not require re-import: rules reference
  categories by name in `rules.json` and by id in the database, resolved at
  load.
- Every transaction has at most one category. ⚠️ **Splitting one transaction
  across categories is not supported in step 1** — noted because it is the
  most common "I need this eventually" for a weekly shop that includes
  non-grocery items. Deliberate omission; revisit with evidence.

---

## 9. Acceptance thresholds for categorization

The playbook's feedback loop, made quantitative. Measured on the real 9-year
corpus via `make coverage`:

| Metric | Threshold |
|---|---|
| Rows categorized (excluding `transfer_own`, `cash_withdrawal`) | **≥ 90%** |
| Outflow **value** categorized | **≥ 95%** |
| Rows needing manual triage in a typical month | **≤ 15** |
| Rules that match nothing in history | **0** |

Rationale for value ≥ rows: a few uncategorized €2 purchases matter far less
than one uncategorized €400 one, so value coverage is the stricter test.

**Holdout check:** derive rules from 2017–2024 only, then measure coverage on
2025–2026. This measures what actually matters — how well rules handle
*future* months — and is the honest version of "it works on my data."

---

## 10. Query layer

### 10.1 The dominant query

```
GET /api/spend?from=2026-10-01&to=2026-10-31&account=1
   -> [ { category, total_cents, txn_count, pct_of_total,
          reference_total_cents, delta_pct }, ... ]
```

- Arbitrary `from`/`to` — month, week, or any range (intent §1).
- Excludes `kind='transfer'` and `'excluded'` categories unless asked.
- Sorted by `total_cents` descending: the biggest thing first.

### 10.2 Comparison reference (R6)

Each row carries one reference figure so a total means something:

- **Default: the immediately preceding period of equal length.**
- Also available: same period one year earlier; trailing 12-month average.

With nine years loaded, all three are cheap. The default is the previous
period because month-over-month is the change a person actually notices.

### 10.3 Saved filters (R7)

A filter is stored JSON, and the default view is just an unnamed one:

```json
{ "from": "2026-10-01", "to": "2026-10-31",
  "accounts": [1], "categories": [], "kinds": ["card_purchase"],
  "min_cents": null, "max_cents": null, "text": null,
  "include_transfers": false }
```

Named, listed, re-runnable, editable, deletable. **This is the direct answer to
"I can't save filters" — the bank's second failure** (intent §1), so it is a
step‑1 requirement, not a later nicety.

### 10.4 Drill-down (R5)

`GET /api/transactions?<filter>` returns the rows behind any figure, with the
rule that categorized each one — so a wrong rule is visible at the point of
suspicion, and fixable from there.

---

## 11. UI (React + TypeScript)

Five screens. Deliberately few.

| Screen | Purpose |
|---|---|
| **Overview** | Period selector + category breakdown with comparison. The default landing view. |
| **Category detail** | Transactions in a category; each shows which rule assigned it, with an override. |
| **Triage** | Only uncategorized transactions. Assign a category → offers to create a rule, previewing what else it would capture. |
| **Rules** | List, edit, reorder, delete. Shows each rule's historical hit count. |
| **Import** | Pick a file, see inserted/skipped/rejected, then a link straight to Triage. |

Design notes:
- The **monthly ritual is Import → Triage → done.** That path must be fast;
  everything else is reading.
- The period selector needs one-tap month/week presets *and* a free range.
- No charting library in slice 1 — a sorted list with bars reads fine and
  avoids a dependency before the data is trusted.

---

## 12. Testing — the feedback loop

v1 had an empty `tests/` directory. This is the playbook play that most
directly addresses why v1 failed.

**One command**: `make test` runs pytest + Vitest. Nothing is "done" before it
passes and the output is shown.

⚠️ **Fixtures must be synthetic.** Real statements cannot be committed. A
small generator builds `.xls` fixtures reproducing the real file's *structure*
— title block, row-3 header, Catalan names, split amount columns, 17-char
truncation, the `ã` damage, a trailing empty row — with invented merchants and
amounts.

Required tests, each pinned to a measured trap:

| Test | Guards against |
|---|---|
| Header found when the preamble is 2, 3 or 5 rows | Hardcoded row index |
| Columns mapped by name with a column empty throughout | Schema inferred from populated columns |
| `Ingrés`/`Despesa` → signed cents; both-filled and neither-filled rejected | Sign and null handling |
| Money arithmetic stays integral | Float rounding drift |
| Two same-day, same-amount, same-merchant rows both survive | The 98 genuine collisions |
| Re-importing a file inserts 0 rows | Idempotency |
| Overlapping date ranges insert only the new rows | Idempotency |
| `ã`→`Ñ`, accent stripping, whitespace collapse, case folding | Normalization |
| Rule precedence: lower priority wins; ties by id | Deterministic matching |
| `explain()` returns all matches in order | Debuggability |
| `kind` derivation incl. an unmapped code → `other` + reported | Silent misclassification |
| `transfer_own` excluded from spend totals | The €205k distortion |
| Coverage thresholds on the real corpus (local-only, skipped in absence) | Regression in categorization |

---

## 13. Slices

Each slice ends with something that works (intent §4).

| # | Slice | Done when | New learning |
|---|---|---|---|
| **S1** | Parse → SQLite, CLI summary | 10,034 rows imported; re-import is a no-op; tests green | — (plays to existing strength) |
| **S2** | Bootstrap + categorizer + `make coverage` | Thresholds in §9 met on real data | Rules-as-data |
| **S3** | FastAPI + React **Overview** | The dominant query answered in a browser | **React + TS** |
| **S4** | **Triage** + rule creation with preview | A month categorized end-to-end in minutes | React forms/state |
| **S5** | Drill-down, saved filters, comparison | R5–R7 complete | — |
| **S6** | Snapshot export for step 2 | A file the phone will read | Prepares step 2 |

**S1–S2 are the riskiest data work and need no UI.** S3 is where the React
learning starts, and it is also the first slice that produces something
pleasant to use. **A usable tool exists at the end of S3**; S4 makes the
monthly ritual sustainable; S5 completes the stated requirements.

*Optional, recommended, not yet agreed:* a one-hour Expo "hello world" spike
on the real phone, any time before S6, purely to confirm the
Windows → iPhone toolchain cooperates.

---

## 14. Open questions

Non-blocking — defaults chosen, stated for veto:

1. **Category granularity.** The bootstrap will propose something; 15–25
   categories is the usual sweet spot. Fewer is uninformative, more makes
   triage a chore. Decided when the proposal is reviewed.
2. **Does the UI need to edit `rules.json` directly**, or is DB-plus-export
   enough? Spec assumes the file is canonical and the UI writes back.
3. **Comparison default** — previous period assumed (§10.2).
4. **Transaction splitting** — omitted from step 1 (§8).
5. **Second account** — modelled, not loaded (intent).

---

## 15. Review checklist

- [ ] Scope in §1 is what Jose wants from step 1
- [ ] Schema (§3) survives ABAP scrutiny
- [ ] Database-outside-Google-Drive decision accepted (§2)
- [ ] `Categorizer` interface (§6) matches the encapsulation he had in mind
- [ ] Rule format (§6.1) is something he'd be comfortable hand-editing
- [ ] Coverage thresholds (§9) are the right bar
- [ ] Five screens (§11) are the right five
- [ ] Slice order (§13) is agreeable
- [ ] Five flagged concerns reviewed
- [ ] **Approved → proceed to `plan.md` for S1**
