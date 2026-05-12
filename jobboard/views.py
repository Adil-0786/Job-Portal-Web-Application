import secrets
from functools import wraps
from sqlite3 import IntegrityError

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .oauth import oauth

bp = Blueprint("main", __name__)

JOB_TYPES = {
    "full_time": "Full Time",
    "part_time": "Part Time",
    "contract": "Contract",
    "internship": "Internship",
}

APPLICATION_STATUSES = {
    "submitted": "Submitted",
    "reviewing": "Reviewing",
    "shortlisted": "Shortlisted",
    "rejected": "Rejected",
    "hired": "Hired",
}


def build_next_destination():
    destination = request.path
    if request.query_string:
        destination = f"{request.path}?{request.query_string.decode()}"
    return destination


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("main.login", next=build_next_destination()))
        return view(**kwargs)

    return wrapped_view


def roles_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped_view(**kwargs):
            if g.user is None:
                flash("Please sign in to continue.", "warning")
                return redirect(url_for("main.login", next=build_next_destination()))
            if g.user["role"] not in roles:
                abort(403)
            return view(**kwargs)

        return wrapped_view

    return decorator


def dashboard_endpoint(role):
    return {
        "seeker": "main.seeker_dashboard",
        "employer": "main.employer_dashboard",
        "admin": "main.admin_dashboard",
    }[role]


def google_oauth_enabled():
    return current_app.config.get("GOOGLE_OAUTH_ENABLED", False)


def portal_stats():
    db = get_db()
    return {
        "jobs": db.execute("SELECT COUNT(*) AS count FROM jobs WHERE status = 'open'").fetchone()["count"],
        "companies": db.execute("SELECT COUNT(DISTINCT company) AS count FROM jobs").fetchone()["count"],
        "applications": db.execute("SELECT COUNT(*) AS count FROM applications").fetchone()["count"],
    }


def sanitize_job_form(form, default_company=None):
    payload = {
        "title": form.get("title", "").strip(),
        "description": form.get("description", "").strip(),
        "location": form.get("location", "").strip(),
        "category": form.get("category", "").strip(),
        "company": form.get("company", "").strip() or (default_company or "").strip(),
        "job_type": form.get("job_type", "full_time").strip().lower(),
        "status": form.get("status", "open").strip().lower(),
    }

    errors = []
    salary_value = form.get("salary", "").strip()
    try:
        payload["salary"] = int(salary_value)
        if payload["salary"] < 0:
            raise ValueError
    except ValueError:
        errors.append("Salary must be a non-negative whole number.")

    for field in ("title", "description", "location", "category", "company"):
        if not payload[field]:
            errors.append(f"{field.capitalize()} is required.")

    if payload["job_type"] not in JOB_TYPES:
        errors.append("Select a valid job type.")
    if payload["status"] not in {"open", "closed"}:
        errors.append("Status must be open or closed.")

    return payload, errors


def get_job_or_404(job_id):
    job = get_db().execute(
        """
        SELECT jobs.*, users.name AS employer_name, users.email AS employer_email
        FROM jobs
        JOIN users ON users.id = jobs.employer_id
        WHERE jobs.id = ?
        """,
        (job_id,),
    ).fetchone()
    if job is None:
        abort(404)
    return job


def save_login(user_id):
    session.clear()
    session["user_id"] = user_id


def complete_google_user(profile, role, company=None):
    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO users (
            name, email, password_hash, role, company, auth_provider,
            google_sub, avatar_url, email_verified
        )
        VALUES (?, ?, '', ?, ?, 'google', ?, ?, 1)
        """,
        (
            profile["name"],
            profile["email"],
            role,
            company,
            profile["sub"],
            profile.get("picture"),
        ),
    )
    db.commit()
    return cursor.lastrowid


def sync_google_user(user, profile):
    db = get_db()
    db.execute(
        """
        UPDATE users
        SET name = ?, google_sub = ?, avatar_url = ?, email_verified = 1, auth_provider = 'google'
        WHERE id = ?
        """,
        (
            profile["name"],
            profile["sub"],
            profile.get("picture"),
            user["id"],
        ),
    )
    db.commit()


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
        return

    g.user = get_db().execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,),
    ).fetchone()
    if g.user is None:
        session.clear()


@bp.app_context_processor
def inject_view_helpers():
    return {
        "job_type_labels": JOB_TYPES,
        "application_status_labels": APPLICATION_STATUSES,
    }


@bp.route("/")
def home():
    if g.user is not None:
        return redirect(url_for(dashboard_endpoint(g.user["role"])))
    return render_template("login.html", next_url="", stats=portal_stats())


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user is not None:
        return redirect(url_for(dashboard_endpoint(g.user["role"])))

    next_url = request.args.get("next", "").strip()
    if request.method == "POST":
        if not current_app.config.get("ALLOW_LOCAL_LOGIN", True):
            flash("Local login is disabled. Use Google sign-in.", "warning")
            return redirect(url_for("main.login"))

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        next_url = request.form.get("next", "").strip()

        user = get_db().execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ).fetchone()

        if user is None or not user["password_hash"] or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "danger")
        else:
            save_login(user["id"])
            flash("Signed in successfully.", "success")
            return redirect(next_url or url_for(dashboard_endpoint(user["role"])))

    return render_template("login.html", next_url=next_url, stats=portal_stats())


@bp.route("/register", methods=("GET", "POST"))
def register():
    if g.user is not None:
        return redirect(url_for(dashboard_endpoint(g.user["role"])))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "seeker").strip().lower()
        company = request.form.get("company", "").strip() or None

        errors = []
        if not name:
            errors.append("Full name is required.")
        if not email:
            errors.append("Email is required.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if role not in {"seeker", "employer"}:
            errors.append("Select a valid account type.")
        if role == "employer" and not company:
            errors.append("Company is required for employer accounts.")

        db = get_db()
        if not errors:
            try:
                cursor = db.execute(
                    """
                    INSERT INTO users (
                        name, email, password_hash, role, company, auth_provider, email_verified
                    )
                    VALUES (?, ?, ?, ?, ?, 'local', 1)
                    """,
                    (name, email, generate_password_hash(password), role, company),
                )
                db.commit()
            except IntegrityError:
                errors.append("An account with that email already exists.")
            else:
                save_login(cursor.lastrowid)
                flash("Your account is ready.", "success")
                return redirect(url_for(dashboard_endpoint(role)))

        for error in errors:
            flash(error, "danger")

    return render_template("register.html")


@bp.get("/auth/google")
def google_login():
    if g.user is not None:
        return redirect(url_for(dashboard_endpoint(g.user["role"])))
    if not google_oauth_enabled():
        flash("Google sign-in is not configured yet.", "warning")
        return redirect(url_for("main.login"))

    next_url = request.args.get("next", "").strip()
    if next_url:
        session["auth_next"] = next_url
    nonce = secrets.token_urlsafe(24)
    session["google_oauth_nonce"] = nonce
    redirect_uri = url_for("main.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri, nonce=nonce, prompt="select_account")


@bp.get("/auth/google/callback")
def google_callback():
    if not google_oauth_enabled():
        flash("Google sign-in is not configured yet.", "warning")
        return redirect(url_for("main.login"))

    try:
        token = oauth.google.authorize_access_token()
        profile = oauth.google.parse_id_token(token, nonce=session.pop("google_oauth_nonce", None))
    except Exception:
        flash("Google sign-in did not complete. Try again.", "danger")
        return redirect(url_for("main.login"))

    if not profile:
        flash("Google did not return a valid profile.", "danger")
        return redirect(url_for("main.login"))

    email = profile.get("email", "").strip().lower()
    sub = profile.get("sub", "").strip()
    name = profile.get("name", "").strip()
    if not email or not sub or not name or not profile.get("email_verified"):
        flash("Only verified Google accounts can sign in.", "danger")
        return redirect(url_for("main.login"))

    db = get_db()
    user_by_sub = db.execute("SELECT * FROM users WHERE google_sub = ?", (sub,)).fetchone()
    user_by_email = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if user_by_sub is not None and user_by_email is not None and user_by_sub["id"] != user_by_email["id"]:
        flash("This Google account cannot be linked automatically.", "danger")
        return redirect(url_for("main.login"))

    user = user_by_sub or user_by_email
    profile_data = {
        "sub": sub,
        "email": email,
        "name": name,
        "picture": profile.get("picture"),
    }

    if user is None:
        if email == current_app.config["ADMIN_EMAIL"].strip().lower():
            next_url = session.get("auth_next", "")
            user_id = complete_google_user(profile_data, "admin")
            save_login(user_id)
            flash("Signed in successfully.", "success")
            return redirect(next_url or url_for("main.admin_dashboard"))

        session["pending_google_profile"] = profile_data
        return redirect(url_for("main.complete_google_signup"))

    next_url = session.get("auth_next", "")
    sync_google_user(user, profile_data)
    save_login(user["id"])
    flash("Signed in successfully.", "success")
    return redirect(next_url or url_for(dashboard_endpoint(user["role"])))


@bp.route("/auth/google/complete", methods=("GET", "POST"))
def complete_google_signup():
    if g.user is not None:
        return redirect(url_for(dashboard_endpoint(g.user["role"])))

    profile = session.get("pending_google_profile")
    if not profile:
        flash("Start with Google sign-in first.", "warning")
        return redirect(url_for("main.login"))

    if request.method == "POST":
        role = request.form.get("role", "seeker").strip().lower()
        company = request.form.get("company", "").strip() or None
        errors = []
        if role not in {"seeker", "employer"}:
            errors.append("Select a valid account type.")
        if role == "employer" and not company:
            errors.append("Company is required for employer accounts.")

        if not errors:
            try:
                next_url = session.get("auth_next", "")
                user_id = complete_google_user(profile, role, company)
                session.pop("pending_google_profile", None)
                save_login(user_id)
                flash("Your account is ready.", "success")
                return redirect(next_url or url_for(dashboard_endpoint(role)))
            except IntegrityError:
                errors.append("An account with that email already exists.")

        for error in errors:
            flash(error, "danger")

    return render_template("complete_google_signup.html", profile=profile)


@bp.post("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.login"))


@bp.route("/jobs")
def jobs():
    db = get_db()
    filters = {
        "q": request.args.get("q", "").strip(),
        "location": request.args.get("location", "").strip(),
        "category": request.args.get("category", "").strip(),
        "company": request.args.get("company", "").strip(),
        "job_type": request.args.get("job_type", "").strip(),
    }

    clauses = ["jobs.status = 'open'"]
    params = []
    if filters["q"]:
        like = f"%{filters['q']}%"
        clauses.append("(jobs.title LIKE ? OR jobs.description LIKE ? OR jobs.company LIKE ?)")
        params.extend([like, like, like])
    if filters["location"]:
        clauses.append("jobs.location = ?")
        params.append(filters["location"])
    if filters["category"]:
        clauses.append("jobs.category = ?")
        params.append(filters["category"])
    if filters["company"]:
        clauses.append("jobs.company = ?")
        params.append(filters["company"])
    if filters["job_type"] in JOB_TYPES:
        clauses.append("jobs.job_type = ?")
        params.append(filters["job_type"])

    jobs_list = db.execute(
        f"""
        SELECT jobs.*, users.name AS employer_name,
               (SELECT COUNT(*) FROM applications WHERE applications.job_id = jobs.id) AS application_total
        FROM jobs
        JOIN users ON users.id = jobs.employer_id
        WHERE {" AND ".join(clauses)}
        ORDER BY jobs.created_at DESC
        """,
        params,
    ).fetchall()

    filter_options = {
        "locations": db.execute(
            "SELECT DISTINCT location FROM jobs WHERE status = 'open' ORDER BY location"
        ).fetchall(),
        "categories": db.execute(
            "SELECT DISTINCT category FROM jobs WHERE status = 'open' ORDER BY category"
        ).fetchall(),
        "companies": db.execute(
            "SELECT DISTINCT company FROM jobs WHERE status = 'open' ORDER BY company"
        ).fetchall(),
    }
    return render_template(
        "jobs.html",
        jobs=jobs_list,
        filters=filters,
        filter_options=filter_options,
        total_jobs=len(jobs_list),
    )


@bp.route("/jobs/<int:job_id>")
def job_detail(job_id):
    db = get_db()
    job = get_job_or_404(job_id)
    application = None
    if g.user is not None and g.user["role"] == "seeker":
        application = db.execute(
            "SELECT * FROM applications WHERE job_id = ? AND seeker_id = ?",
            (job_id, g.user["id"]),
        ).fetchone()

    similar_jobs = db.execute(
        """
        SELECT id, title, company, location, category, salary, job_type
        FROM jobs
        WHERE status = 'open' AND category = ? AND id != ?
        ORDER BY created_at DESC
        LIMIT 3
        """,
        (job["category"], job_id),
    ).fetchall()
    return render_template(
        "job_detail.html",
        job=job,
        application=application,
        similar_jobs=similar_jobs,
    )


@bp.post("/jobs/<int:job_id>/apply")
@roles_required("seeker")
def apply(job_id):
    db = get_db()
    job = get_job_or_404(job_id)
    if job["status"] != "open":
        flash("This job is no longer accepting applications.", "warning")
        return redirect(url_for("main.job_detail", job_id=job_id))

    cover_letter = request.form.get("cover_letter", "").strip() or None
    try:
        db.execute(
            """
            INSERT INTO applications (job_id, seeker_id, cover_letter, status)
            VALUES (?, ?, ?, 'submitted')
            """,
            (job_id, g.user["id"], cover_letter),
        )
        db.commit()
    except IntegrityError:
        flash("You have already applied for this role.", "warning")
    else:
        flash("Application submitted.", "success")
    return redirect(url_for("main.job_detail", job_id=job_id))


@bp.route("/dashboard")
@login_required
def dashboard_redirect():
    return redirect(url_for(dashboard_endpoint(g.user["role"])))


@bp.route("/seeker/dashboard")
@roles_required("seeker")
def seeker_dashboard():
    db = get_db()
    applications = db.execute(
        """
        SELECT applications.id, applications.created_at, applications.status,
               jobs.id AS job_id, jobs.title, jobs.company, jobs.location, jobs.job_type
        FROM applications
        JOIN jobs ON jobs.id = applications.job_id
        WHERE applications.seeker_id = ?
        ORDER BY applications.created_at DESC
        """,
        (g.user["id"],),
    ).fetchall()

    recommended_jobs = db.execute(
        """
        SELECT jobs.*, users.name AS employer_name
        FROM jobs
        JOIN users ON users.id = jobs.employer_id
        WHERE jobs.status = 'open'
          AND jobs.id NOT IN (SELECT job_id FROM applications WHERE seeker_id = ?)
        ORDER BY jobs.created_at DESC
        LIMIT 6
        """,
        (g.user["id"],),
    ).fetchall()

    stats = [
        {"label": "Applications", "value": len(applications), "icon": "bi-file-earmark-text", "tone": "purple"},
        {
            "label": "Reviewing",
            "value": sum(1 for item in applications if item["status"] == "reviewing"),
            "icon": "bi-search",
            "tone": "slate",
        },
        {
            "label": "Shortlisted",
            "value": sum(1 for item in applications if item["status"] == "shortlisted"),
            "icon": "bi-stars",
            "tone": "green",
        },
        {
            "label": "Hired",
            "value": sum(1 for item in applications if item["status"] == "hired"),
            "icon": "bi-people",
            "tone": "lavender",
        },
    ]
    return render_template(
        "seeker_dashboard.html",
        stats=stats,
        applications=applications,
        recommended_jobs=recommended_jobs,
    )


@bp.route("/employer/dashboard")
@roles_required("employer")
def employer_dashboard():
    db = get_db()
    summary = db.execute(
        """
        SELECT
            (SELECT COUNT(*) FROM jobs WHERE employer_id = ?) AS total_jobs,
            (SELECT COUNT(*) FROM jobs WHERE employer_id = ? AND status = 'open') AS active_jobs,
            (
                SELECT COUNT(*)
                FROM applications
                JOIN jobs ON jobs.id = applications.job_id
                WHERE jobs.employer_id = ?
            ) AS application_total,
            (
                SELECT COUNT(*)
                FROM applications
                JOIN jobs ON jobs.id = applications.job_id
                WHERE jobs.employer_id = ? AND applications.status = 'hired'
            ) AS hired_total
        """,
        (g.user["id"], g.user["id"], g.user["id"], g.user["id"]),
    ).fetchone()
    recent_jobs = db.execute(
        """
        SELECT jobs.*,
               COUNT(applications.id) AS application_total,
               SUM(CASE WHEN applications.status = 'hired' THEN 1 ELSE 0 END) AS hired_total
        FROM jobs
        LEFT JOIN applications ON applications.job_id = jobs.id
        WHERE jobs.employer_id = ?
        GROUP BY jobs.id
        ORDER BY jobs.created_at DESC
        LIMIT 6
        """,
        (g.user["id"],),
    ).fetchall()
    stats = [
        {"label": "Total Jobs", "value": summary["total_jobs"] or 0, "icon": "bi-briefcase", "tone": "lavender"},
        {
            "label": "Applications",
            "value": summary["application_total"] or 0,
            "icon": "bi-file-earmark-text",
            "tone": "purple",
        },
        {
            "label": "Active Jobs",
            "value": summary["active_jobs"] or 0,
            "icon": "bi-graph-up-arrow",
            "tone": "green",
        },
        {
            "label": "Hired",
            "value": summary["hired_total"] or 0,
            "icon": "bi-people",
            "tone": "lavender",
        },
    ]
    return render_template("employer_dashboard.html", stats=stats, recent_jobs=recent_jobs)


@bp.route("/employer/jobs")
@roles_required("employer")
def employer_manage_jobs():
    db = get_db()
    jobs_list = db.execute(
        """
        SELECT jobs.*,
               COUNT(applications.id) AS application_total
        FROM jobs
        LEFT JOIN applications ON applications.job_id = jobs.id
        WHERE jobs.employer_id = ?
        GROUP BY jobs.id
        ORDER BY jobs.created_at DESC
        """,
        (g.user["id"],),
    ).fetchall()
    return render_template(
        "manage_jobs.html",
        jobs=jobs_list,
        page_title="Manage Jobs",
        page_count=f"{len(jobs_list)} total listings",
        admin_mode=False,
        show_create=True,
    )


@bp.route("/employer/jobs/new", methods=("GET", "POST"))
@roles_required("employer")
def create_job():
    draft = {
        "title": "",
        "description": "",
        "salary": "",
        "location": "",
        "category": "",
        "company": g.user["company"] or "",
        "job_type": "full_time",
        "status": "open",
    }
    if request.method == "POST":
        draft = request.form.to_dict()
        payload, errors = sanitize_job_form(request.form, g.user["company"])
        if not errors:
            db = get_db()
            db.execute(
                """
                INSERT INTO jobs (
                    employer_id, title, description, salary, location, category,
                    company, job_type, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    g.user["id"],
                    payload["title"],
                    payload["description"],
                    payload["salary"],
                    payload["location"],
                    payload["category"],
                    payload["company"],
                    payload["job_type"],
                    payload["status"],
                ),
            )
            db.commit()
            flash("Job listing published.", "success")
            return redirect(url_for("main.employer_manage_jobs"))

        for error in errors:
            flash(error, "danger")

    return render_template("job_form.html", draft=draft, form_title="Post a job", submit_label="Publish job")


@bp.route("/employer/jobs/<int:job_id>/edit", methods=("GET", "POST"))
@roles_required("employer")
def edit_job(job_id):
    db = get_db()
    job = db.execute(
        "SELECT * FROM jobs WHERE id = ? AND employer_id = ?",
        (job_id, g.user["id"]),
    ).fetchone()
    if job is None:
        abort(404)

    draft = dict(job)
    if request.method == "POST":
        draft = request.form.to_dict()
        payload, errors = sanitize_job_form(request.form, g.user["company"])
        if not errors:
            db.execute(
                """
                UPDATE jobs
                SET title = ?, description = ?, salary = ?, location = ?, category = ?,
                    company = ?, job_type = ?, status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND employer_id = ?
                """,
                (
                    payload["title"],
                    payload["description"],
                    payload["salary"],
                    payload["location"],
                    payload["category"],
                    payload["company"],
                    payload["job_type"],
                    payload["status"],
                    job_id,
                    g.user["id"],
                ),
            )
            db.commit()
            flash("Job listing updated.", "success")
            return redirect(url_for("main.employer_manage_jobs"))

        for error in errors:
            flash(error, "danger")

    return render_template("job_form.html", draft=draft, form_title="Edit job", submit_label="Save changes")


@bp.post("/employer/jobs/<int:job_id>/delete")
@roles_required("employer")
def delete_job(job_id):
    db = get_db()
    db.execute("DELETE FROM jobs WHERE id = ? AND employer_id = ?", (job_id, g.user["id"]))
    db.commit()
    flash("Job listing deleted.", "info")
    return redirect(url_for("main.employer_manage_jobs"))


@bp.route("/employer/jobs/<int:job_id>/applications")
@roles_required("employer")
def job_applications(job_id):
    db = get_db()
    job = db.execute(
        "SELECT * FROM jobs WHERE id = ? AND employer_id = ?",
        (job_id, g.user["id"]),
    ).fetchone()
    if job is None:
        abort(404)

    applications = db.execute(
        """
        SELECT applications.*, users.name, users.email
        FROM applications
        JOIN users ON users.id = applications.seeker_id
        WHERE applications.job_id = ?
        ORDER BY applications.created_at DESC
        """,
        (job_id,),
    ).fetchall()
    return render_template("job_applications.html", job=job, applications=applications)


@bp.post("/employer/applications/<int:application_id>/status")
@roles_required("employer")
def update_application_status(application_id):
    status = request.form.get("status", "").strip().lower()
    if status not in APPLICATION_STATUSES:
        flash("Invalid application status.", "danger")
        return redirect(url_for("main.employer_manage_jobs"))

    db = get_db()
    application = db.execute(
        """
        SELECT applications.id, applications.job_id
        FROM applications
        JOIN jobs ON jobs.id = applications.job_id
        WHERE applications.id = ? AND jobs.employer_id = ?
        """,
        (application_id, g.user["id"]),
    ).fetchone()
    if application is None:
        abort(404)

    db.execute("UPDATE applications SET status = ? WHERE id = ?", (status, application_id))
    db.commit()
    flash("Application status updated.", "success")
    return redirect(url_for("main.job_applications", job_id=application["job_id"]))


@bp.route("/admin/dashboard")
@roles_required("admin")
def admin_dashboard():
    db = get_db()
    recent_jobs = db.execute(
        """
        SELECT jobs.*,
               users.name AS employer_name,
               (SELECT COUNT(*) FROM applications WHERE applications.job_id = jobs.id) AS application_total
        FROM jobs
        JOIN users ON users.id = jobs.employer_id
        ORDER BY jobs.created_at DESC
        LIMIT 6
        """
    ).fetchall()
    stats = [
        {
            "label": "Total Jobs",
            "value": db.execute("SELECT COUNT(*) AS count FROM jobs").fetchone()["count"],
            "icon": "bi-briefcase",
            "tone": "lavender",
        },
        {
            "label": "Applications",
            "value": db.execute("SELECT COUNT(*) AS count FROM applications").fetchone()["count"],
            "icon": "bi-file-earmark-text",
            "tone": "purple",
        },
        {
            "label": "Active Jobs",
            "value": db.execute("SELECT COUNT(*) AS count FROM jobs WHERE status = 'open'").fetchone()["count"],
            "icon": "bi-graph-up-arrow",
            "tone": "green",
        },
        {
            "label": "Users",
            "value": db.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"],
            "icon": "bi-people",
            "tone": "lavender",
        },
    ]
    return render_template("admin_dashboard.html", stats=stats, recent_jobs=recent_jobs)


@bp.route("/admin/users")
@roles_required("admin")
def manage_users():
    db = get_db()
    users = db.execute(
        """
        SELECT users.*,
               (SELECT COUNT(*) FROM jobs WHERE jobs.employer_id = users.id) AS job_total,
               (SELECT COUNT(*) FROM applications WHERE applications.seeker_id = users.id) AS application_total
        FROM users
        ORDER BY users.created_at DESC
        """
    ).fetchall()
    return render_template("manage_users.html", users=users, total_users=len(users))


@bp.route("/admin/jobs")
@roles_required("admin")
def admin_manage_jobs():
    db = get_db()
    jobs_list = db.execute(
        """
        SELECT jobs.*, users.name AS employer_name,
               (SELECT COUNT(*) FROM applications WHERE applications.job_id = jobs.id) AS application_total
        FROM jobs
        JOIN users ON users.id = jobs.employer_id
        ORDER BY jobs.created_at DESC
        """
    ).fetchall()
    return render_template(
        "manage_jobs.html",
        jobs=jobs_list,
        page_title="Manage Jobs",
        page_count=f"{len(jobs_list)} total listings",
        admin_mode=True,
        show_create=False,
    )


@bp.post("/admin/users/<int:user_id>/role")
@roles_required("admin")
def update_user_role(user_id):
    new_role = request.form.get("role", "").strip().lower()
    if new_role not in {"seeker", "employer"}:
        flash("Invalid role selected.", "danger")
        return redirect(url_for("main.manage_users"))

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    if user["role"] == "admin":
        flash("Admin accounts cannot be reassigned here.", "warning")
        return redirect(url_for("main.manage_users"))

    db.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
    db.commit()
    flash("User role updated.", "success")
    return redirect(url_for("main.manage_users"))


@bp.post("/admin/users/<int:user_id>/delete")
@roles_required("admin")
def delete_user(user_id):
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    if user is None:
        abort(404)
    if user["role"] == "admin" or user["id"] == g.user["id"]:
        flash("This account cannot be deleted from the dashboard.", "warning")
        return redirect(url_for("main.manage_users"))

    db.execute("DELETE FROM users WHERE id = ?", (user_id,))
    db.commit()
    flash("User removed.", "info")
    return redirect(url_for("main.manage_users"))


@bp.post("/admin/jobs/<int:job_id>/delete")
@roles_required("admin")
def admin_delete_job(job_id):
    db = get_db()
    db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    db.commit()
    flash("Job deleted.", "info")
    return redirect(url_for("main.admin_manage_jobs"))
