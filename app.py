import os
import sys
import sqlite3
import secrets
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, g, flash, make_response
)
from werkzeug.security import generate_password_hash, check_password_hash

_REQUIRED_ENV = ["SECRET_KEY", "ADMIN_PASSWORD_ADMIN", "ADMIN_PASSWORD_DANIEL"]
_missing = [v for v in _REQUIRED_ENV if not os.environ.get(v, "").strip()]
if _missing:
    print(
        f"[FEHLER] Fehlende Pflicht-Umgebungsvariablen: {\', \'.join(_missing)}\n"
        "Bitte in der .env auf dem Host setzen. Anwendung wird beendet.",
        file=sys.stderr,
    )
    sys.exit(1)

SEED_ADMIN_USERS = {
    "Admin": os.environ.get("ADMIN_PASSWORD_ADMIN"),
    "Daniel": os.environ.get("ADMIN_PASSWORD_DANIEL"),
}

SLOT_DEFINITIONS = [
    {"key": "slot_a", "label": "Slot A: 18:00 - 20:00 Uhr"},
    {"key": "slot_b", "label": "Slot B: 20:00 - 22:00 Uhr"},
]
SLOT_LABEL = {s["key"]: s["label"] for s in SLOT_DEFINITIONS}
WAITLIST_LIMIT = 4

THEMES = {
    "default": {
        "label": "Standard (Blau)",
        "gradient": "radial-gradient(circle at top left, #e0ecff 0, #f5f5fb 40%, #fdfdfd 100%)",
        "background_image": None,
        "accent": "#2563eb",
        "accent2": "#0ea5e9",
    },
    "sunset": {
        "label": "Sunset (Orange)",
        "gradient": "radial-gradient(circle at top left, #ffe4d6 0, #fff5f0 40%, #fffaf7 100%)",
        "background_image": None,
        "accent": "#ea580c",
        "accent2": "#f59e0b",
    },
    "court": {
        "label": "Court (Gruen)",
        "gradient": "radial-gradient(circle at top left, #dcfce7 0, #f0fdf4 40%, #fbfffc 100%)",
        "background_image": None,
        "accent": "#16a34a",
        "accent2": "#22c55e",
    },
    "night": {
        "label": "Night (Dunkel)",
        "gradient": "radial-gradient(circle at top left, #1e293b 0, #0f172a 60%, #020617 100%)",
        "background_image": None,
        "accent": "#38bdf8",
        "accent2": "#818cf8",
    },
    "racket_fire": {
        "label": "Racket Fire (Bild)",
        "gradient": "linear-gradient(rgba(15,23,42,0.55), rgba(15,23,42,0.55))",
        "background_image": "Racketfire.png",
        "accent": "#f97316",
        "accent2": "#facc15",
    },
    "racket_splash": {
        "label": "Racket Splash (Bild)",
        "gradient": "linear-gradient(rgba(15,23,42,0.55), rgba(15,23,42,0.55))",
        "background_image": "Racketsplash.png",
        "accent": "#0ea5e9",
        "accent2": "#38bdf8",
    },
    "padel_court_bg": {
        "label": "Padel Court (Foto)",
        "gradient": "linear-gradient(rgba(15,23,42,0.5), rgba(15,23,42,0.5))",
        "background_image": "padel_bg_1.jpg",
        "accent": "#16a34a",
        "accent2": "#4ade80",
    },
}
DEFAULT_THEME = "default"

SIGNUP_COOKIE_PREFIX = "mtp_signed_"


def normalize_name(name: str) -> str:
    return " ".join(name.strip().split()).lower()


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        DATABASE=os.path.join(app.instance_path, "matchtreff.sqlite3"),
    )
    if test_config is not None:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(
                app.config["DATABASE"],
                detect_types=sqlite3.PARSE_DECLTYPES,
            )
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
        return g.db

    @app.teardown_appcontext
    def close_db(exception=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    def init_db():
        db = get_db()
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_key TEXT UNIQUE NOT NULL,
                label TEXT NOT NULL,
                max_players INTEGER NOT NULL DEFAULT 8
            );

            CREATE TABLE IF NOT EXISTS signups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                name_normalized TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT \'confirmed\',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(slot_id) REFERENCES slots(id),
                UNIQUE(slot_id, name_normalized)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS admin_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_by TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        existing_theme = db.execute(
            "SELECT value FROM settings WHERE key = \'theme\'"
        ).fetchone()
        if not existing_theme:
            db.execute(
                "INSERT INTO settings (key, value) VALUES (\'theme\', ?)",
                (DEFAULT_THEME,),
            )

        for seed_name, seed_password in SEED_ADMIN_USERS.items():
            if not seed_password:
                continue
            existing_admin = db.execute(
                "SELECT id FROM admin_users WHERE username = ?", (seed_name,)
            ).fetchone()
            if not existing_admin:
                db.execute(
                    "INSERT INTO admin_users (username, password_hash, created_by) VALUES (?, ?, ?)",
                    (seed_name, generate_password_hash(seed_password), "system"),
                )
        for s in SLOT_DEFINITIONS:
            existing = db.execute(
                "SELECT id FROM slots WHERE slot_key = ?", (s["key"],)
            ).fetchone()
            if not existing:
                db.execute(
                    "INSERT INTO slots (slot_key, label, max_players) VALUES (?, ?, ?)",
                    (s["key"], s["label"], 8),
                )
        db.commit()

    with app.app_context():
        init_db()

    def next_thursday():
        today = datetime.today().date()
        days_ahead = (3 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return today + timedelta(days=days_ahead)

    def get_slots_with_counts():
        db = get_db()
        rows = db.execute("SELECT * FROM slots ORDER BY id").fetchall()
        result = []
        for row in rows:
            confirmed = db.execute(
                "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = \'confirmed\'",
                (row["id"],),
            ).fetchone()["c"]
            waitlisted = db.execute(
                "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = \'waitlist\'",
                (row["id"],),
            ).fetchone()["c"]
            result.append({
                "id": row["id"],
                "slot_key": row["slot_key"],
                "label": row["label"],
                "max_players": row["max_players"],
                "count": confirmed,
                "waitlist_count": waitlisted,
                "full": confirmed >= row["max_players"],
                "waitlist_full": waitlisted >= WAITLIST_LIMIT,
            })
        return result

    def get_signups_for_slot(slot_id, status):
        db = get_db()
        return db.execute(
            "SELECT * FROM signups WHERE slot_id = ? AND status = ? ORDER BY created_at ASC",
            (slot_id, status),
        ).fetchall()

    def admin_required(view):
        from functools import wraps

        @wraps(view)
        def wrapped(*args, **kwargs):
            if not session.get("is_admin"):
                flash("Admin-Login erforderlich.", "danger")
                return redirect(url_for("admin_login"))
            return view(*args, **kwargs)
        return wrapped

    def get_current_theme_key():
        db = get_db()
        row = db.execute("SELECT value FROM settings WHERE key = \'theme\'").fetchone()
        key = row["value"] if row else DEFAULT_THEME
        return key if key in THEMES else DEFAULT_THEME

    @app.context_processor
    def inject_globals():
        theme_key = get_current_theme_key()
        return {
            "is_admin": bool(session.get("is_admin")),
            "admin_username": session.get("admin_username"),
            "next_thursday": next_thursday().strftime("%d.%m.%Y"),
            "current_theme_key": theme_key,
            "current_theme": THEMES[theme_key],
            "themes": THEMES,
        }

    @app.route("/")
    def index():
        slots = get_slots_with_counts()
        signups_by_slot = {
            s["id"]: {
                "confirmed": get_signups_for_slot(s["id"], "confirmed"),
                "waitlist": get_signups_for_slot(s["id"], "waitlist"),
            }
            for s in slots
        }
        cookie_locked = {
            s["slot_key"]: request.cookies.get(SIGNUP_COOKIE_PREFIX + s["slot_key"]) is not None
            for s in slots
        }
        return render_template(
            "index.html",
            slots=slots,
            signups_by_slot=signups_by_slot,
            cookie_locked=cookie_locked,
        )

    @app.route("/eintragen", methods=["POST"])
    def eintragen():
        name = request.form.get("name", "").strip()
        selected_slots = request.form.getlist("slots")

        if not name:
            flash("Bitte einen Namen eingeben.", "danger")
            return redirect(url_for("index"))

        if not selected_slots:
            flash("Bitte mindestens einen Slot auswaehlen.", "danger")
            return redirect(url_for("index"))

        name_norm = normalize_name(name)
        db = get_db()
        added, waitlisted, blocked_cookie, blocked_duplicate = [], [], [], []

        for slot_key in selected_slots:
            cookie_name = SIGNUP_COOKIE_PREFIX + slot_key
            if request.cookies.get(cookie_name):
                blocked_cookie.append(SLOT_LABEL.get(slot_key, slot_key))
                continue

            slot_row = db.execute(
                "SELECT * FROM slots WHERE slot_key = ?", (slot_key,)
            ).fetchone()
            if slot_row is None:
                continue

            confirmed_count = db.execute(
                "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = \'confirmed\'",
                (slot_row["id"],),
            ).fetchone()["c"]
            waitlist_count = db.execute(
                "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = \'waitlist\'",
                (slot_row["id"],),
            ).fetchone()["c"]

            status = "confirmed" if confirmed_count < slot_row["max_players"] else "waitlist"

            if status == "waitlist" and waitlist_count >= WAITLIST_LIMIT:
                blocked_duplicate.append(slot_row["label"] + " (Warteliste voll)")
                continue

            try:
                db.execute(
                    "INSERT INTO signups (slot_id, name, name_normalized, status) VALUES (?, ?, ?, ?)",
                    (slot_row["id"], name, name_norm, status),
                )
                db.commit()
            except sqlite3.IntegrityError:
                blocked_duplicate.append(slot_row["label"])
                continue

            if status == "confirmed":
                added.append((slot_row["label"], slot_key))
            else:
                waitlisted.append((slot_row["label"], slot_key))

        messages = []
        if added:
            messages.append("Eingetragen fuer: " + ", ".join(l for l, _ in added))
        if waitlisted:
            messages.append("Auf Warteliste fuer: " + ", ".join(l for l, _ in waitlisted))
        if blocked_cookie:
            messages.append("Bereits von diesem Geraet eingetragen fuer: " + ", ".join(blocked_cookie))
        if blocked_duplicate:
            messages.append("Nicht moeglich (Name bereits vorhanden oder Warteliste voll): " + ", ".join(blocked_duplicate))

        category = "success" if (added or waitlisted) else "warning"
        if messages:
            flash(" | ".join(messages), category)

        resp = make_response(redirect(url_for("index")))
        max_age = 60 * 60 * 24 * 7
        for _, slot_key in added + waitlisted:
            resp.set_cookie(SIGNUP_COOKIE_PREFIX + slot_key, "1", max_age=max_age, httponly=True, samesite="Lax")
        return resp

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            db = get_db()
            row = db.execute(
                "SELECT * FROM admin_users WHERE username = ?", (username,)
            ).fetchone()

            if row and check_password_hash(row["password_hash"], password):
                session["is_admin"] = True
                session["admin_username"] = row["username"]
                flash(f"Admin-Login erfolgreich als {row[\'username\']}.", "success")
                return redirect(url_for("admin_dashboard"))
            flash("Benutzername oder Passwort falsch.", "danger")
        return render_template("admin_login.html")

    @app.route("/admin/logout")
    def admin_logout():
        session.pop("is_admin", None)
        session.pop("admin_username", None)
        flash("Admin abgemeldet.", "info")
        return redirect(url_for("index"))

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        slots = get_slots_with_counts()
        signups_by_slot = {
            s["id"]: {
                "confirmed": get_signups_for_slot(s["id"], "confirmed"),
                "waitlist": get_signups_for_slot(s["id"], "waitlist"),
            }
            for s in slots
        }
        return render_template(
            "admin_dashboard.html",
            slots=slots,
            signups_by_slot=signups_by_slot,
            waitlist_limit=WAITLIST_LIMIT,
        )

    @app.route("/admin/slot/<int:slot_id>/update", methods=["POST"])
    @admin_required
    def admin_update_slot(slot_id):
        db = get_db()
        max_raw = request.form.get("max_players", "0")
        try:
            max_players = int(max_raw)
        except ValueError:
            max_players = 0

        if max_players <= 0:
            flash("Bitte eine gueltige maximale Anzahl eintragen.", "danger")
            return redirect(url_for("admin_dashboard"))

        db.execute(
            "UPDATE slots SET max_players = ? WHERE id = ?",
            (max_players, slot_id),
        )
        db.commit()

        row = db.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
        confirmed = get_signups_for_slot(slot_id, "confirmed")
        waitlist = get_signups_for_slot(slot_id, "waitlist")
        free_slots = row["max_players"] - len(confirmed)
        moved = 0
        for su in waitlist:
            if free_slots <= 0:
                break
            db.execute("UPDATE signups SET status = \'confirmed\' WHERE id = ?", (su["id"],))
            free_slots -= 1
            moved += 1
        db.commit()

        msg = "Maximale Anzahl aktualisiert."
        if moved:
            msg += f" {moved} Spieler von der Warteliste nachgerueckt."
        flash(msg, "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/signup/<int:signup_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_signup(signup_id):
        db = get_db()
        row = db.execute("SELECT * FROM signups WHERE id = ?", (signup_id,)).fetchone()
        if row is None:
            flash("Anmeldung nicht gefunden.", "danger")
            return redirect(url_for("admin_dashboard"))

        slot_id = row["slot_id"]
        was_confirmed = row["status"] == "confirmed"
        db.execute("DELETE FROM signups WHERE id = ?", (signup_id,))
        db.commit()

        if was_confirmed:
            slot_row = db.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
            next_waiting = db.execute(
                "SELECT * FROM signups WHERE slot_id = ? AND status = \'waitlist\' ORDER BY created_at ASC LIMIT 1",
                (slot_id,),
            ).fetchone()
            if next_waiting:
                db.execute(
                    "UPDATE signups SET status = \'confirmed\' WHERE id = ?",
                    (next_waiting["id"],),
                )
                db.commit()
                flash(f"Anmeldung geloescht. {next_waiting[\'name\']} ist von der Warteliste nachgerueckt.", "info")
                return redirect(url_for("admin_dashboard"))

        flash("Anmeldung geloescht.", "info")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/users", methods=["GET"])
    @admin_required
    def admin_users_list():
        db = get_db()
        users = db.execute(
            "SELECT id, username, created_by, created_at FROM admin_users ORDER BY created_at ASC"
        ).fetchall()
        return render_template(
            "admin_users.html",
            users=users,
        )

    @app.route("/admin/users/create", methods=["POST"])
    @admin_required
    def admin_users_create():
        new_username = request.form.get("new_username", "").strip()
        new_password = request.form.get("new_password", "")
        new_password_confirm = request.form.get("new_password_confirm", "")

        if not new_username:
            flash("Bitte einen Benutzernamen angeben.", "danger")
            return redirect(url_for("admin_users_list"))

        if len(new_password) < 6:
            flash("Passwort muss mindestens 6 Zeichen lang sein.", "danger")
            return redirect(url_for("admin_users_list"))

        if new_password != new_password_confirm:
            flash("Passwoerter stimmen nicht ueberein.", "danger")
            return redirect(url_for("admin_users_list"))

        db = get_db()
        existing = db.execute(
            "SELECT id FROM admin_users WHERE username = ?", (new_username,)
        ).fetchone()
        if existing:
            flash("Dieser Benutzername existiert bereits.", "danger")
            return redirect(url_for("admin_users_list"))

        db.execute(
            "INSERT INTO admin_users (username, password_hash, created_by) VALUES (?, ?, ?)",
            (new_username, generate_password_hash(new_password), session.get("admin_username")),
        )
        db.commit()
        flash(f"Admin \'{new_username}\' wurde angelegt.", "success")
        return redirect(url_for("admin_users_list"))

    @app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
    @admin_required
    def admin_users_delete(user_id):
        db = get_db()
        row = db.execute("SELECT * FROM admin_users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            flash("Admin nicht gefunden.", "danger")
            return redirect(url_for("admin_users_list"))

        total_admins = db.execute("SELECT COUNT(*) AS c FROM admin_users").fetchone()["c"]
        if total_admins <= 1:
            flash("Der letzte verbleibende Admin kann nicht geloescht werden.", "danger")
            return redirect(url_for("admin_users_list"))

        if row["username"] == session.get("admin_username"):
            flash("Du kannst dich nicht selbst loeschen. Bitte von einem anderen Admin loeschen lassen.", "danger")
            return redirect(url_for("admin_users_list"))

        db.execute("DELETE FROM admin_users WHERE id = ?", (user_id,))
        db.commit()
        flash(f"Admin \'{row[\'username\']}\' wurde geloescht.", "info")
        return redirect(url_for("admin_users_list"))

    @app.route("/admin/theme/update", methods=["POST"])
    @admin_required
    def admin_update_theme():
        theme_key = request.form.get("theme", DEFAULT_THEME)
        if theme_key not in THEMES:
            flash("Unbekanntes Design.", "danger")
            return redirect(url_for("admin_dashboard"))

        db = get_db()
        db.execute(
            "INSERT INTO settings (key, value) VALUES (\'theme\', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (theme_key,),
        )
        db.commit()
        flash(f"Design auf \'{THEMES[theme_key][\'label\']}\' geaendert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/signups/clear", methods=["POST"])
    @admin_required
    def admin_clear_signups():
        db = get_db()
        db.execute("DELETE FROM signups")
        db.commit()
        flash("Alle Anmeldungen wurden zurueckgesetzt.", "info")
        return redirect(url_for("admin_dashboard"))

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "1905"))
    app.run(host="0.0.0.0", port=port)
