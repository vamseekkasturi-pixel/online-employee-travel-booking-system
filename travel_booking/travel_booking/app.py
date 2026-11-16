"""Online Employee Travel Booking System - simple base project (Flask + SQLite)."""
import os
import secrets
import sqlite3
from datetime import date, datetime
from functools import wraps

from flask import (Flask, abort, flash, g, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.environ.get("TRAVEL_DB", os.path.join(BASE_DIR, "travel.db"))

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

TRAVEL_MODES = ["Flight", "Train", "Bus", "Cab"]
STATUS_FILTERS = ["All", "Pending", "Approved", "Rejected", "Cancelled"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    department    TEXT NOT NULL DEFAULT 'General',
    role          TEXT NOT NULL DEFAULT 'employee',   -- employee | admin
    created_at    TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS bookings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id),
    travel_mode    TEXT NOT NULL,
    origin         TEXT NOT NULL,
    destination    TEXT NOT NULL,
    depart_date    TEXT NOT NULL,
    return_date    TEXT,
    purpose        TEXT NOT NULL,
    estimated_cost REAL NOT NULL DEFAULT 0,
    hotel_required INTEGER NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'Pending',   -- Pending|Approved|Rejected|Cancelled
    admin_remark   TEXT,
    created_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at     TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create tables and seed a demo admin and employee on first run."""
    db = sqlite3.connect(DATABASE)
    db.executescript(SCHEMA)
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        db.execute(
            "INSERT INTO users (name, email, password_hash, department, role) "
            "VALUES (?, ?, ?, ?, ?)",
            ("Travel Admin", "admin@company.com",
             generate_password_hash("admin123"), "HR", "admin"),
        )
        db.execute(
            "INSERT INTO users (name, email, password_hash, department, role) "
            "VALUES (?, ?, ?, ?, ?)",
            ("Demo Employee", "employee@company.com",
             generate_password_hash("employee123"), "Engineering", "employee"),
        )
    db.commit()
    db.close()


# --------------------------------------------------------------------------
# Auth helpers, CSRF, template context
# --------------------------------------------------------------------------
@app.before_request
def load_user_and_check_csrf():
    g.user = None
    user_id = session.get("user_id")
    if user_id is not None:
        g.user = get_db().execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if g.user is None:
            session.clear()

    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        expected = session.get("csrf_token", "")
        if not expected or not secrets.compare_digest(sent, expected):
            abort(400, "Invalid or missing CSRF token.")


@app.context_processor
def inject_globals():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return {"csrf_token": session["csrf_token"], "current_user": g.get("user")}


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if g.user["role"] != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------
# Public / auth routes
# --------------------------------------------------------------------------
@app.route("/")
def index():
    if g.user:
        return redirect(url_for("admin_dashboard" if g.user["role"] == "admin"
                                else "dashboard"))
    return redirect(url_for("login"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        department = request.form.get("department", "").strip() or "General"
        password = request.form.get("password", "")
        errors = []
        if not name:
            errors.append("Name is required.")
        if "@" not in email:
            errors.append("A valid email is required.")
        if len(password) < 6:
            errors.append("Password must be at least 6 characters.")
        db = get_db()
        if not errors and db.execute(
                "SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            errors.append("That email is already registered.")
        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("register.html", form=request.form)
        db.execute(
            "INSERT INTO users (name, email, password_hash, department) "
            "VALUES (?, ?, ?, ?)",
            (name, email, generate_password_hash(password), department))
        db.commit()
        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("login"))
    return render_template("register.html", form={})


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = get_db().execute(
            "SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "danger")
            return render_template("login.html", email=email)
        session.clear()
        session["user_id"] = user["id"]
        session["csrf_token"] = secrets.token_hex(16)
        flash(f"Welcome back, {user['name']}!", "success")
        return redirect(url_for("index"))
    return render_template("login.html", email="")


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# --------------------------------------------------------------------------
# Employee routes
# --------------------------------------------------------------------------
@app.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    counts = {s: 0 for s in STATUS_FILTERS[1:]}
    for row in db.execute(
            "SELECT status, COUNT(*) AS n FROM bookings WHERE user_id = ? "
            "GROUP BY status", (g.user["id"],)):
        counts[row["status"]] = row["n"]
    upcoming = db.execute(
        "SELECT * FROM bookings WHERE user_id = ? AND status = 'Approved' "
        "AND depart_date >= ? ORDER BY depart_date LIMIT 5",
        (g.user["id"], date.today().isoformat())).fetchall()
    return render_template("dashboard.html", counts=counts, upcoming=upcoming)


@app.route("/bookings")
@login_required
def my_bookings():
    bookings = get_db().execute(
        "SELECT * FROM bookings WHERE user_id = ? ORDER BY created_at DESC, id DESC",
        (g.user["id"],)).fetchall()
    return render_template("my_bookings.html", bookings=bookings)


@app.route("/bookings/new", methods=["GET", "POST"])
@login_required
def new_booking():
    if request.method == "POST":
        f = request.form
        mode = f.get("travel_mode", "")
        origin = f.get("origin", "").strip()
        destination = f.get("destination", "").strip()
        depart = parse_date(f.get("depart_date"))
        ret_raw = f.get("return_date", "").strip()
        ret = parse_date(ret_raw) if ret_raw else None
        purpose = f.get("purpose", "").strip()
        hotel = 1 if f.get("hotel_required") == "on" else 0
        try:
            cost = float(f.get("estimated_cost", "0") or 0)
        except ValueError:
            cost = -1

        errors = []
        if mode not in TRAVEL_MODES:
            errors.append("Choose a valid travel mode.")
        if not origin or not destination:
            errors.append("Origin and destination are required.")
        elif origin.lower() == destination.lower():
            errors.append("Origin and destination must be different.")
        if depart is None:
            errors.append("A valid departure date is required.")
        elif depart < date.today():
            errors.append("Departure date cannot be in the past.")
        if ret_raw and ret is None:
            errors.append("Return date is invalid.")
        elif ret and depart and ret < depart:
            errors.append("Return date cannot be before departure date.")
        if not purpose:
            errors.append("Purpose of travel is required.")
        if cost < 0:
            errors.append("Estimated cost must be a non-negative number.")

        if errors:
            for e in errors:
                flash(e, "danger")
            return render_template("new_booking.html", modes=TRAVEL_MODES,
                                   form=f, today=date.today().isoformat())

        db = get_db()
        db.execute(
            "INSERT INTO bookings (user_id, travel_mode, origin, destination, "
            "depart_date, return_date, purpose, estimated_cost, hotel_required) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (g.user["id"], mode, origin, destination, depart.isoformat(),
             ret.isoformat() if ret else None, purpose, cost, hotel))
        db.commit()
        flash("Travel request submitted and is awaiting approval.", "success")
        return redirect(url_for("my_bookings"))
    return render_template("new_booking.html", modes=TRAVEL_MODES, form={},
                           today=date.today().isoformat())


@app.route("/bookings/<int:booking_id>/cancel", methods=["POST"])
@login_required
def cancel_booking(booking_id):
    db = get_db()
    booking = db.execute("SELECT * FROM bookings WHERE id = ? AND user_id = ?",
                         (booking_id, g.user["id"])).fetchone()
    if booking is None:
        abort(404)
    if booking["status"] not in ("Pending", "Approved"):
        flash("Only pending or approved bookings can be cancelled.", "warning")
    else:
        db.execute("UPDATE bookings SET status = 'Cancelled', "
                   "updated_at = CURRENT_TIMESTAMP WHERE id = ?", (booking_id,))
        db.commit()
        flash("Booking cancelled.", "info")
    return redirect(url_for("my_bookings"))


# --------------------------------------------------------------------------
# Admin routes
# --------------------------------------------------------------------------
@app.route("/admin")
@admin_required
def admin_dashboard():
    status = request.args.get("status", "Pending")
    if status not in STATUS_FILTERS:
        status = "Pending"
    query = ("SELECT b.*, u.name AS employee, u.department FROM bookings b "
             "JOIN users u ON u.id = b.user_id")
    params = ()
    if status != "All":
        query += " WHERE b.status = ?"
        params = (status,)
    query += " ORDER BY b.created_at DESC, b.id DESC"
    db = get_db()
    bookings = db.execute(query, params).fetchall()
    stats = {s: 0 for s in STATUS_FILTERS[1:]}
    for row in db.execute("SELECT status, COUNT(*) AS n FROM bookings GROUP BY status"):
        stats[row["status"]] = row["n"]
    return render_template("admin.html", bookings=bookings, stats=stats,
                           filters=STATUS_FILTERS, active=status)


@app.route("/admin/bookings/<int:booking_id>/decide", methods=["POST"])
@admin_required
def decide_booking(booking_id):
    action = request.form.get("action")
    remark = request.form.get("remark", "").strip()
    if action not in ("approve", "reject"):
        abort(400)
    db = get_db()
    booking = db.execute("SELECT * FROM bookings WHERE id = ?",
                         (booking_id,)).fetchone()
    if booking is None:
        abort(404)
    if booking["status"] != "Pending":
        flash("Only pending requests can be approved or rejected.", "warning")
        return redirect(url_for("admin_dashboard"))
    if action == "reject" and not remark:
        flash("Please add a remark when rejecting a request.", "danger")
        return redirect(url_for("admin_dashboard"))
    new_status = "Approved" if action == "approve" else "Rejected"
    db.execute("UPDATE bookings SET status = ?, admin_remark = ?, "
               "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
               (new_status, remark or None, booking_id))
    db.commit()
    flash(f"Request #{booking_id} {new_status.lower()}.", "success")
    return redirect(url_for("admin_dashboard"))


# --------------------------------------------------------------------------
# Template filters & error pages
# --------------------------------------------------------------------------
@app.template_filter("money")
def money(value):
    return f"₹{value:,.2f}"


@app.errorhandler(400)
@app.errorhandler(403)
@app.errorhandler(404)
def handle_error(err):
    return render_template("error.html", error=err), err.code


init_db()

if __name__ == "__main__":
    app.run(debug=True)
