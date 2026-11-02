"""Giving a transaction a stable identity.

There is no natural key in this data. Measured over the real 9-year export,
(date, amount, merchant) collides 98 times -- and every one of those
collisions is a pair of GENUINE distinct transactions: two coffees at the same
bar, on the same day, for the same price. Deduplicating on those fields would
silently delete real spending, and nobody would notice.

What distinguishes them is the running balance, because every transaction
moves it. Rather than guess which subset of columns is sufficient, the
identity is a hash of the whole source row: zero collisions across 10,034
rows, and re-importing an overlapping date range becomes a no-op.
"""

from __future__ import annotations

import hashlib
from typing import Sequence

#: ASCII unit separator. Used to join cells so that values cannot run
#: together: without it, cells ('AB', 'C') and ('A', 'BC') would hash alike.
_SEP = "\x1f"


def row_hash(cells: Sequence[str], account_number: str) -> str:
    """A stable identifier for one source row.

    The account number participates so that the same figures appearing in two
    different accounts remain two different transactions.
    """
    payload = _SEP.join([account_number.strip(), *(str(c).strip() for c in cells)])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def file_hash(path) -> str:
    """SHA-256 of a whole file, recorded against each import run."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
