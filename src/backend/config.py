import json
import os

CONFIG_FILE = os.path.join(os.path.dirname(__file__), '..', 'config.json')

DEFAULT_CONFIG = {
    'database_path': os.path.join(os.path.dirname(__file__), '..', 'database', 'finance.db'),
    'app_name': 'Personal Finance Tracker'
}


def load_config():
    """Load configuration from config.json file."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                # Merge with defaults for any missing keys
                return {**DEFAULT_CONFIG, **config}
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_CONFIG.copy()


def save_config(config):
    """Save configuration to config.json file."""
    # Ensure directory exists
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)

    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f, indent=2)


def get_database_path():
    """Get the configured database path."""
    config = load_config()
    db_path = config.get('database_path', DEFAULT_CONFIG['database_path'])

    # Convert to absolute path if relative
    if not os.path.isabs(db_path):
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', db_path))

    return db_path


def set_database_path(new_path):
    """Set a new database path."""
    config = load_config()

    # Validate the path
    parent_dir = os.path.dirname(new_path)
    if parent_dir and not os.path.exists(parent_dir):
        os.makedirs(parent_dir, exist_ok=True)

    config['database_path'] = new_path
    save_config(config)

    return new_path


def get_database_uri():
    """Get the SQLAlchemy database URI."""
    db_path = get_database_path()
    return f'sqlite:///{db_path}'
