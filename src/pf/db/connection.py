"""Opening the database and applying the schema."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pf import config

_SCHEMA_FILE = Path(__file__).with_name("schema.sql")


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    """Open the database, creating its directory if needed.

    WAL is enabled because it is the right default for a local app, and
    foreign keys are enabled because SQLite leaves them off by default —
    a reference to a missing account should fail loudly, not silently.
    """
    target = Path(path) if path is not None else config.db_path()

    if str(target) != ":memory:":
        target.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(target))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    if str(target) != ":memory:":
        con.execute("PRAGMA journal_mode = WAL")
    return con


def init_schema(con: sqlite3.Connection) -> None:
    """Create any missing tables and indexes. Safe to call repeatedly."""
    con.executescript(_SCHEMA_FILE.read_text(encoding="utf-8"))
    con.commit()


def open_initialised(path: Path | str | None = None) -> sqlite3.Connection:
    """connect() + init_schema(), which is what every caller actually wants."""
    con = connect(path)
    init_schema(con)
    return con
