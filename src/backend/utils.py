import csv
import io
import re
from datetime import datetime


# Supported date formats
DATE_FORMATS = [
    '%d/%m/%Y',  # DD/MM/YYYY
    '%Y-%m-%d',  # YYYY-MM-DD
    '%m/%d/%Y',  # MM/DD/YYYY
    '%d-%m-%Y',  # DD-MM-YYYY
    '%Y/%m/%d',  # YYYY/MM/DD
    '%d.%m.%Y',  # DD.MM.YYYY
]


def parse_date(date_string):
    """Try to parse a date string using multiple formats."""
    date_string = date_string.strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(date_string, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Could not parse date: {date_string}")


def parse_amount(amount_string):
    """Parse amount string, handling different formats."""
    amount_string = amount_string.strip()
    # Remove currency symbols and spaces
    amount_string = re.sub(r'[€$£\s]', '', amount_string)
    # Handle European format (comma as decimal separator)
    if ',' in amount_string and '.' in amount_string:
        # Format like 1.234,56 -> 1234.56
        amount_string = amount_string.replace('.', '').replace(',', '.')
    elif ',' in amount_string:
        # Could be 1234,56 or 1,234.56 - check position
        parts = amount_string.split(',')
        if len(parts) == 2 and len(parts[1]) == 2:
            # Likely decimal comma: 1234,56
            amount_string = amount_string.replace(',', '.')
        else:
            # Likely thousands separator: 1,234
            amount_string = amount_string.replace(',', '')
    return float(amount_string)


def detect_csv_columns(headers):
    """Detect which columns contain date, description, and amount."""
    headers_lower = [h.lower().strip() for h in headers]

    date_col = None
    desc_col = None
    amount_col = None

    # Date column detection
    date_keywords = ['date', 'fecha', 'datum', 'data']
    for i, h in enumerate(headers_lower):
        if any(kw in h for kw in date_keywords):
            date_col = i
            break

    # Description column detection
    desc_keywords = ['description', 'desc', 'concept', 'concepto', 'details', 'memo', 'text']
    for i, h in enumerate(headers_lower):
        if any(kw in h for kw in desc_keywords):
            desc_col = i
            break

    # Amount column detection
    amount_keywords = ['amount', 'importe', 'monto', 'value', 'sum', 'total']
    for i, h in enumerate(headers_lower):
        if any(kw in h for kw in amount_keywords):
            amount_col = i
            break

    return date_col, desc_col, amount_col


def parse_csv(file_content, filename='upload.csv'):
    """
    Parse CSV content and return list of transaction dictionaries.

    Returns:
        tuple: (transactions_list, errors_list)
    """
    transactions = []
    errors = []

    try:
        # Decode if bytes
        if isinstance(file_content, bytes):
            file_content = file_content.decode('utf-8-sig')  # Handle BOM

        # Read CSV
        reader = csv.reader(io.StringIO(file_content))
        rows = list(reader)

        if len(rows) < 2:
            return [], ["CSV file is empty or has no data rows"]

        headers = rows[0]
        date_col, desc_col, amount_col = detect_csv_columns(headers)

        # Fallback to positional if detection fails
        if date_col is None:
            date_col = 0
        if desc_col is None:
            desc_col = 1
        if amount_col is None:
            amount_col = 2

        # Parse data rows
        for row_num, row in enumerate(rows[1:], start=2):
            if len(row) < 3:
                errors.append(f"Row {row_num}: Not enough columns")
                continue

            try:
                date = parse_date(row[date_col])
                description = row[desc_col].strip()
                amount = parse_amount(row[amount_col])

                if not description:
                    errors.append(f"Row {row_num}: Empty description")
                    continue

                transactions.append({
                    'date': date,
                    'description': description,
                    'amount': amount
                })
            except ValueError as e:
                errors.append(f"Row {row_num}: {str(e)}")
            except IndexError:
                errors.append(f"Row {row_num}: Missing columns")

    except Exception as e:
        errors.append(f"Failed to parse CSV: {str(e)}")

    return transactions, errors


def sanitize_csv_field(value):
    """Prevent CSV injection by escaping potentially dangerous characters."""
    if isinstance(value, str):
        # Fields starting with =, +, -, @ could be formula injection
        if value and value[0] in ('=', '+', '-', '@'):
            return "'" + value
    return value
