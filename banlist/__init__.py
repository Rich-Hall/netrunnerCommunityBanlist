"""Flask application factory and shared extensions."""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

from config import Config

db = SQLAlchemy()


def create_app(config_class=Config):
    """Create and configure the Flask application.

    Args:
        config_class: Config object or class providing Flask settings.

    Returns:
        A fully initialized Flask app with routes, DB, and CLI commands.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    from banlist import models  # noqa: F401
    from banlist.routes import bp as main_bp

    app.register_blueprint(main_bp)

    @app.cli.command("sync-cards")
    def sync_cards_command():
        """Import/refresh the Standard card pool from NetrunnerDB."""
        from banlist.nrdb import sync_standard_cards

        count = sync_standard_cards()
        print(f"Synced {count} Standard cards.")

    with app.app_context():
        db.create_all()

    return app
