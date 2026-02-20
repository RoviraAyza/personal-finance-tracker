"""
Migration script to add XLS-specific fields to the transactions table:
- office, currency, common_concept, bank_concept, reference_1, reference_2
- compl_1 through compl_10

Safe to run multiple times — checks for existing columns before altering.
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
        'office': 'TEXT',
        'currency': 'TEXT',
        'common_concept': 'TEXT',
        'bank_concept': 'TEXT',
        'reference_1': 'TEXT',
        'reference_2': 'TEXT',
        'compl_1': 'TEXT',
        'compl_2': 'TEXT',
        'compl_3': 'TEXT',
        'compl_4': 'TEXT',
        'compl_5': 'TEXT',
        'compl_6': 'TEXT',
        'compl_7': 'TEXT',
        'compl_8': 'TEXT',
        'compl_9': 'TEXT',
        'compl_10': 'TEXT',
    }

    added = 0
    for col_name, col_type in new_columns.items():
        if col_name not in existing:
            print(f"Adding column: {col_name} ({col_type})")
            cursor.execute(f"ALTER TABLE transactions ADD COLUMN {col_name} {col_type}")
            added += 1
        else:
            print(f"Column already exists: {col_name}")

    conn.commit()
    conn.close()
    print(f"Migration complete! Added {added} new columns.")


if __name__ == '__main__':
    default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'finance.db')
    db_path = sys.argv[1] if len(sys.argv) > 1 else default_path
    migrate(db_path)
