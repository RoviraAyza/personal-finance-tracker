-- Personal Finance Tracker Database Schema

-- Categories Table
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#6c757d',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Import History (must be created before transactions for FK)
CREATE TABLE IF NOT EXISTS import_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    records_imported INTEGER,
    import_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Transactions Table
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE NOT NULL,
    description TEXT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    value_date DATE,
    extra_details TEXT,
    balance DECIMAL(10,2),
    account_number TEXT,
    category_id INTEGER,
    import_batch_id INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (category_id) REFERENCES categories(id),
    FOREIGN KEY (import_batch_id) REFERENCES import_history(id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date);
CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category_id);
CREATE INDEX IF NOT EXISTS idx_transactions_import_batch ON transactions(import_batch_id);
CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_number);

-- Composite index for duplicate detection (not unique — real bank data can have
-- identical date/description/amount entries on the same day)
CREATE INDEX IF NOT EXISTS idx_transactions_dup_check
ON transactions(date, description, amount, account_number);

-- Default categories
INSERT OR IGNORE INTO categories (name, color) VALUES
    ('Supermercado', '#28a745'),
    ('Restaurantes', '#fd7e14'),
    ('Transporte', '#007bff'),
    ('Suministros', '#6c757d'),
    ('Ocio', '#e83e8c'),
    ('Salud', '#dc3545'),
    ('Compras', '#6f42c1'),
    ('Otros', '#17a2b8');
