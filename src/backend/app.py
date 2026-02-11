import os
from flask import Flask
from dotenv import load_dotenv

load_dotenv()


def create_app():
    app = Flask(
        __name__,
        template_folder='../frontend/templates',
        static_folder='../frontend/static'
    )

    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URI',
        'sqlite:///' + os.path.join(os.path.dirname(__file__), '..', 'database', 'finance.db')
    )
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024  # 5MB max upload

    # Initialize database
    from models import db
    db.init_app(app)

    # Register routes
    from routes import register_routes
    register_routes(app)

    # Create tables and seed default categories
    with app.app_context():
        db.create_all()
        seed_categories()

    return app


def seed_categories():
    """Seed default categories if they don't exist."""
    from models import Category, db

    default_categories = [
        ('Groceries', '#28a745'),
        ('Dining', '#fd7e14'),
        ('Transport', '#007bff'),
        ('Utilities', '#6c757d'),
        ('Entertainment', '#e83e8c'),
        ('Healthcare', '#dc3545'),
        ('Shopping', '#6f42c1'),
        ('Other', '#17a2b8'),
    ]

    for name, color in default_categories:
        existing = Category.query.filter_by(name=name).first()
        if not existing:
            category = Category(name=name, color=color)
            db.session.add(category)

    db.session.commit()


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
