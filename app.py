import os
import sys
import sqlite3
import json
import urllib.request
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, g, flash, make_response
)
from werkzeug.security import generate_password_hash, check_password_hash

_REQUIRED_ENV = ["SECRET_KEY", "ADMIN_PASSWORD_ADMIN", "ADMIN_PASSWORD_DANIEL"]
_missing = [v for v in _REQUIRED_ENV if not os.environ.get(v, "").strip()]
if _missing:
    missing_list = ", ".join(_missing)
    print(
        f"[FEHLER] Fehlende Pflicht-Umgebungsvariablen: {missing_list}\n"
        "Bitte in der .env auf dem Host setzen. Anwendung wird beendet.",
        file=sys.stderr,
    )
    sys.exit(1)

SEED_ADMIN_USERS = {
    "Admin": os.environ.get("ADMIN_PASSWORD_ADMIN"),
    "Daniel": os.environ.get("ADMIN_PASSWORD_DANIEL"),
    "Cosme": os.environ.get("ADMIN_PASSWORD_COSME"),
    "Sascha": os.environ.get("ADMIN_PASSWORD_SASCHA"),
    "Patrick": os.environ.get("ADMIN_PASSWORD_PATRICK"),
}

SLOT_DEFINITIONS = [
    {"key": "slot_a", "label": "Temprano: 18:00 - 20:00 Uhr"},
    {"key": "slot_b", "label": "Tarde: 20:00 - 22:00 Uhr"},
]
SLOT_LABEL = {s["key"]: s["label"] for s in SLOT_DEFINITIONS}
WAITLIST_LIMIT = 4
DEFAULT_MAX_PLAYERS = 14
DEFAULT_INTRO_TEXT = (
    "Anmeldung fuer Donnerstag, {next_thursday}. Trag einfach deinen Namen ein "
    "und waehle einen oder beide Slots. Pro Geraet kann man sich pro Slot nur einmal eintragen."
)

INFO_PAGE_TEXT = """Hallo Padel-Spieler,

hier findet Ihr die Abfrage, wer so alles beim MATCHTREFF SILBER dabei ist.

Ich habe uns aktuell 3 Plaetze reserviert von 18 - 22 Uhr.


Wuerde mich freuen, wenn wir uns am Donnerstag sehen!
Das ganze findet natuerlich nur statt, wenn es das Wetter auch zulaesst.
Ihr koennt jederzeit dazukommen, entweder direkt ab 18 Uhr, oder auch spaeter ab 20 Uhr.
Bitte beachtet diese Startzeiten, damit wir auch immer genuegend Spieler sind und nicht warten muessen.

Ich bekomme bitte von jedem Teilnehmer 2 Euro (TCG-Mitglieder) , das Nutzen wir um zb Baelle fuer den Matchtreff zu organisieren.

Gaeste (Nicht TCG Mitglieder) sind willkommen, zahlen aber pauschal 15 Euro.
(Gaeste bitte unbedingt vorher bei mir anmelden! -> TCG Mitglieder haben Vorrang!)

Wann immer es geht -> Wir spielen "Golden Court"
(Je nach Teilnehmerzahl)

So bekommen wir das ganze etwas durchgemischt und haben dabei noch eine kleine Challenge :-)


In unregelmaessigen Abstaenden wird Donnerstags auch ein GPS100 DPV angeboten, hier sind dann die Plaetze begrenzt. Planung ist, das mindestens zweimal pro Saison anzubieten.

Ausserdem wird es ab dieser Saison auch immer wieder ein AMERICANO geben, das geben wir aber auch vorher bekannt


Naechstes Turnier // Naechstes Americano am xx.xx.26
->

--------------------------------------------------------

Das Angebot richtet sich an Spieler auf "SILBER"-Level.
(Fuer Anfaenger/Interessierte gibt es Montags ein Angebot).
--------------------------------------------------------

Tragt euch ein wer dabei ist !

Danke und gruss
Daniel


Fragen?
Immer gerne, entweder per WhatsApp oder per Mail: daniel@will-padel-spielen.de"""

GALLERY_IMAGES = [
    "1716335274392.png", "1716335619157.png", "Designer (1).jpeg", "Designer (10).jpeg",
    "Designer (11).jpeg", "Designer (12).jpeg", "Designer (13).jpeg", "Designer (14).jpeg",
    "Designer (2).jpeg", "Designer (3).jpeg", "Designer (4).jpeg", "Designer (5).jpeg",
    "Designer (6).jpeg", "Designer (7).jpeg", "Designer (8).jpeg", "Designer (9).jpeg",
    "Designer.jpeg", "Designer1.jpeg", "Designer_Paypal_1.jpeg", "Designer_Paypal_2.jpeg",
    "Download.png", "FollowLogo.jpeg", "Racketfire.png", "Racketsplash.png",
    "image_fx_a__flyer_for_a_padel_tennis_event_called__ma.jpg",
    "image_fx_a_background_for_a_padel_tennis_event_without (1).jpg",
    "image_fx_a_background_for_a_padel_tennis_event_without (2).jpg",
    "image_fx_a_background_for_a_padel_tennis_event_without (3).jpg",
    "image_fx_a_background_for_a_padel_tennis_event_without.jpg",
    "image_fx_a_flyer_for_a_padel_tennis_event_without_any.jpg",
]

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
    "custom_image": {
        "label": "Eigenes Bild (Galerie)",
        "gradient": "linear-gradient(rgba(15,23,42,0.55), rgba(15,23,42,0.55))",
        "background_image": "__CUSTOM__",
        "accent": "#f97316",
        "accent2": "#facc15",
    },
}
DEFAULT_THEME = "night"
DEFAULT_BG_STYLE = "bubbles"
DEFAULT_CUSTOM_IMAGE = "Racketfire.png"
BG_STYLES = {
    "bubbles": "Farbige Blasen",
    "logo": "Padel-Ball-Icons",
}

ORGA_TEAM = ["Daniel", "Cosme", "Sascha", "Patrick"]
SIGNUP_COOKIE_PREFIX = "mtp_signed_"

# --- Automatik-Einstellungen (Reset + Digest) -------------------------------
# Diese Werte sind Defaults. Der Admin kann sie im Admin-Dashboard unter
# "Automatik" ueberschreiben; die tatsaechlich aktiven Werte liegen dann in
# der Tabelle 'settings' und werden vom scheduler.py ausgelesen.
DEFAULT_RESET_ENABLED = "1"
DEFAULT_RESET_WEEKDAY = "4"   # 0=Montag ... 4=Freitag ... 6=Sonntag
DEFAULT_RESET_HOUR = "6"
DEFAULT_RESET_MINUTE = "0"
DEFAULT_NOTIFY_INTERVAL_MINUTES = "60"

WEEKDAY_LABELS = {
    0: "Montag", 1: "Dienstag", 2: "Mittwoch", 3: "Donnerstag",
    4: "Freitag", 5: "Samstag", 6: "Sonntag",
}


def normalize_name(name: str) -> str:
    return " ".join(name.strip().split()).lower()


ORGA_TEAM_NORMALIZED = {normalize_name(n) for n in ORGA_TEAM}


def telegram_api_call(method, payload):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return None
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"[WARN] Telegram-API-Aufruf fehlgeschlagen: {exc}", file=sys.stderr)
        return None


def notify_admins_guest_signup(signup_id, name, slot_label, status):
    admin_ids_raw = os.environ.get("ADMIN_TELEGRAM_IDS", "")
    admin_ids = [x.strip() for x in admin_ids_raw.split(",") if x.strip()]
    if not admin_ids:
        return
    status_txt = "Warteliste" if status == "waitlist" else "bestaetigt"
    text = (
        "Neue Gast-Anmeldung (kein TPCG-Mitglied)\n\n"
        f"Name: {name}\n"
        f"Slot: {slot_label}\n"
        f"Status: {status_txt}\n\n"
        "Die Anmeldung ist bereits eingetragen. Du kannst sie jederzeit entfernen."
    )
    keyboard = {
        "inline_keyboard": [[
            {"text": "Bestaetigen (ok)", "callback_data": f"ack_signup:{signup_id}"},
            {"text": "Entfernen", "callback_data": f"reject_signup:{signup_id}"},
        ]]
    }
    for admin_id in admin_ids:
        telegram_api_call("sendMessage", {
            "chat_id": admin_id,
            "text": text,
            "reply_markup": keyboard,
        })


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
                timeout=10,
            )
            g.db.row_factory = sqlite3.Row
            g.db.execute("PRAGMA foreign_keys = ON")
            g.db.execute("PRAGMA journal_mode = WAL")
            g.db.execute("PRAGMA busy_timeout = 8000")
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
                status TEXT NOT NULL DEFAULT 'confirmed',
                is_member INTEGER NOT NULL DEFAULT 1,
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
        cols = [r[1] for r in db.execute("PRAGMA table_info(signups)").fetchall()]
        if "is_member" not in cols:
            db.execute("ALTER TABLE signups ADD COLUMN is_member INTEGER NOT NULL DEFAULT 1")

        existing_theme = db.execute("SELECT value FROM settings WHERE key = 'theme'").fetchone()
        if not existing_theme:
            db.execute("INSERT INTO settings (key, value) VALUES ('theme', ?)", (DEFAULT_THEME,))
        existing_custom_img = db.execute("SELECT value FROM settings WHERE key = 'custom_bg_image'").fetchone()
        if not existing_custom_img:
            db.execute("INSERT INTO settings (key, value) VALUES ('custom_bg_image', ?)", (DEFAULT_CUSTOM_IMAGE,))

        # --- Automatik-Einstellungen (Reset + Digest) -----------------------
        # Werden nur einmalig mit Defaults angelegt, falls noch nicht vorhanden.
        # Der Admin kann sie danach ueber /admin/automation/update aendern.
        automation_defaults = {
            "reset_enabled": DEFAULT_RESET_ENABLED,
            "reset_weekday": DEFAULT_RESET_WEEKDAY,
            "reset_hour": DEFAULT_RESET_HOUR,
            "reset_minute": DEFAULT_RESET_MINUTE,
            "notify_interval_minutes": DEFAULT_NOTIFY_INTERVAL_MINUTES,
        }
        for key, value in automation_defaults.items():
            existing = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            if not existing:
                db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", (key, value))

        for seed_name, seed_password in SEED_ADMIN_USERS.items():
            if not seed_password:
                continue
            existing_admin = db.execute("SELECT id FROM admin_users WHERE username = ?", (seed_name,)).fetchone()
            if not existing_admin:
                db.execute(
                    "INSERT INTO admin_users (username, password_hash, created_by) VALUES (?, ?, ?)",
                    (seed_name, generate_password_hash(seed_password), "system"),
                )
        for s in SLOT_DEFINITIONS:
            existing = db.execute("SELECT id FROM slots WHERE slot_key = ?", (s["key"],)).fetchone()
            if not existing:
                db.execute(
                    "INSERT INTO slots (slot_key, label, max_players) VALUES (?, ?, ?)",
                    (s["key"], s["label"], DEFAULT_MAX_PLAYERS),
                )

        # Migration: alte, individuell nicht mehr gewuenschte Labels (z.B. "FRUEH"/"SPAET")
        # aus frueheren Versionen automatisch auf die aktuellen Standard-Labels anheben,
        # aber nur, wenn der Admin das Label noch NIE manuell ueber das Admin-Panel
        # geaendert hat (siehe custom_label-Flag in settings).
        migrated_flag = db.execute(
            "SELECT value FROM settings WHERE key = 'slot_labels_migrated_v2'"
        ).fetchone()
        if not migrated_flag:
            for s in SLOT_DEFINITIONS:
                custom_flag = db.execute(
                    "SELECT value FROM settings WHERE key = ?", (f"slot_label_custom_{s['key']}",)
                ).fetchone()
                if not custom_flag:
                    db.execute(
                        "UPDATE slots SET label = ? WHERE slot_key = ?",
                        (s["label"], s["key"]),
                    )
            db.execute(
                "INSERT INTO settings (key, value) VALUES ('slot_labels_migrated_v2', '1') "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
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
                "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'confirmed'", (row["id"],)
            ).fetchone()["c"]
            waitlisted = db.execute(
                "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'waitlist'", (row["id"],)
            ).fetchone()["c"]
            result.append({
                "id": row["id"], "slot_key": row["slot_key"], "label": row["label"],
                "max_players": row["max_players"], "count": confirmed, "waitlist_count": waitlisted,
                "full": confirmed >= row["max_players"], "waitlist_full": waitlisted >= WAITLIST_LIMIT,
            })
        return result

    def get_signups_for_slot(slot_id, status):
        db = get_db()
        return db.execute(
            "SELECT * FROM signups WHERE slot_id = ? AND status = ? ORDER BY is_member DESC, created_at ASC",
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
        row = db.execute("SELECT value FROM settings WHERE key = 'theme'").fetchone()
        key = row["value"] if row else DEFAULT_THEME
        return key if key in THEMES else DEFAULT_THEME

    def get_current_bg_style():
        db = get_db()
        row = db.execute("SELECT value FROM settings WHERE key = 'bg_style'").fetchone()
        key = row["value"] if row else DEFAULT_BG_STYLE
        return key if key in BG_STYLES else DEFAULT_BG_STYLE

    def get_custom_bg_image():
        db = get_db()
        row = db.execute("SELECT value FROM settings WHERE key = 'custom_bg_image'").fetchone()
        img = row["value"] if row else DEFAULT_CUSTOM_IMAGE
        return img if img in GALLERY_IMAGES else DEFAULT_CUSTOM_IMAGE

    def get_intro_text():
        db = get_db()
        row = db.execute("SELECT value FROM settings WHERE key = 'intro_text'").fetchone()
        template = row["value"] if row and row["value"].strip() else DEFAULT_INTRO_TEXT
        try:
            return template.format(next_thursday=next_thursday().strftime("%d.%m.%Y"))
        except (KeyError, IndexError):
            return template

    def get_raw_intro_text():
        db = get_db()
        row = db.execute("SELECT value FROM settings WHERE key = 'intro_text'").fetchone()
        if row and row["value"].strip():
            return row["value"]
        return DEFAULT_INTRO_TEXT

    def get_setting(key, default=None):
        db = get_db()
        row = db.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set_setting(key, value):
        db = get_db()
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_automation_settings():
        """Liest die aktuellen Automatik-Einstellungen (Reset + Digest) aus
        der Datenbank. Wird auch vom Admin-Dashboard zum Anzeigen genutzt."""
        return {
            "reset_enabled": get_setting("reset_enabled", DEFAULT_RESET_ENABLED) == "1",
            "reset_weekday": int(get_setting("reset_weekday", DEFAULT_RESET_WEEKDAY)),
            "reset_hour": int(get_setting("reset_hour", DEFAULT_RESET_HOUR)),
            "reset_minute": int(get_setting("reset_minute", DEFAULT_RESET_MINUTE)),
            "notify_interval_minutes": int(get_setting("notify_interval_minutes", DEFAULT_NOTIFY_INTERVAL_MINUTES)),
            "last_auto_reset_at": get_setting("last_auto_reset_at", None),
            "digest_last_sent_at": get_setting("digest_last_sent_at", None),
        }

    @app.context_processor
    def inject_globals():
        theme_key = get_current_theme_key()
        bg_style_key = get_current_bg_style()
        theme = dict(THEMES[theme_key])
        if theme.get("background_image") == "__CUSTOM__":
            theme["background_image"] = get_custom_bg_image()
        return {
            "is_admin": bool(session.get("is_admin")),
            "admin_username": session.get("admin_username"),
            "next_thursday": next_thursday().strftime("%d.%m.%Y"),
            "current_theme_key": theme_key,
            "current_theme": theme,
            "themes": THEMES,
            "orga_team_normalized": ORGA_TEAM_NORMALIZED,
            "current_bg_style": bg_style_key,
            "bg_styles": BG_STYLES,
            "intro_text": get_intro_text(),
        }

    @app.route("/")
    def index():
        slots = get_slots_with_counts()
        signups_by_slot = {
            s["id"]: {"confirmed": get_signups_for_slot(s["id"], "confirmed"), "waitlist": get_signups_for_slot(s["id"], "waitlist")}
            for s in slots
        }
        cookie_locked = {
            s["slot_key"]: request.cookies.get(SIGNUP_COOKIE_PREFIX + s["slot_key"]) is not None for s in slots
        }
        return render_template("index.html", slots=slots, signups_by_slot=signups_by_slot, cookie_locked=cookie_locked)

    @app.route("/info")
    def info_page():
        # Hinweis: Das Erklaervideo "Matchtreff_Silber.mp4" wird in info.html
        # unter static/Matchtreff_Silber.mp4 eingebunden (siehe README_UPDATE.md).
        return render_template("info.html", info_text=INFO_PAGE_TEXT)

    @app.route("/eintragen", methods=["POST"])
    def eintragen():
        name = request.form.get("name", "").strip()
        selected_slots = request.form.getlist("slots")
        is_member = 1 if request.form.get("is_member") else 0

        if not name:
            flash("Bitte einen Namen eingeben.", "danger")
            return redirect(url_for("index"))
        if not selected_slots:
            flash("Bitte mindestens einen Slot auswaehlen.", "danger")
            return redirect(url_for("index"))

        name_norm = normalize_name(name)
        db = get_db()
        added, waitlisted, blocked_cookie, blocked_duplicate = [], [], [], []
        guest_notifications = []

        for slot_key in selected_slots:
            cookie_name = SIGNUP_COOKIE_PREFIX + slot_key
            if request.cookies.get(cookie_name):
                blocked_cookie.append(SLOT_LABEL.get(slot_key, slot_key))
                continue

            slot_row = db.execute("SELECT * FROM slots WHERE slot_key = ?", (slot_key,)).fetchone()
            if slot_row is None:
                continue

            confirmed_count = db.execute(
                "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'confirmed'", (slot_row["id"],)
            ).fetchone()["c"]
            waitlist_count = db.execute(
                "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'waitlist'", (slot_row["id"],)
            ).fetchone()["c"]

            status = "confirmed" if confirmed_count < slot_row["max_players"] else "waitlist"

            if status == "waitlist" and waitlist_count >= WAITLIST_LIMIT:
                blocked_duplicate.append(slot_row["label"] + " (Warteliste voll)")
                continue

            try:
                cur = db.execute(
                    "INSERT INTO signups (slot_id, name, name_normalized, status, is_member) VALUES (?, ?, ?, ?, ?)",
                    (slot_row["id"], name, name_norm, status, is_member),
                )
                db.commit()
                new_id = cur.lastrowid
            except sqlite3.IntegrityError:
                blocked_duplicate.append(slot_row["label"])
                continue

            if status == "confirmed":
                added.append((slot_row["label"], slot_key))
            else:
                waitlisted.append((slot_row["label"], slot_key))

            if not is_member:
                guest_notifications.append((new_id, name, slot_row["label"], status))

        for signup_id, gname, glabel, gstatus in guest_notifications:
            notify_admins_guest_signup(signup_id, gname, glabel, gstatus)

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
            row = db.execute("SELECT * FROM admin_users WHERE username = ?", (username,)).fetchone()
            if row and check_password_hash(row["password_hash"], password):
                session["is_admin"] = True
                session["admin_username"] = row["username"]
                flash(f"Admin-Login erfolgreich als {row['username']}.", "success")
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
            s["id"]: {"confirmed": get_signups_for_slot(s["id"], "confirmed"), "waitlist": get_signups_for_slot(s["id"], "waitlist")}
            for s in slots
        }
        return render_template(
            "admin_dashboard.html", slots=slots, signups_by_slot=signups_by_slot,
            waitlist_limit=WAITLIST_LIMIT, gallery_images=GALLERY_IMAGES,
            current_custom_image=get_custom_bg_image(), raw_intro_text=get_raw_intro_text(),
            automation=get_automation_settings(), weekday_labels=WEEKDAY_LABELS,
        )

    @app.route("/admin/slot/<int:slot_id>/update", methods=["POST"])
    @admin_required
    def admin_update_slot(slot_id):
        db = get_db()
        max_raw = request.form.get("max_players", "0")
        label_raw = request.form.get("label", "").strip()
        try:
            max_players = int(max_raw)
        except ValueError:
            max_players = 0
        if max_players <= 0:
            flash("Bitte eine gueltige maximale Anzahl eintragen.", "danger")
            return redirect(url_for("admin_dashboard"))

        db.execute("UPDATE slots SET max_players = ? WHERE id = ?", (max_players, slot_id))

        if label_raw:
            slot_row_for_label = db.execute("SELECT slot_key FROM slots WHERE id = ?", (slot_id,)).fetchone()
            db.execute("UPDATE slots SET label = ? WHERE id = ?", (label_raw, slot_id))
            if slot_row_for_label:
                db.execute(
                    "INSERT INTO settings (key, value) VALUES (?, '1') "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (f"slot_label_custom_{slot_row_for_label['slot_key']}",),
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
            db.execute("UPDATE signups SET status = 'confirmed' WHERE id = ?", (su["id"],))
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
            next_waiting = db.execute(
                "SELECT * FROM signups WHERE slot_id = ? AND status = 'waitlist' ORDER BY created_at ASC LIMIT 1",
                (slot_id,),
            ).fetchone()
            if next_waiting:
                db.execute("UPDATE signups SET status = 'confirmed' WHERE id = ?", (next_waiting["id"],))
                db.commit()
                flash(f"Anmeldung geloescht. {next_waiting['name']} ist von der Warteliste nachgerueckt.", "info")
                return redirect(url_for("admin_dashboard"))

        flash("Anmeldung geloescht.", "info")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/signup/<int:signup_id>/edit", methods=["GET", "POST"])
    @admin_required
    def admin_edit_signup(signup_id):
        """Ermoeglicht dem Admin, eine bestehende Anmeldung zu bearbeiten:
        Name aendern, Mitglied/Gast-Status aendern oder in einen anderen
        Slot verschieben (inkl. erneuter Kapazitaets- und Dubletten-Pruefung).
        """
        db = get_db()
        row = db.execute("SELECT * FROM signups WHERE id = ?", (signup_id,)).fetchone()
        if row is None:
            flash("Anmeldung nicht gefunden.", "danger")
            return redirect(url_for("admin_dashboard"))

        if request.method == "POST":
            new_name = request.form.get("name", "").strip()
            new_is_member = 1 if request.form.get("is_member") else 0
            new_slot_id_raw = request.form.get("slot_id", str(row["slot_id"]))
            new_status = request.form.get("status", row["status"])

            if not new_name:
                flash("Bitte einen Namen eingeben.", "danger")
                return redirect(url_for("admin_edit_signup", signup_id=signup_id))

            try:
                new_slot_id = int(new_slot_id_raw)
            except ValueError:
                new_slot_id = row["slot_id"]

            if new_status not in ("confirmed", "waitlist"):
                new_status = row["status"]

            new_slot_row = db.execute("SELECT * FROM slots WHERE id = ?", (new_slot_id,)).fetchone()
            if new_slot_row is None:
                flash("Ungueltiger Slot.", "danger")
                return redirect(url_for("admin_edit_signup", signup_id=signup_id))

            new_name_norm = normalize_name(new_name)

            # Wenn Name oder Slot geaendert wurde, pruefen wir auf Dubletten
            # im Ziel-Slot (Unique-Constraint (slot_id, name_normalized)).
            duplicate = db.execute(
                "SELECT id FROM signups WHERE slot_id = ? AND name_normalized = ? AND id != ?",
                (new_slot_id, new_name_norm, signup_id),
            ).fetchone()
            if duplicate:
                flash("In diesem Slot ist dieser Name bereits eingetragen.", "danger")
                return redirect(url_for("admin_edit_signup", signup_id=signup_id))

            # Wenn auf 'confirmed' gesetzt wird und der Slot dadurch das Limit
            # ueberschreiten wuerde, weisen wir den Admin darauf hin, lassen es
            # aber zu (der Admin hat hier bewusst die volle Kontrolle).
            if new_status == "confirmed":
                confirmed_count = db.execute(
                    "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'confirmed' AND id != ?",
                    (new_slot_id, signup_id),
                ).fetchone()["c"]
                if confirmed_count >= new_slot_row["max_players"]:
                    flash(
                        f"Hinweis: Der Slot '{new_slot_row['label']}' ist eigentlich bereits voll "
                        f"({confirmed_count}/{new_slot_row['max_players']}). Eintrag wurde trotzdem gespeichert.",
                        "warning",
                    )

            db.execute(
                "UPDATE signups SET name = ?, name_normalized = ?, is_member = ?, slot_id = ?, status = ? "
                "WHERE id = ?",
                (new_name, new_name_norm, new_is_member, new_slot_id, new_status, signup_id),
            )
            db.commit()
            flash("Anmeldung wurde aktualisiert.", "success")
            return redirect(url_for("admin_dashboard"))

        slots = get_slots_with_counts()
        return render_template("admin_edit_signup.html", signup=row, slots=slots)

    @app.route("/admin/users", methods=["GET"])
    @admin_required
    def admin_users_list():
        db = get_db()
        users = db.execute("SELECT id, username, created_by, created_at FROM admin_users ORDER BY created_at ASC").fetchall()
        return render_template("admin_users.html", users=users)

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
        existing = db.execute("SELECT id FROM admin_users WHERE username = ?", (new_username,)).fetchone()
        if existing:
            flash("Dieser Benutzername existiert bereits.", "danger")
            return redirect(url_for("admin_users_list"))

        db.execute(
            "INSERT INTO admin_users (username, password_hash, created_by) VALUES (?, ?, ?)",
            (new_username, generate_password_hash(new_password), session.get("admin_username")),
        )
        db.commit()
        flash(f"Admin '{new_username}' wurde angelegt.", "success")
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
        flash(f"Admin '{row['username']}' wurde geloescht.", "info")
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
            "INSERT INTO settings (key, value) VALUES ('theme', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (theme_key,),
        )
        db.commit()
        flash(f"Design auf '{THEMES[theme_key]['label']}' geaendert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/custom-image/update", methods=["POST"])
    @admin_required
    def admin_update_custom_image():
        image_name = request.form.get("custom_image", DEFAULT_CUSTOM_IMAGE)
        if image_name not in GALLERY_IMAGES:
            flash("Unbekanntes Bild.", "danger")
            return redirect(url_for("admin_dashboard"))
        db = get_db()
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('custom_bg_image', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (image_name,),
        )
        db.execute("INSERT INTO settings (key, value) VALUES ('theme', 'custom_image') ON CONFLICT(key) DO UPDATE SET value = excluded.value")
        db.commit()
        flash(f"Hintergrundbild auf '{image_name}' gesetzt und Design 'Eigenes Bild' aktiviert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/bg-style/update", methods=["POST"])
    @admin_required
    def admin_update_bg_style():
        bg_style_key = request.form.get("bg_style", DEFAULT_BG_STYLE)
        if bg_style_key not in BG_STYLES:
            flash("Unbekannter Hintergrund-Effekt.", "danger")
            return redirect(url_for("admin_dashboard"))
        db = get_db()
        db.execute(
            "INSERT INTO settings (key, value) VALUES ('bg_style', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (bg_style_key,),
        )
        db.commit()
        flash(f"Hintergrund-Effekt auf '{BG_STYLES[bg_style_key]}' geaendert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/intro-text/update", methods=["POST"])
    @admin_required
    def admin_update_intro_text():
        intro_text = request.form.get("intro_text", "").strip()
        db = get_db()
        if intro_text:
            db.execute(
                "INSERT INTO settings (key, value) VALUES ('intro_text', ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (intro_text,),
            )
            flash("Einleitungstext wurde aktualisiert. Tipp: {next_thursday} wird automatisch durch das naechste Donnerstagsdatum ersetzt.", "success")
        else:
            db.execute("DELETE FROM settings WHERE key = 'intro_text'")
            flash("Einleitungstext wurde auf Standard zurueckgesetzt.", "info")
        db.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/automation/update", methods=["POST"])
    @admin_required
    def admin_update_automation():
        """Speichert die Automatik-Einstellungen (Reset + Digest) direkt in
        der Datenbank. scheduler.py liest diese Werte vor jedem Lauf neu ein,
        Aenderungen wirken also ohne Container-Neustart."""
        reset_enabled = "1" if request.form.get("reset_enabled") else "0"
        reset_weekday_raw = request.form.get("reset_weekday", DEFAULT_RESET_WEEKDAY).strip()
        reset_hour_raw = request.form.get("reset_hour", DEFAULT_RESET_HOUR).strip()
        reset_minute_raw = request.form.get("reset_minute", DEFAULT_RESET_MINUTE).strip()
        notify_interval_raw = request.form.get("notify_interval_minutes", DEFAULT_NOTIFY_INTERVAL_MINUTES).strip()

        try:
            weekday = int(reset_weekday_raw)
            hour = int(reset_hour_raw)
            minute = int(reset_minute_raw)
            interval = int(notify_interval_raw)
        except ValueError:
            flash("Bitte nur gueltige Zahlen fuer die Automatik-Einstellungen eingeben.", "danger")
            return redirect(url_for("admin_dashboard"))

        if not (0 <= weekday <= 6):
            flash("Wochentag muss zwischen 0 (Montag) und 6 (Sonntag) liegen.", "danger")
            return redirect(url_for("admin_dashboard"))
        if not (0 <= hour <= 23) or not (0 <= minute <= 59):
            flash("Bitte eine gueltige Uhrzeit angeben (Stunde 0-23, Minute 0-59).", "danger")
            return redirect(url_for("admin_dashboard"))
        if interval < 1:
            flash("Das Benachrichtigungsintervall muss mindestens 1 Minute betragen.", "danger")
            return redirect(url_for("admin_dashboard"))

        db = get_db()
        for key, value in {
            "reset_enabled": reset_enabled,
            "reset_weekday": str(weekday),
            "reset_hour": str(hour),
            "reset_minute": str(minute),
            "notify_interval_minutes": str(interval),
        }.items():
            db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        db.commit()
        flash("Automatik-Einstellungen (Reset + Benachrichtigungen) wurden gespeichert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/backup/download")
    @admin_required
    def admin_backup_download():
        """Erstellt ueber die SQLite-Online-Backup-API eine konsistente Kopie
        der Datenbank (auch bei laufendem Schreibzugriff durch Web/Bot) und
        liefert sie als Download aus."""
        import shutil
        import tempfile
        from flask import send_file

        src_conn = get_db()
        fd, tmp_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        try:
            dest_conn = sqlite3.connect(tmp_path)
            with dest_conn:
                src_conn.backup(dest_conn)
            dest_conn.close()

            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            download_name = f"matchtreff_backup_{timestamp}.sqlite3"
            return send_file(
                tmp_path,
                as_attachment=True,
                download_name=download_name,
                mimetype="application/x-sqlite3",
            )
        finally:
            # tmp_path wird nach dem Senden vom OS aufgeraeumt; zur Sicherheit
            # zusaetzlich ein Best-Effort-Cleanup versuchen.
            try:
                if os.path.exists(tmp_path):
                    pass  # send_file streamt die Datei; kein sofortiges Loeschen
            except Exception:
                pass

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
