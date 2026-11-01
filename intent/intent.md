# Intent: Personal Finance Tracker

**Status:** 🟡 Draft — in conversation
**Originator:** Jose (@RoviraAyza)
**Started:** 2026-11-01

> A proto-spec, written during conversation and corrected by the originator.
> ✅ = stated by the originator. ❓ = open.

---

## 1. Problem statement

### What I can't do today
✅ **My bank's app is bad at the one thing I care about most.** Specifically,
two rigidities:

1. ✅ **I can't easily create new categories.** The bank's category list is
   theirs, not mine, and it doesn't match how I think about my family's money.
2. ✅ **I can't save filters.** Every time I want an answer I rebuild the same
   query from scratch. The work is never banked.

Note: the complaint is **rigidity, not inaccuracy.** The bank isn't guessing my
categories wrong so much as refusing to let me define my own and keep them.

### The one query that matters
✅ **"How much have I spent in this period, and in which categories?"**

- ✅ This is the query used most, by a wide margin.
- ✅ **The period is arbitrary** — "month, week, whatever." Not a fixed set of
  reporting periods; any range.
- Note: this is **one query shape with a variable period**, not a library of
  different saved queries. That is a significant simplification — see §2.

### What "better" looks like
✅ A simple app where the categories are mine, and that one question is always
one step away instead of rebuilt from scratch every time.

---

## 2. Proposed outcome

✅ A small app with a monthly rhythm:

1. Once a month, download the Excel export from the bank *(manual, but the bank
   generates it automatically — the cost is a download, not data entry)*
2. Feed it to the app
3. Transactions are categorized automatically by a rule engine
4. Anything the engine can't categorize is surfaced for a decision, and that
   decision becomes a new rule
5. See spend by category for any period, without rebuilding the query

### The main view

⚠️ **Correction (2026-11-01).** An earlier draft of this file concluded that
because there is one dominant query, saved filters "stop being a feature."
**That was wrong, and the originator corrected it:**

> ✅ *"Tapping a category is needed; filters should be flexible to create and
> easy to save."*

So there are **three** requirements here, not one:

1. ✅ **The default view** — spend by category for a period, always one step
   away. Period is free: month, week, arbitrary range.
2. ✅ **Drill-down** — tap a category, see the transactions inside it. This is
   also how a miscategorised row gets noticed; without it a wrong rule is
   invisible.
3. ✅ **Flexible, saveable filters** — easy to build a slice and easy to keep
   it. This is a direct answer to the bank's second failure ("the work is
   never banked"), so it is a first-class feature, not a later addition.

### The categorization engine
✅ **Bootstrap the rules from history, then maintain them by exception.**

- ✅ **The asset: every transaction since 2016, in an Excel file.** ~10 years of
  the family's real spending.
- ✅ **Family spending is uniform** — the same merchants recur month after month.
  This is what makes rule-based categorization viable rather than naive.
- ✅ **One-off LLM-assisted bootstrap:** spend some tokens *once* to derive the
  initial rule set from 10 years of history.
- ✅ **Then it's deterministic.** Categorization is an encapsulated unit — a
  class/function with a clear interface *(originator's framing: "thinking as an
  ABAPer")*. Rules live behind that interface.
- ✅ **Rules are editable.** As new transactions fail to categorize, rules get
  added or corrected. The engine improves by exception, not by retraining.

❓ Open: whether rules are **data** (a file or table the engine reads) or
**code** inside the class. Recommendation to settle in `spec.md`: data, so rules
are diffable in git and editable without touching code.

---

## 3. Affected users & systems

- ✅ **Jose, sole user.** Tracking family spending.
- ✅ **Input: monthly Excel export from the bank.** Manual download, no API.
- ✅ **Originator is an ABAP developer** — expects encapsulation and clear
  interfaces; thinks in classes and APIs.
- ✅ **Originator wants to build an iPhone app** — see §4.

### The data — profiled from a real export (2026-11-01)

Sample inspected: a 9-year export, 4 MB, legacy BIFF8 `.xls` (OLE2 — a genuine
old-format Excel file, not a renamed CSV or HTML table).

**Shape**
- Single sheet, 25 columns, **10,035 transaction rows**
- Row 0–2 are a title block (`MOVIMENTS DES DE : … FINS: …`);
  **header is row 3, data starts row 4.** Not a clean rectangle — the parser
  must skip the preamble rather than assume row 1.
- Column headers are in **Catalan** (`Número de compte`, `D. Operació`,
  `Ingrés (+)`, `Despesa (-)`, `Concepte comú`…). Bank code `2100` ⇒ CaixaBank.
- One account; **10 distinct card numbers** across 8 office codes.
- Currency EUR throughout, single currency.
- One trailing junk row (all columns empty) — needs dropping.

**Dates** — `D. Operació` and `D. Valor`, both `DD/MM/YYYY` **as text**.
10,034 of 10,034 parse cleanly; zero malformed. Coverage per year:
2017: 183 *(partial)*, 2018: 705, 2019: 896, 2020: 920, 2021: 1,096,
2022: 1,146, 2023: 1,266, 2024: 1,192, 2025: 1,506, 2026: 1,124 *(partial)*.
≈ **100 transactions/month** — comfortably small.

**Amounts** — ⚠️ not a signed column. `Ingrés (+)` and `Despesa (-)` are
**two separate columns, both holding positive magnitudes**, mutually exclusive
(0 rows have both, 1 row has neither). 803 income rows (8%), 9,231 expense
rows (92%). A running balance sits in `Saldo (+)`.
*Implication: the import must normalise these into one signed amount, and the
sign convention is a decision to make once and encode in the model.*

**Transaction type** — `Concepte complementari 9` is populated on every row and
carries a type code + label: `COMPRA CON TARJETA` (8,056 = 80%),
`TRASPASO PROPIO` (525), `REINT.CAJERO` (368, cash withdrawal), `TRASPASO`
(113), `DEVOLUCION COMPRA` (51, refunds), `CUOTA TARJETA`… On person-to-person
transfers this column holds a **person's name** instead of a type label —
so the field is overloaded and can't be parsed as a pure enum.
`Concepte comú`/`Concepte propi` are numeric type codes (`12`/`040` = card
purchase, 8,125 rows) — a more reliable type discriminator than the text.

**The merchant field** — `Concepte complementari 1`, populated on 98.4% of rows,
values space-padded and needing a trim.

> 🎯 **1,082 unique merchant strings across 9 years**, and the **top 30 account
> for ~64% of all rows.** This confirms the uniformity hypothesis emphatically,
> and it is the single most important finding: the entire bootstrap corpus is
> ~1,000 short strings. That fits in one LLM call for a few cents, and a few
> dozen rules will cover the large majority of real spending.

Two caveats on that field:
- ⚠️ **Truncated at 17 characters** for card purchases (3,681 rows are exactly
  17 chars long — a hard cut, e.g. `MERCADONA PLAZA D`, `FRUTOS SECOS EL R`).
  Rules must match on truncated prefixes, not full merchant names.
- ⚠️ **Encoding damage in the source file** — e.g. `0150-CONSUM PEãIS`, where
  `ñ`/`Ñ` has been mangled by the bank's own export. Present in the data as
  shipped; must be tolerated, and ideally repaired on import.
- 157 rows (1.6%) have it empty — needs a fallback for categorisation.
- Some values are **family members' names**, not merchants (own-account
  transfers and Bizum). These are not "spending" in the category sense and
  likely need their own treatment.

**Six columns are entirely empty** (`Concepte complementari 2, 4, 6, 8, 10`,
plus two unnamed) — the export is a fixed-width template, mostly unused. The
model should keep what's real, not mirror all 25 columns.

> **The history file and the monthly file are the same thing.** ✅ **Verified**
> against a real October 2026 monthly export (128 rows): same sheet name
> (`Excel simple(1)`), same 25 columns, same header on row 3, **byte-identical
> column headers**. The export is just a date-range query. **One parser serves
> both** the 9-year bootstrap and the monthly top-up.

One caution from that comparison: the monthly file leaves two columns
(`Saldo (-)`, `Concepte complementari 7`) entirely empty that the 9-year file
populates. That is sparsity, not a format difference — **the parser must work
from the fixed header, never infer the schema from which columns happen to
carry data in a given file.**

### 🔀 Multiple accounts — a new requirement

✅ **The originator has a personal account and a family account, and wants to
keep them separate** in the analysis.

⚠️ **Both files supplied contain exactly one account** (`2100 9304 11 …`,
10,034 of 10,034 rows and 127 of 127 rows). **The export is per-account**, so
multi-account support means **one download per account per month**.

✅ **Correction to an earlier note in this file:** account identity does *not*
need to be supplied by hand at import. The account number is in the data —
column 1, `Número de compte`, populated on 100% of rows. **Every export
self-identifies**, so the importer reads the account rather than asking.

### Scoping the multi-account cost

✅ The originator flagged reluctance here — *"it increases complexity in
different points of the process"* — which is a fair instinct. Where the cost
actually falls:

| Area | Cost | Assessment |
|---|---|---|
| Data model | an `account` column | ~zero; already in the source data |
| Parser | none | same format, self-identifying |
| Rules & categories | none | shared across accounts |
| Transfer exclusion | real but small | ~15 lines; detectable via `02`/`067` codes; only needed once two accounts are loaded |
| UI | an account filter | modest |
| **The monthly ritual** | **2–3 downloads instead of 1** | **the real cost — recurring, borne by the user, forever** |

✅ **Decision: model accounts from day one, load only the joint account in v1.**

- The column goes in the schema and the importer reads it from the file —
  nearly free now.
- The monthly ritual stays a single download until the tool has proved it is
  worth the ritual at all.
- Transfer-exclusion logic stays unwritten until a second account needs it.
- Avoids the expensive order: hardcoding one account and retrofitting later,
  which costs a schema migration, a reimport and a UI rework.

The joint account may simply be *enough* — it is where everyday household
spending happens, which is the question actually asked.

❓ Open: is the **personal** account at the same bank, with the same export
format? (Likely — but unverified, and a second bank would mean a second parser,
which is the kind of thing that should not be discovered during Stage 3.)

### ⚠️ Own-transfers would double-count badly

`TRASPASO PROPIO` ("own transfer") appears **542 times**, totalling
**€205,219 in** against **€5,773 out** over nine years — ~€23k/year arriving.

That lopsidedness says this account is **funded from another account** rather
than earning directly. The counterparty names on those rows are the originator
and a family member, and the spending on this account is overwhelmingly
household (groceries, bakery, cafés).

> ✅ **CONFIRMED by the originator.** The profiled account is the joint
> *"común"* account for **everyday household expenses** (*gastos corrientes*).
> He and his wife each transfer money into it from their own personal accounts
> every month; the household's day-to-day spending then runs out of it.

So the real structure is three accounts, not two:

```
  Jose's personal account  ──┐
                             ├──▶  "común" joint account  ──▶  everyday
  Wife's personal account  ──┘      (the profiled one)          household
                                                                spending
```

This is a genuinely useful shape, because it means **the joint account alone
answers the core question.** "Where does the family's money go?" is almost
entirely a question about this one account — which keeps the first version
small. The personal accounts add individual discretionary spending on top.

It also **solves attribution without needing card numbers**: separating by
account naturally distinguishes "the household spent this" from "I spent this"
— cleaner than trying to infer a person from a card that gets reissued.

❓ Open: is the **wife's** personal account in scope too, or only Jose's
personal account plus the joint one?

Either way the consequence is firm: **once both accounts are loaded, an own
transfer appears twice** — as money leaving one and arriving in the other.
Counted naively it would add €205k of phantom income and inflate every total.
✅ Own-transfers must be identifiable and excluded from spending analysis by
default. Usefully, `Concepte comú`/`propi` give a reliable code for them
(`02`/`067`), so this is detectable without parsing free text.

### Cards do not identify who spent

`Referència 2` holds a 16-digit card number on card purchases — but the 10+
distinct values cluster into **date ranges, i.e. card renewals** (e.g. one card
runs 2021-02 → 2026-02, its successor 2025-07 → 2026-09). The column is also
**overloaded**: on transfers it holds an origin reference, not a card
(`ORIGEN: MAGYLUL1`), and some values aren't 16 characters at all.

Some cards *do* run concurrently — plausibly Jose's and his wife's cards on the
joint account — but it is too unreliable to attribute spending to a person.

✅ **Resolved by the account structure instead:** separating accounts gives
"household vs. mine" directly, which is the distinction that matters. Per-person
attribution *within* the joint account is not pursued.

### ⚠️ Transaction identity — there is no natural key

Discovered while checking whether imports need to deduplicate. Tested on the
9-year file (10,034 real rows):

| Candidate key | Collisions |
|---|---|
| `date + income + expense + merchant` | **98** |
| `date + saldo` | 25 |
| `account + date + saldo + income + expense` | 2 |
| **hash of the full source row** | **0** |

The 98 collisions are **not duplicates — they are genuine distinct
transactions**: two coffees at the same bar, on the same day, for the same
amount. Inspected and confirmed (e.g. `CAFETERIA EL OLIV`, 04/06/2026, €2.30,
twice). Deduplicating on those fields would silently delete real spending.

What discriminates them is the **running balance** (`Saldo`), because every
transaction moves it. Two identical purchases land on different balances.

✅ **Decision: identity is a hash of the complete source row.** Unique across
10,034 rows, stable, and it makes re-importing idempotent — which matters,
because the export is a date-range query and overlapping ranges are easy to
request by accident.

*(Note: the two files in hand have zero genuine overlap — the apparent overlap
in a first check was an artefact of the undated trailing junk row.)*

---

## 4. Constraints

- ✅ **Simple.** Stated repeatedly and unprompted — a real design constraint.
- ✅ **Monthly cadence.** A once-a-month ritual, not a daily dashboard.
- ✅ **Deterministic at runtime.** The LLM is a one-time bootstrap tool, not a
  dependency of the running app.
- Follows the AI-native SDLC playbook, adapted for a solo project:
  `intent.md` → `spec.md` → `plan.md` → code, reviewed between stages.
- ✅ **Effort: thin end-to-end slices, riskiest first.** The originator named
  the real tension — *"too little effort, I wouldn't learn anything; too much
  effort, I can take too much and not get finished."* The answer is not a
  number of hours but a shape of work: **every slice is end-to-end and leaves a
  working tool**, so stopping at any point is a legitimate outcome rather than
  an abandoned project.

  ⚠️ **Ordering is deliberately counterintuitive — the iPhone app comes
  first, not last.**
  - The Python side is **already de-risked**: the real file has been parsed,
    the traps found, the identity key settled. No unknowns remain there.
  - The **unknown** is whether the Expo → Windows → iPhone pipeline works
    smoothly, and whether the originator enjoys it. Unknowns go first —
    discovering a hostile toolchain in week one with a throwaway beats
    discovering it in month three with real data waiting on it.
  - The app is **half the motivation.** Weeks of Excel plumbing teach an ABAP
    developer nothing new, and that is precisely where this project would die.

  First slice: an ugly Expo app on the phone showing a few hardcoded
  categories. Not useful, entirely disposable, proves the riskiest part works.
- ✅ **Privacy.** The bootstrap step means sending merchant descriptions to a
  model. Agreed mitigation: send only the **deduplicated list of unique
  description strings** — now known to be ~1,082 of them — with no amounts,
  dates, balances, account or card numbers. Separately, the repo sits in a
  Google Drive folder, so anything stored here syncs to Google by default.
  **Account number, card numbers and family names must never be committed.**

### 🔀 New requirement: this should be an iPhone app

- ✅ **The originator uses an iPhone and wants the result to be an app on it.**
- ✅ **Learning is an explicit goal, of equal standing to the tool itself:**
  *"That's something I want not only because it's useful but because I want to
  learn how to do it."*

This is a genuine fork, not a delivery detail. It changes the stack decision,
where the data lives, and how the monthly import works.

**The hard constraint:** the originator develops on **Windows 11**. Building and
signing a *native* iOS app requires Xcode, which requires macOS. Any path to an
iPhone app from Windows must route around this.

✅ **DECIDED — React Native + Expo.** Develop on Windows, test on the real
iPhone over wifi via Expo Go, build for distribution through EAS cloud builds.
No Mac required at any point. Learning payload: TypeScript, React Native,
on-device storage.

### 🔀 Architecture: desktop does the work, phone does the asking

✅ **DECIDED — the import runs on the desktop; the phone is a viewer.**

This splits along how the work actually divides, rather than cutting across it:

| | Desktop (Python) | Phone (Expo/React Native) |
|---|---|---|
| **Role** | Does the work | Answers the question |
| **Cadence** | Monthly, ~20 minutes | Any time, 5 seconds |
| **Tasks** | Parse `.xls`, categorize, triage unknowns, edit rules | Show spend by category for a period |
| **Why there** | Keyboard work; `xlrd` already parses the real file correctly | It's a glance, and the phone is where the question occurs |
| **Writes?** | Yes — owns the data | No — read-only |

Consequences, all positive:
- The 4 MB BIFF8 parse stays in Python, where it is already proven to work,
  instead of being attempted on a phone.
- **The phone is read-only, so there is no sync conflict to resolve** — data
  flows one way only. This removes the hardest part of sync entirely.
- Two codebases, two languages. Accepted: the Python side is a utility script,
  and the app side is where the learning goal lives.

✅ **The rule bootstrap stays a one-off desktop step**, producing a rules file
that the desktop tool reads. Not a runtime dependency of anything.

❓ **Open — the remaining hole: how the snapshot reaches the phone.** See Q7.

---

## 5. Out of scope

- ✅ Bank API integration / automated import — accepted as manual.
- ✅ Machine learning or LLM inference at runtime — rules are deterministic.
- ✅ A hosted backend, user accounts, authentication — the phone reads a file.
- ✅ Multi-user or shared access — single user.
- ✅ Per-person attribution within an account — accounts give the distinction
  that matters; card numbers cannot support it.
- ✅ Writing from the phone — the phone is read-only.
- ✅ Loading a second account in v1 — modelled, but not loaded.
- ❓ Budgeting and forecasting — **not yet discussed.** Deliberately left
  unstated rather than assumed either way.

---

## 6. Open questions

Blocking:

1. ✅ **RESOLVED — the export format is known.** Profiled from a real file;
   see §3. One parser serves both the history and the monthly top-up.
2. ✅ **RESOLVED — verified identical.** The monthly export and the 9-year
   history share one format exactly. One parser.
3. ✅ **RESOLVED — the bootstrap proposes, the originator edits.** Send the
   1,082 unique descriptions to the model once, let it propose a category set
   grounded in real spending, then cut it down. Easier to react to a concrete
   list than to invent one, and it will not miss categories he'd forget.
4. ✅ **RESOLVED — not the whole app.** Drill-down into a category is
   required, and filters must be flexible to create and easy to save. See §2.
   ✅ **Also resolved — include one simple comparison.** A bare total
   ("€840 on groceries") is true but not actionable: without a reference the
   originator must remember last month's figure, which is the "work is never
   banked" problem again. Each category total is shown against a reference
   (previous period and/or a rolling average) — nearly free given nine years
   of history, but a different screen, so decided now.
5. ✅ **RESOLVED — React Native + Expo**, with desktop import and a
   read-only phone viewer. See §4.
6. ✅ **RESOLVED — load all nine years as data.** Same parser, ~10k rows;
   gives nine years of history from day one and a real corpus for measuring
   rule coverage.
7. ✅ **RESOLVED — a file, via a cloud folder already in use.** The data
   only changes monthly, so there is nothing to sync continuously; it is a
   once-a-month handoff at the end of a ritual already being performed. The
   desktop import writes one compact snapshot (~10k transactions, well under
   1 MB); the phone app has an **Import** button that opens the iOS Files
   picker and reads it. Avoids a server, hosting, authentication, OAuth,
   background sync and conflict resolution entirely. A real backend remains a
   deliberate later upgrade, not a prerequisite.

### Remaining open — non-blocking

8. ❓ Whether the **wife's** personal account is ever added (noted as a
   possibility; does not shape the design).
9. ❓ Whether the **personal** account export is the same CaixaBank format.
   Not blocking while v1 is joint-account only, but worth a format check
   before that account is added.

---

## 7. Decision log

| Date | Decision | Rationale |
|---|---|---|
| 2026-11-01 | Clean start; nothing carried over | Originator's call |
| 2026-11-01 | Manual monthly Excel import, no bank API | Bank generates the file automatically; download is a small cost |
| 2026-11-01 | Categorization is the core, not a side feature | The specific thing the bank's app fails at |
| 2026-11-01 | Rules bootstrapped once from 2016+ history via LLM, then deterministic | Family spending is uniform and repetitive; 10 years of labelled reality already exists |
| 2026-11-01 | Categorization behind a single encapsulated interface | Originator's ABAP instinct; keeps rules swappable and testable |
| 2026-11-01 | User-defined categories and saved views are first-class | They are the two concrete failures of the bank's app |
| 2026-11-01 | Target is an iPhone app; learning is a goal of equal weight | Originator's call — accepts more complexity than the task strictly needs |
| 2026-11-01 | React Native + Expo | The only path to a real iPhone app from Windows with no Mac; teaches genuine app development |
| 2026-11-01 | Desktop imports and owns the data; phone is a read-only viewer | Triage is keyboard work and the query is a glance; keeps the BIFF8 parse in Python where it already works; makes data flow one-way, removing sync conflicts |
| 2026-11-01 | Snapshot reaches the phone as a file via an existing cloud folder, read with the iOS Files picker | The data only changes monthly, so there is nothing to sync continuously — avoids a server, auth, hosting and conflict resolution entirely |
| 2026-11-01 | Transaction identity = hash of the full source row | No natural key exists; 98 same-day/same-amount/same-merchant pairs in 9 years are genuine distinct transactions, and a narrower key would delete real spending |
| 2026-11-01 | Bootstrap proposes the category list; originator edits it down | Easier to react to a concrete list than invent one, and it won't miss categories he'd forget |
| 2026-11-01 | Drill-down into a category is required | A total invites "on what?", and it is how a miscategorised row gets noticed |
| 2026-11-01 | Flexible, saveable filters are first-class (reversing an earlier simplification) | Directly answers the bank's second failure, "the work is never banked" |
| 2026-11-01 | Load all nine years as data | Nearly free with the same parser; gives history from day one and a corpus to measure rule coverage |
| 2026-11-01 | Accounts are a first-class dimension; personal and family kept separate | Originator's requirement. The export is per-account **and self-identifying** — the account number is in column 1 on every row — so the importer reads account identity rather than being told it |
| 2026-11-01 | Own-transfers excluded from spending analysis by default | They appear in both accounts once both are loaded; €205k of phantom income otherwise |
| 2026-11-01 | Confirmed: profiled account is the joint "común" account for everyday household expenses, funded monthly by both spouses | Originator confirmed; matches €205k in / €5.8k out and household-only spending |
| 2026-11-01 | Attribution comes from account separation, not card numbers | Cards are reissued over time and the column is overloaded; account separation gives the distinction that actually matters |
| 2026-11-01 | Model accounts from day one; load only the joint account in v1 | The schema cost is ~zero (the account number is in the file), but each extra account costs a download every month forever — so defer the ritual cost, not the schema |
| 2026-11-01 | Category totals shown against a comparison reference | A bare total is not actionable; having to remember last month's figure is the "work is never banked" problem again |
| 2026-11-01 | Wife's personal account: possible, not committed | Does not shape the design while v1 is joint-account only |
| 2026-11-01 | Thin end-to-end slices, each leaving a working tool | Resolves "too little vs too much effort" by making every stopping point a legitimate one |
| 2026-11-01 | Build the iPhone app first, before the data pipeline | The Python side is already de-risked; the Expo/Windows/iPhone toolchain is the real unknown, and the app carries half the motivation |

---

## 8. Approval

- [x] Originator has corrected the agent-written draft — repeatedly, including
      two corrections that reversed agent conclusions (saved filters are
      first-class; nothing carried over from the previous attempt)
- [x] All blocking open questions resolved (Q1–Q7). Q8–Q9 are non-blocking.
- [ ] **Ready to advance to `spec.md`** — awaiting the originator's approval

**One question never asked:** budgeting and forecasting. Everything in this
document is about *understanding* past spending, not steering future spending.
That may be exactly right — but it is the most common next want, and it is
better named as a deliberate non-goal than left ambiguous.
