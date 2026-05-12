from pathlib import Path
import sqlite3

from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_error=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def ensure_column(db, table, name, definition):
    columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()}
    if name not in columns:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def init_db():
    db = get_db()
    schema_path = Path(__file__).with_name("schema.sql")
    db.executescript(schema_path.read_text(encoding="utf-8"))
    ensure_column(db, "users", "auth_provider", "TEXT NOT NULL DEFAULT 'local'")
    ensure_column(db, "users", "google_sub", "TEXT")
    ensure_column(db, "users", "avatar_url", "TEXT")
    ensure_column(db, "users", "email_verified", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(
        db,
        "jobs",
        "job_type",
        "TEXT NOT NULL DEFAULT 'full_time' CHECK (job_type IN ('full_time', 'part_time', 'contract', 'internship'))",
    )
    ensure_column(
        db,
        "applications",
        "status",
        "TEXT NOT NULL DEFAULT 'submitted' CHECK (status IN ('submitted', 'reviewing', 'shortlisted', 'rejected', 'hired'))",
    )
    db.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub) "
        "WHERE google_sub IS NOT NULL AND google_sub != ''"
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_jobs_job_type ON jobs(job_type)")
    db.execute("CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status)")
    db.execute("UPDATE users SET auth_provider = 'local' WHERE auth_provider IS NULL OR auth_provider = ''")
    db.execute("UPDATE users SET email_verified = 1 WHERE role = 'admin' AND (email_verified IS NULL OR email_verified = 0)")
    db.commit()


def ensure_admin():
    db = get_db()
    existing = db.execute(
        "SELECT id FROM users WHERE email = ?",
        (current_app.config["ADMIN_EMAIL"],),
    ).fetchone()
    if existing is not None:
        return

    db.execute(
        """
        INSERT INTO users (
            name, email, password_hash, role, company, auth_provider, email_verified
        )
        VALUES (?, ?, ?, 'admin', ?, 'local', 1)
        """,
        (
            "Platform Admin",
            current_app.config["ADMIN_EMAIL"],
            generate_password_hash(current_app.config["ADMIN_PASSWORD"]),
            "TalentBridge",
        ),
    )
    db.commit()


def seed_sample_data():
    db = get_db()
    has_jobs = db.execute("SELECT 1 FROM jobs LIMIT 1").fetchone()
    if has_jobs is not None:
        return

    sample_users = [
        {
            "name": "Ava Chen",
            "email": "employer@talentbridge.local",
            "password": "Employer123!",
            "role": "employer",
            "company": "Northwind Labs",
            "auth_provider": "local",
        },
        {
            "name": "Marcus Reid",
            "email": "hiring@talentbridge.local",
            "password": "Hiring123!",
            "role": "employer",
            "company": "BluePeak Commerce",
            "auth_provider": "local",
        },
        {
            "name": "Jordan Lee",
            "email": "seeker@talentbridge.local",
            "password": "Seeker123!",
            "role": "seeker",
            "company": None,
            "auth_provider": "local",
        },
    ]

    user_ids = {}
    for user in sample_users:
        existing = db.execute(
            "SELECT id FROM users WHERE email = ?",
            (user["email"],),
        ).fetchone()
        if existing is None:
            cursor = db.execute(
                """
                INSERT INTO users (
                    name, email, password_hash, role, company, auth_provider, email_verified
                )
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    user["name"],
                    user["email"],
                    generate_password_hash(user["password"]),
                    user["role"],
                    user["company"],
                    user["auth_provider"],
                ),
            )
            user_ids[user["email"]] = cursor.lastrowid
        else:
            user_ids[user["email"]] = existing["id"]

    jobs = [
        (
            user_ids["employer@talentbridge.local"],
            "Senior Backend Engineer",
            "Build and scale customer-facing APIs, improve system reliability, and mentor a small platform team.",
            150000,
            "New York, NY",
            "Engineering",
            "Northwind Labs",
            "full_time",
            "open",
        ),
        (
            user_ids["employer@talentbridge.local"],
            "Product Designer",
            "Own end-to-end UX for employer tooling, prototype new workflows, and partner closely with engineering.",
            110000,
            "Austin, TX",
            "Design",
            "Northwind Labs",
            "full_time",
            "open",
        ),
        (
            user_ids["hiring@talentbridge.local"],
            "Growth Marketing Manager",
            "Lead lifecycle and acquisition campaigns across paid, CRM, and partner channels with clear reporting.",
            95000,
            "Remote",
            "Marketing",
            "BluePeak Commerce",
            "full_time",
            "open",
        ),
        (
            user_ids["hiring@talentbridge.local"],
            "Operations Analyst",
            "Support inventory planning, vendor reporting, and process improvement across the retail operations team.",
            82000,
            "Chicago, IL",
            "Operations",
            "BluePeak Commerce",
            "contract",
            "open",
        ),
    ]

    db.executemany(
        """
        INSERT INTO jobs (
            employer_id, title, description, salary, location, category, company, job_type, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        jobs,
    )

    first_job = db.execute("SELECT id FROM jobs ORDER BY id LIMIT 1").fetchone()
    seeker = user_ids["seeker@talentbridge.local"]
    if first_job is not None:
        db.execute(
            """
            INSERT OR IGNORE INTO applications (job_id, seeker_id, cover_letter, status)
            VALUES (?, ?, ?, 'submitted')
            """,
            (
                first_job["id"],
                seeker,
                "I have five years of experience building Flask and FastAPI services and would be ready to contribute quickly.",
            ),
        )

    db.commit()


def init_app(app):
    app.teardown_appcontext(close_db)
