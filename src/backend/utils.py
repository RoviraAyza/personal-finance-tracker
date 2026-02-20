import csv
import io
import re
from datetime import datetime

try:
    import xlrd
except ImportError:
    xlrd = None


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
    # Remove currency symbols, spaces, and quotes
    amount_string = re.sub(r'[€$£\s"\']', '', amount_string)

    # Handle formats with both comma and dot
    if ',' in amount_string and '.' in amount_string:
        # Determine which is the decimal separator by position
        last_comma = amount_string.rfind(',')
        last_dot = amount_string.rfind('.')

        if last_dot > last_comma:
            # Format like 1,234.56 (US) -> comma is thousands
            amount_string = amount_string.replace(',', '')
        else:
            # Format like 1.234,56 (EU) -> dot is thousands, comma is decimal
            amount_string = amount_string.replace('.', '').replace(',', '.')

    elif ',' in amount_string:
        # Only comma - could be decimal or thousands
        parts = amount_string.split(',')
        if len(parts) == 2 and len(parts[1]) == 2:
            # Likely decimal comma: 1234,56
            amount_string = amount_string.replace(',', '.')
        else:
            # Likely thousands separator: 1,234
            amount_string = amount_string.replace(',', '')

    return float(amount_string)


def extract_account_number(rows):
    """Extract IBAN account number from CSV metadata rows (before header)."""
    iban_pattern = re.compile(r'(ES\d{2}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4}\s?\d{4})')
    for row in rows:
        for cell in row:
            match = iban_pattern.search(cell)
            if match:
                # Normalize: remove spaces
                return match.group(1).replace(' ', '')
    return None


def detect_csv_columns(headers):
    """Detect which columns contain date, description, amount, and optional fields."""
    headers_lower = [h.lower().strip() for h in headers]

    date_col = None
    desc_col = None
    amount_col = None
    value_date_col = None
    extra_details_col = None
    balance_col = None

    # Date column detection (first date-like column that is NOT "fecha valor")
    date_keywords = ['date', 'fecha', 'datum', 'data']
    value_date_keywords = ['fecha valor', 'value date', 'valor']
    for i, h in enumerate(headers_lower):
        if any(kw == h or h.startswith(kw) for kw in value_date_keywords):
            value_date_col = i
        elif any(kw == h or h.startswith(kw) for kw in date_keywords):
            if date_col is None:
                date_col = i

    # Description column detection
    desc_keywords = ['description', 'desc', 'concept', 'concepto', 'details', 'memo', 'text', 'movimiento']
    for i, h in enumerate(headers_lower):
        if any(kw in h for kw in desc_keywords):
            desc_col = i
            break

    # Extra details column detection
    extra_keywords = ['m\u00e1s datos', 'mas datos', 'extra', 'additional', 'más datos']
    for i, h in enumerate(headers_lower):
        if any(kw in h for kw in extra_keywords):
            extra_details_col = i
            break

    # Amount column detection
    amount_keywords = ['amount', 'importe', 'monto', 'value', 'sum', 'total']
    for i, h in enumerate(headers_lower):
        if any(kw in h for kw in amount_keywords):
            amount_col = i
            break

    # Balance column detection
    balance_keywords = ['balance', 'saldo', 'disponible']
    for i, h in enumerate(headers_lower):
        if any(kw in h for kw in balance_keywords):
            balance_col = i
            break

    return date_col, desc_col, amount_col, value_date_col, extra_details_col, balance_col


def find_header_row(rows):
    """Find the row that contains the actual column headers."""
    date_keywords = ['date', 'fecha', 'datum', 'data']

    for i, row in enumerate(rows):
        if len(row) >= 3:
            first_cell = row[0].lower().strip()
            if any(kw == first_cell or first_cell.startswith(kw) for kw in date_keywords):
                return i

    return 0  # Default to first row


def parse_csv(file_content, filename='upload.csv'):
    """
    Parse CSV content and return list of transaction dictionaries.

    Returns:
        tuple: (transactions_list, errors_list)
    """
    transactions = []
    errors = []

    try:
        # Decode if bytes - try multiple encodings
        if isinstance(file_content, bytes):
            for encoding in ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']:
                try:
                    file_content = file_content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue

        # Read CSV
        reader = csv.reader(io.StringIO(file_content))
        rows = list(reader)

        if len(rows) < 2:
            return [], ["CSV file is empty or has no data rows"]

        # Find the actual header row (skip bank info rows)
        header_idx = find_header_row(rows)
        headers = rows[header_idx]

        # Extract account number from metadata rows before header
        account_number = extract_account_number(rows[:header_idx])

        date_col, desc_col, amount_col, value_date_col, extra_details_col, balance_col = detect_csv_columns(headers)

        # Fallback to positional if detection fails
        if date_col is None:
            date_col = 0
        if desc_col is None:
            desc_col = 1
        if amount_col is None:
            amount_col = 2

        # Parse data rows (start after header row)
        data_rows = rows[header_idx + 1:]
        for row_num, row in enumerate(data_rows, start=header_idx + 2):
            if len(row) < 3:
                continue  # Skip short rows silently

            # Skip empty rows
            if not any(cell.strip() for cell in row):
                continue

            try:
                date_str = row[date_col].strip()
                if not date_str:
                    continue  # Skip rows without date

                date = parse_date(date_str)
                description = row[desc_col].strip()
                amount = parse_amount(row[amount_col])

                if not description:
                    errors.append(f"Row {row_num}: Empty description")
                    continue

                txn = {
                    'date': date,
                    'description': description,
                    'amount': amount,
                    'account_number': account_number,
                }

                # Optional fields
                if value_date_col is not None and value_date_col < len(row) and row[value_date_col].strip():
                    try:
                        txn['value_date'] = parse_date(row[value_date_col])
                    except ValueError:
                        txn['value_date'] = None
                else:
                    txn['value_date'] = None

                if extra_details_col is not None and extra_details_col < len(row):
                    txn['extra_details'] = row[extra_details_col].strip() or None
                else:
                    txn['extra_details'] = None

                if balance_col is not None and balance_col < len(row) and row[balance_col].strip():
                    try:
                        txn['balance'] = parse_amount(row[balance_col])
                    except ValueError:
                        txn['balance'] = None
                else:
                    txn['balance'] = None

                transactions.append(txn)
            except ValueError as e:
                errors.append(f"Row {row_num}: {str(e)}")
            except IndexError:
                errors.append(f"Row {row_num}: Missing columns")

    except Exception as e:
        errors.append(f"Failed to parse CSV: {str(e)}")

    return transactions, errors


def _safe_str(value):
    """Convert an XLS cell value to a clean string, handling floats that are really ints."""
    if value is None or value == '':
        return None
    if isinstance(value, float):
        # Concept codes like 12.0 should become "12"
        if value == int(value):
            return str(int(value))
        return str(value)
    return str(value).strip() or None


def _safe_float(value):
    """Convert an XLS cell to float, returning 0.0 for empty/missing."""
    if value is None or value == '':
        return 0.0
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def parse_xls(file_path, filename='upload.xls'):
    """
    Parse a CaixaBank XLS file and return list of transaction dictionaries.

    CaixaBank XLS layout (header at row 3, data from row 4):
      Col 1: Número de cuenta  Col 2: Oficina  Col 3: Divisa
      Col 4: F. Operación      Col 5: F. Valor
      Col 6: Ingreso (+)       Col 7: Gasto (-)
      Col 8: Saldo (+)         Col 9: Saldo (-)
      Col 10: Concepto común   Col 11: Concepto propio
      Col 12: Referencia 1     Col 13: Referencia 2
      Col 14-23: Concepto complementario 1-10

    Returns:
        tuple: (transactions_list, errors_list)
    """
    if xlrd is None:
        return [], ["xlrd library not installed. Run: pip install xlrd"]

    transactions = []
    errors = []

    try:
        workbook = xlrd.open_workbook(file_path)
        sheet = workbook.sheet_by_index(0)

        if sheet.nrows < 5:
            return [], ["XLS file has too few rows"]

        # Data starts at row 4 (0-indexed)
        for row_idx in range(4, sheet.nrows):
            try:
                row = [sheet.cell_value(row_idx, c) for c in range(sheet.ncols)]

                # Skip empty rows
                if not any(str(v).strip() for v in row):
                    continue

                # Pad row to at least 24 columns
                while len(row) < 24:
                    row.append('')

                # Parse dates (col 4 = F. Operación, col 5 = F. Valor)
                op_date = None
                raw_date = row[4]
                if isinstance(raw_date, float) and raw_date > 0:
                    try:
                        op_date = xlrd.xldate_as_datetime(raw_date, workbook.datemode).date()
                    except (ValueError, OverflowError):
                        pass
                if op_date is None and raw_date:
                    try:
                        op_date = parse_date(str(raw_date).strip())
                    except ValueError:
                        pass

                if op_date is None:
                    continue  # Skip rows without a valid operation date

                value_date = None
                raw_vdate = row[5]
                if isinstance(raw_vdate, float) and raw_vdate > 0:
                    try:
                        value_date = xlrd.xldate_as_datetime(raw_vdate, workbook.datemode).date()
                    except (ValueError, OverflowError):
                        pass
                if value_date is None and raw_vdate:
                    try:
                        value_date = parse_date(str(raw_vdate).strip())
                    except ValueError:
                        pass

                # Amount = Ingreso(+) - Gasto(-)
                income = _safe_float(row[6])
                expense = _safe_float(row[7])
                amount = income - expense

                # Balance = Saldo(+) - Saldo(-)
                bal_pos = _safe_float(row[8])
                bal_neg = _safe_float(row[9])
                balance = bal_pos - bal_neg if (bal_pos or bal_neg) else None

                # Account and office
                account_number = _safe_str(row[1])
                office = _safe_str(row[2])
                currency = _safe_str(row[3])

                # Concepts and references
                common_concept = _safe_str(row[10])
                bank_concept = _safe_str(row[11])
                reference_1 = _safe_str(row[12])
                reference_2 = _safe_str(row[13])

                # Complementary details (cols 14-23)
                compl = [_safe_str(row[14 + i]) for i in range(10)]

                # Description = compl_1 (merchant name) with fallback to compl_9
                description = compl[0] or compl[8] or common_concept or 'Sin descripción'

                # Extra details = concatenation of compl_3, compl_5, compl_7
                extra_parts = [p for p in [compl[2], compl[4], compl[6]] if p]
                extra_details = ' | '.join(extra_parts) if extra_parts else None

                txn = {
                    'date': op_date,
                    'description': description,
                    'amount': amount,
                    'value_date': value_date,
                    'extra_details': extra_details,
                    'balance': balance,
                    'account_number': account_number,
                    'office': office,
                    'currency': currency,
                    'common_concept': common_concept,
                    'bank_concept': bank_concept,
                    'reference_1': reference_1,
                    'reference_2': reference_2,
                    'compl_1': compl[0],
                    'compl_2': compl[1],
                    'compl_3': compl[2],
                    'compl_4': compl[3],
                    'compl_5': compl[4],
                    'compl_6': compl[5],
                    'compl_7': compl[6],
                    'compl_8': compl[7],
                    'compl_9': compl[8],
                    'compl_10': compl[9],
                }

                transactions.append(txn)

            except Exception as e:
                errors.append(f"Row {row_idx + 1}: {str(e)}")

    except Exception as e:
        errors.append(f"Failed to parse XLS: {str(e)}")

    return transactions, errors


def sanitize_csv_field(value):
    """Prevent CSV injection by escaping potentially dangerous characters."""
    if isinstance(value, str):
        # Fields starting with =, +, -, @ could be formula injection
        if value and value[0] in ('=', '+', '-', '@'):
            return "'" + value
    return value
