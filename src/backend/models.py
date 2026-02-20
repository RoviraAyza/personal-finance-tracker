from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Category(db.Model):
    __tablename__ = 'categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    color = db.Column(db.String(7), default='#6c757d')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    transactions = db.relationship('Transaction', backref='category', lazy=True)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'color': self.color
        }


class ImportHistory(db.Model):
    __tablename__ = 'import_history'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255))
    records_imported = db.Column(db.Integer, default=0)
    import_date = db.Column(db.DateTime, default=datetime.utcnow)

    transactions = db.relationship('Transaction', backref='import_batch', lazy=True)


class Transaction(db.Model):
    __tablename__ = 'transactions'

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    description = db.Column(db.String(200), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    value_date = db.Column(db.Date, nullable=True)
    extra_details = db.Column(db.String(300), nullable=True)
    balance = db.Column(db.Float, nullable=True)
    account_number = db.Column(db.String(34), nullable=True)
    office = db.Column(db.String(20), nullable=True)
    currency = db.Column(db.String(10), nullable=True)
    common_concept = db.Column(db.String(50), nullable=True)
    bank_concept = db.Column(db.String(50), nullable=True)
    reference_1 = db.Column(db.String(100), nullable=True)
    reference_2 = db.Column(db.String(100), nullable=True)
    compl_1 = db.Column(db.String(200), nullable=True)
    compl_2 = db.Column(db.String(200), nullable=True)
    compl_3 = db.Column(db.String(200), nullable=True)
    compl_4 = db.Column(db.String(200), nullable=True)
    compl_5 = db.Column(db.String(200), nullable=True)
    compl_6 = db.Column(db.String(200), nullable=True)
    compl_7 = db.Column(db.String(200), nullable=True)
    compl_8 = db.Column(db.String(200), nullable=True)
    compl_9 = db.Column(db.String(200), nullable=True)
    compl_10 = db.Column(db.String(200), nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    import_batch_id = db.Column(db.Integer, db.ForeignKey('import_history.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'date': self.date.isoformat(),
            'description': self.description,
            'amount': self.amount,
            'value_date': self.value_date.isoformat() if self.value_date else None,
            'extra_details': self.extra_details,
            'balance': self.balance,
            'account_number': self.account_number,
            'office': self.office,
            'currency': self.currency,
            'common_concept': self.common_concept,
            'bank_concept': self.bank_concept,
            'reference_1': self.reference_1,
            'reference_2': self.reference_2,
            'compl_1': self.compl_1,
            'compl_2': self.compl_2,
            'compl_3': self.compl_3,
            'compl_4': self.compl_4,
            'compl_5': self.compl_5,
            'compl_6': self.compl_6,
            'compl_7': self.compl_7,
            'compl_8': self.compl_8,
            'compl_9': self.compl_9,
            'compl_10': self.compl_10,
            'category_id': self.category_id,
            'category_name': self.category.name if self.category else None,
            'category_color': self.category.color if self.category else None
        }
