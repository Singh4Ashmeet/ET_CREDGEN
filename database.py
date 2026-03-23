import os
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()

def init_db(app):
    """Initialize the database with the app."""
    database_url = os.environ.get("DATABASE_URL", "")

    if not database_url:
        raise RuntimeError("DATABASE_URL env var is required")

    app.config["SQLALCHEMY_DATABASE_URI"] = database_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    # Pool options only valid for non-SQLite
    if "sqlite" not in database_url.lower():
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_pre_ping": True,
            "pool_recycle": 3600
        }

    db.init_app(app)
    migrate.init_app(app, db)
