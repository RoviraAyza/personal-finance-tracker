# Plan — S2: Categorise

**Status:** 🟢 **APPROVED** 2026-11-02 — in progress
**Slice:** S2 of 6 (see [`spec/spec.md`](../spec/spec.md) §13)
**Author:** Claude (agent-written), for review by Jose
**Date:** 2026-11-02
**Derives from:** `spec/spec.md` (approved), `plan/s1-ingest.md` (complete)

> **Convention.** If implementation departs from this plan, **this file is
> updated in the same commit** (playbook Play 3a).

---

## 1. Goal

Give every transaction a category, automatically, from rules that are data —
and then **prove in numbers** whether that works, before any UI exists.

This is the slice that validates the project's central premise. If the
thresholds in §6 do not hold, the approach needs rethinking, and it is far
better to learn that now than after building two screens on top of it.

### Done when

| #   | Criterion                                                             | How it is checked        |
| --- | --------------------------------------------------------------------- | ------------------------ |
| D1  | ≥ **90%** of rows categorised (excluding own-transfers)               | `pf coverage`            |
| D2  | ≥ **95%** of the **€231,729** non-transfer outflow categorised        | `pf coverage`            |
| D3  | **0** rules that match nothing in nine years                          | `pf rules check`         |
| D4  | **Holdout**: rules built from 2017–2024 cover ≥ 85% of 2025–2026 rows | `pf coverage --holdout`  |
| D5  | A typical month leaves ≤ **15** rows needing a human decision         | `pf coverage --by-month` |
| D6  | Re-running categorisation never overwrites a manual decision          | test                     |
| D7  | `python -m pytest` passes                                             | one command              |

D4 is the honest test. D1–D2 measure how well rules fit data they were derived
from, which always flatters. D4 asks whether they will work on *next month*.

### Explicitly not in S2

FastAPI, React, any UI, drill-down, saved filters, the comparison baseline,
the snapshot export, the second account. No transaction splitting.

---

## 2. The one real design decision: how the model gets called

The spec says the bootstrap is a one-off, offline, LLM-assisted step. There are
three ways to do that, and the choice matters more than it looks.

| Option                                                                                      | Cost                                                                                        |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Python script calling the Anthropic API                                                     | A new dependency, an API key to manage, money per run, and the payload is invisible to Jose |
| Paste a prompt into claude.ai by hand                                                       | Free, uses his existing subscription, but the extraction is manual and unrepeatable         |
| **Generate the prompt as a file; a model fills it in; the answer is saved as `rules.json`** | **Chosen**                                                                                  |

✅ **Chosen: the deterministic parts are code, the model call is a step.**

```
pf bootstrap-prompt  -->  bootstrap/prompt.md   (what gets sent, as a file)
                          bootstrap/merchants.txt (the 1,052 strings)
                                    |
                          [ a model answers -- Claude Code in this
                            session, or claude.ai, or an API call ]
                                    |
                          rules/categories.json
                          rules/rules.json       -->  reviewed and edited by Jose
                                    |
                          pf rules check  /  pf categorize  /  pf coverage
```

Why this shape:

- **No new runtime dependency, no API key, no per-run cost.** The project keeps
  its single dependency.
- **The payload is a file Jose can read before it goes anywhere.** Given he
  has already flagged that he cannot review code in this stack, "here is
  literally the text being sent" is worth more than any assurance.
- **The deterministic work is testable**: extracting, deduplicating, excluding
  transfer-only strings, validating the response, measuring coverage. The
  model's judgement is the only non-deterministic part, and its output is
  committed data that can be diffed and corrected.
- **Repeatable later** for newly-seen merchants, without redoing the first run.

### What the payload contains

- ✅ The **1,052** deduplicated merchant strings, normalised.
- ✅ **Excluded: the 33 strings that only ever appear on transfer rows** — the
  family's names. The bank's type codes already identify those rows, so the
  names add nothing to categorisation (intent decision log, 2026-11-02).
- ✅ **No amounts, dates, balances, account numbers, card numbers or running
  totals.**
- ❓ **Not sending frequency counts**, to stay faithful to the recorded
  decision ("only the deduplicated list of strings"). Frequency would help the
  model prioritise; it is held in reserve if the first proposal is poor.

---

## 3. Files

```
src/pf/rules/__init__.py
src/pf/rules/model.py          Rule, Category, RuleSet  (frozen dataclasses)
src/pf/rules/loader.py         read/write categories.json + rules.json; validate
src/pf/rules/categorizer.py    the Categorizer class -- pure
src/pf/rules/apply.py          run the categorizer over stored transactions
src/pf/rules/coverage.py       the measurements behind D1-D5
src/pf/bootstrap/__init__.py
src/pf/bootstrap/prompt.py     build prompt.md + merchants.txt
src/pf/bootstrap/ingest.py     validate a model response into the two json files

rules/categories.json          DATA, version-controlled, hand-editable
rules/rules.json               DATA, version-controlled, hand-editable
bootstrap/prompt.md            generated; what gets sent
bootstrap/merchants.txt        generated; the strings

tests/test_rules_model.py
tests/test_rules_loader.py
tests/test_categorizer.py
tests/test_apply.py
tests/test_coverage.py
tests/test_bootstrap_prompt.py
```

`src/pf/cli.py` gains: `bootstrap-prompt`, `rules check`, `categorize`,
`coverage`. `src/pf/db/schema.sql` is unchanged — S1 already created
`categories` and `rules`.

### Module boundaries

`categorizer.py` is **pure**: rules in, decision out, no I/O and no database.
`apply.py` is the only module that writes categories to transactions.
`coverage.py` only reads. `loader.py` is the only module that touches the JSON.

---

## 4. Interfaces

```python
# rules/model.py
@dataclass(frozen=True)
class Category:
    name: str
    kind: str = "spending"      # spending | income | transfer | excluded
    parent: str | None = None

@dataclass(frozen=True)
class Rule:
    pattern: str
    match: str                  # exact | prefix | contains | regex
    category: str               # by NAME; resolved against the category set
    priority: int = 100         # lower wins
    kind_filter: str | None = None
    note: str | None = None
    id: int = 0                 # assignment order; breaks priority ties

@dataclass(frozen=True)
class Candidate:                # all the categorizer may look at
    description_norm: str
    kind: str
    amount_cents: int

@dataclass(frozen=True)
class Decision:
    category: str | None        # None => uncategorised
    rule_id: int | None
    reason: str                 # 'rule' | 'no_match'

# rules/categorizer.py
class Categorizer:
    def __init__(self, categories: Sequence[Category], rules: Sequence[Rule]): ...
    def categorize(self, c: Candidate) -> Decision: ...
    def explain(self, c: Candidate) -> list[Rule]:
        """Every matching rule, in precedence order. Not a debug extra: it is
        how a wrong rule gets found, and the UI will need it in S4."""
    def unused_rules(self, candidates: Iterable[Candidate]) -> list[Rule]:
        """Rules that matched nothing. Almost always a typo (D3)."""

# rules/apply.py
@dataclass(frozen=True)
class ApplyResult:
    considered: int
    assigned: int
    changed: int                # was categorised, now differently
    left_alone: int             # manual decisions, never touched
    still_uncategorised: int

def apply_rules(con, categorizer, *, only_uncategorised: bool = True) -> ApplyResult: ...

# rules/coverage.py
@dataclass(frozen=True)
class Coverage:
    rows_total: int
    rows_categorised: int
    value_total_cents: int        # non-transfer outflow
    value_categorised_cents: int
    by_category: list[tuple[str, int, int]]      # name, rows, cents
    worst_uncategorised: list[tuple[str, int, int]]   # description, rows, cents

def measure(con, *, date_from=None, date_to=None) -> Coverage: ...
def measure_holdout(con, train_to: str, test_from: str) -> tuple[Coverage, Coverage]: ...
```

### Matching and precedence

- Patterns match against `description_norm`, so they are written upper-case and
  accent-free. **Prefix matching is safe** — measured: zero genuine merchant
  collisions among 1,082 strings truncated at 17 characters.
- Order: **`priority` ascending, then `id` ascending. First match wins.** No
  scoring, no fuzzy ranking.
- `regex` patterns are compiled **at load time**, so a bad pattern fails
  immediately rather than mid-run.
- A rule naming a category that does not exist is a **load error**.

### ⚠️ Manual decisions are sacred

`categorized_by = 'manual'` is never overwritten by rule application, under
any flag. If Jose has told the system what something is, a rule must not
silently disagree with him later. `--all` re-applies rules to rows categorised
*by rule*, and leaves manual ones alone. (D6.)

---

## 5. Work order

| # | Step | Why here |
|---|---|---|
| 1 | `rules/model.py`, `loader.py` + tests | Define and validate the data before anything consumes it |
| 2 | `categorizer.py` + tests | Pure, and the heart of the slice |
| 3 | `bootstrap/prompt.py` + tests | Produces the payload; **Jose reads it before anything is sent** |
| 4 | **Generate the prompt; run the bootstrap; review the proposal** | The human-in-the-loop step |
| 5 | `bootstrap/ingest.py` + tests | Validate the response into the two JSON files |
| 6 | `coverage.py` + tests | Needed to judge step 4's output |
| 7 | `apply.py` + tests | Writes to the database, so last |
| 8 | CLI commands | Thin wiring |
| 9 | **Measure D1–D5; iterate on rules with Jose** | The acceptance moment |
| 10 | Update `CLAUDE.md`; close the plan | |

Steps 1–3 before any model call: the prompt is built by tested code, and seen,
before it leaves the machine. Step 9 is expected to loop — the first rule set
will miss things, and tightening it *is* the work.

---

## 6. Acceptance thresholds, and what they really mean

| Metric | Threshold | Note |
|---|---|---|
| Rows categorised | ≥ 90% | Excludes `transfer_own` |
| Non-transfer outflow value | ≥ 95% | Denominator **€231,729** (measured) |
| Rules matching nothing | 0 | A typo detector |
| Holdout rows (2025–26 from 2017–24 rules) | ≥ 85% | The one that predicts next month |
| Rows per month needing a decision | ≤ 15 | Whether the ritual is sustainable |

⚠️ **Cash is 16% of the measured denominator.** €37,970 of the €231,729 is
cash withdrawals, which go into a single `Cash withdrawn` category. That counts
as categorised — correctly, since the category is honest about what it is — but
it means the value threshold is easier to hit than it first appears, and a
report saying "16% of your spending: cash, destination unknown" is the expected
outcome, not a defect. Agreed with Jose 2026-11-02.

---

## 7. Tests

### `test_categorizer.py` — the pure core
- each match type: `exact`, `prefix`, `contains`, `regex`
- lower `priority` wins; ties broken by `id`; first match wins
- no match → `Decision(category=None, reason='no_match')`
- `explain()` returns **all** matching rules in precedence order
- `kind_filter` restricts a rule to one transaction kind
- a rule written with accents/lower case still matches `description_norm`
- `contains` over-reach is demonstrated: `EL ARBOL` matches `EL ARBOLITO`
  *(documents the known hazard rather than pretending it away)*
- truncated 17-character description matched by a `prefix` rule
- empty description → no match, no crash

### `test_rules_loader.py`
- round-trips categories and rules through JSON unchanged
- a rule naming an unknown category is a load error, naming the category
- an invalid regex is a load error, naming the pattern
- an unknown `match` type is a load error
- duplicate `(pattern, match, kind_filter)` is a load error
- rule `id`s are assigned by file order, so precedence is stable and reviewable
- writing is deterministic — stable key order, so diffs stay readable

### `test_apply.py`
- uncategorised rows get `category_id`, `rule_id`, `categorized_by='rule'`
- **`categorized_by='manual'` is never changed, with or without `--all`** (D6)
- running twice changes nothing the second time
- `--all` re-applies after a rule edit; default only touches uncategorised
- a row whose rule was deleted becomes uncategorised again under `--all`
- `transfer_own` rows are categorised into a `transfer`-kind category

### `test_coverage.py`
- row and value percentages computed on known fixtures
- own-transfers excluded from both numerator and denominator
- `worst_uncategorised` ranks by **value**, not count — one €400 unknown
  matters more than ten €2 ones
- holdout split respects the date boundary in both directions
- an empty database reports 0%, not a division error

### `test_bootstrap_prompt.py`
- the payload contains **no** amounts, dates, balances, account or card numbers
  *(asserted by scanning the generated file for digit patterns and for the
  account number)*
- descriptions appearing only on transfer rows are **excluded**
- the list is deduplicated and sorted, so the file is stable between runs
- a description appearing on both transfer and non-transfer rows is kept

### `test_real_corpus.py` (extended, opt-in)
- coverage thresholds D1, D2, D4 against the real database

---

## 8. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **Model proposes too many categories** | High | Review step; 15–25 is the target. Easier to merge than to split |
| **Model proposes categories that don't match how Jose thinks** | Medium | He edits; the proposal is a starting point, not an answer |
| `contains` rules over-reaching silently | Medium | `explain()`, plus S4's preview of what a rule would capture. A test documents the hazard |
| Holdout coverage much worse than fitted | Medium | **This is the finding, not a failure.** If rules don't generalise, the approach needs revisiting — which is exactly what D4 is for |
| Cash flattering the value metric | **Certain** | Reported separately so the number is honest |
| Over-fitting to nine years of history | Medium | D4; and rules preferring short general patterns over long specific ones |
| Scope creep into UI | Medium | The "not in S2" list |
| Family names leaking into the payload | Low | Excluded by construction, and asserted by a test |

---

## 9. What this slice does *not* prove

- **Nothing about the UI.** Coverage can be excellent and the monthly ritual
  still unpleasant; that is S3–S4.
- **Nothing about cash.** 16% of outflow stays unexplainable by construction.
- **Nothing about a second account.** Rules are account-agnostic, untested
  across accounts.
- Coverage is measured on **one household's nine years**. It says nothing about
  anyone else's statements, which is fine — there is one user.

---

## 10. Review checklist

- [ ] The bootstrap approach in §2 is right — prompt as a readable file, no API key
- [ ] Not sending frequency counts is the right call
- [ ] The `Categorizer` interface (§4) is one he'd want to maintain
- [ ] **Manual decisions being sacred** (§4) is the right rule
- [ ] Two JSON files (categories, rules) rather than one
- [ ] Thresholds in §6 are the right bar, including the 85% holdout
- [ ] The cash caveat is understood and acceptable
- [ ] Work order agreed — prompt built and read before anything is sent
- [ ] **Approved → implement S2**

---

## 11. Progress log

| Step | State | Notes |
|---|---|---|
| 1 — `model.py`, `loader.py` | ✅ done | all rule-set errors caught at load time with the offender named; **23 tests** |
| 2 — `categorizer.py` | ✅ done | pure; first match wins by (priority, id); `explain()`, `unused_rules()`, `shadowed_rules()`; **27 tests** |
| 3 — `bootstrap/prompt.py` | ✅ done | `pf bootstrap-prompt` writes the payload to files, sends nothing; **16 tests**, including assertions that no amounts, dates, account or card numbers are present |
| 4 — run the bootstrap, review | ✅ done | 23 categories, 350 rules, by Claude Code in-session from the 1,059-string payload | payload regenerated after the kind correction: **1,059 strings, 26 excluded**, audited clean (§12) |
| 5 — `bootstrap/ingest.py` | ➖ not needed | the model wrote the two JSON files directly; `loader.py` already validates them fully, so a separate ingest step would duplicate it |
| 6 — `coverage.py` | ✅ done | rows + value, holdout, per-month; **12 tests** |
| 7 — `apply.py` | ✅ done | manual decisions never overwritten; **14 tests** |
| 8 — CLI commands | ✅ done | `rules check`, `categorize [--all]`, `coverage [--by-month|--holdout]` |
| 9 — measure D1–D5, iterate | ✅ measured | **see §13 — the thresholds are not met, and the reason matters** |
| 10 — `CLAUDE.md`, close | ⬜ | |

### Added beyond the plan

- **`Categorizer.shadowed_rules()`** — detects the clear cases where an
  earlier rule makes a later one unreachable (an earlier `contains` whose
  pattern is inside a later rule's pattern). Not in the approved interface,
  but it costs ten lines and catches the commonest rule-writing mistake:
  adding a specific rule below a general one and wondering why it never fires.
- **Category parent validation** — a missing or self-referential parent is a
  load error. The plan did not mention nesting validation.
- **The prompt template carries no real data.** A test asserts the prompt
  itself contains no merchant strings; the data lives only in
  `merchants.txt`. The first draft used a real merchant name as a teaching
  example and the test caught it, so the examples are now placeholders.
- **`bootstrap/merchants.txt` is gitignored** — derived bank data, and
  regenerable from the database. `prompt.md` is data-free and committed.
- **`pf reclassify`** and two new transaction kinds — see §12.
- **Identifier redaction** in the payload — see §12.

---

## 12. Mid-slice correction: the kind mapping was wrong

Found at step 4, while reviewing the generated payload. Recorded here because
it changed the data model, not just the payload.

### What was wrong

`03`/`038`, `03`/`005`, `03`/`033`, `03`/`034` were classified as
`transfer_person` — "money sent to a person". They are **direct debits**. The
type-label column on those rows carries a *person's* name, which is the
account holder being **debited**; the payee is the company in the description,
behind the bank's `CORE` prefix. 296 rows, €20,572 over nine years: school
catering, electricity, council vehicle tax, language classes, a basketball
club.

Totals were unaffected — both kinds count as spending — but the labels were
misleading, and `direct_debit` is a category the originator will want.

### What changed

- **Two new kinds**: `direct_debit` and `transfer_in`.
- **21 code pairs mapped** (was 12). **No unmapped pairs remain** in nine years
  of data, so the importer's long-tail report is now empty.
- **`pf reclassify`** re-derives every row's kind from the stored source codes.
  Not in the approved plan. It is possible *only* because `code_common`,
  `code_own` and `type_label` are stored raw alongside the derived kind — the
  payoff of that S1 decision. 386 of 10,161 rows corrected.
- **Redaction added to the payload**: DNI, NIE and Spanish phone numbers are
  stripped from merchant descriptions. Company tax IDs (CIF) are deliberately
  kept — public register data that identifies a business and helps the model.

### Two near-misses worth recording

1. **A dropped mapping.** Rewriting `_CODE_MAP` silently lost `02`/`032` and
   `99`/`067`, which would have moved 47 rows to `other`. Caught by
   `pf reclassify --dry-run` before anything was written. The dry run paid for
   itself the first time it was used.
2. **A one-row privacy leak.** `transfer_in` was added as a kind and *not*
   added to the payload's exclusion list. A single incoming transfer was then
   enough to put a family member's name into a payload of a thousand strings.
   Caught by reading the regenerated file. There is now a test naming this
   exact scenario, and a comment in `prompt.py` saying that any new
   transfer-shaped kind belongs in that list.

Both were found by *looking at output*, not by the test suite — which is the
argument for the human-in-the-loop step existing at all.

### Payload after the correction

| | |
|---|---|
| Distinct descriptions | 1,086 |
| Excluded (transfer-only) | 26 |
| **Sent** | **1,059** |
| Audited absent | DNI, NIE, phone, card, account number, dates, amounts |
| Family surnames present | 0 |

---

## 13. Verdict: the thresholds fail, and D5 was measuring the wrong thing

### What the bootstrap achieved on its own

| | result | target | |
|---|---|---|---|
| D1 rows | 85.9% (7,890 / 9,181) | ≥ 90% | ✗ |
| D2 value | 88.9% (€231,970 / €260,795) | ≥ 95% | ✗ |
| D3 unused rules | **0** | 0 | ✓ |
| D4 holdout rows | 80.2% (fitted: 88.1%) | ≥ 85% | ✗ |
| D5 unknown rows/month | median 21 | ≤ 15 | ✗ |

### ⚠️ D5 was measuring the wrong thing

D5 counted uncategorised **rows** per month. But the same unknown merchant
reappears every month, and in real use it is triaged **once** and a rule covers
it from then on. Simulating the actual workflow — a merchant is new only the
first time it is ever seen — gives the true ongoing cost:

**Median 4 new merchants per month. Mean 3.8. Worst month in two years: 8.**

So D5's *intent* — "is the monthly ritual sustainable?" — passes decisively.
Its *formulation* was wrong. The same error makes D4 pessimistic: the holdout
simulates never updating the rules for two years, which is not how the tool
will be used.

**Correction for later slices:** the sustainability metric is *new distinct
merchants per month*, not uncategorised rows per month.

### The gap is irreducibly local knowledge

303 distinct unknown merchants remain, and they are small local businesses
whose nature cannot be inferred from the name with any confidence — bars,
small shops, individual tradespeople. The bootstrap prompt instructed the model
to leave anything doubtful alone rather than guess, and it did: `HECHOS Y
DICHOS` (496 rows), `EL CALLEJON` (129 rows) and `EL RINCON` (152 rows) have no
rule, because guessing would corrupt a total invisibly.

What triage buys, measured:

| Merchants triaged | rows | value | time at 15s each |
|---|---|---|---|
| 0 (bootstrap only) | 85.9% | 88.9% | — |
| 20 | 92.8% | **95.0%** | 5 min |
| **50** | **95.4%** | **97.2%** | **12 min** |
| 100 | 96.5% | 98.6% | 25 min |

**Twelve minutes of one-off triage clears both D1 and D2.**

### Conclusion

The approach works. Rules bootstrapped from history cover ~86% of rows and ~89%
of value immediately; a short, one-off triage pass clears the thresholds; and
the ongoing cost is about four decisions a month.

What it does **not** support is the idea that a bootstrap alone is sufficient.
The triage screen (S4) is not a convenience — it is the mechanism by which this
tool reaches and stays at useful coverage. That is the main thing this slice
establishes, and it was worth knowing before any UI was built.

### Additions beyond the approved plan

- **The `any` match type.** A rule that matches on transaction kind alone,
  ignoring the description. Needed because 155 real rows have **no description
  at all** and were otherwise uncategorisable by construction. Used only as a
  priority-900 structural fallback, so merchant rules always win.
- **`Categorizer.shadowed_rules()`** earned its place immediately: it caught
  `ZARA` as a prefix rule swallowing `ZARAOPTICOS`, `ZARAFILMS` and
  `ZARAGOZA P INDEPE`, which would have filed an optician and a car park under
  Clothing.
- **One-record-per-line JSON.** Standard `indent=2` turned a 350-rule file into
  1,700 lines and made a one-word change an unreadable diff. The writer now
  puts each rule on its own line.
- **`bootstrap/ingest.py` was dropped** as redundant — see the progress log.
