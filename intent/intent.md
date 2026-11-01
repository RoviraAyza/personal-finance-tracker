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

### What "better" looks like
✅ A simple app where the categories are mine, and the questions I ask stay
asked — so I can see where my family's money goes without redoing work.

---

## 2. Proposed outcome

✅ A small app with a monthly rhythm:

1. Once a month, download the Excel export from the bank *(manual, but the bank
   generates it automatically — the cost is a download, not data entry)*
2. Feed it to the app
3. Transactions are categorized automatically by a rule engine
4. Anything the engine can't categorize is surfaced for a decision, and that
   decision becomes a new rule
5. See where the money went, through saved views I don't have to rebuild

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
- ✅ **Bootstrap corpus: Excel with all transactions since 2016.**
- ✅ **Originator is an ABAP developer** — expects encapsulation and clear
  interfaces; thinks in classes and APIs.
- ❓ Which bank, how many accounts/cards, and what the files actually look like.

---

## 4. Constraints

- ✅ **Simple.** Stated repeatedly and unprompted — a real design constraint.
- ✅ **Monthly cadence.** A once-a-month ritual, not a daily dashboard.
- ✅ **Deterministic at runtime.** The LLM is a one-time bootstrap tool, not a
  dependency of the running app.
- Follows the AI-native SDLC playbook, adapted for a solo project:
  `intent.md` → `spec.md` → `plan.md` → code, reviewed between stages.
- ❓ Stack.
- ❓ **Privacy.** The bootstrap step means sending transaction history to a
  model. Mitigation to consider: send only the deduplicated list of unique
  merchant description strings — no amounts, dates, or balances. Far fewer
  tokens and far less exposure. Separately, the repo sits in a Google Drive
  folder, so anything stored here syncs to Google by default.

---

## 5. Out of scope

- ✅ Bank API integration / automated import — accepted as manual.
- ✅ Machine learning or LLM inference at runtime — rules are deterministic.
- ❓ Anything else not yet stated.

---

## 6. Open questions

Blocking:

1. ❓ **What do the Excel files look like?** Both the monthly export and the
   2016-onward history. Columns, date formats, how debits/credits are signed,
   whether the header is on row 1 or row 8. Everything downstream depends on
   this, and it's the one thing that can't be reasoned about — it has to be seen.
2. ❓ **Do the two files have the same shape**, or is the history file something
   you've been maintaining by hand in a different format?
3. ❓ **Categories** — do you have a list in mind, or should the bootstrap
   propose one from the history for you to edit?
4. ❓ **Saved views: what are the questions you keep re-asking?** These are
   literal requirements. "Groceries per month this year", "everything at
   Amazon", "this month vs. the same month last year" — name the real ones.
5. ❓ Stack.
6. ❓ **Does the 2016 history get loaded as data**, or is it only a rule-training
   corpus? (Loading it means instant 10-year trends on day one.)

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
