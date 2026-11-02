"""Recomputing transaction kinds after the mapping changes.

The kind is derived at import time, so correcting the mapping would normally
mean re-importing everything. It does not here, because `code_common`,
`code_own` and `type_label` are stored raw alongside the derived kind -- so
every row can be reclassified from the database, with no original files
needed.

That is the whole payoff of keeping the source values: the derivation is
allowed to be wrong, because it can be redone.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field

from pf.ingest.kinds import derive_kind


@dataclass
class ReclassifyResult:
    """What changed, in enough detail to review before committing."""

    considered: int = 0
    changed: int = 0
    unmapped: int = 0
    transitions: Counter = field(default_factory=Counter)   # (old, new) -> n
    unmapped_codes: Counter = field(default_factory=Counter)

    @property
    def unchanged(self) -> int:
        return self.considered - self.changed


def reclassify(con: sqlite3.Connection, *, dry_run: bool = False) -> ReclassifyResult:
    """Re-derive `kind` for every stored transaction."""
    result = ReclassifyResult()

    rows = con.execute(
        """SELECT row_hash, kind, code_common, code_own, type_label
           FROM transactions"""
    ).fetchall()

    updates: list[tuple[str, str]] = []
    for row in rows:
        result.considered += 1
        new_kind, mapped = derive_kind(
            row["code_common"], row["code_own"], row["type_label"] or ""
        )
        if not mapped:
            result.unmapped += 1
            result.unmapped_codes[(row["code_common"], row["code_own"])] += 1
        if new_kind != row["kind"]:
            result.changed += 1
            result.transitions[(row["kind"], new_kind)] += 1
            updates.append((new_kind, row["row_hash"]))

    if updates and not dry_run:
        con.executemany(
            "UPDATE transactions SET kind = ? WHERE row_hash = ?", updates
        )
        con.commit()

    return result
