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
Because there is really only **one** query (§1), the app does not need a
saved-view library. It needs that one view, always present, with a period
selector that handles month / week / arbitrary range. "Saving filters" stops
being a feature and becomes the default state of the app.

❓ Open: whether anything beyond this one view is actually needed (see Q4).

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

> **The history file and the monthly file are the same thing.** This export is
> just a date-range query. One parser handles both the 9-year bootstrap and the
> monthly top-up — no second import path. *(Worth confirming that the monthly
> download uses the same "Excel simple" option.)*

---

## 4. Constraints

- ✅ **Simple.** Stated repeatedly and unprompted — a real design constraint.
- ✅ **Monthly cadence.** A once-a-month ritual, not a daily dashboard.
- ✅ **Deterministic at runtime.** The LLM is a one-time bootstrap tool, not a
  dependency of the running app.
- Follows the AI-native SDLC playbook, adapted for a solo project:
  `intent.md` → `spec.md` → `plan.md` → code, reviewed between stages.
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

❓ Open — this is now the main blocking decision (Q5). The realistic options,
their trade-offs, and a recommendation are to be settled before `spec.md`.

**Consequences to decide along with it:**
- ❓ **Where does the data live?** On the phone, or on the desktop with the phone
  as a viewer? On-device keeps the privacy story simple and needs no server;
  desktop-hosted means sync, which is where "simple" usually dies.
- ❓ **Where does the Excel import happen?** Importing a 4 MB `.xls` on a phone
  is possible (iOS share sheet → app), and would make the monthly ritual
  entirely phone-based. The alternative splits the app in two.
- ❓ **Does the rule bootstrap stay a desktop step?** Likely yes — a one-off
  script producing a rules file that ships with the app.

---

## 5. Out of scope

- ✅ Bank API integration / automated import — accepted as manual.
- ✅ Machine learning or LLM inference at runtime — rules are deterministic.
- ❓ Anything else not yet stated.

---

## 6. Open questions

Blocking:

1. ✅ **RESOLVED — the export format is known.** Profiled from a real file;
   see §3. One parser serves both the history and the monthly top-up.
2. ❓ **Confirm the monthly download is the same "Excel simple" export**, so
   there is genuinely only one input format to support.
3. ❓ **Categories** — do you have a list in mind, or should the bootstrap
   propose one from the 1,082 descriptions for you to edit?
4. ❓ **Is "spend by category for a period" the whole app, or just the front
   door?** Answered in part: it is the dominant query. Still open —
   - Does a total need something to be compared *against* to be useful?
     ("€840 on groceries" only means something next to a typical month.)
   - Do you ever need to drill from a category into its transactions?
   - Is there a second question you ask occasionally but genuinely need?
5. ❓ **Stack — now the main blocking decision**, because of the iPhone
   requirement plus the Windows development machine. See §4.
6. ❓ **Does the 9-year history get loaded as data**, or is it only a
   rule-bootstrap corpus? Loading it gives instant 9-year trends on day one,
   for the same parser and ~10k rows — cheap, and hard to argue against.

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

---

## 8. Approval

- [ ] Originator has corrected the agent-written draft
- [ ] Open questions resolved
- [ ] Ready to advance to `spec.md`
