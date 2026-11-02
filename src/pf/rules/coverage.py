"""Measuring how much of the spending the rules actually explain.

Read-only. This is the slice's verdict, and it is deliberately expressed in
numbers the user can check without reading any code.

Two measures, because they answer different questions:

  * **rows** -- how much of the monthly review is automated
  * **value** -- how much of the money is accounted for

Value is the stricter test. One uncategorised 400 EUR purchase matters more
than ten uncategorised 2 EUR ones, and a rule set can look excellent by row
count while leaving the expensive things unexplained.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

#: Excluded from the measurement entirely: moving money between the
#: household's own accounts is not spending, and counting it would both
#: inflate the denominator and flatter the result.
_EXCLUDED_KINDS = ("transfer_own",)


@dataclass(frozen=True)
class Coverage:
    """What the rules explain, over some period."""

    rows_total: int = 0
    rows_categorised: int = 0
    value_total_cents: int = 0
    value_categorised_cents: int = 0
    by_category: list[tuple[str, int, int]] = field(default_factory=list)
    worst_uncategorised: list[tuple[str, int, int]] = field(default_factory=list)
    date_from: str | None = None
    date_to: str | None = None

    @property
    def rows_pct(self) -> float:
        return 100.0 * self.rows_categorised / self.rows_total if self.rows_total else 0.0

    @property
    def value_pct(self) -> float:
        if not self.value_total_cents:
            return 0.0
        return 100.0 * self.value_categorised_cents / self.value_total_cents

    @property
    def rows_uncategorised(self) -> int:
        return self.rows_total - self.rows_categorised

    @property
    def value_uncategorised_cents(self) -> int:
        return self.value_total_cents - self.value_categorised_cents


def _window(
    date_from: str | None, date_to: str | None, alias: str = ""
) -> tuple[str, list[str]]:
    """The WHERE clause for the measured population.

    `alias` qualifies the columns. It is needed wherever `categories` is
    joined, because both tables have a `kind` column and SQLite will not guess.
    """
    prefix = f"{alias}." if alias else ""
    clauses = [
        f"{prefix}amount_cents < 0",
        f"{prefix}kind NOT IN ({','.join('?' * len(_EXCLUDED_KINDS))})",
    ]
    params: list[str] = list(_EXCLUDED_KINDS)
    if date_from:
        clauses.append(f"{prefix}date_op >= ?")
        params.append(date_from)
    if date_to:
        clauses.append(f"{prefix}date_op <= ?")
        params.append(date_to)
    return " AND ".join(clauses), params


def measure(
    con: sqlite3.Connection,
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    limit_worst: int = 15,
) -> Coverage:
    """Coverage over outgoing, non-own-transfer transactions."""
    where, params = _window(date_from, date_to)

    totals = con.execute(
        f"""SELECT COUNT(*) AS rows_total,
                   COALESCE(SUM(-amount_cents), 0) AS value_total,
                   COALESCE(SUM(CASE WHEN category_id IS NOT NULL
                                     THEN 1 ELSE 0 END), 0) AS rows_cat,
                   COALESCE(SUM(CASE WHEN category_id IS NOT NULL
                                     THEN -amount_cents ELSE 0 END), 0) AS value_cat
            FROM transactions WHERE {where}""",
        params,
    ).fetchone()

    joined_where, joined_params = _window(date_from, date_to, alias="t")
    by_category = [
        (row["name"], row["n"], row["v"])
        for row in con.execute(
            f"""SELECT COALESCE(c.name, '(uncategorised)') AS name,
                       COUNT(*) AS n, SUM(-t.amount_cents) AS v
                FROM transactions t
                LEFT JOIN categories c ON c.id = t.category_id
                WHERE {joined_where}
                GROUP BY name ORDER BY v DESC""",
            joined_params,
        )
    ]

    # Ranked by VALUE, not count: the expensive unknowns are the ones worth a
    # rule, and the ones that move the value percentage.
    worst = [
        (row["description_norm"], row["n"], row["v"])
        for row in con.execute(
            f"""SELECT description_norm, COUNT(*) AS n, SUM(-amount_cents) AS v
                FROM transactions
                WHERE {where} AND category_id IS NULL
                GROUP BY description_norm ORDER BY v DESC LIMIT ?""",
            [*params, limit_worst],
        )
    ]

    return Coverage(
        rows_total=totals["rows_total"],
        rows_categorised=totals["rows_cat"],
        value_total_cents=totals["value_total"],
        value_categorised_cents=totals["value_cat"],
        by_category=by_category,
        worst_uncategorised=worst,
        date_from=date_from,
        date_to=date_to,
    )


def monthly_uncategorised(con: sqlite3.Connection) -> list[tuple[str, int, int]]:
    """Per month: rows needing a human decision, and rows in total.

    This is the measure of whether the monthly ritual is sustainable. A rule
    set that leaves 80 decisions a month will not be used twice.
    """
    where, params = _window(None, None)
    return [
        (row["month"], row["unknown"], row["total"])
        for row in con.execute(
            f"""SELECT substr(date_op, 1, 7) AS month,
                       SUM(CASE WHEN category_id IS NULL THEN 1 ELSE 0 END) AS unknown,
                       COUNT(*) AS total
                FROM transactions WHERE {where}
                GROUP BY month ORDER BY month""",
            params,
        )
    ]


def measure_holdout(
    con: sqlite3.Connection, train_to: str, test_from: str
) -> tuple[Coverage, Coverage]:
    """Coverage on the period the rules were derived from, and on later data.

    The honest test. Coverage over the training period only shows how well the
    rules fit data they were written against, which always flatters. What
    matters is whether they work on months nobody looked at -- which is what
    next month will be.
    """
    return (
        measure(con, date_to=train_to),
        measure(con, date_from=test_from),
    )
