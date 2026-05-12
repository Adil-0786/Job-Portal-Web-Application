import os
from datetime import datetime
from pathlib import Path

from flask import Flask

from .db import ensure_admin, init_app as init_db_app, init_db, seed_sample_data
from .oauth import init_oauth
from .views import bp


def env_flag(name, default):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def create_app(test_config=None):
    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        instance_relative_config=True,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
    )
    data_dir = os.environ.get("DATA_DIR", "")
    if data_dir:
        database_path = os.path.join(data_dir, "talentbridge.sqlite3")
    else:
        database_path = os.path.join(app.instance_path, "talentbridge.sqlite3")
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY", "change-me-in-production"),
        DATABASE=database_path,
        ADMIN_EMAIL=os.environ.get("ADMIN_EMAIL", "admin@talentbridge.local"),
        ADMIN_PASSWORD=os.environ.get("ADMIN_PASSWORD", "Admin123!"),
        GOOGLE_CLIENT_ID=os.environ.get("GOOGLE_CLIENT_ID", ""),
        GOOGLE_CLIENT_SECRET=os.environ.get("GOOGLE_CLIENT_SECRET", ""),
        GOOGLE_DISCOVERY_URL="https://accounts.google.com/.well-known/openid-configuration",
        ALLOW_LOCAL_LOGIN=env_flag("ALLOW_LOCAL_LOGIN", True),
        SEED_SAMPLE_DATA=env_flag("SEED_SAMPLE_DATA", True),
    )

    if test_config is not None:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)

    init_oauth(app)
    init_db_app(app)
    app.register_blueprint(bp)

    @app.template_filter("currency")
    def currency(value):
        return f"${int(value):,}"

    @app.template_filter("pretty_date")
    def pretty_date(value):
        if value is None:
            return ""
        text = str(value).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text).strftime("%b %d")
        except ValueError:
            return str(value)[:10]

    @app.context_processor
    def inject_globals():
        return {
            "current_year": datetime.now().year,
            "google_oauth_enabled": app.config.get("GOOGLE_OAUTH_ENABLED", False),
        }

    with app.app_context():
        init_db()
        ensure_admin()
        if app.config.get("SEED_SAMPLE_DATA", True):
            seed_sample_data()

    return app
