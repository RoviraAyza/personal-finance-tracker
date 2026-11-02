"""Building the bootstrap payload.

This is the one place in the project where data leaves the machine, so it is
built by tested code and written to files that can be read **before** anything
is sent. Nothing here calls a network.

What goes out: the deduplicated list of normalised merchant strings.
What does not: amounts, dates, balances, account numbers, card numbers,
running totals, and the descriptions that only ever appear on transfer rows --
which is where the family's names live, and which the bank's own type codes
already identify without reading a name.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

#: Kinds whose counterparty is a person or an account rather than a merchant.
#: A description seen ONLY on these is excluded from the payload.
#:
#: `transfer_in` was missing from this list when it was first added as a kind,
#: and one single incoming transfer was enough to expose a family member's
#: name in a payload of a thousand strings. Any new transfer-shaped kind
#: belongs here.
_TRANSFER_KINDS = ("transfer_person", "transfer_own", "transfer_in")

TARGET_CATEGORY_COUNT = "15 to 25"

# Identifiers that turn up inside merchant descriptions and must not leave the
# machine. Found by reading the generated payload, which is why the payload is
# written to a file and reviewed before being sent.
#
#   DNI    8 digits + a control letter, sometimes zero-padded to 9
#   NIE    X, Y or Z + 7 digits + a letter
#   phone  a Spanish mobile or landline, 9 digits beginning 6, 7, 8 or 9
#
# Company tax IDs (CIF) are deliberately NOT redacted: they are public
# register data, they identify a business rather than a person, and leaving
# them in helps the model recognise the company.
_REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b\d{8,9}[A-Z]\b"), ""),        # DNI
    (re.compile(r"\b[XYZ]\d{7}[A-Z]\b"), ""),     # NIE
    (re.compile(r"\b[6789]\d{8}\b"), ""),         # Spanish phone number
)


def redact(text: str) -> str:
    """Strip personal identifiers from a merchant description.

    Only ever removes characters, so a pattern written against the redacted
    form still matches the stored description with `contains` or `prefix`.
    """
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return re.sub(r"\s+", " ", text).strip(" :,-")


@dataclass(frozen=True)
class Payload:
    """Exactly what will be sent, and what was held back."""

    merchants: tuple[str, ...]
    excluded_transfer_only: int
    total_distinct: int
    redacted: int = 0

    @property
    def count(self) -> int:
        return len(self.merchants)


def collect_merchants(con: sqlite3.Connection) -> Payload:
    """The merchant strings worth asking about.

    A description is excluded when **every** transaction carrying it is a
    transfer. Those rows are already classified by the bank's type codes, so
    the name adds nothing to categorisation -- and they are overwhelmingly
    people's names.
    """
    rows = con.execute(
        f"""
        SELECT description_norm AS d,
               COUNT(*) AS n,
               SUM(CASE WHEN kind IN ({','.join('?' * len(_TRANSFER_KINDS))})
                        THEN 1 ELSE 0 END) AS transfers
        FROM transactions
        WHERE TRIM(description_norm) <> ''
        GROUP BY description_norm
        """,
        _TRANSFER_KINDS,
    ).fetchall()

    kept_raw = [r["d"] for r in rows if r["transfers"] < r["n"]]
    excluded = sum(1 for r in rows if r["transfers"] == r["n"])

    redacted_count = 0
    cleaned: set[str] = set()
    for value in kept_raw:
        clean = redact(value)
        if clean != value:
            redacted_count += 1
        if clean:
            cleaned.add(clean)

    return Payload(
        merchants=tuple(sorted(cleaned)),
        excluded_transfer_only=excluded,
        total_distinct=len(rows),
        redacted=redacted_count,
    )


def build_prompt(payload: Payload) -> str:
    """The instructions that accompany the merchant list."""
    return f"""# Bootstrap: propose categories and categorisation rules

You are helping set up a personal finance tracker for one household in Spain.

Attached (`merchants.txt`) are **{payload.count} distinct merchant description
strings**, taken from nine years of one joint current account used for everyday
household expenses. They are the complete vocabulary of places this family
spends money.

## What I need back

Two JSON objects, in separate fenced code blocks, in this exact shape.

**categories.json**

```json
{{
  "version": 1,
  "categories": [
    {{"name": "<category name>", "kind": "spending", "parent": null}}
  ]
}}
```

- `kind` is one of `spending`, `income`, `transfer`, `excluded`.
  Use `transfer` or `excluded` for anything that is not really household
  consumption, so it can be left out of spend totals.
- `parent` may name another category, one level deep only, or be `null`.

**rules.json**

```json
{{
  "version": 1,
  "rules": [
    {{"pattern": "<PATTERN>", "match": "contains", "category": "<category name>", "priority": 100}}
  ]
}}
```

- `match` is one of `exact`, `prefix`, `contains`, `regex`.
- `priority` orders rules; **lower wins**. Use 50 for a specific rule that must
  beat a general one, 100 for ordinary rules, 200 for broad catch-alls.
- Rules are tried in priority order, then file order, and **the first match
  wins**.

## How to write the patterns

1. **The strings are already normalised**: upper case, accents stripped,
   whitespace collapsed. Write patterns the same way -- `CAFETERIA`, never
   `Cafetería`.
2. **Many names are truncated at 17 characters** by the bank, mid-word. If a
   string reads `SOME LONG SHOP NA`, that is the whole value you will ever
   see. Match what is actually in the list; never write a pattern for the
   full name you infer it must have.
3. **Prefer the shortest pattern that is unambiguous.** For a chain with many
   branches, match the chain name alone so every branch is covered. But do not
   shorten so far that you catch unrelated shops -- check the list first.
4. **One rule can cover many strings.** A single `contains` rule on a common
   word can handle every cafe in the list. That is the goal: a few dozen rules
   covering most rows.
5. **Use `regex` sparingly**, only where a prefix or contains genuinely cannot
   express it.

## How to choose the categories

- **Aim for {TARGET_CATEGORY_COUNT} categories.** Fewer tells the family
  nothing; more makes the monthly review a chore.
- Categories should reflect **how a household thinks about its money**
  -- Groceries, Eating out, Transport, Health, Children, Utilities, Clothing --
  not how a shop classifies itself.
- Where you genuinely cannot tell what a merchant is, **leave it without a
  rule.** An uncategorised transaction is honest and will be reviewed by hand;
  a wrong rule is invisible and corrupts a total. This is the single most
  important instruction here.
- Some strings are clearly **not merchants** -- a person's name, a bank
  reference, a cash machine. Give those a `transfer` or `excluded` category
  rather than inventing a spending bucket for them.
- Add a short `note` to any rule where your reasoning would not be obvious to
  the person reviewing it.

## Context that may help

- The household is in Aragon, Spain, so expect Spanish and regional chains
  alongside small local businesses.
- Strings beginning `CORE` are a prefix the bank adds to some direct debits;
  the merchant name follows it.
- A few strings carry the bank's own encoding damage, already repaired:
  `N` with a tilde may appear as plain `N`.
- Cash withdrawals and card fees exist as separate transaction types and do not
  need merchant rules, but a `Cash withdrawn` category is wanted so that cash
  can be reported honestly as money whose destination is unknown.

Do not include any commentary outside the two code blocks.
"""


def write_payload(con: sqlite3.Connection, out_dir: Path | str) -> tuple[Path, Path, Payload]:
    """Write the prompt and the merchant list. Sends nothing anywhere."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    payload = collect_merchants(con)

    merchants_path = out / "merchants.txt"
    merchants_path.write_text("\n".join(payload.merchants) + "\n", encoding="utf-8")

    prompt_path = out / "prompt.md"
    prompt_path.write_text(build_prompt(payload), encoding="utf-8")

    return prompt_path, merchants_path, payload
