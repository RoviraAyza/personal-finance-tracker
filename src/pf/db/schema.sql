-- Schema for the personal finance tracker.
-- Lifted from spec/spec.md section 3, with tables ordered so that every
-- foreign-key target exists before the table referencing it.
--
-- Money is stored as signed integer cents. Never floats: see
-- ingest/normalize.py:to_cents, which converts once at the import boundary.

CREATE TABLE IF NOT EXISTS accounts (
    id              INTEGER PRIMARY KEY,
    account_number  TEXT    NOT NULL UNIQUE,   -- exactly as the export gives it
    label           TEXT    NOT NULL,          -- e.g. 'Comun (household)'
    is_active       INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS categories (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NOT NULL UNIQUE,
    parent_id   INTEGER REFERENCES categories(id),
    -- 'spending' | 'income' | 'transfer' | 'excluded'
    -- 'transfer' and 'excluded' are omitted from spend analysis by default
    kind        TEXT    NOT NULL DEFAULT 'spending',
    sort_order  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS rules (
    id           INTEGER PRIMARY KEY,
    pattern      TEXT    NOT NULL,
    match_type   TEXT    NOT NULL,   -- 'exact' | 'prefix' | 'contains' | 'regex'
    field        TEXT    NOT NULL DEFAULT 'description_norm',
    category_id  INTEGER NOT NULL REFERENCES categories(id),
    priority     INTEGER NOT NULL DEFAULT 100,   -- lower wins
    kind_filter  TEXT,                -- optional: restrict to one transaction kind
    origin       TEXT    NOT NULL,    -- 'bootstrap' | 'manual'
    note         TEXT,
    created_at   TEXT    NOT NULL,
    UNIQUE(pattern, match_type, field, kind_filter)
);

CREATE TABLE IF NOT EXISTS transactions (
    -- Identity is a hash of every source cell plus the account number.
    -- There is no natural key: date+amount+merchant collides 98 times in 9
    -- years of real data, and those collisions are genuine distinct
    -- transactions. See spec/spec.md section 4.3.
    row_hash        TEXT    PRIMARY KEY,
    account_id      INTEGER NOT NULL REFERENCES accounts(id),

    date_op         TEXT    NOT NULL,          -- ISO 'YYYY-MM-DD'
    date_value      TEXT    NOT NULL,

    amount_cents    INTEGER NOT NULL,          -- signed; negative = money out
    balance_cents   INTEGER,                   -- running balance; nullable
    currency        TEXT    NOT NULL DEFAULT 'EUR',

    kind            TEXT    NOT NULL,          -- derived; see ingest/kinds.py
    code_common     TEXT    NOT NULL,          -- 'Concepte comu', kept raw
    code_own        TEXT    NOT NULL,          -- 'Concepte propi', kept raw

    description_raw  TEXT   NOT NULL,          -- exactly as exported
    description_norm TEXT   NOT NULL,          -- normalised; what rules match
    type_label       TEXT,                     -- e.g. 'COMPRA CON TARJETA'
    counterparty_ref TEXT,                     -- card no. / origin ref, raw

    category_id     INTEGER REFERENCES categories(id),
    rule_id         INTEGER REFERENCES rules(id),
    categorized_by  TEXT    NOT NULL DEFAULT 'none',  -- 'none'|'rule'|'manual'

    source_file     TEXT    NOT NULL,
    imported_at     TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_tx_date     ON transactions(date_op);
CREATE INDEX IF NOT EXISTS ix_tx_cat_date ON transactions(category_id, date_op);
CREATE INDEX IF NOT EXISTS ix_tx_acct     ON transactions(account_id, date_op);
CREATE INDEX IF NOT EXISTS ix_tx_uncat    ON transactions(categorized_by)
    WHERE categorized_by = 'none';

CREATE TABLE IF NOT EXISTS saved_filters (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    definition  TEXT NOT NULL,        -- JSON; see spec section 10.3
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS import_runs (
    id            INTEGER PRIMARY KEY,
    source_file   TEXT    NOT NULL,
    file_sha256   TEXT    NOT NULL,
    rows_read     INTEGER NOT NULL,
    rows_inserted INTEGER NOT NULL,
    rows_skipped  INTEGER NOT NULL,   -- already present (idempotent re-import)
    rows_rejected INTEGER NOT NULL,   -- unparseable; written out for inspection
    started_at    TEXT    NOT NULL,
    finished_at   TEXT    NOT NULL
);
