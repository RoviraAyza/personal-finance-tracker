"""Applying the rule set to stored transactions.

The only module that writes categories. Two promises:

  * **A manual decision is never overwritten.** If the user has said what
    something is, no rule may quietly disagree with him later -- under any
    flag. That is the one rule in this slice with no exceptions.
  * **Running it twice changes nothing the second time.**

The JSON files are the authority for categories and rules; the database copies
exist so that queries can join to them. `sync_rule_set` pushes the files into
the database and hands back the name-to-id maps.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Sequence

from pf.rules.categorizer import Categorizer
from pf.rules.model import Candidate, Category, Rule


@dataclass(frozen=True)
class ApplyResult:
    """What one run did."""

    considered: int = 0
    assigned: int = 0          # was uncategorised, now has a category
    changed: int = 0           # had a rule category, now a different one
    cleared: int = 0           # had a rule category, now matches nothing
    left_alone: int = 0        # manual decisions, untouched
    unchanged: int = 0
    still_uncategorised: int = 0


def sync_rule_set(
    con: sqlite3.Connection,
    categories: Sequence[Category],
    rules: Sequence[Rule],
) -> tuple[dict[str, int], dict[int, int]]:
    """Mirror the JSON files into the database.

    Returns (category name -> db id, rule file id -> db id). Rules are
    replaced wholesale: the file is the authority, so a rule deleted from the
    file must disappear from the database rather than linger.
    """
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for category in categories:
        con.execute(
            "INSERT INTO categories (name, kind) VALUES (?, ?) "
            "ON CONFLICT(name) DO UPDATE SET kind = excluded.kind",
            (category.name, category.kind),
        )
    cat_ids = {
        row["name"]: row["id"]
        for row in con.execute("SELECT id, name FROM categories")
    }
    # Parents are resolved in a second pass so order in the file does not matter.
    for category in categories:
        if category.parent:
            con.execute(
                "UPDATE categories SET parent_id = ? WHERE name = ?",
                (cat_ids[category.parent], category.name),
            )

    # Detach transactions from rules before clearing the table, so the foreign
    # key stays satisfied; they are re-attached below.
    con.execute("UPDATE transactions SET rule_id = NULL")
    con.execute("DELETE FROM rules")

    rule_ids: dict[int, int] = {}
    for rule in rules:
        cur = con.execute(
            """INSERT INTO rules (
                   pattern, match_type, field, category_id, priority,
                   kind_filter, origin, note, created_at
               ) VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                rule.pattern,
                rule.match,
                "description_norm",
                cat_ids[rule.category],
                rule.priority,
                rule.kind_filter,
                "bootstrap",
                rule.note,
                now,
            ),
        )
        rule_ids[rule.id] = int(cur.lastrowid)

    con.commit()
    return cat_ids, rule_ids


def apply_rules(
    con: sqlite3.Connection,
    categorizer: Categorizer,
    cat_ids: dict[str, int],
    rule_ids: dict[int, int],
    *,
    only_uncategorised: bool = True,
) -> ApplyResult:
    """Categorise stored transactions.

    `only_uncategorised=False` re-applies rules to rows previously categorised
    by rule -- what you want after editing the rule set. Manual decisions are
    excluded either way.
    """
    considered = assigned = changed = cleared = unchanged = 0

    where = "WHERE categorized_by != 'manual'"
    if only_uncategorised:
        where = "WHERE categorized_by = 'none'"

    rows = con.execute(
        f"""SELECT row_hash, description_norm, kind, amount_cents,
                   category_id, categorized_by
            FROM transactions {where}"""
    ).fetchall()

    updates: list[tuple[int | None, int | None, str, str]] = []
    for row in rows:
        considered += 1
        decision = categorizer.categorize(
            Candidate(
                description_norm=row["description_norm"],
                kind=row["kind"],
                amount_cents=row["amount_cents"],
            )
        )

        new_cat = cat_ids[decision.category] if decision.category else None
        new_rule = rule_ids.get(decision.rule_id) if decision.rule_id else None
        new_by = "rule" if decision.category else "none"

        if new_cat == row["category_id"] and new_by == row["categorized_by"]:
            unchanged += 1
            continue

        if row["category_id"] is None and new_cat is not None:
            assigned += 1
        elif row["category_id"] is not None and new_cat is None:
            cleared += 1
        else:
            changed += 1

        updates.append((new_cat, new_rule, new_by, row["row_hash"]))

    if updates:
        con.executemany(
            """UPDATE transactions
               SET category_id = ?, rule_id = ?, categorized_by = ?
               WHERE row_hash = ?""",
            updates,
        )
        con.commit()

    left_alone = con.execute(
        "SELECT COUNT(*) AS n FROM transactions WHERE categorized_by = 'manual'"
    ).fetchone()["n"]
    still = con.execute(
        "SELECT COUNT(*) AS n FROM transactions WHERE category_id IS NULL"
    ).fetchone()["n"]

    return ApplyResult(
        considered=considered,
        assigned=assigned,
        changed=changed,
        cleared=cleared,
        left_alone=left_alone,
        unchanged=unchanged,
        still_uncategorised=still,
    )
