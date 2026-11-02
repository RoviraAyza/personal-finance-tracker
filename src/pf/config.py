"""Where things live on disk.

The database deliberately does NOT live in the repository. This repo sits in a
Google Drive folder, and Drive syncs files while they are open — which corrupts
SQLite, because the database and its write-ahead log get copied out of step
with each other. See spec/spec.md, flagged concern 1.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Environment variable that overrides the database location.
DB_PATH_ENV = "PF_DB_PATH"

#: Environment variable pointing at a real bank export, for the opt-in tests.
REAL_XLS_ENV = "PF_REAL_XLS"

_APP_DIR_NAME = "PersonalFinance"


def app_data_dir() -> Path:
    """Per-user writable directory that is *not* cloud-synced.

    Windows: %LOCALAPPDATA% (LocalAppData is excluded from roaming/sync).
    Otherwise: $XDG_DATA_HOME or ~/.local/share.
    """
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / _APP_DIR_NAME
        return Path.home() / "AppData" / "Local" / _APP_DIR_NAME

    base = os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / _APP_DIR_NAME
    return Path.home() / ".local" / "share" / _APP_DIR_NAME


def db_path() -> Path:
    """The SQLite file to use. Override with PF_DB_PATH (':memory:' works)."""
    override = os.environ.get(DB_PATH_ENV)
    if override:
        return Path(override)
    return app_data_dir() / "finance.db"


def rejects_dir() -> Path:
    """Where rejected rows are written for inspection."""
    return app_data_dir() / "rejects"


def real_xls_path() -> Path | None:
    """A real export to validate against, if the user has pointed us at one."""
    value = os.environ.get(REAL_XLS_ENV)
    return Path(value) if value else None
