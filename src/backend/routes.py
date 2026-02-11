import os
from flask import render_template, request, jsonify, redirect, url_for, flash, session, current_app
from models import db, Transaction, Category, ImportHistory
from utils import parse_csv
from config import load_config, save_config, get_database_path


MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB


def register_routes(app):

    @app.route('/')
    def index():
        total_transactions = Transaction.query.count()
        uncategorized = Transaction.query.filter_by(category_id=None).count()
        return render_template('index.html',
                               total_transactions=total_transactions,
                               uncategorized=uncategorized)

    # ==================== CSV IMPORT ====================

    @app.route('/import', methods=['GET'])
    def import_page():
        return render_template('import.html')

    @app.route('/import/preview', methods=['POST'])
    def import_preview():
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400

        if not file.filename.endswith('.csv'):
            return jsonify({'error': 'File must be a CSV'}), 400

        # Check file size
        file.seek(0, 2)  # Seek to end
        size = file.tell()
        file.seek(0)  # Seek back to start

        if size > MAX_FILE_SIZE:
            return jsonify({'error': 'File too large. Maximum size is 5MB'}), 400

        content = file.read()
        transactions, errors = parse_csv(content, file.filename)

        # Check for duplicates
        duplicates = []
        new_transactions = []

        for t in transactions:
            existing = Transaction.query.filter_by(
                date=t['date'],
                description=t['description'],
                amount=t['amount']
            ).first()

            t_dict = {
                'date': t['date'].isoformat(),
                'description': t['description'],
                'amount': t['amount']
            }

            if existing:
                t_dict['duplicate'] = True
                duplicates.append(t_dict)
            else:
                t_dict['duplicate'] = False
                new_transactions.append(t_dict)

        # Store in session for confirmation
        session['pending_import'] = new_transactions
        session['import_filename'] = file.filename

        return jsonify({
            'transactions': new_transactions,
            'duplicates': duplicates,
            'errors': errors,
            'total': len(transactions),
            'new_count': len(new_transactions),
            'duplicate_count': len(duplicates)
        })

    @app.route('/import/confirm', methods=['POST'])
    def import_confirm():
        pending = session.get('pending_import', [])
        filename = session.get('import_filename', 'unknown.csv')

        if not pending:
            return jsonify({'error': 'No pending import found'}), 400

        # Create import history record
        import_record = ImportHistory(
            filename=filename,
            records_imported=len(pending)
        )
        db.session.add(import_record)
        db.session.flush()  # Get the ID

        # Import transactions
        imported_count = 0
        for t in pending:
            from datetime import datetime
            transaction = Transaction(
                date=datetime.fromisoformat(t['date']).date(),
                description=t['description'],
                amount=t['amount'],
                import_batch_id=import_record.id
            )
            db.session.add(transaction)
            imported_count += 1

        db.session.commit()

        # Clear session
        session.pop('pending_import', None)
        session.pop('import_filename', None)

        return jsonify({
            'success': True,
            'imported': imported_count,
            'batch_id': import_record.id
        })

    # ==================== TRANSACTIONS ====================

    @app.route('/transactions')
    def transactions():
        filter_type = request.args.get('filter', 'all')

        query = Transaction.query.order_by(Transaction.date.desc())

        if filter_type == 'uncategorized':
            query = query.filter_by(category_id=None)
        elif filter_type == 'categorized':
            query = query.filter(Transaction.category_id.isnot(None))

        all_transactions = query.all()
        categories = Category.query.order_by(Category.name).all()

        return render_template('transactions.html',
                               transactions=all_transactions,
                               categories=categories,
                               current_filter=filter_type)

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

    @app.route('/api/categories')
    def api_categories():
        categories = Category.query.order_by(Category.name).all()
        return jsonify([c.to_dict() for c in categories])

    # ==================== SETTINGS ====================

    @app.route('/settings')
    def settings():
        config = load_config()
        db_path = get_database_path()
        db_exists = os.path.exists(db_path)
        db_size = os.path.getsize(db_path) if db_exists else 0

        return render_template('settings.html',
                               config=config,
                               db_path=db_path,
                               db_exists=db_exists,
                               db_size=db_size)

    @app.route('/settings/database', methods=['POST'])
    def update_database_path():
        data = request.get_json()
        new_path = data.get('database_path', '').strip()

        if not new_path:
            return jsonify({'error': 'Database path is required'}), 400

        # Ensure path ends with .db
        if not new_path.endswith('.db'):
            new_path += '.db'

        # Check if parent directory exists or can be created
        parent_dir = os.path.dirname(new_path)
        if parent_dir and not os.path.exists(parent_dir):
            try:
                os.makedirs(parent_dir, exist_ok=True)
            except OSError as e:
                return jsonify({'error': f'Cannot create directory: {str(e)}'}), 400

        # Save the new config
        config = load_config()
        config['database_path'] = new_path
        save_config(config)

        return jsonify({
            'success': True,
            'message': 'Database path updated. Please restart the application for changes to take effect.',
            'new_path': new_path
        })

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
