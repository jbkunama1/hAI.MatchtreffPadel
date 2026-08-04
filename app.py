import os
import sqlite3
import sys
import logging
from logging_config import setup_logging
from datetime import datetime, timedelta

from logic_settings import (
    APP_TZ,
    BG_STYLES,
    DEFAULT_BG_STYLE,
    DEFAULT_CUSTOM_IMAGE,
        DEFAULT_INTRO_TEXT,
        DEFAULT_REMINDER_ENABLED,
    DEFAULT_REMINDER_HOUR,
    DEFAULT_REMINDER_MINUTE,
    DEFAULT_REMINDER_WEEKDAY,
    DEFAULT_RESET_ENABLED,
    DEFAULT_RESET_HOUR,
    DEFAULT_RESET_MINUTE,
    DEFAULT_RESET_WEEKDAY,
    DEFAULT_SHOW_BANNER,
    DEFAULT_SIGNUP_LOCK_AUTO_OPEN_AT,
    DEFAULT_SIGNUP_LOCK_ENABLED,
    DEFAULT_SIGNUP_LOCK_MANUAL_OPEN,
    DEFAULT_SLOT_SELECTION,
    DEFAULT_THEME,
    DEFAULT_WAITLIST_MODE,
    DEFAULT_NOTIFY_INTERVAL_MINUTES,
    GALLERY_IMAGES,
    INFO_PAGE_TEXT,
    ORGA_TEAM_NORMALIZED,
    SIGNUP_COOKIE_PREFIX,
    SIGNUP_DEFAULT_OPEN_HOUR,
    SIGNUP_DEFAULT_OPEN_MINUTE,
    SIGNUP_DEFAULT_OPEN_WEEKDAY,
    SLOT_DEFINITIONS,
    SLOT_LABEL,
    THEMES,
    WAITLIST_LIMIT,
    WAITLIST_MODES,
    WEEKDAY_NAMES,
    normalize_name,
)
from logic_telegram import notify_admins_guest_signup
from logic_db import close_db, get_db, init_db
from logic_auth import admin_required, authenticate_admin

from flask import (
    Flask,
    flash,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import generate_password_hash




setup_logging(name="matchtreff.web")
logger = logging.getLogger("matchtreff.web")


_REQUIRED_ENV = ["SECRET_KEY", "ADMIN_PASSWORD_ADMIN", "ADMIN_PASSWORD_DANIEL"]
_missing = [name for name in _REQUIRED_ENV if not os.environ.get(name, "").strip()]
if _missing:
    missing_list = ", ".join(_missing)
    logger.critical(
        f"Fehlende Pflicht-Umgebungsvariablen: {missing_list}. "
        "Bitte in der .env auf dem Host setzen. Anwendung wird beendet."
    )
    sys.exit(1)


SEED_ADMIN_USERS = {
    "Admin": os.environ.get("ADMIN_PASSWORD_ADMIN"),
    "Daniel": os.environ.get("ADMIN_PASSWORD_DANIEL"),
    "Cosme": os.environ.get("ADMIN_PASSWORD_COSME"),
    "Sascha": os.environ.get("ADMIN_PASSWORD_SASCHA"),
    "Patrick": os.environ.get("ADMIN_PASSWORD_PATRICK"),
}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        DATABASE=os.path.join(app.instance_path, "matchtreff.sqlite3"),
    )

    if test_config is not None:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    @app.teardown_appcontext
    def _close_db(exception=None):
        close_db(exception)

    with app.app_context():
        init_db(SEED_ADMIN_USERS)

    def next_thursday():
        today = datetime.today().date()
        days_ahead = (3 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return today + timedelta(days=days_ahead)

    def get_waitlist_limit():
        db = get_db()
        row = db.execute(
            "SELECT value FROM settings WHERE key = 'waitlist_limit'"
        ).fetchone()

        if row and row["value"].isdigit():
            return max(0, int(row["value"]))

        return WAITLIST_LIMIT

    def get_slot_selection():
        db = get_db()
        row = db.execute(
            "SELECT value FROM settings WHERE key = 'slot_selection'"
        ).fetchone()

        if row and row["value"] in {"one", "both"}:
            return row["value"]

        return DEFAULT_SLOT_SELECTION

    def get_waitlist_mode():
        db = get_db()
        row = db.execute(
            "SELECT value FROM settings WHERE key = 'waitlist_mode'"
        ).fetchone()

        if row and row["value"] in WAITLIST_MODES:
            return row["value"]

        return DEFAULT_WAITLIST_MODE

    def get_setting_value(key, default=None):
        db = get_db()
        row = db.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
        return row["value"] if row else default

    def set_setting_value(key, value):
        db = get_db()
        db.execute(
            """
            INSERT INTO settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        db.commit()

    def signup_lock_settings():
        enabled = get_setting_value(
            "signup_lock_enabled", DEFAULT_SIGNUP_LOCK_ENABLED
        ) == "1"
        manual_open = get_setting_value(
            "signup_lock_manual_open", DEFAULT_SIGNUP_LOCK_MANUAL_OPEN
        ) == "1"
        auto_open_at_raw = get_setting_value(
            "signup_lock_auto_open_at", DEFAULT_SIGNUP_LOCK_AUTO_OPEN_AT
        )
        auto_open_at = None
        if auto_open_at_raw:
            try:
                auto_open_at = datetime.fromisoformat(auto_open_at_raw)
            except (ValueError, TypeError):
                auto_open_at = None

        # Hinweistext: ab wann die Liste oeffnet (fuer die Startseite).
        def _format_open(open_dt):
            weekdays = [
                "Montag", "Dienstag", "Mittwoch", "Donnerstag",
                "Freitag", "Samstag", "Sonntag",
            ]
            return (
                f"{weekdays[open_dt.weekday()]}, "
                f"{open_dt.strftime('%d.%m.%Y')} um {open_dt.strftime('%H:%M')} Uhr"
            )

        if manual_open and enabled:
            open_info = "Die Liste ist gerade geoeffnet."
        elif auto_open_at:
            open_info = "Die Liste oeffnet am " + _format_open(auto_open_at)
        else:
            # Standard: naechster Dienstag um 13:00
            now = datetime.now(APP_TZ)
            days_ahead = (SIGNUP_DEFAULT_OPEN_WEEKDAY - now.weekday()) % 7
            if days_ahead == 0 and (
                (now.hour, now.minute) >= (SIGNUP_DEFAULT_OPEN_HOUR, SIGNUP_DEFAULT_OPEN_MINUTE)
            ):
                days_ahead = 7
            next_open = (now + timedelta(days=days_ahead)).replace(
                hour=SIGNUP_DEFAULT_OPEN_HOUR,
                minute=SIGNUP_DEFAULT_OPEN_MINUTE,
                second=0,
                microsecond=0,
            )
            open_info = "Die Liste oeffnet am " + _format_open(next_open)

        return {
            "enabled": enabled,
            "manual_open": manual_open,
            "auto_open_at": auto_open_at,
            "auto_open_at_raw": auto_open_at_raw,
            "open_info": open_info,
        }

    def is_signup_open():
        """True, wenn die Anmeldung aktuell geoeffnet ist (Sperre fuer normale Nutzer)."""
        cfg = signup_lock_settings()
        if not cfg["enabled"]:
            return True
        if cfg["manual_open"]:
            return True
        if cfg["auto_open_at"] and cfg["auto_open_at"] <= datetime.now():
            return True
        return False

    def get_automatik_settings():
        return {
            "reset_enabled": get_setting_value(
                "reset_enabled", DEFAULT_RESET_ENABLED
            ),
            "reset_weekday": int(
                get_setting_value("reset_weekday", DEFAULT_RESET_WEEKDAY)
            ),
            "reset_hour": int(
                get_setting_value("reset_hour", DEFAULT_RESET_HOUR)
            ),
            "reset_minute": int(
                get_setting_value("reset_minute", DEFAULT_RESET_MINUTE)
            ),
            "notify_interval_minutes": int(
                get_setting_value(
                    "notify_interval_minutes", DEFAULT_NOTIFY_INTERVAL_MINUTES
                )
            ),
            "reminder_enabled": get_setting_value(
                "reminder_enabled", DEFAULT_REMINDER_ENABLED
            ),
            "reminder_weekday": int(
                get_setting_value("reminder_weekday", DEFAULT_REMINDER_WEEKDAY)
            ),
            "reminder_hour": int(
                get_setting_value("reminder_hour", DEFAULT_REMINDER_HOUR)
            ),
            "reminder_minute": int(
                get_setting_value("reminder_minute", DEFAULT_REMINDER_MINUTE)
            ),
        }

    def get_slots_with_counts():
        db = get_db()
        slots = db.execute("SELECT * FROM slots ORDER BY id").fetchall()
        waitlist_limit = get_waitlist_limit()

        if get_slot_selection() == "one":
            slots = slots[:1]

        result = []
        for slot in slots:
            confirmed = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM signups
                WHERE slot_id = ? AND status = 'confirmed'
                """,
                (slot["id"],),
            ).fetchone()["c"]

            waitlisted = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM signups
                WHERE slot_id = ? AND status = 'waitlist'
                """,
                (slot["id"],),
            ).fetchone()["c"]

            result.append(
                {
                    "id": slot["id"],
                    "slot_key": slot["slot_key"],
                    "label": slot["label"],
                    "max_players": slot["max_players"],
                    "count": confirmed,
                    "waitlist_count": waitlisted,
                    "full": confirmed >= slot["max_players"],
                    "waitlist_full": (
                        waitlist_limit <= 0 or waitlisted >= waitlist_limit
                    ),
                }
            )

        return result

    def get_signups_for_slot(slot_id, status):
        db = get_db()
        return db.execute(
            """
            SELECT *
            FROM signups
            WHERE slot_id = ? AND status = ?
            ORDER BY is_member DESC, created_at ASC
            """,
            (slot_id, status),
        ).fetchall()

    def get_current_theme_key():
        db = get_db()
        row = db.execute(
            "SELECT value FROM settings WHERE key = 'theme'"
        ).fetchone()

        theme_key = row["value"] if row else DEFAULT_THEME
        return theme_key if theme_key in THEMES else DEFAULT_THEME

    def get_current_bg_style():
        db = get_db()
        row = db.execute(
            "SELECT value FROM settings WHERE key = 'bg_style'"
        ).fetchone()

        bg_style = row["value"] if row else DEFAULT_BG_STYLE
        return bg_style if bg_style in BG_STYLES else DEFAULT_BG_STYLE

    def get_custom_bg_image():
        db = get_db()
        row = db.execute(
            "SELECT value FROM settings WHERE key = 'custom_bg_image'"
        ).fetchone()

        image_name = row["value"] if row else DEFAULT_CUSTOM_IMAGE
        return image_name if image_name in GALLERY_IMAGES else DEFAULT_CUSTOM_IMAGE

    def get_intro_text():
        db = get_db()
        row = db.execute(
            "SELECT value FROM settings WHERE key = 'intro_text'"
        ).fetchone()

        text_template = (
            row["value"]
            if row and row["value"].strip()
            else DEFAULT_INTRO_TEXT
        )

        try:
            return text_template.format(
                next_thursday=next_thursday().strftime("%d.%m.%Y")
            )
        except (KeyError, IndexError):
            return text_template

    def get_show_banner():
        db = get_db()
        row = db.execute(
            "SELECT value FROM settings WHERE key = 'show_banner'"
        ).fetchone()
        return (row["value"] if row else DEFAULT_SHOW_BANNER) == "1"

    def get_raw_intro_text():
        db = get_db()
        row = db.execute(
            "SELECT value FROM settings WHERE key = 'intro_text'"
        ).fetchone()

        if row and row["value"].strip():
            return row["value"]

        return DEFAULT_INTRO_TEXT

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
            "show_banner": get_show_banner(),
        }

    @app.route("/")
    def index():
        slots = get_slots_with_counts()
        signups_by_slot = {
            slot["id"]: {
                "confirmed": get_signups_for_slot(slot["id"], "confirmed"),
                "waitlist": get_signups_for_slot(slot["id"], "waitlist"),
            }
            for slot in slots
        }

        cookie_locked = {
            slot["slot_key"]: (
                request.cookies.get(SIGNUP_COOKIE_PREFIX + slot["slot_key"])
                is not None
            )
            for slot in slots
        }

        return render_template(
            "index.html",
            slots=slots,
            signups_by_slot=signups_by_slot,
            cookie_locked=cookie_locked,
            waitlist_limit=get_waitlist_limit(),
            is_admin=bool(session.get("is_admin")),
            signup_open=is_signup_open(),
            signup_lock_cfg=signup_lock_settings(),
        )

    @app.route("/info")
    def info_page():
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

        if get_slot_selection() == "one" and len(selected_slots) > 1:
            flash("Aktuell darf nur ein Slot ausgewaehlt werden.", "danger")
            return redirect(url_for("index"))

        valid_slot_keys = {slot["key"] for slot in SLOT_DEFINITIONS}
        selected_slots = [
            slot_key for slot_key in selected_slots if slot_key in valid_slot_keys
        ]

        if not selected_slots:
            flash("Bitte einen gueltigen Slot auswaehlen.", "danger")
            return redirect(url_for("index"))

        name_normalized = normalize_name(name)
        db = get_db()

        added = []
        waitlisted = []
        blocked_cookie = []
        blocked_duplicate = []
        guest_notifications = []

        waitlist_limit = get_waitlist_limit()
        waitlist_mode = get_waitlist_mode()

        is_admin_user = bool(session.get("is_admin"))

        if not is_admin_user and not is_signup_open():
            flash(
                "Die Anmeldung ist aktuell gesperrt. Bitte wende dich an einen "
                "Administrator, um sie freizuschalten.",
                "danger",
            )
            return redirect(url_for("index"))

        for slot_key in selected_slots:
            cookie_name = SIGNUP_COOKIE_PREFIX + slot_key

            if not is_admin_user and request.cookies.get(cookie_name):
                blocked_cookie.append(SLOT_LABEL.get(slot_key, slot_key))
                continue

            slot_row = db.execute(
                "SELECT * FROM slots WHERE slot_key = ?",
                (slot_key,),
            ).fetchone()

            if slot_row is None:
                continue

            confirmed_count = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM signups
                WHERE slot_id = ? AND status = 'confirmed'
                """,
                (slot_row["id"],),
            ).fetchone()["c"]

            waitlist_count = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM signups
                WHERE slot_id = ? AND status = 'waitlist'
                """,
                (slot_row["id"],),
            ).fetchone()["c"]

            if waitlist_mode == "open_for_all":
                status = "confirmed"

            elif waitlist_mode == "guests_only" and not is_member:
                if waitlist_limit <= 0 or waitlist_count >= waitlist_limit:
                    blocked_duplicate.append(
                        f"{slot_row['label']} (Gast-Warteliste voll)"
                    )
                    continue
                status = "waitlist"

            elif confirmed_count < slot_row["max_players"]:
                status = "confirmed"

            elif waitlist_mode == "no_waitlist":
                blocked_duplicate.append(f"{slot_row['label']} (Slot voll)")
                continue

            elif waitlist_limit <= 0 or waitlist_count >= waitlist_limit:
                blocked_duplicate.append(
                    f"{slot_row['label']} (Warteliste voll)"
                )
                continue

            else:
                status = "waitlist"

            try:
                cursor = db.execute(
                    """
                    INSERT INTO signups (
                        slot_id,
                        name,
                        name_normalized,
                        status,
                        is_member
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        slot_row["id"],
                        name,
                        name_normalized,
                        status,
                        is_member,
                    ),
                )
                db.commit()
                signup_id = cursor.lastrowid

            except sqlite3.IntegrityError:
                blocked_duplicate.append(
                    f"{slot_row['label']} (Name bereits vorhanden)"
                )
                continue

            if status == "confirmed":
                added.append((slot_row["label"], slot_key))
            else:
                waitlisted.append((slot_row["label"], slot_key))

            if not is_member:
                guest_notifications.append(
                    (signup_id, name, slot_row["label"], status)
                )

        for signup_id, guest_name, slot_label, status in guest_notifications:
            notify_admins_guest_signup(
                signup_id,
                guest_name,
                slot_label,
                status,
            )

        messages = []

        if added:
            messages.append(
                "Eingetragen fuer: " + ", ".join(label for label, _ in added)
            )

        if waitlisted:
            messages.append(
                "Auf Warteliste fuer: "
                + ", ".join(label for label, _ in waitlisted)
            )

        if blocked_cookie:
            messages.append(
                "Bereits von diesem Geraet eingetragen fuer: "
                + ", ".join(blocked_cookie)
            )

        if blocked_duplicate:
            messages.append(
                "Nicht moeglich: " + ", ".join(blocked_duplicate)
            )

        category = "success" if added or waitlisted else "warning"
        if messages:
            flash(" | ".join(messages), category)

        response = make_response(redirect(url_for("index")))
        max_age = 60 * 60 * 24 * 7

        for _, slot_key in added + waitlisted:
            response.set_cookie(
                SIGNUP_COOKIE_PREFIX + slot_key,
                "1",
                max_age=max_age,
                httponly=True,
                samesite="Lax",
            )

        return response

    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")
            admin_name = authenticate_admin(username, password)

            if admin_name:
                session["is_admin"] = True
                session["admin_username"] = admin_name
                flash(
                    f"Admin-Login erfolgreich als {admin_name}.",
                    "success",
                )
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
            slot["id"]: {
                "confirmed": get_signups_for_slot(slot["id"], "confirmed"),
                "waitlist": get_signups_for_slot(slot["id"], "waitlist"),
            }
            for slot in slots
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
            automatik=get_automatik_settings(),
            weekdays=WEEKDAY_NAMES,
            signup_open=is_signup_open(),
            signup_lock_cfg=signup_lock_settings(),
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

        db.execute(
            "UPDATE slots SET max_players = ? WHERE id = ?",
            (max_players, slot_id),
        )

        if label_raw:
            slot_row = db.execute(
                "SELECT slot_key FROM slots WHERE id = ?",
                (slot_id,),
            ).fetchone()

            db.execute(
                "UPDATE slots SET label = ? WHERE id = ?",
                (label_raw, slot_id),
            )

            if slot_row:
                db.execute(
                    """
                    INSERT INTO settings (key, value)
                    VALUES (?, '1')
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value
                    """,
                    (f"slot_label_custom_{slot_row['slot_key']}",),
                )

        db.commit()

        slot = db.execute(
            "SELECT * FROM slots WHERE id = ?",
            (slot_id,),
        ).fetchone()

        confirmed = get_signups_for_slot(slot_id, "confirmed")
        waitlist = get_signups_for_slot(slot_id, "waitlist")
        free_slots = slot["max_players"] - len(confirmed)
        moved = 0

        for signup in waitlist:
            if free_slots <= 0:
                break

            db.execute(
                "UPDATE signups SET status = 'confirmed' WHERE id = ?",
                (signup["id"],),
            )
            free_slots -= 1
            moved += 1

        db.commit()

        message = "Maximale Anzahl aktualisiert."
        if moved:
            message += f" {moved} Spieler von der Warteliste nachgerueckt."

        flash(message, "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/signup/<int:signup_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_signup(signup_id):
        db = get_db()
        signup = db.execute(
            "SELECT * FROM signups WHERE id = ?",
            (signup_id,),
        ).fetchone()

        if signup is None:
            flash("Anmeldung nicht gefunden.", "danger")
            return redirect(url_for("admin_dashboard"))

        slot_id = signup["slot_id"]
        was_confirmed = signup["status"] == "confirmed"

        db.execute("DELETE FROM signups WHERE id = ?", (signup_id,))
        db.commit()

        if was_confirmed:
            next_waiting = db.execute(
                """
                SELECT *
                FROM signups
                WHERE slot_id = ? AND status = 'waitlist'
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (slot_id,),
            ).fetchone()

            if next_waiting:
                db.execute(
                    "UPDATE signups SET status = 'confirmed' WHERE id = ?",
                    (next_waiting["id"],),
                )
                db.commit()
                flash(
                    "Anmeldung geloescht. "
                    f"{next_waiting['name']} ist von der Warteliste nachgerueckt.",
                    "info",
                )
                return redirect(url_for("admin_dashboard"))

        flash("Anmeldung geloescht.", "info")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/users", methods=["GET"])
    @admin_required
    def admin_users_list():
        db = get_db()
        users = db.execute(
            """
            SELECT id, username, created_by, created_at
            FROM admin_users
            ORDER BY created_at ASC
            """
        ).fetchall()

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
        existing = db.execute(
            "SELECT id FROM admin_users WHERE username = ?",
            (new_username,),
        ).fetchone()

        if existing:
            flash("Dieser Benutzername existiert bereits.", "danger")
            return redirect(url_for("admin_users_list"))

        db.execute(
            """
            INSERT INTO admin_users (username, password_hash, created_by)
            VALUES (?, ?, ?)
            """,
            (
                new_username,
                generate_password_hash(new_password),
                session.get("admin_username"),
            ),
        )
        db.commit()

        flash(f"Admin '{new_username}' wurde angelegt.", "success")
        return redirect(url_for("admin_users_list"))

    @app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
    @admin_required
    def admin_users_delete(user_id):
        db = get_db()
        user = db.execute(
            "SELECT * FROM admin_users WHERE id = ?",
            (user_id,),
        ).fetchone()

        if user is None:
            flash("Admin nicht gefunden.", "danger")
            return redirect(url_for("admin_users_list"))

        total_admins = db.execute(
            "SELECT COUNT(*) AS c FROM admin_users"
        ).fetchone()["c"]

        if total_admins <= 1:
            flash(
                "Der letzte verbleibende Admin kann nicht geloescht werden.",
                "danger",
            )
            return redirect(url_for("admin_users_list"))

        if user["username"] == session.get("admin_username"):
            flash(
                "Du kannst dich nicht selbst loeschen. "
                "Bitte von einem anderen Admin loeschen lassen.",
                "danger",
            )
            return redirect(url_for("admin_users_list"))

        db.execute("DELETE FROM admin_users WHERE id = ?", (user_id,))
        db.commit()

        flash(f"Admin '{user['username']}' wurde geloescht.", "info")
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
            """
            INSERT INTO settings (key, value)
            VALUES ('theme', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (theme_key,),
        )
        db.commit()

        flash(
            f"Design auf '{THEMES[theme_key]['label']}' geaendert.",
            "success",
        )
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
            """
            INSERT INTO settings (key, value)
            VALUES ('custom_bg_image', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (image_name,),
        )
        db.execute(
            """
            INSERT INTO settings (key, value)
            VALUES ('theme', 'custom_image')
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """
        )
        db.commit()

        flash(
            f"Hintergrundbild auf '{image_name}' gesetzt und "
            "Design 'Eigenes Bild' aktiviert.",
            "success",
        )
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
            """
            INSERT INTO settings (key, value)
            VALUES ('bg_style', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (bg_style_key,),
        )
        db.commit()

        flash(
            f"Hintergrund-Effekt auf '{BG_STYLES[bg_style_key]}' geaendert.",
            "success",
        )
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/intro-text/update", methods=["POST"])
    @admin_required
    def admin_update_intro_text():
        intro_text = request.form.get("intro_text", "").strip()
        db = get_db()

        if intro_text:
            db.execute(
                """
                INSERT INTO settings (key, value)
                VALUES ('intro_text', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (intro_text,),
            )
            flash(
                "Einleitungstext wurde aktualisiert. "
                "Tipp: {next_thursday} wird automatisch durch "
                "das naechste Donnerstagsdatum ersetzt.",
                "success",
            )
        else:
            db.execute("DELETE FROM settings WHERE key = 'intro_text'")
            flash(
                "Einleitungstext wurde auf Standard zurueckgesetzt.",
                "info",
            )

        db.commit()
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/banner/update", methods=["POST"])
    @admin_required
    def admin_update_banner_visibility():
        show_banner = "1" if request.form.get("show_banner") else "0"
        set_setting_value("show_banner", show_banner)
        flash("Banner-Sichtbarkeit aktualisiert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/waitlist-settings/update", methods=["POST"])
    @admin_required
    def admin_update_waitlist_settings():
        waitlist_limit_raw = request.form.get("waitlist_limit", "").strip()
        slot_selection = request.form.get(
            "slot_selection",
            DEFAULT_SLOT_SELECTION,
        ).strip()
        waitlist_mode = request.form.get(
            "waitlist_mode",
            DEFAULT_WAITLIST_MODE,
        ).strip()

        try:
            waitlist_limit = int(waitlist_limit_raw)
        except ValueError:
            waitlist_limit = -1

        if waitlist_limit < 0:
            flash(
                "Bitte eine gueltige Wartelistengroesse eingeben.",
                "danger",
            )
            return redirect(url_for("admin_dashboard"))

        if slot_selection not in {"one", "both"}:
            slot_selection = DEFAULT_SLOT_SELECTION

        if waitlist_mode not in WAITLIST_MODES:
            waitlist_mode = DEFAULT_WAITLIST_MODE

        db = get_db()
        settings = {
            "waitlist_limit": str(waitlist_limit),
            "slot_selection": slot_selection,
            "waitlist_mode": waitlist_mode,
        }

        for key, value in settings.items():
            db.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )

        db.commit()
        flash("Wartelisten-Einstellungen gespeichert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/automatik/update", methods=["POST"])
    @admin_required
    def admin_update_automatik_settings():
        reset_enabled = "1" if request.form.get("reset_enabled") else "0"
        reminder_enabled = "1" if request.form.get("reminder_enabled") else "0"

        try:
            reset_weekday = int(request.form.get("reset_weekday", DEFAULT_RESET_WEEKDAY))
        except ValueError:
            reset_weekday = int(DEFAULT_RESET_WEEKDAY)
        try:
            reset_hour = int(request.form.get("reset_hour", DEFAULT_RESET_HOUR))
        except ValueError:
            reset_hour = int(DEFAULT_RESET_HOUR)
        try:
            reset_minute = int(request.form.get("reset_minute", DEFAULT_RESET_MINUTE))
        except ValueError:
            reset_minute = int(DEFAULT_RESET_MINUTE)
        try:
            notify_interval = int(
                request.form.get("notify_interval_minutes", DEFAULT_NOTIFY_INTERVAL_MINUTES)
            )
        except ValueError:
            notify_interval = int(DEFAULT_NOTIFY_INTERVAL_MINUTES)
        try:
            reminder_weekday = int(request.form.get("reminder_weekday", DEFAULT_REMINDER_WEEKDAY))
        except ValueError:
            reminder_weekday = int(DEFAULT_REMINDER_WEEKDAY)
        try:
            reminder_hour = int(request.form.get("reminder_hour", DEFAULT_REMINDER_HOUR))
        except ValueError:
            reminder_hour = int(DEFAULT_REMINDER_HOUR)
        try:
            reminder_minute = int(request.form.get("reminder_minute", DEFAULT_REMINDER_MINUTE))
        except ValueError:
            reminder_minute = int(DEFAULT_REMINDER_MINUTE)

        if reset_weekday not in range(7):
            reset_weekday = int(DEFAULT_RESET_WEEKDAY)
        if reminder_weekday not in range(7):
            reminder_weekday = int(DEFAULT_REMINDER_WEEKDAY)
        if reset_hour not in range(24):
            reset_hour = int(DEFAULT_RESET_HOUR)
        if reminder_hour not in range(24):
            reminder_hour = int(DEFAULT_REMINDER_HOUR)
        if reset_minute not in range(60):
            reset_minute = int(DEFAULT_RESET_MINUTE)
        if reminder_minute not in range(60):
            reminder_minute = int(DEFAULT_REMINDER_MINUTE)
        if notify_interval < 5:
            notify_interval = 5

        settings = {
            "reset_enabled": reset_enabled,
            "reset_weekday": str(reset_weekday),
            "reset_hour": str(reset_hour),
            "reset_minute": str(reset_minute),
            "notify_interval_minutes": str(notify_interval),
            "reminder_enabled": reminder_enabled,
            "reminder_weekday": str(reminder_weekday),
            "reminder_hour": str(reminder_hour),
            "reminder_minute": str(reminder_minute),
        }

        for key, value in settings.items():
            db = get_db()
            db.execute(
                """
                INSERT INTO settings (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (key, value),
            )
            db.commit()

        flash("Automatik-Einstellungen gespeichert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/signup-lock/update", methods=["POST"])
    @admin_required
    def admin_update_signup_lock():
        action = request.form.get("action")
        if action == "open":
            set_setting_value("signup_lock_manual_open", "1")
            set_setting_value("signup_lock_auto_open_at", "")
            flash("Anmeldung manuell geoeffnet.", "success")
        elif action == "close":
            set_setting_value("signup_lock_manual_open", "0")
            set_setting_value("signup_lock_auto_open_at", "")
            flash("Anmeldung gesperrt.", "success")
        elif action == "auto":
            auto_raw = request.form.get("auto_open_datetime", "").strip()
            if auto_raw:
                try:
                    datetime.fromisoformat(auto_raw)
                except (ValueError, TypeError):
                    flash("Ungueltiges Datum/Uhrzeit fuer die automatische Oeffnung.", "danger")
                    return redirect(url_for("admin_dashboard"))
                set_setting_value("signup_lock_manual_open", "0")
                set_setting_value("signup_lock_auto_open_at", auto_raw)
                flash("Automatische Oeffnung geplant.", "success")
            else:
                flash("Bitte ein Datum und Uhrzeit angeben.", "danger")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/backup/download")
    @admin_required
    def admin_backup_download():
        return send_file(
            app.config["DATABASE"],
            as_attachment=True,
            download_name="matchtreff_backup.sqlite3",
        )

    @app.route("/admin/signups/clear", methods=["POST"])
    @admin_required
    def admin_clear_signups():
        db = get_db()
        db.execute("DELETE FROM signups")
        db.commit()

        flash("Alle Anmeldungen wurden zurueckgesetzt.", "info")
        return redirect(url_for("admin_dashboard"))

    @app.route("/healthz")
    def healthz():
        return {"status": "ok"}

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "1905"))
    app.run(host="0.0.0.0", port=port)
