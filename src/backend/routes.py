import os
from flask import render_template, request, jsonify, redirect, url_for, flash, session, current_app
from models import db, Transaction, Category, ImportHistory
from utils import parse_csv, parse_xls
import glob
from config import load_config, save_config, get_database_path, get_csv_source_folder


MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def get_category_for_description(description):
    """Find category based on matching description from existing categorized transactions."""
    existing = Transaction.query.filter(
        Transaction.description == description,
        Transaction.category_id.isnot(None)
    ).first()
    return existing.category_id if existing else None


def register_routes(app):

    @app.route('/')
    def index():
        return redirect(url_for('transactions'))

    # ==================== SYNC FROM FOLDER ====================

    @app.route('/sync', methods=['POST'])
    def sync_from_folder():
        """Sync transactions from all CSV files in configured folder."""
        from datetime import datetime

        csv_folder = get_csv_source_folder()

        if not csv_folder:
            return jsonify({'error': 'No CSV folder configured. Go to Settings to set it up.'}), 400

        if not os.path.isdir(csv_folder):
            return jsonify({'error': f'Folder not found: {csv_folder}'}), 404

        # Find all CSV and XLS files in folder
        csv_files = glob.glob(os.path.join(csv_folder, '*.csv'))
        xls_files = glob.glob(os.path.join(csv_folder, '*.xls')) + glob.glob(os.path.join(csv_folder, '*.XLS'))
        # Deduplicate XLS (case-insensitive match on Windows)
        seen_xls = set()
        unique_xls = []
        for f in xls_files:
            norm = os.path.normcase(f)
            if norm not in seen_xls:
                seen_xls.add(norm)
                unique_xls.append(f)
        all_files = csv_files + unique_xls

        if not all_files:
            return jsonify({'error': 'No CSV/XLS files found in the configured folder.'}), 400

        total_new = 0
        total_duplicates = 0
        files_processed = 0
        all_errors = []

        for file_path in all_files:
            # Check file size
            file_size = os.path.getsize(file_path)
            if file_size > MAX_FILE_SIZE:
                all_errors.append(f'{os.path.basename(file_path)}: File too large (max 5MB)')
                continue

            ext = os.path.splitext(file_path)[1].lower()

            if ext == '.xls':
                transactions, errors = parse_xls(file_path, os.path.basename(file_path))
            else:
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                except IOError:
                    all_errors.append(f'{os.path.basename(file_path)}: Cannot read file')
                    continue
                transactions, errors = parse_csv(content, os.path.basename(file_path))

            if errors:
                all_errors.extend([f'{os.path.basename(file_path)}: {e}' for e in errors[:3]])

            if not transactions:
                continue

            # Filter out duplicates
            new_transactions = []

            for t in transactions:
                dup_filter = {
                    'date': t['date'],
                    'description': t['description'],
                    'amount': t['amount'],
                }
                if t.get('account_number'):
                    dup_filter['account_number'] = t['account_number']
                if t.get('balance') is not None:
                    dup_filter['balance'] = t['balance']

                existing = Transaction.query.filter_by(**dup_filter).first()

                if existing:
                    total_duplicates += 1
                else:
                    new_transactions.append(t)

            if new_transactions:
                # Create import history record for this file
                import_record = ImportHistory(
                    filename=os.path.basename(file_path),
                    records_imported=len(new_transactions)
                )
                db.session.add(import_record)
                db.session.flush()

                # Import new transactions with auto-categorization
                for t in new_transactions:
                    # Try to find category from existing transaction with same description
                    category_id = get_category_for_description(t['description'])

                    transaction = Transaction(
                        date=t['date'],
                        description=t['description'],
                        amount=t['amount'],
                        value_date=t.get('value_date'),
                        extra_details=t.get('extra_details'),
                        balance=t.get('balance'),
                        account_number=t.get('account_number'),
                        office=t.get('office'),
                        currency=t.get('currency'),
                        common_concept=t.get('common_concept'),
                        bank_concept=t.get('bank_concept'),
                        reference_1=t.get('reference_1'),
                        reference_2=t.get('reference_2'),
                        compl_1=t.get('compl_1'),
                        compl_2=t.get('compl_2'),
                        compl_3=t.get('compl_3'),
                        compl_4=t.get('compl_4'),
                        compl_5=t.get('compl_5'),
                        compl_6=t.get('compl_6'),
                        compl_7=t.get('compl_7'),
                        compl_8=t.get('compl_8'),
                        compl_9=t.get('compl_9'),
                        compl_10=t.get('compl_10'),
                        category_id=category_id,
                        import_batch_id=import_record.id
                    )
                    db.session.add(transaction)

                total_new += len(new_transactions)

            files_processed += 1

        db.session.commit()

        # Count how many were auto-categorized
        auto_categorized = Transaction.query.filter(
            Transaction.import_batch_id == import_record.id if 'import_record' in dir() else False,
            Transaction.category_id.isnot(None)
        ).count() if total_new > 0 else 0

        if total_new == 0:
            return jsonify({
                'success': True,
                'imported': 0,
                'auto_categorized': 0,
                'duplicates': total_duplicates,
                'files_processed': files_processed,
                'message': f'No new transactions found in {files_processed} files. All transactions already exist.',
                'errors': all_errors[:5] if all_errors else []
            })

        return jsonify({
            'success': True,
            'imported': total_new,
            'auto_categorized': auto_categorized,
            'duplicates': total_duplicates,
            'files_processed': files_processed,
            'message': f'Imported {total_new} new transactions from {files_processed} files.',
            'errors': all_errors[:5] if all_errors else []
        })

    # ==================== AUTO-CATEGORIZE ====================

    @app.route('/transactions/auto-categorize', methods=['POST'])
    def auto_categorize():
        """Auto-categorize uncategorized transactions based on matching descriptions."""
        uncategorized = Transaction.query.filter_by(category_id=None).all()

        categorized_count = 0
        for transaction in uncategorized:
            category_id = get_category_for_description(transaction.description)
            if category_id:
                transaction.category_id = category_id
                categorized_count += 1

        db.session.commit()

        return jsonify({
            'success': True,
            'categorized': categorized_count,
            'remaining': len(uncategorized) - categorized_count,
            'message': f'Auto-categorized {categorized_count} transactions.'
        })

    # ==================== TRANSACTIONS ====================

    @app.route('/transactions')
    def transactions():
        from datetime import datetime

        # Get filter parameters
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        description = request.args.get('description', '').strip()
        amount_min = request.args.get('amount_min', '').strip()
        amount_max = request.args.get('amount_max', '').strip()
        category_ids = request.args.getlist('category')
        account = request.args.get('account', '').strip()

        query = Transaction.query.order_by(Transaction.date.desc())

        # Apply date range filter
        if date_from:
            try:
                from_date = datetime.strptime(date_from, '%Y-%m-%d').date()
                query = query.filter(Transaction.date >= from_date)
            except ValueError:
                pass

        if date_to:
            try:
                to_date = datetime.strptime(date_to, '%Y-%m-%d').date()
                query = query.filter(Transaction.date <= to_date)
            except ValueError:
                pass

        # Apply description search (case-insensitive partial match)
        if description:
            query = query.filter(Transaction.description.ilike(f'%{description}%'))

        # Apply amount range filter
        if amount_min:
            try:
                min_val = float(amount_min)
                query = query.filter(Transaction.amount >= min_val)
            except ValueError:
                pass

        if amount_max:
            try:
                max_val = float(amount_max)
                query = query.filter(Transaction.amount <= max_val)
            except ValueError:
                pass

        # Apply account filter
        if account:
            query = query.filter(Transaction.account_number == account)

        # Apply category filter (multiple selection)
        if category_ids:
            try:
                cat_ids = [int(cid) for cid in category_ids if cid]
                if cat_ids:
                    query = query.filter(Transaction.category_id.in_(cat_ids))
            except ValueError:
                pass

        all_transactions = query.all()
        categories = Category.query.order_by(Category.name).all()

        # Build active filters dict for template
        active_filters = {}
        if date_from:
            active_filters['date_from'] = date_from
        if date_to:
            active_filters['date_to'] = date_to
        if description:
            active_filters['description'] = description
        if amount_min:
            active_filters['amount_min'] = amount_min
        if amount_max:
            active_filters['amount_max'] = amount_max
        if category_ids:
            active_filters['categories'] = category_ids
        if account:
            active_filters['account'] = account

        # Get distinct account numbers for filter dropdown
        account_numbers = [row[0] for row in
                          db.session.query(Transaction.account_number)
                          .filter(Transaction.account_number.isnot(None))
                          .distinct().all()]

        return render_template('transactions.html',
                               transactions=all_transactions,
                               categories=categories,
                               active_filters=active_filters,
                               account_numbers=account_numbers)

    @app.route('/transactions/<int:id>/categorize', methods=['POST'])
    def categorize_transaction(id):
        transaction = Transaction.query.get_or_404(id)
        data = request.get_json()

        category_id = data.get('category_id')
        if category_id:
            transaction.category_id = int(category_id)
        else:
            transaction.category_id = None

        db.session.commit()

        return jsonify({'success': True, 'transaction': transaction.to_dict()})

    @app.route('/transactions/bulk-categorize', methods=['POST'])
    def bulk_categorize():
        data = request.get_json()
        transaction_ids = data.get('transaction_ids', [])
        category_id = data.get('category_id')

        if not transaction_ids:
            return jsonify({'error': 'No transactions selected'}), 400

        updated = 0
        for tid in transaction_ids:
            transaction = Transaction.query.get(tid)
            if transaction:
                transaction.category_id = int(category_id) if category_id else None
                updated += 1

        db.session.commit()

        return jsonify({'success': True, 'updated': updated})

    # ==================== CATEGORIES ====================

    @app.route('/categories')
    def categories():
        all_categories = Category.query.all()
        # Add transaction count to each category
        for cat in all_categories:
            cat.transaction_count = Transaction.query.filter_by(category_id=cat.id).count()
        return render_template('categories.html', categories=all_categories)

    @app.route('/categories/add', methods=['POST'])
    def add_category():
        data = request.get_json()
        name = data.get('name', '').strip()
        color = data.get('color', '#6c757d')

        if not name:
            return jsonify({'error': 'Category name is required'}), 400

        existing = Category.query.filter_by(name=name).first()
        if existing:
            return jsonify({'error': 'Category already exists'}), 400

        category = Category(name=name, color=color)
        db.session.add(category)
        db.session.commit()

        return jsonify({'success': True, 'category': category.to_dict()})

    @app.route('/categories/<int:id>', methods=['PUT'])
    def update_category(id):
        category = Category.query.get_or_404(id)
        data = request.get_json()

        if 'name' in data:
            category.name = data['name'].strip()
        if 'color' in data:
            category.color = data['color']

        db.session.commit()

        return jsonify({'success': True, 'category': category.to_dict()})

    @app.route('/categories/<int:id>', methods=['DELETE'])
    def delete_category(id):
        category = Category.query.get_or_404(id)

        # Check if category has transactions
        transaction_count = Transaction.query.filter_by(category_id=id).count()
        if transaction_count > 0:
            return jsonify({
                'error': f'Cannot delete category with {transaction_count} transactions assigned'
            }), 400

        db.session.delete(category)
        db.session.commit()

        return jsonify({'success': True})

    # ==================== API ====================

    @app.route('/api/transactions/<int:id>')
    def api_transaction_detail(id):
        transaction = Transaction.query.get_or_404(id)
        return jsonify(transaction.to_dict())

    @app.route('/api/categories')
    def api_categories():
        categories = Category.query.order_by(Category.name).all()
        return jsonify([c.to_dict() for c in categories])

    # ==================== SETTINGS ====================

    @app.route('/settings')
    def settings():
        csv_folder = get_csv_source_folder()
        folder_exists = os.path.isdir(csv_folder) if csv_folder else False
        file_count = 0
        if folder_exists:
            csv_files = glob.glob(os.path.join(csv_folder, '*.csv'))
            xls_files = glob.glob(os.path.join(csv_folder, '*.xls')) + glob.glob(os.path.join(csv_folder, '*.XLS'))
            seen = set()
            for f in xls_files:
                seen.add(os.path.normcase(f))
            file_count = len(csv_files) + len(seen)

        return render_template('settings.html',
                               csv_folder=csv_folder,
                               folder_exists=folder_exists,
                               file_count=file_count)

    @app.route('/settings/csv-folder', methods=['POST'])
    def update_csv_folder():
        data = request.get_json()
        new_path = data.get('csv_folder', '').strip()

        # Allow empty path to clear the setting
        if new_path and not os.path.isdir(new_path):
            return jsonify({'error': f'Folder not found: {new_path}'}), 400

        # Save the new config
        config = load_config()
        config['csv_source_folder'] = new_path
        save_config(config)

        # Count data files (CSV + XLS)
        file_count = 0
        if new_path:
            csv_files = glob.glob(os.path.join(new_path, '*.csv'))
            xls_files = glob.glob(os.path.join(new_path, '*.xls')) + glob.glob(os.path.join(new_path, '*.XLS'))
            seen = set()
            for f in xls_files:
                seen.add(os.path.normcase(f))
            file_count = len(csv_files) + len(seen)

        return jsonify({
            'success': True,
            'message': f'Folder updated. Found {file_count} data files (CSV/XLS).' if new_path else 'Folder cleared.',
            'new_path': new_path,
            'file_count': file_count
        })

    @app.route('/settings/browse-folder', methods=['POST'])
    def browse_folder():
        """Open a native OS folder picker dialog and return the selected path."""
        import threading

        result = {'path': None}

        def pick_folder():
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            folder = filedialog.askdirectory(title='Select Bank CSV Folder')
            root.destroy()
            result['path'] = folder

        # tkinter must run on its own thread to avoid blocking Flask
        thread = threading.Thread(target=pick_folder)
        thread.start()
        thread.join(timeout=120)

        if result['path']:
            return jsonify({'success': True, 'path': result['path']})
        else:
            return jsonify({'success': False, 'path': ''})

    @app.route('/api/stats')
    def api_stats():
        """Get database statistics."""
        total_transactions = Transaction.query.count()
        total_categories = Category.query.count()
        total_imports = ImportHistory.query.count()
        categorized = Transaction.query.filter(Transaction.category_id.isnot(None)).count()

        return jsonify({
            'total_transactions': total_transactions,
            'total_categories': total_categories,
            'total_imports': total_imports,
            'categorized': categorized,
            'uncategorized': total_transactions - categorized
        })
