# Intent: Personal Finance Tracker (v2)

**Status:** 🔴 Draft — in conversation, not ready for review
**Originator:** Jose (@RoviraAyza)
**Started:** 2026-11-01
**Supersedes:** v1 implementation, archived at branch `archive/v1`

> **How to read this file.** This is a proto-spec, written during conversation and
> corrected by the originator. Confidence is marked inline so nothing unverified
> gets quietly promoted into `spec.md`:
>
> - ✅ **Stated** — the originator said this
> - 🟡 **Carried over** — inherited from the v1 PRD; plausible but unconfirmed
> - ❓ **Open** — not yet known

---

## 1. Problem statement

### What I can't do today
❓ *Open — awaiting the originator's own description.*

The v1 PRD framed it as:

> "Currently lacking visibility into personal spending patterns. Bank statements
> provide raw transaction data but no easy way to analyze spending by custom
> categories over specific time periods."

🟡 That was written 2026-02-11, before v1 was built and used. It describes the
problem of someone with *no tool*. The originator has since built one, used it,
and chosen to delete it — so the real v2 problem statement is probably about what
v1 failed to answer, not about having no tool at all. **Needs replacing.**

### Why v1 was abandoned
❓ *Open.* Known facts, not yet an explanation:

- ~3,000 lines (Flask + vanilla JS + SQLite), 15 commits over ~9 months
- `tests/` directory existed but was **empty** — no automated verification
- Two ad-hoc schema migrations (`migrate_add_fields.py`, `migrate_add_xls_fields.py`)
  suggest the data model was being patched rather than designed
- Last three commits were all UI rework of the same transactions table
  (category column → inline dot → picker moved into a detail modal), suggesting
  the categorization interaction was the unresolved part
- ✅ The originator chose to restart from zero rather than refactor

### What "better" looks like
❓ *Open — the Sunday-afternoon scenario. What happens when you open it?*

---

## 2. Proposed outcome
❓ *Open.* To be written once the problem statement is settled.

---

## 3. Affected users & systems

### Users
- ✅ **Jose, sole user.** Technical, comfortable with manual exports/imports.
  No second user, now or planned.

### Systems & data
- ✅ **Bank transaction exports.** v1 ingested CSV and XLS. Files named
  `Movimientos_cuenta_*.csv` were gitignored, so at least one Spanish bank
  (statement export, manually downloaded).
  - ❓ Which bank(s)? How many accounts? Cards as well as current accounts?
- ✅ **Existing data: `_old_data/finance.db`** — 1.5 MB SQLite from v1, holding
  real categorized transactions. Preserved and available.
  - ❓ Migrate this history into v2, or start the data clean too?
  - This is a decision with real consequences: months of manual categorization
    live in there, and re-doing it by hand would be miserable.
- ✅ **`_old_data/config.json`** — v1 config (watched-folder paths etc.)
- 🟡 **A watched folder.** v1 had a "Sync from Folder" feature, implying
  statements get dropped into a directory rather than uploaded one at a time.
  Worth confirming — it shapes the whole import model.

---

## 4. Constraints

### Stated
- ✅ **Starting from zero.** No v1 code carried forward. Reference only.
- ✅ **Follows the AI-native SDLC playbook**, adapted for a solo project:
  adopt `intent.md` → `spec.md` → `plan.md` → code with review between stages,
  plus `CLAUDE.md` and a real test feedback loop. Skipping enterprise plays
  (approval gates, CI/CD tiers, evals, security scanning, on-call).
- ✅ **Runs locally**, single machine. Repo lives in Google Drive
  (`Mi unidad/Projects/`), so it syncs across the originator's devices.

### Open
- ❓ **Stack.** v1 was Flask + server-rendered Jinja + vanilla JS + SQLite.
  Unknown whether "I learnt a lot" includes wanting a different stack.
- ❓ **Privacy.** Real financial data. Does anything leave the machine
  (cloud sync, hosted deploy, third-party APIs), or strictly local?
  Note: the repo already sits in Google Drive, so the DB is effectively
  in Google's cloud today — possibly unintentionally.
- ❓ **Effort appetite.** A weekend's worth of tool, or an ongoing project?
  This decides how much of v1's scope survives.

---

## 5. Out of scope

🟡 Carried from the v1 PRD's non-goals — **all need re-confirming**, since one of
them may be exactly what v2 should add:

- Direct bank API integration (manual export only)
- Multi-user / shared accounts
- Budget planning or forecasting
- Native mobile apps (responsive web deemed sufficient)
- Accounting software integration
- Bill payment or reminders
- Investment tracking

❓ The interesting question: after using v1 for months, is **budgeting or
forecasting** still out of scope? "Where did my money go" is a different product
from "am I on track" — and the second is the one people usually want next.

---

## 6. Open questions

Blocking — `spec.md` cannot be written without these:

1. ❓ What question about your money does v1 still not answer?
2. ❓ What specifically annoyed you about using v1?
3. ❓ Same stack, or a different one?
4. ❓ Migrate `_old_data/finance.db`, or start the data clean?
5. ❓ Which banks / how many accounts / cards too?
6. ❓ Are the v1 non-goals still non-goals — especially budgeting?

Non-blocking, decide during design:

7. ❓ Is the import a watched folder, a manual upload, or both?
8. ❓ How much does auto-categorization matter vs. manual control?
   (v1's last three commits suggest manual categorization was the friction point.)
9. ❓ Does the Google Drive location need addressing for privacy?

---

## 7. Decision log

| Date | Decision | Rationale |
|---|---|---|
| 2026-11-01 | Restart from zero rather than refactor v1 | Originator's call; v1 preserved on `archive/v1` |
| 2026-11-01 | Keep `LICENSE`, `.gitignore`, `.claude/settings.local.json` | Reusable scaffolding, nothing to re-learn |
| 2026-11-01 | Preserve v1 DB + config in gitignored `_old_data/` | Real data, never in git, would be unrecoverable if deleted |
| 2026-11-01 | Adopt playbook stages 1–4 fully, 5 lightly, skip 6 | Solo project; enterprise gates cost more than they return |

---

## 8. Approval

- [ ] Originator has corrected the agent-written draft
- [ ] All blocking open questions resolved
- [ ] Ready to advance to `spec.md`
