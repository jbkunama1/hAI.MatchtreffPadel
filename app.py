import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps
from flask import Flask, abort, flash, g, redirect, render_template, request, send_file, session, url_for, current_app

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "data", "matchtreff.db")
ADMIN_INITIAL_PASSWORD = os.environ.get("ADMIN_INITIAL_PASSWORD", "padel-admin")
DEFAULT_THEME = "dark"
DEFAULT_BG_STYLE = "bubbles"
DEFAULT_CUSTOM_IMAGE = "wappen.png"
DEFAULT_INTRO_TEXT = "Melde dich hier für den nächsten Matchtreff am Donnerstag ({next_thursday}) an und stelle sicher, dass du einen Platz bekommst!"
DEFAULT_WAITLIST_LIMIT = 4
DEFAULT_SLOT_SELECTION = "both"  # "one" oder "both"
DEFAULT_WAITLIST_MODE = "with_waitlist"  # "with_waitlist", "open_for_all", "no_waitlist", "guests_only"
ORGA_TEAM = {"daniel", "cosme", "sascha", "patrick"}


def create_app():
    app = Flask(__name__)
    app.config["DATABASE"] = os.environ.get("DATABASE_PATH", DEFAULT_DB_PATH)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "matchtreff-secret")
    app.config["WEEK_START_DATE"] = os.environ.get("WEEK_START_DATE", date.today().isoformat())

    @app.context_processor
    def inject_theme_and_badges():
        return {
            "current_theme": get_theme_config(),
            "current_bg_style": get_bg_style(),
            "orga_team_normalized": ORGA_TEAM,
            "is_admin": session.get("is_admin", False),
        }

    @app.teardown_appcontext
    def close_db(exception=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.route("/")
    def index():
        slots = get_slots_with_counts()
        return render_template(
            "index.html",
            slots=slots,
            week_date=get_current_week_date(),
            intro_text=get_intro_text(),
        )

    @app.route("/signup", methods=["POST"])
    def signup():
        name = request.form.get("name", "").strip()
        slot_id = request.form.get("slot_id", "").strip()
        honeypot = request.form.get("website", "").strip()

        if honeypot:
            flash("Ungueltige Anfrage.", "error")
            return redirect(url_for("index"))

        if not name or not slot_id.isdigit():
            flash("Bitte Namen und Slot auswaehlen.", "error")
            return redirect(url_for("index"))

        if len(name) > 80:
            flash("Name ist zu lang (max. 80 Zeichen).", "error")
            return redirect(url_for("index"))

        slot_id = int(slot_id)
        week_date = get_current_week_date()
        name_key = normalize_name(name)
        is_member = 1 if request.form.get("is_member") else 0

        if is_member == 0 and name_key not in ORGA_TEAM:
            send_guest_signup_notification(name, slot_id)

        db = get_db()
        db.execute(
            "INSERT OR IGNORE INTO signup_locks (week_date, name_normalized) VALUES (?, ?)",
            (week_date, name_key),
        )
        lock_result = db.execute(
            "SELECT changes() AS changed"
        ).fetchone()
        if lock_result["changed"] == 0:
            db.rollback()
            flash("Du bist diese Woche bereits angemeldet.", "error")
            return redirect(url_for("index"))

        try:
            status = get_status_for_slot(slot_id, week_date)
            if status == "waitlist_full":
                db.rollback()
                flash("Slot und Warteliste sind voll.", "error")
                return redirect(url_for("index"))

            db.execute(
                """
                INSERT INTO signups (name, name_normalized, slot_id, week_date, status, is_member)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, name_key, slot_id, week_date, status, is_member),
            )
            db.commit()
        except Exception:
            db.rollback()
            flash("Anmeldung fehlgeschlagen. Bitte erneut versuchen.", "error")
            return redirect(url_for("index"))

        if status == "waitlist":
            flash("Slot ist voll - du stehst auf der Warteliste.", "success")
        else:
            flash("Du bist angemeldet.", "success")
        return redirect(url_for("index"))

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if session.get("is_admin"):
            return redirect(url_for("admin_dashboard"))

        if request.method == "POST":
            password = request.form.get("password", "")
            db = get_db()
            row = db.execute(
                "SELECT password_hash FROM admin_users WHERE username = ?",
                ("admin",),
            ).fetchone()
            if not row:
                flash("Admin-Konto fehlt. Bitte Datenbank initialisieren.", "error")
                return redirect(url_for("admin_login"))

            if check_password(password, row["password_hash"]):
                session["is_admin"] = True
                flash("Erfolgreich eingeloggt.", "success")
                return redirect(url_for("admin_dashboard"))
            flash("Passwort falsch.", "error")
            return redirect(url_for("admin_login"))

        return render_template("admin_login.html")

    @app.route("/admin/logout", methods=["POST"])
    @admin_required
    def admin_logout():
        session.pop("is_admin", None)
        flash("Abgemeldet.", "success")
        return redirect(url_for("index"))

    @app.route("/admin")
    @admin_required
    def admin_dashboard():
        slots = get_slots_with_counts()
        signups_by_slot = {
            s["id"]: {"confirmed": get_signups_for_slot(s["id"], "confirmed"),
                      "waitlist": get_signups_for_slot(s["id"], "waitlist")}
            for s in slots
        }
        return render_template(
            "admin_dashboard.html",
            slots=slots,
            signups_by_slot=signups_by_slot,
            waitlist_limit=get_waitlist_limit(),
            slot_selection=get_slot_selection(),
            waitlist_mode=get_waitlist_mode(),
            gallery_images=GALLERY_IMAGES,
            current_custom_image=get_custom_bg_image(),
            raw_intro_text=get_raw_intro_text(),
        )

    @app.route("/admin/backup/download")
    @admin_required
    def admin_backup_download():
        db_path = app.config["DATABASE"]
        return send_file(db_path, as_attachment=True, download_name="matchtreff_backup.sqlite3")

    @app.route("/admin/slot/<int:slot_id>", methods=["POST"])
    @admin_required
    def admin_update_slot(slot_id):
        label = request.form.get("label", "").strip()
        max_players = request.form.get("max_players", "").strip()

        if not label or not max_players.isdigit():
            flash("Bitte Slot-Name und maximale Plaetze angeben.", "error")
            return redirect(url_for("admin_dashboard"))

        max_players = int(max_players)
        if max_players < 1:
            flash("Max. Plaetze muessen mindestens 1 sein.", "error")
            return redirect(url_for("admin_dashboard"))

        db = get_db()
        db.execute(
            "UPDATE slots SET label = ?, max_players = ? WHERE id = ?",
            (label, max_players, slot_id),
        )
        db.commit()
        flash("Slot aktualisiert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/theme", methods=["POST"])
    @admin_required
    def admin_update_theme():
        theme = request.form.get("theme", "").strip()
        if theme not in THEMES:
            flash("Unbekanntes Design.", "error")
            return redirect(url_for("admin_dashboard"))

        db = get_db()
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('theme', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (theme,),
        )
        db.commit()
        flash("Design gespeichert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/bg-style", methods=["POST"])
    @admin_required
    def admin_update_bg_style():
        bg_style = request.form.get("bg_style", "").strip()
        if bg_style not in BG_STYLES:
            flash("Unbekannter Hintergrund-Effekt.", "error")
            return redirect(url_for("admin_dashboard"))

        db = get_db()
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('bg_style', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (bg_style,),
        )
        db.commit()
        flash("Hintergrund-Effekt gespeichert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/custom-image", methods=["POST"])
    @admin_required
    def admin_update_custom_image():
        image = request.form.get("custom_image", "").strip()
        if not image:
            flash("Bitte ein Bild auswaehlen.", "error")
            return redirect(url_for("admin_dashboard"))

        if image not in GALLERY_IMAGES:
            flash("Unbekanntes Bild.", "error")
            return redirect(url_for("admin_dashboard"))

        db = get_db()
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('custom_bg_image', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (image,),
        )
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('theme', 'custom_gallery') ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        )
        db.commit()
        flash("Hintergrundbild gespeichert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/intro-text", methods=["POST"])
    @admin_required
    def admin_update_intro_text():
        intro_text = request.form.get("intro_text", "").strip()
        if not intro_text:
            intro_text = DEFAULT_INTRO_TEXT

        db = get_db()
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('intro_text', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (intro_text,),
        )
        db.commit()
        flash("Intro-Text gespeichert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/waitlist-settings", methods=["POST"])
    @admin_required
    def admin_update_waitlist_settings():
        waitlist_limit = request.form.get("waitlist_limit", "").strip()
        slot_selection = request.form.get("slot_selection", "").strip()
        waitlist_mode = request.form.get("waitlist_mode", "").strip()

        if not waitlist_limit.isdigit() or int(waitlist_limit) < 0:
            flash("Bitte eine gueltige Wartelisten-Groesse angeben.", "error")
            return redirect(url_for("admin_dashboard"))

        if slot_selection not in ["one", "both"]:
            slot_selection = DEFAULT_SLOT_SELECTION

        if waitlist_mode not in ["with_waitlist", "open_for_all", "no_waitlist", "guests_only"]:
            waitlist_mode = DEFAULT_WAITLIST_MODE

        db = get_db()
        for key, value in [
            ("waitlist_limit", waitlist_limit),
            ("slot_selection", slot_selection),
            ("waitlist_mode", waitlist_mode),
        ]:
            db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        db.commit()
        flash("Wartelisten-Einstellungen gespeichert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/signup/<int:signup_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_signup(signup_id):
        db = get_db()
        db.execute("DELETE FROM signups WHERE id = ?", (signup_id,))
        db.commit()
        flash("Anmeldung geloescht.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/reset", methods=["POST"])
    @admin_required
    def admin_clear_signups():
        db = get_db()
        db.execute("DELETE FROM signups")
        db.execute("DELETE FROM signup_locks")
        db.commit()
        flash("Alle Anmeldungen wurden geloescht.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/admins")
    @admin_required
    def admin_users_list():
        db = get_db()
        users = db.execute("SELECT id, username FROM admin_users ORDER BY username").fetchall()
        return render_template("admin_users.html", users=users)

    @app.route("/admin/admins/add", methods=["POST"])
    @admin_required
    def admin_users_add():
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if not username or not password:
            flash("Bitte Benutzername und Passwort angeben.", "error")
            return redirect(url_for("admin_users_list"))

        db = get_db()
        existing = db.execute(
            "SELECT id FROM admin_users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            flash("Admin existiert bereits.", "error")
            return redirect(url_for("admin_users_list"))

        db.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
            (username, hash_password(password)),
        )
        db.commit()
        flash("Admin hinzugefuegt.", "success")
        return redirect(url_for("admin_users_list"))

    @app.route("/admin/admins/<int:user_id>/password", methods=["POST"])
    @admin_required
    def admin_users_password(user_id):
        password = request.form.get("password", "").strip()
        if not password:
            flash("Bitte ein Passwort angeben.", "error")
            return redirect(url_for("admin_users_list"))

        db = get_db()
        db.execute(
            "UPDATE admin_users SET password_hash = ? WHERE id = ?",
            (hash_password(password), user_id),
        )
        db.commit()
        flash("Passwort aktualisiert.", "success")
        return redirect(url_for("admin_users_list"))

    @app.route("/admin/admins/<int:user_id>/delete", methods=["POST"])
    @admin_required
    def admin_users_delete(user_id):
        db = get_db()
        row = db.execute("SELECT username FROM admin_users WHERE id = ?", (user_id,)).fetchone()
        if row and row["username"] == "admin":
            flash("Der Standard-Admin kann nicht geloescht werden.", "error")
            return redirect(url_for("admin_users_list"))

        db.execute("DELETE FROM admin_users WHERE id = ?", (user_id,))
        db.commit()
        flash("Admin geloescht.", "success")
        return redirect(url_for("admin_users_list"))

    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}

    return app


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
    return g.db


def get_current_week_date():
    return current_app.config["WEEK_START_DATE"]


def normalize_name(name):
    return " ".join(name.lower().split())


def hash_password(password):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 150000)
    return f"{salt.hex()}${digest.hex()}"


def check_password(password, stored):
    try:
        salt_hex, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    salt = bytes.fromhex(salt_hex)
    expected = bytes.fromhex(digest_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 150000)
    return hmac.compare_digest(digest, expected)


def get_slots_with_counts():
    week_date = get_current_week_date()
    db = get_db()
    slots = db.execute(
        "SELECT id, label, sort_order, max_players FROM slots ORDER BY sort_order"
    ).fetchall()
    result = []
    for slot in slots:
        count = db.execute(
            """
            SELECT COUNT(*) AS c FROM signups
            WHERE slot_id = ? AND week_date = ? AND status = 'confirmed'
            """,
            (slot["id"], week_date),
        ).fetchone()["c"]
        waitlist_count = db.execute(
            """
            SELECT COUNT(*) AS c FROM signups
            WHERE slot_id = ? AND week_date = ? AND status = 'waitlist'
            """,
            (slot["id"], week_date),
        ).fetchone()["c"]
        result.append(
            {
                "id": slot["id"],
                "label": slot["label"],
                "max_players": slot["max_players"],
                "count": count,
                "waitlist_count": waitlist_count,
                "full": count >= slot["max_players"],
                "waitlist_full": waitlist_count >= get_waitlist_limit(),
            }
        )
    return result


def get_signups_for_slot(slot_id, status):
    week_date = get_current_week_date()
    db = get_db()
    return db.execute(
        """
        SELECT id, name, name_normalized, is_member FROM signups
        WHERE slot_id = ? AND week_date = ? AND status = ?
        ORDER BY created_at ASC
        """,
        (slot_id, week_date, status),
    ).fetchall()


def get_status_for_slot(slot_id, week_date):
    db = get_db()
    slot = db.execute(
        "SELECT max_players FROM slots WHERE id = ?", (slot_id,)
    ).fetchone()
    if not slot:
        return "waitlist_full"

    confirmed = db.execute(
        """
        SELECT COUNT(*) AS c FROM signups
        WHERE slot_id = ? AND week_date = ? AND status = 'confirmed'
        """,
        (slot_id, week_date),
    ).fetchone()["c"]
    if confirmed < slot["max_players"]:
        return "confirmed"

    waitlist = db.execute(
        """
        SELECT COUNT(*) AS c FROM signups
        WHERE slot_id = ? AND week_date = ? AND status = 'waitlist'
        """,
        (slot_id, week_date),
    ).fetchone()["c"]
    if waitlist < get_waitlist_limit():
        return "waitlist"
    return "waitlist_full"


def get_theme_key():
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = 'theme'").fetchone()
    return row["value"] if row else DEFAULT_THEME


def get_bg_style():
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = 'bg_style'").fetchone()
    value = row["value"] if row else DEFAULT_BG_STYLE
    return value if value in BG_STYLES else DEFAULT_BG_STYLE


def get_custom_bg_image():
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = 'custom_bg_image'").fetchone()
    return row["value"] if row else DEFAULT_CUSTOM_IMAGE


def get_theme_config():
    key = get_theme_key()
    theme = THEMES.get(key, THEMES[DEFAULT_THEME]).copy()
    if key == "custom_gallery":
        image = get_custom_bg_image()
        theme = theme.copy()
        theme["background_url"] = url_for("static", filename=f"pictures/{image}")
    return theme


def get_raw_intro_text():
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = 'intro_text'").fetchone()
    return row["value"] if row else DEFAULT_INTRO_TEXT


def get_waitlist_limit():
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = 'waitlist_limit'").fetchone()
    return int(row["value"]) if row and row["value"].isdigit() else DEFAULT_WAITLIST_LIMIT


def get_slot_selection():
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = 'slot_selection'").fetchone()
    return row["value"] if row else DEFAULT_SLOT_SELECTION


def get_waitlist_mode():
    db = get_db()
    row = db.execute("SELECT value FROM settings WHERE key = 'waitlist_mode'").fetchone()
    return row["value"] if row else DEFAULT_WAITLIST_MODE


def next_thursday():
    today = date.today()
    days_ahead = (3 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def get_intro_text():
    raw = get_raw_intro_text()
    next_thu = next_thursday()
    weekday = next_thu.strftime("%A")
    german_weekdays = {
        "Monday": "Montag",
        "Tuesday": "Dienstag",
        "Wednesday": "Mittwoch",
        "Thursday": "Donnerstag",
        "Friday": "Freitag",
        "Saturday": "Samstag",
        "Sunday": "Sonntag",
    }
    weekday = german_weekdays.get(weekday, weekday)
    return raw.replace("{next_thursday}", f"{weekday}, {next_thu.strftime('%d.%m.%Y')}")


def send_guest_signup_notification(name, slot_id):
    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    admin_chat_ids = os.environ.get("TELEGRAM_ADMIN_CHAT_IDS", "")
    if not telegram_token or not admin_chat_ids:
        return

    message = f"Neue Gast-Anmeldung: {name} (Slot {slot_id})"
    for chat_id in admin_chat_ids.split(","):
        chat_id = chat_id.strip()
        if not chat_id:
            continue
        try:
            url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
            payload = {"chat_id": chat_id, "text": message}
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as response:
                response.read()
        except Exception:
            pass


THEMES = {
    "dark": {
        "label": "Dunkel",
        "background": "#121212",
        "surface": "#1e1e1e",
        "accent": "#4f98a3",
        "text": "#cdccca",
    },
    "light": {
        "label": "Hell",
        "background": "#f7f6f2",
        "surface": "#f9f8f5",
        "accent": "#01696f",
        "text": "#28251d",
    },
    "custom_gallery": {
        "label": "Eigenes Bild (Galerie)",
        "background": "#000000",
        "surface": "rgba(0,0,0,0.5)",
        "accent": "#4f98a3",
        "text": "#ffffff",
    },
}

BG_STYLES = {
    "bubbles": "Farbige Blasen",
    "padel_icons": "Padel-Ball-Icons",
    "none": "Kein Effekt",
}

GALLERY_IMAGES = [
    "wappen.png",
    "padel-court-1.jpg",
    "padel-court-2.jpg",
    "padel-court-3.jpg",
]


def init_db():
    db_path = current_app.config["DATABASE"]
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row  # ← Diese Zeile hinzufügen
    db.execute("PRAGMA foreign_keys = ON")
    db.execute("PRAGMA journal_mode = WAL")

    db.execute(
        """
        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            sort_order INTEGER NOT NULL,
            max_players INTEGER NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS signups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            name_normalized TEXT NOT NULL,
            slot_id INTEGER NOT NULL REFERENCES slots(id),
            week_date TEXT NOT NULL,
            status TEXT NOT NULL,
            is_member INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS signup_locks (
            week_date TEXT NOT NULL,
            name_normalized TEXT NOT NULL,
            PRIMARY KEY (week_date, name_normalized)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )

    existing = db.execute("SELECT COUNT(*) AS c FROM slots").fetchone()
    if existing["c"] == 0:
        db.execute(
            "INSERT INTO slots (label, sort_order, max_players) VALUES (?, ?, ?)",
            ("18:00 - 20:00", 1, 8),
        )
        db.execute(
            "INSERT INTO slots (label, sort_order, max_players) VALUES (?, ?, ?)",
            ("20:00 - 22:00", 2, 8),
        )

    existing_theme = db.execute("SELECT value FROM settings WHERE key = 'theme'").fetchone()
    if not existing_theme:
        db.execute("INSERT INTO settings (key, value) VALUES ('theme', ?)", (DEFAULT_THEME,))

    existing_bg = db.execute("SELECT value FROM settings WHERE key = 'bg_style'").fetchone()
    if not existing_bg:
        db.execute("INSERT INTO settings (key, value) VALUES ('bg_style', ?)", (DEFAULT_BG_STYLE,))

    existing_img = db.execute("SELECT value FROM settings WHERE key = 'custom_bg_image'").fetchone()
    if not existing_img:
        db.execute("INSERT INTO settings (key, value) VALUES ('custom_bg_image', ?)", (DEFAULT_CUSTOM_IMAGE,))

    existing_intro = db.execute("SELECT value FROM settings WHERE key = 'intro_text'").fetchone()
    if not existing_intro:
        db.execute("INSERT INTO settings (key, value) VALUES ('intro_text', ?)", (DEFAULT_INTRO_TEXT,))

    existing_wl = db.execute("SELECT value FROM settings WHERE key = 'waitlist_limit'").fetchone()
    if not existing_wl:
        db.execute("INSERT INTO settings (key, value) VALUES ('waitlist_limit', ?)", (str(DEFAULT_WAITLIST_LIMIT),))

    existing_slot_sel = db.execute("SELECT value FROM settings WHERE key = 'slot_selection'").fetchone()
    if not existing_slot_sel:
        db.execute("INSERT INTO settings (key, value) VALUES ('slot_selection', ?)", (DEFAULT_SLOT_SELECTION,))

    existing_wl_mode = db.execute("SELECT value FROM settings WHERE key = 'waitlist_mode'").fetchone()
    if not existing_wl_mode:
        db.execute("INSERT INTO settings (key, value) VALUES ('waitlist_mode', ?)", (DEFAULT_WAITLIST_MODE,))

    existing_admin = db.execute("SELECT id FROM admin_users WHERE username = 'admin'").fetchone()
    if not existing_admin:
        db.execute(
            "INSERT INTO admin_users (username, password_hash) VALUES (?, ?)",
            ("admin", hash_password(ADMIN_INITIAL_PASSWORD)),
        )

    db.commit()
    db.close()


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)
    return wrapped


app = create_app()
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=1905, debug=True)
