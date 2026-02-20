"""
Migration script to add new fields to the transactions table:
- value_date, extra_details, balance, account_number

Safe to run multiple times — checks for existing columns before altering.
Also updates the unique index to include account_number.
"""

import sqlite3
import sys
import os


def get_existing_columns(cursor, table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    return {row[1] for row in cursor.fetchall()}


def migrate(db_path):
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    existing = get_existing_columns(cursor, 'transactions')
    print(f"Existing columns: {sorted(existing)}")

    new_columns = {
        'value_date': 'DATE',
        'extra_details': 'TEXT',
        'balance': 'DECIMAL(10,2)',
        'account_number': 'TEXT',
    }

    for col_name, col_type in new_columns.items():
        if col_name not in existing:
            print(f"Adding column: {col_name} ({col_type})")
            cursor.execute(f"ALTER TABLE transactions ADD COLUMN {col_name} {col_type}")
        else:
            print(f"Column already exists: {col_name}")

    # Drop old unique index (too strict for real bank data with identical
    # date/description/amount on the same day) and replace with non-unique index
    cursor.execute("DROP INDEX IF EXISTS idx_transactions_unique")
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_dup_check "
        "ON transactions(date, description, amount, account_number)"
    )
    print("Replaced unique index with non-unique composite index for dup checking")

    # Add account index
    cursor.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_account "
        "ON transactions(account_number)"
    )
    print("Added account_number index")

    conn.commit()
    conn.close()
    print("Migration complete!")


if __name__ == '__main__':
    # Default path: same directory as this script
    default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'finance.db')
    db_path = sys.argv[1] if len(sys.argv) > 1 else default_path
    migrate(db_path)
