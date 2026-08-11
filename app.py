import os
import sqlite3
import sys
import logging
import hashlib
from logging_config import setup_logging
from datetime import datetime, timedelta, time
from functools import wraps
from io import BytesIO
from zoneinfo import ZoneInfo

from flask import (
    Flask,
    abort,
    flash,
    g,
    make_response,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from logic_auth import admin_required, authenticate_admin
try:
    import qrcode
except ImportError:
    qrcode = None


_REQUIRED_ENV = ["SECRET_KEY", "ADMIN_PASSWORD_ADMIN", "ADMIN_PASSWORD_DANIEL"]
logger = logging.getLogger("matchtreff.web")
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
    "Dominik": os.environ.get("ADMIN_PASSWORD_DOMINIK"),
}

SLOT_DEFINITIONS = [
    {"key": "slot_a", "label": "Temprano: 18:00 - 20:00 Uhr"},
    {"key": "slot_b", "label": "Tarde: 20:00 - 22:00 Uhr"},
]
SLOT_LABEL = {slot["key"]: slot["label"] for slot in SLOT_DEFINITIONS}
DEFAULT_SLOT_CLOSE_ENABLED = "1"
DEFAULT_SLOT_CLOSE_TIMES = {slot["key"]: (18, 0) for slot in SLOT_DEFINITIONS}

WAITLIST_LIMIT = 4
DEFAULT_SLOT_SELECTION = "both"
DEFAULT_WAITLIST_MODE = "with_waitlist"
WAITLIST_MODES = {
    "with_waitlist",
    "open_for_all",
    "no_waitlist",
    "guests_only",
    "member_priority_24h",
}

DEFAULT_MAX_PLAYERS = 14
DEFAULT_THEME = "night"
DEFAULT_BG_STYLE = "bubbles"
DEFAULT_CUSTOM_IMAGE = "Racketfire.png"
SIGNUP_COOKIE_PREFIX = "mtp_signed_"
DEFAULT_MAX_ENTRIES_PER_DEVICE = 2  # Pro Geraet/Slot max. Eintraege

# Automatik / Scheduler (Reset + Digest + Reminder)
DEFAULT_RESET_ENABLED = "1"
DEFAULT_RESET_WEEKDAY = "4"  # 0=Montag ... 4=Freitag
DEFAULT_RESET_HOUR = "6"
DEFAULT_RESET_MINUTE = "0"
DEFAULT_NOTIFY_INTERVAL_MINUTES = "60"
DEFAULT_REMINDER_ENABLED = "1"
DEFAULT_REMINDER_WEEKDAY = "3"  # 0=Montag ... 3=Donnerstag (Spieltag)
DEFAULT_REMINDER_HOUR = "12"
DEFAULT_REMINDER_MINUTE = "0"
WEEKDAY_NAMES = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]

# Anmeldesperre: Standard gesperrt fuer normale Nutzer, Oeffnung nur durch Admin
DEFAULT_SIGNUP_LOCK_ENABLED = "1"  # Sperre aktiv
DEFAULT_SIGNUP_LOCK_MANUAL_OPEN = "0"  # manuell durch Admin geoeffnet?
DEFAULT_SIGNUP_LOCK_AUTO_OPEN_AT = ""  # ISO-Datetime fuer automatische Freigabe (leer = aus)

# Standard: Liste oeffnet am Dienstag um 13:00 Uhr (nach EU-Zeit).
# Wird ueberschrieben, wenn ein Admin eine Abweichung hinterlegt hat.
SIGNUP_DEFAULT_OPEN_WEEKDAY = 1  # 0=Mo ... 1=Di ... 6=So
SIGNUP_DEFAULT_OPEN_HOUR = 13
SIGNUP_DEFAULT_OPEN_MINUTE = 0
APP_TZ = ZoneInfo("Europe/Berlin")

DEFAULT_SHOW_BANNER = "1"  # Banner auf der Startseite sichtbar (1=ja, 0=aus)

DEFAULT_INTRO_TEXT = (
    "Anmeldung für Donnerstag, {next_thursday}. Trag einfach deinen Namen ein "
    "und wähle einen oder beide Slots. Pro Gerät kann man sich pro Slot bis "
    "zu zwei Mal eintragen (z. B. für dich und eine Begleitperson)."
)

# Verfuegbare Platzhalter im Einleitungstext
INTRO_PLACEHOLDERS = {
    "next_thursday": "Datum des naechsten Donnerstags (z. B. 07.08.2026)",
    "slot_a": "Bezeichnung des ersten Slots",
    "slot_b": "Bezeichnung des zweiten Slots",
    "event_name": "Name des Events (MATCHTREFF SILBER)",
    "entry_count": "Anzahl erlaubter Eintraege pro Geraet und Slot",
}

INFO_PAGE_TEXT = """Hallo Padel-Spieler,

hier findet Ihr die Abfrage, wer so alles beim MATCHTREFF SILBER dabei ist.

Ich habe uns aktuell 3 Plaetze reserviert von 18 - 22 Uhr.

Wuerde mich freuen, wenn wir uns am Donnerstag sehen!
Das ganze findet natuerlich nur statt, wenn es das Wetter auch zulaesst.
Ihr koennt jederzeit dazukommen, entweder direkt ab 18 Uhr, oder auch spaeter ab 20 Uhr.
Bitte beachtet diese Startzeiten, damit wir auch immer genuegend Spieler sind und nicht warten muessen.

Ich bekomme bitte von jedem Teilnehmer 2 Euro (TCG-Mitglieder), das nutzen wir,
um zum Beispiel Baelle fuer den Matchtreff zu organisieren.

Gaeste (Nicht-TCG-Mitglieder) sind willkommen, zahlen aber pauschal 15 Euro.
Gaeste bitte unbedingt vorher bei mir anmelden. TCG-Mitglieder haben Vorrang.

Wann immer es geht, spielen wir Golden Court, je nach Teilnehmerzahl.

In unregelmaessigen Abstaenden wird donnerstags auch ein GPS100 DPV angeboten.
Ausserdem wird es ab dieser Saison immer wieder ein AMERICANO geben.

Das Angebot richtet sich an Spieler auf SILBER-Level.
Fuer Anfaenger und Interessierte gibt es montags ein Angebot.

Tragt euch ein, wer dabei ist!

Danke und Gruss
Daniel

Fragen? Immer gerne, entweder per WhatsApp oder per Mail:
daniel@will-padel-spielen.de
"""

GALLERY_IMAGES = [
    "1716335274392.png",
    "1716335619157.png",
    "Designer (1).jpeg",
    "Designer (10).jpeg",
    "Designer (11).jpeg",
    "Designer (12).jpeg",
    "Designer (13).jpeg",
    "Designer (14).jpeg",
    "Designer (2).jpeg",
    "Designer (6).jpeg",
    "Designer (7).jpeg",
    "Designer (8).jpeg",
    "Designer (9).jpeg",
    "Designer.jpeg",
    "Designer1.jpeg",
    "Designer_Paypal_1.jpeg",
    "Designer_Paypal_2.jpeg",
    "Download.png",
    "FollowLogo.jpeg",
    "Racketfire.png",
    "Racketsplash.png",
    "padelbackground_01.jpg",
    "padelbackground_02.jpg",
    "padelbackground_03.jpg",
    "padelbackground_04.jpg",
    "padelbackground_05.jpg",
    "padelbackground_06.jpg",
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
    "ocean": {
        "label": "Ozean (Tuerkis)",
        "gradient": "radial-gradient(circle at top right, #cffafe 0, #ecfeff 45%, #f8feff 100%)",
        "background_image": None,
        "accent": "#0891b2",
        "accent2": "#06b6d4",
    },
    "forest": {
        "label": "Wald (Tiefgruen)",
        "gradient": "radial-gradient(circle at top left, #d1fae5 0, #ecfdf5 45%, #f7fffb 100%)",
        "background_image": None,
        "accent": "#047857",
        "accent2": "#10b981",
    },
    "lavender": {
        "label": "Lavendel (Lila)",
        "gradient": "radial-gradient(circle at top left, #ede9fe 0, #f5f3ff 45%, #fbfaff 100%)",
        "background_image": None,
        "accent": "#7c3aed",
        "accent2": "#a855f7",
    },
    "candy": {
        "label": "Candy (Rosa)",
        "gradient": "radial-gradient(circle at top right, #fce7f3 0, #fdf2f8 45%, #fff7fb 100%)",
        "background_image": None,
        "accent": "#db2777",
        "accent2": "#ec4899",
    },
    "desert": {
        "label": "Wueste (Sand)",
        "gradient": "radial-gradient(circle at top left, #fef3c7 0, #fffbeb 45%, #fffdf5 100%)",
        "background_image": None,
        "accent": "#b45309",
        "accent2": "#d97706",
    },
}

BG_STYLES = {
    "bubbles": "Farbige Blasen",
    "logo": "Padel-Ball-Icons",
}

ORGA_TEAM = ["Daniel", "Cosme", "Sascha", "Patrick", "Dominik"]


def normalize_name(name: str) -> str:
    """Normalisiert Namen: Leerzeichen, Kleinbuchstaben, ae/oe/ue zu ä/ö/ü."""
    name = name.strip()
    name = " ".join(name.split()).lower()
    name = name.replace("ae", "ä").replace("oe", "ö").replace("ue", "ü")
    return name


ORGA_TEAM_NORMALIZED = {normalize_name(name) for name in ORGA_TEAM}

# Status-Optionen fuer das Orga-Team (admin_status Tabelle)
# "" = Anwesend/eingeplant, "zuschauen" = ohne Slot, sonst Abwesenheit
ADMIN_STATUS_OPTIONS = {
    "": "Anwesend / eingeplant",
    "zuschauen": "Zuschauen (ohne Slot)",
    "nein": "Nicht da",
    "urlaub": "Urlaub",
    "krank": "Krank",
}


SLOT_ICONS = {
    "slot_a": "Racketfire.png",
    "slot_b": "Racketsplash.png",
}


def telegram_api_call(method, payload):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        return None

    url = f"https://api.telegram.org/bot{token}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print(f"[WARN] Telegram-API-Aufruf fehlgeschlagen: {exc}", file=sys.stderr)
        return None


def forward_contact_message_to_admin(
    name, email, recipient, contact_channel="", contact_value="", message_text=""
):
    """Leitet eine Kontaktnachricht an Admins per Telegram weiter."""
    admin_ids_raw = os.environ.get("ADMIN_TELEGRAM_IDS", "")
    admin_ids = [item.strip() for item in admin_ids_raw.split(",") if item.strip()]
    if not admin_ids:
        return 0

    parts = [f"Name: {name or 'Anonym'}"]
    if email:
        parts.append(f"E-Mail: {email}")
    if recipient:
        parts.append(f"An: {recipient}")
    if contact_channel and contact_value:
        parts.append(f"Kontakt ({contact_channel}): {contact_value}")
    text = (
        "📨 Neue Nachricht über das Kontaktformular\n\n"
        + "\n".join(parts)
        + f"\n\n{message_text}"
    )

    sent = 0
    for admin_id in admin_ids:
        result = telegram_api_call(
            "sendMessage",
            {"chat_id": admin_id, "text": text},
        )
        if result and result.get("ok"):
            sent += 1

    return sent


def notify_admins_guest_signup(signup_id, name, slot_label, status):
    admin_ids_raw = os.environ.get("ADMIN_TELEGRAM_IDS", "")
    admin_ids = [item.strip() for item in admin_ids_raw.split(",") if item.strip()]
    if not admin_ids:
        return

    status_text = "Warteliste" if status == "waitlist" else "bestaetigt"
    text = (
        "Neue Gast-Anmeldung (kein TPCG-Mitglied)\n\n"
        f"Name: {name}\n"
        f"Slot: {slot_label}\n"
        f"Status: {status_text}\n\n"
        "Die Anmeldung ist bereits eingetragen. Du kannst sie jederzeit entfernen."
    )
    keyboard = {
        "inline_keyboard": [[
            {
                "text": "Bestaetigen (ok)",
                "callback_data": f"ack_signup:{signup_id}",
            },
            {
                "text": "Entfernen",
                "callback_data": f"reject_signup:{signup_id}",
            },
        ]]
    }

    for admin_id in admin_ids:
        telegram_api_call(
            "sendMessage",
            {
                "chat_id": admin_id,
                "text": text,
                "reply_markup": keyboard,
            },
        )


def build_checklist_pdf(slots_data, event_date):
    """Erzeugt eine A4-Anmeldeliste als PDF (reines Python, keine Abhängigkeit).

    slots_data: Liste von dicts mit label, confirmed[], waitlist[]
    event_date: str (z. B. "13.08.2026")
    """
    W, H = 595, 842  # DIN A4
    M = 40
    line_h = 17
    checkbox = 10

    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    pages = []
    ops = []

    def start_blank_page():
        """Aktuelle Seite abschliessen und mit leerer Seite neu beginnen."""
        pages.append(ops)
        return []

    def text(size, bold, x, y, s):
        font = "F2" if bold else "F1"
        ops.append(
            f"BT /{font} {size} Tf 1 0 0 1 {x} {y} Tm "
            f"({esc(s.encode('latin-1', 'replace').decode('latin-1'))}) Tj ET"
        )

    y = H - M - 30
    text(20, True, M, y, "MATCHTREFF PADEL - Anmeldeliste")
    y -= 24
    text(12, False, M, y, f"Donnerstag, {event_date}    Zum Abhaken (mit manuellen Notizen)")
    y -= 22

    for slot in slots_data:
        if y < 90:
            ops = start_blank_page()
            y = H - M - 30
        text(13, True, M, y, slot["label"])
        y -= 18
        for name in slot["confirmed"]:
            if y < 55:
                ops = start_blank_page()
                y = H - M - 30
            ops.append(f"{M} {y - 4} {checkbox} {checkbox} re S")
            text(11, False, M + checkbox + 8, y, name)
            y -= line_h
        if slot["waitlist"]:
            if y < 80:
                ops = start_blank_page()
                y = H - M - 30
            text(11, True, M, y, "Warteliste:")
            y -= 17
            for name in slot["waitlist"]:
                if y < 55:
                    ops = start_blank_page()
                    y = H - M - 30
                ops.append(f"{M} {y - 4} {checkbox} {checkbox} re S")
                text(11, False, M + checkbox + 8, y, name)
                y -= line_h
        y -= 14

    # 4 Freifelder fuer manuelle Aenderungen
    if y < 160:
        ops = start_blank_page()
        y = H - M - 30
    text(12, True, M, y, "Freifelder (manuelle Notizen)")
    y -= 20
    for i in range(4):
        ops.append(f"{M} {y - 8} {W - M} 0.6 re S")
        text(10, False, M, y, f"Name {i + 1}:")
        y -= 26

    pages.append(ops)

    # --- PDF-Assemblierung (deterministische Objekt-IDs) ---
    n = len(pages)
    # Objekt-IDs: 1 Catalog, 2 Pages, 3..3+n-1 Seiten, 3+n..3+2n-1 Contents, dann Fonts
    page_id = 3
    content_base = 3 + n
    font1_id = 3 + 2 * n
    font2_id = 4 + 2 * n

    def obj(obj_id, payload):
        return f"{obj_id} 0 obj\n".encode("latin-1") + payload + b"\nendobj\n"

    kids = " ".join(f"{page_id + i} 0 R" for i in range(n))
    body_parts = [
        obj(1, b"<< /Type /Catalog /Pages 2 0 R >>"),
        obj(2, f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode("latin-1")),
    ]
    for i, page_ops in enumerate(pages):
        body_parts.append(
            obj(
                page_id + i,
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {W} {H}] "
                f"/Resources << /Font << /F1 {font1_id} 0 R /F2 {font2_id} 0 R >> >> "
                f"/Contents {content_base + i} 0 R >>".encode("latin-1"),
            )
        )
    for i, page_ops in enumerate(pages):
        stream = "\n".join(page_ops).encode("latin-1")
        body_parts.append(
            obj(
                content_base + i,
                f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
                + stream
                + b"\nendstream",
            )
        )
    body_parts.append(obj(font1_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    body_parts.append(obj(font2_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>"))

    header = b"%PDF-1.4\n"
    body = b"".join(body_parts)
    offsets = []
    pos = len(header)
    for part in body_parts:
        offsets.append(pos)
        pos += len(part)
    xref_pos = pos
    xref = b"xref\n0 " + str(len(body_parts) + 1).encode() + b"\n"
    xref += b"0000000000 65535 f \n"
    xref += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    trailer = (
        f"trailer\n<< /Size {len(body_parts) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n"
    ).encode("latin-1")
    return header + body + xref + trailer


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

            CREATE TABLE IF NOT EXISTS admin_status (
                name_normalized TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS telegram_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                is_member_default INTEGER NOT NULL DEFAULT 1,
                                is_active INTEGER NOT NULL DEFAULT 1,
                                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                            );

                            CREATE TABLE IF NOT EXISTS signup_delete_pin_attempts (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                signup_id INTEGER NOT NULL,
                                ip_hash TEXT NOT NULL,
                                failed_attempts INTEGER NOT NULL DEFAULT 1,
                                locked_until TIMESTAMP,
                                last_attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                UNIQUE(signup_id, ip_hash)
                            );

                                        CREATE TABLE IF NOT EXISTS contact_messages (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL DEFAULT '',
                            email TEXT NOT NULL DEFAULT '',
                            recipient TEXT NOT NULL DEFAULT '',
                            message TEXT NOT NULL DEFAULT '',
                            is_read INTEGER NOT NULL DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS liste_comments (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            name TEXT NOT NULL DEFAULT '',
                            comment TEXT NOT NULL DEFAULT '',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );

                        CREATE TABLE IF NOT EXISTS faq_entries (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            question TEXT NOT NULL DEFAULT '',
                            answer TEXT NOT NULL DEFAULT '',
                            sort_order INTEGER NOT NULL DEFAULT 0,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                        """
        )

        columns = [row[1] for row in db.execute("PRAGMA table_info(signups)").fetchall()]
        if "is_member" not in columns:
            db.execute(
                "ALTER TABLE signups ADD COLUMN is_member INTEGER NOT NULL DEFAULT 1"
            )
        if "delete_pin_hash" not in columns:
                    db.execute(
                        "ALTER TABLE signups ADD COLUMN delete_pin_hash TEXT"
                    )

        # Admin-Bestaetigung fuer Wartelisten-Eintraege
        # 0 = noch nicht bestaetigt, 1 = von Admin bestaetigt (bleibt auf Warteliste)
        if "admin_confirmed" not in columns:
            db.execute(
                "ALTER TABLE signups ADD COLUMN admin_confirmed INTEGER NOT NULL DEFAULT 0"
            )

        # Chatbox: Kontakt-Kanal und -Wert fuer Rueckmeldung
        contact_columns = [row[1] for row in db.execute("PRAGMA table_info(contact_messages)").fetchall()]
        if "contact_channel" not in contact_columns:
            db.execute(
                "ALTER TABLE contact_messages ADD COLUMN contact_channel TEXT NOT NULL DEFAULT ''"
            )
        if "contact_value" not in contact_columns:
            db.execute(
                "ALTER TABLE contact_messages ADD COLUMN contact_value TEXT NOT NULL DEFAULT ''"
            )

        # Migration: name_normalized mit Umlauten neu berechnen (ae/oe/ue -> ae/oe/ue)
        rows = db.execute(
            "SELECT id, name FROM signups"
        ).fetchall()
        for row in rows:
            fresh = normalize_name(row["name"])
            db.execute(
                "UPDATE signups SET name_normalized = ? WHERE id = ?",
                (fresh, row["id"]),
            )

        # Migration: bestehenden Einleitungstext auf Umlaute umstellen (ae->ae/ue->ue/oe->oe)
        intro_row = db.execute(
            "SELECT value FROM settings WHERE key = 'intro_text'"
        ).fetchone()
        if intro_row and intro_row["value"]:
            converted = (
                intro_row["value"]
                .replace("ae", "ä")
                .replace("oe", "ö")
                .replace("ue", "ü")
            )
            if converted != intro_row["value"]:
                db.execute(
                    "UPDATE settings SET value = ? WHERE key = 'intro_text'",
                    (converted,),
                )

        setting_defaults = {
            "theme": DEFAULT_THEME,
            "bg_style": DEFAULT_BG_STYLE,
            "custom_bg_image": DEFAULT_CUSTOM_IMAGE,
            "waitlist_limit": str(WAITLIST_LIMIT),
            "slot_selection": DEFAULT_SLOT_SELECTION,
            "waitlist_mode": DEFAULT_WAITLIST_MODE,
            "reset_enabled": DEFAULT_RESET_ENABLED,
            "reset_weekday": DEFAULT_RESET_WEEKDAY,
            "reset_hour": DEFAULT_RESET_HOUR,
            "reset_minute": DEFAULT_RESET_MINUTE,
            "notify_interval_minutes": DEFAULT_NOTIFY_INTERVAL_MINUTES,
            "reminder_enabled": DEFAULT_REMINDER_ENABLED,
            "reminder_weekday": DEFAULT_REMINDER_WEEKDAY,
            "reminder_hour": DEFAULT_REMINDER_HOUR,
            "reminder_minute": DEFAULT_REMINDER_MINUTE,
            "signup_lock_enabled": DEFAULT_SIGNUP_LOCK_ENABLED,
            "signup_lock_manual_open": DEFAULT_SIGNUP_LOCK_MANUAL_OPEN,
            "signup_lock_auto_open_at": DEFAULT_SIGNUP_LOCK_AUTO_OPEN_AT,
            "signup_lock_opened_at": "",
            "show_banner": DEFAULT_SHOW_BANNER,
            "max_entries_per_device": str(DEFAULT_MAX_ENTRIES_PER_DEVICE),
            "telegram_channel_url": os.environ.get("TELEGRAM_CHANNEL_URL", ""),
            "homebrew_url": os.environ.get("HOMEBREW_URL", ""),
            "homebrew_image": os.environ.get("HOMEBREW_IMAGE", "homebrew.png"),
            "paypal_url": os.environ.get("PAYPAL_URL", ""),
            "paypal_image": os.environ.get("PAYPAL_IMAGE", "Designer_Paypal_2.jpeg"),
            "americana_url": os.environ.get("AMERICANA_URL", ""),
            "americana_text": os.environ.get(
                "AMERICANA_TEXT",
                "Entdecke die Padel Americana App - das schnelle Turnierformat f\u00fcr deinen Club!",
            ),
        }

        for key, value in setting_defaults.items():
            db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO NOTHING",
                (key, value),
            )

        for seed_name, seed_password in SEED_ADMIN_USERS.items():
            if not seed_password:
                continue

            db.execute(
                """
                INSERT INTO admin_users (username, password_hash, created_by)
                VALUES (?, ?, ?)
                ON CONFLICT(username) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    created_by = excluded.created_by
                """,
                (seed_name, generate_password_hash(seed_password), "system"),
            )

        for slot in SLOT_DEFINITIONS:
            db.execute(
                """
                INSERT INTO slots (slot_key, label, max_players)
                VALUES (?, ?, ?)
                ON CONFLICT(slot_key) DO NOTHING
                """,
                (slot["key"], slot["label"], DEFAULT_MAX_PLAYERS),
            )

        migrated_flag = db.execute(
            "SELECT value FROM settings WHERE key = 'slot_labels_migrated_v2'"
        ).fetchone()

        if not migrated_flag:
            for slot in SLOT_DEFINITIONS:
                custom_flag = db.execute(
                    "SELECT value FROM settings WHERE key = ?",
                    (f"slot_label_custom_{slot['key']}",),
                ).fetchone()

                if not custom_flag:
                    db.execute(
                        "UPDATE slots SET label = ? WHERE slot_key = ?",
                        (slot["label"], slot["key"]),
                    )

            db.execute(
                """
                INSERT INTO settings (key, value)
                VALUES ('slot_labels_migrated_v2', '1')
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """
            )

        db.commit()

    with app.app_context():
        init_db()

        # Einstellungen fuer den Loesch-PIN.
        DELETE_PIN_MIN_ATTEMPTS = int(
            os.environ.get("DELETE_PIN_MAX_FAILED_ATTEMPTS", "3")
        )
        DELETE_PIN_LOCK_MINUTES = float(
            os.environ.get("DELETE_PIN_LOCK_MINUTES", "15")
        )
        DELETE_PIN_IP_ATTEMPTS = int(
            os.environ.get("DELETE_PIN_IP_WINDOW_ATTEMPTS", "10")
        )
        DELETE_PIN_IP_WINDOW_MINUTES = float(
            os.environ.get("DELETE_PIN_IP_WINDOW_MINUTES", "15")
        )
        DELETE_PIN_CLIENT_SALT = os.environ.get(
            "DELETE_PIN_CLIENT_SALT", "matchtreff-delete-pin"
        ).encode("utf-8")

        def _ip_hash():
            """Stabiler, nicht-reversibler Hash der Client-IP fuer Rate-Limiting."""
            return hashlib.sha256(
                DELETE_PIN_CLIENT_SALT + request.remote_addr.encode("utf-8")
            ).hexdigest()

        def _normalize_pin(pin):
            """Akzeptiert '1234', '1 2 3 4' oder '1-2-3-4' -> '1234'."""
            if pin is None:
                return None
            digits = [ch for ch in str(pin).strip() if ch.isdigit()]
            if len(digits) != 4:
                return None
            return "".join(digits)

        def _is_delete_locked(signup_id):
            """True wenn fuer diesen Eintrag + IP der PIN gesperrt ist."""
            db = get_db()
            row = db.execute(
                """
                SELECT locked_until
                FROM signup_delete_pin_attempts
                WHERE signup_id = ? AND ip_hash = ?
                """,
                (signup_id, _ip_hash()),
            ).fetchone()
            if not row or not row["locked_until"]:
                return False
            try:
                locked_until = datetime.fromisoformat(str(row["locked_until"]))
            except ValueError:
                return False
            return datetime.now() < locked_until

        def _remaining_pin_attempts(signup_id):
            db = get_db()
            row = db.execute(
                """
                SELECT failed_attempts, locked_until
                FROM signup_delete_pin_attempts
                WHERE signup_id = ? AND ip_hash = ?
                """,
                (signup_id, _ip_hash()),
            ).fetchone()
            if row and row["locked_until"]:
                try:
                    if datetime.now() < datetime.fromisoformat(str(row["locked_until"])):
                        return 0
                except ValueError:
                    pass
            if not row:
                return DELETE_PIN_MIN_ATTEMPTS
            remaining = DELETE_PIN_MIN_ATTEMPTS - row["failed_attempts"]
            return max(0, remaining)

        def _record_pin_failure(signup_id):
            db = get_db()
            now = datetime.now()
            row = db.execute(
                """
                SELECT failed_attempts
                FROM signup_delete_pin_attempts
                WHERE signup_id = ? AND ip_hash = ?
                """,
                (signup_id, _ip_hash()),
            ).fetchone()

            if row:
                failed = row["failed_attempts"] + 1
                locked_until = (
                    now + timedelta(minutes=DELETE_PIN_LOCK_MINUTES)
                    if failed >= DELETE_PIN_MIN_ATTEMPTS
                    else None
                )
                db.execute(
                    """
                    UPDATE signup_delete_pin_attempts
                    SET failed_attempts = ?, locked_until = ?,
                        last_attempt_at = CURRENT_TIMESTAMP
                    WHERE signup_id = ? AND ip_hash = ?
                    """,
                    (failed, locked_until, signup_id, _ip_hash()),
                )
            else:
                locked_until = (
                    now + timedelta(minutes=DELETE_PIN_LOCK_MINUTES)
                    if DELETE_PIN_MIN_ATTEMPTS <= 1
                    else None
                )
                db.execute(
                    """
                    INSERT INTO signup_delete_pin_attempts (
                        signup_id, ip_hash, failed_attempts, locked_until
                    )
                    VALUES (?, ?, 1, ?)
                    """,
                    (signup_id, _ip_hash(), locked_until),
                )
            db.commit()

        def _clear_pin_attempts(signup_id):
            db = get_db()
            db.execute(
                "DELETE FROM signup_delete_pin_attempts WHERE signup_id = ?",
                (signup_id,),
            )
            db.commit()

        def _ip_rate_limited():
            """Grobes IP-Rate-Limiting: max. X Versuche in Y Minuten pro IP."""
            db = get_db()
            recent = db.execute(
                """
                SELECT COUNT(*) AS c
                FROM signup_delete_ip_attempts
                WHERE ip_hash = ? AND attempted_at > datetime('now', ?)
                """,
                (
                    _ip_hash(),
                    f"-{DELETE_PIN_IP_WINDOW_MINUTES} minutes",
                ),
            ).fetchone()["c"]

            if recent >= DELETE_PIN_IP_ATTEMPTS:
                return True

            db.execute(
                "INSERT INTO signup_delete_ip_attempts (ip_hash) VALUES (?)",
                (_ip_hash(),),
            )
            db.commit()
            return False

    def format_intro_text(text):
        """Wandelt einfaches Markdown (fett, kursiv, Links, Zeilenumbrueche) in sicheres HTML um."""
        import re as _re
        from markupsafe import Markup

        if not text:
            return Markup("")

        escaped = Markup.escape(text).__html__()

        def _bold(m):
            return "<strong>" + m.group(1) + "</strong>"

        def _italic(m):
            return "<em>" + m.group(1) + "</em>"

        def _link(m):
            url = m.group(1)
            return '<a href="' + url + '" target="_blank" rel="noopener">' + url + "</a>"

        # Verlinkungen (https? URLs)
        escaped = _re.sub(r"(https?://[^\s<]+)", _link, escaped)
        # **fett**
        escaped = _re.sub(r"\*\*(.+?)\*\*", _bold, escaped)
        # *kursiv*
        escaped = _re.sub(r"\*(.+?)\*", _italic, escaped)
        # Absaetze und Zeilenumbrueche
        html_parts = []
        for para in escaped.split("\n\n"):
            para = para.replace("\n", "<br>")
            html_parts.append("<p>" + para + "</p>")
        return Markup("".join(html_parts))

    app.jinja_env.filters["format_intro"] = format_intro_text

    def next_thursday():
        # Get current time in app timezone
        now = datetime.now(APP_TZ)
        today = now.date()
        
        # Calculate days until Thursday (3)
        # If it's Thursday, show today's date
        # If it's Friday before 06:00, still show yesterday's date (Thursday)
        if today.weekday() == 3:
            return today
        elif today.weekday() == 4 and now.hour < 6:
            return today - timedelta(days=1)
            
        days_ahead = (3 - today.weekday()) % 7
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

    def get_max_entries_per_device():
        raw = get_setting_value("max_entries_per_device", str(DEFAULT_MAX_ENTRIES_PER_DEVICE))
        try:
            value = int(raw)
        except (ValueError, TypeError):
            value = DEFAULT_MAX_ENTRIES_PER_DEVICE
        return value if value >= 1 else DEFAULT_MAX_ENTRIES_PER_DEVICE

    def get_telegram_channel_url():
        return get_setting_value("telegram_channel_url", "")

    def get_homebrew_url():
        return get_setting_value("homebrew_url", os.environ.get("HOMEBREW_URL", ""))

    def get_homebrew_image():
        return get_setting_value("homebrew_image", os.environ.get("HOMEBREW_IMAGE", "homebrew.png"))

    def get_paypal_url():
        return get_setting_value("paypal_url", os.environ.get("PAYPAL_URL", ""))

    def get_paypal_image():
        return get_setting_value("paypal_image", os.environ.get("PAYPAL_IMAGE", "Designer_Paypal_2.jpeg"))

    def get_americana_url():
        return get_setting_value("americana_url", os.environ.get("AMERICANA_URL", ""))

    def get_americana_text():
        return get_setting_value(
            "americana_text",
            os.environ.get(
                "AMERICANA_TEXT",
                "Entdecke die Padel Americana App - das schnelle Turnierformat f\u00fcr deinen Club!",
            ),
        )

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
                if auto_open_at.tzinfo is None:
                    # datetime-local liefert naive Zeit in der Zeitzone des
                    # Browsers (Admin) -> als APP_TZ interpretieren.
                    auto_open_at = auto_open_at.replace(tzinfo=APP_TZ)
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
        if cfg["auto_open_at"] and cfg["auto_open_at"] <= datetime.now(APP_TZ):
            return True
        return False

    def signup_open_time():
        """Wann die Liste (zuletzt) geoeffnet wurde - Basis fuer die 24h-Sperre
        von Nichtmitgliedern im Modus 'member_priority_24h'.

        None, wenn der Oeffnungszeitpunkt nicht bestimmbar ist (dann greift
        keine 24h-Sperre, damit Gaeste nicht unbegruendet ausgesperrt werden).
        """
        cfg = signup_lock_settings()
        if not cfg["enabled"]:
            return None
        opened_raw = get_setting_value("signup_lock_opened_at", "")
        if opened_raw:
            try:
                return datetime.fromisoformat(opened_raw)
            except (ValueError, TypeError):
                pass
        # Manuelle Freigabe ohne aufgezeichneten Zeitpunkt (Altbestaende):
        # kein gesicherter Oeffnungszeitpunkt -> keine Sperre erzwingen.
        if cfg["manual_open"]:
            return None
        if cfg["auto_open_at"] and cfg["auto_open_at"] <= datetime.now():
            return cfg["auto_open_at"]
        return None

    def guest_delay_active():
        """True, wenn der Modus 'member_priority_24h' aktiv ist."""
        return get_waitlist_mode() == "member_priority_24h"

    def guest_allowed_at():
        """Zeitpunkt, ab dem sich Nichtmitglieder eintragen duerfen (oder None)."""
        open_time = signup_open_time()
        if open_time is None:
            return None
        return open_time + timedelta(hours=24)

    def _parse_hhmm(value):
        """'HH:MM' -> (h, m). None bei ungueltig."""
        if not value:
            return None
        parts = value.split(":")
        if len(parts) != 2:
            return None
        try:
            h, m = int(parts[0]), int(parts[1])
        except ValueError:
            return None
        if 0 <= h <= 23 and 0 <= m <= 59:
            return h, m
        return None

    def slot_close_info():
        """Pro-slot-Anmeldeschluss am Eventtag (naechster Donnerstag).

        Default: Startzeit des jeweiligen Slots. Admins koennen je Slot eine
        abweichende Zeit hinterlegen; dann wird der Anmeldefrist-Hinweis
        auf der Startseite (klein) angezeigt.
        """
        db = get_db()
        enabled = (
            get_setting_value("slot_close_enabled", DEFAULT_SLOT_CLOSE_ENABLED) == "1"
        )
        event_date = next_thursday()
        now = datetime.now(APP_TZ)

        slots_info = {}
        any_passed = False
        any_custom = False

        for slot in SLOT_DEFINITIONS:
            key = slot["key"]
            raw = get_setting_value(f"slot_close_time_{key}", "").strip()
            custom = bool(raw)
            hhmm = _parse_hhmm(raw)
            if hhmm is None:
                hh, mm = DEFAULT_SLOT_CLOSE_TIMES.get(key, (18, 0))
            else:
                hh, mm = hhmm
            deadline = datetime.combine(
                event_date, time(hh, mm), tzinfo=APP_TZ
            )
            closed = deadline <= now
            any_passed = any_passed or closed
            any_custom = any_custom or custom
            slots_info[key] = {
                "label": slot["label"],
                "deadline": deadline,
                "closed": closed,
                "custom": custom,
                "close_time_raw": raw,
            }

        return {
            "enabled": enabled,
            "slots": slots_info,
            "any_passed": any_passed,
            "any_custom": any_custom,
            "event_date": event_date,
        }

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
            SELECT id, name, name_normalized, is_member, admin_confirmed
            FROM signups
            WHERE slot_id = ? AND status = ?
            ORDER BY is_member DESC, created_at ASC
            """,
            (slot_id, status),
        ).fetchall()

    def get_admin_statuses():
        """Liefert {name_normalized: row} aus der admin_status Tabelle."""
        db = get_db()
        rows = db.execute(
            "SELECT name_normalized, name, status, note FROM admin_status"
        ).fetchall()
        return {row["name_normalized"]: dict(row) for row in rows}

    def get_admin_status_list():
        """Status-Eintraege fuer alle Orga-Mitglieder (fuer Dashboard + Anzeige)."""
        statuses = get_admin_statuses()
        result = []
        for name in ORGA_TEAM:
            norm = normalize_name(name)
            entry = statuses.get(norm, {"name": name, "status": "", "note": ""})
            entry["name_normalized"] = norm
            result.append(entry)
        return result

    def get_admin_status_visible():
        """Nur Orga-Mitglieder mit gesetztem Status (fuer Startseite + Liste)."""
        return [
            entry
            for entry in get_admin_status_list()
            if entry["status"] and entry["status"] != ""
        ]

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

        slots = db.execute("SELECT slot_key, label FROM slots").fetchall()
        slot_labels = {s["slot_key"]: s["label"] for s in slots}

        placeholders = {
            "next_thursday": next_thursday().strftime("%d.%m.%Y"),
            "slot_a": slot_labels.get("slot_a", "Slot 1"),
            "slot_b": slot_labels.get("slot_b", "Slot 2"),
            "event_name": "MATCHTREFF SILBER",
            "entry_count": str(get_max_entries_per_device()),
        }

        try:
            return text_template.format(**placeholders)
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
            "slot_icons": SLOT_ICONS,
            "orga_team": ORGA_TEAM,
            "telegram_channel_url": get_telegram_channel_url(),
            "homebrew_url": get_homebrew_url(),
            "homebrew_image": get_homebrew_image(),
            "paypal_url": get_paypal_url(),
            "paypal_image": get_paypal_image(),
                        "americana_url": get_americana_url(),
                        "americana_text": get_americana_text(),
                        "current_bg_style": bg_style_key,
            "bg_styles": BG_STYLES,
            "intro_text": get_intro_text(),
            "intro_placeholders": INTRO_PLACEHOLDERS,
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

        max_entries = get_max_entries_per_device()

        cookie_counts = {
            slot["slot_key"]: int(
                request.cookies.get(SIGNUP_COOKIE_PREFIX + slot["slot_key"]) or 0
            )
            for slot in slots
        }

        return render_template(
            "index.html",
            slots=slots,
            signups_by_slot=signups_by_slot,
            cookie_counts=cookie_counts,
            max_entries=max_entries,
            waitlist_limit=get_waitlist_limit(),
            is_admin=bool(session.get("is_admin")),
            signup_open=is_signup_open(),
            signup_lock_cfg=signup_lock_settings(),
                        slot_close=slot_close_info(),
                        admin_status_visible=get_admin_status_visible(),
                        admin_status_options=ADMIN_STATUS_OPTIONS,
                        guest_delay_active=guest_delay_active(),
                        guest_allowed_at=guest_allowed_at(),
                    )

    @app.route("/info")
    def info_page():
        return render_template("info.html", info_text=INFO_PAGE_TEXT)

    @app.route("/liste", methods=["GET", "POST"])
    def liste_ansicht():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            comment_text = request.form.get("comment", "").strip()

            if not comment_text:
                flash("Bitte gib einen Kommentar ein.", "danger")
                return redirect(url_for("liste_ansicht"))

            db = get_db()
            db.execute(
                """
                INSERT INTO liste_comments (name, comment)
                VALUES (?, ?)
                """,
                (name, comment_text),
            )
            db.commit()
            flash("Kommentar wurde hinzugefuegt.", "success")
            return redirect(url_for("liste_ansicht"))

        slots = get_slots_with_counts()
        signups_by_slot = {
            slot["id"]: {
                "confirmed": get_signups_for_slot(slot["id"], "confirmed"),
                "waitlist": get_signups_for_slot(slot["id"], "waitlist"),
            }
            for slot in slots
        }
        db = get_db()
        comments = db.execute(
            """
            SELECT id, name, comment, created_at
            FROM liste_comments
            ORDER BY created_at DESC
            LIMIT 50
            """
        ).fetchall()
        return render_template(
            "liste.html",
            slots=slots,
            signups_by_slot=signups_by_slot,
            waitlist_limit=get_waitlist_limit(),
            comments=comments,
            admin_status_visible=get_admin_status_visible(),
            admin_status_options=ADMIN_STATUS_OPTIONS,
        )

    @app.route("/downloads", methods=["GET", "POST"])
    def downloads():
        """Download-Bereich: Liste aller Dateien im static/downloads-Ordner."""
        download_dir = os.path.join(app.static_folder, "downloads")
        os.makedirs(download_dir, exist_ok=True)

        if request.method == "POST":
            if not session.get("is_admin"):
                flash("Nur Administratoren duerfen Dateien hochladen.", "danger")
                return redirect(url_for("downloads"))

            uploaded = request.files.get("file")
            if not uploaded or not uploaded.filename:
                flash("Bitte eine Datei auswaehlen.", "danger")
                return redirect(url_for("downloads"))

            filename = os.path.basename(uploaded.filename)
            if not filename:
                flash("Ungueltiger Dateiname.", "danger")
                return redirect(url_for("downloads"))

            # Nur bestimmte Endungen erlauben
            allowed = {".zip", ".apk", ".jpg", ".jpeg", ".png", ".webp", ".gif", ".pdf", ".mp4", ".txt"}
            ext = os.path.splitext(filename)[1].lower()
            if ext not in allowed:
                flash("Dateityp nicht erlaubt (erlaubt: " + ", ".join(sorted(allowed)) + ").", "danger")
                return redirect(url_for("downloads"))

            uploaded.save(os.path.join(download_dir, filename))
            flash("Datei hochgeladen: " + filename, "success")
            return redirect(url_for("downloads"))

        files = []
        for entry in os.scandir(download_dir):
            if entry.is_file():
                files.append(
                    {
                        "name": entry.name,
                        "size": entry.stat().st_size,
                        "mtime": entry.stat().st_mtime,
                    }
                )

        files.sort(key=lambda f: f["mtime"], reverse=True)

        def _fmt_size(size):
            if size >= 1024 * 1024:
                return f"{size / (1024 * 1024):.1f} MB"
            if size >= 1024:
                return f"{size / 1024:.0f} KB"
            return f"{size} B"

        return render_template(
            "downloads.html",
            files=files,
            fmt_size=_fmt_size,
        )

    @app.route("/downloads/<path:filename>/delete", methods=["POST"])
    @admin_required
    def downloads_delete(filename):
        """Loescht eine Datei aus dem Download-Bereich (nur Admin)."""
        download_dir = os.path.join(app.static_folder, "downloads")
        safe_name = os.path.basename(filename)
        path = os.path.join(download_dir, safe_name)

        if not os.path.exists(path) or not path.startswith(os.path.abspath(download_dir)):
            flash("Datei nicht gefunden.", "danger")
            return redirect(url_for("downloads"))

        try:
            os.remove(path)
            flash("Datei geloescht: " + safe_name, "info")
        except OSError:
            flash("Datei konnte nicht geloescht werden.", "danger")
        return redirect(url_for("downloads"))

    @app.route("/ueber-uns", methods=["GET", "POST"])
    def ueber_uns():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            recipient = request.form.get("recipient", "").strip()
            contact_channel = request.form.get("contact_channel", "").strip()
            contact_value = request.form.get("contact_value", "").strip()
            message_text = request.form.get("message", "").strip()

            if not message_text:
                flash("Bitte gib eine Nachricht ein.", "danger")
                return redirect(url_for("ueber_uns"))

            if not contact_channel or not contact_value:
                flash(
                    "Bitte gib einen Kontakt an (Telegram, WhatsApp oder E-Mail), "
                    "damit wir dir antworten koennen.",
                    "danger",
                )
                return redirect(url_for("ueber_uns"))

            db = get_db()
            db.execute(
                """
                INSERT INTO contact_messages (
                    name, email, recipient, contact_channel, contact_value, message
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, email, recipient, contact_channel, contact_value, message_text),
            )
            db.commit()
            forward_contact_message_to_admin(
                name, email, recipient, contact_channel, contact_value, message_text
            )

            flash(
                "Vielen Dank! Deine Nachricht wurde an uns uebermittelt.",
                "success",
            )
            return redirect(url_for("ueber_uns"))

        return render_template(
            "ueber_uns.html",
            orga_team=ORGA_TEAM,
        )

    @app.route("/chat", methods=["GET", "POST"])
    def chat():
        """Chatbox: Nachricht an Admins mit Pflicht-Kontakt + FAQ-Bereich."""
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            contact_channel = request.form.get("contact_channel", "").strip()
            contact_value = request.form.get("contact_value", "").strip()
            message_text = request.form.get("message", "").strip()

            if not message_text:
                flash("Bitte gib deine Nachricht ein.", "danger")
                return redirect(url_for("chat"))

            if not contact_channel or not contact_value:
                flash(
                    "Bitte gib an, wie wir dir antworten koennen "
                    "(Telegram, WhatsApp oder E-Mail).",
                    "danger",
                )
                return redirect(url_for("chat"))

            db = get_db()
            db.execute(
                """
                INSERT INTO contact_messages (
                    name, email, recipient, contact_channel, contact_value, message
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, "", "", contact_channel, contact_value, message_text),
            )
            db.commit()
            forward_contact_message_to_admin(
                name, "", "", contact_channel, contact_value, message_text
            )

            flash(
                "Vielen Dank! Deine Nachricht wurde an uns uebermittelt. "
                "Wir melden uns ueber deinen angegebenen Kontakt.",
                "success",
            )
            return redirect(url_for("chat"))

        db = get_db()
        faq = db.execute(
            """
            SELECT id, question, answer
            FROM faq_entries
            ORDER BY sort_order ASC, id ASC
            """
        ).fetchall()

        return render_template(
            "chat.html",
            faq=faq,
        )

    @app.route("/telegram/qr.png")
    def telegram_qr_png():
        """Serve QR code for the Telegram channel as PNG."""
        if qrcode is None:
            abort(404)

        channel_url = get_telegram_channel_url()
        if not channel_url:
            abort(404)

        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=8,
            border=2,
        )
        qr.add_data(channel_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        img_io = BytesIO()
        img.save(img_io, format="PNG")
        img_io.seek(0)

        return send_file(
            img_io,
            mimetype="image/png",
            as_attachment=False,
            download_name="telegram_qr.png",
        )

    @app.route("/eintragen", methods=["POST"])
    def eintragen():
        name = request.form.get("name", "").strip()
        selected_slots = request.form.getlist("slots")
        is_member = 1 if request.form.get("is_member") else 0
        delete_pin = _normalize_pin(request.form.get("delete_pin", ""))
        delete_pin_hash = (
            generate_password_hash(delete_pin) if delete_pin else None
        )

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

        # Modus 'member_priority_24h': Nichtmitglieder erst 24h nach Oeffnung.
        if (
            not is_admin_user
            and not is_member
            and waitlist_mode == "member_priority_24h"
        ):
            allowed_at = guest_allowed_at()
            if allowed_at is not None and datetime.now() < allowed_at:
                flash(
                    "Nichtmitglieder koennen sich erst 24 Stunden nach "
                    "Oeffnung der Liste eintragen.",
                    "danger",
                )
                return redirect(url_for("index"))

        slot_close = slot_close_info() if not is_admin_user else None

        for slot_key in selected_slots:
            cookie_name = SIGNUP_COOKIE_PREFIX + slot_key

            if (
                slot_close is not None
                and slot_close["enabled"]
                and slot_close["slots"][slot_key]["closed"]
            ):
                blocked_duplicate.append(
                    f"{SLOT_LABEL.get(slot_key, slot_key)} (Anmeldefrist abgelaufen)"
                )
                continue

            if not is_admin_user:
                cookie_value = request.cookies.get(cookie_name)
                current_count = 0
                if cookie_value:
                    try:
                        current_count = int(cookie_value)
                    except (ValueError, TypeError):
                        current_count = 0

                if current_count >= get_max_entries_per_device():
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
                        is_member,
                        delete_pin_hash
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        slot_row["id"],
                        name,
                        name_normalized,
                        status,
                        is_member,
                        delete_pin_hash,
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
                    cookie_name = SIGNUP_COOKIE_PREFIX + slot_key
                    prior = 0
                    raw_cookie = request.cookies.get(cookie_name)
                    if raw_cookie:
                        try:
                            prior = int(raw_cookie)
                        except (ValueError, TypeError):
                            prior = 0
                    new_count = min(prior + 1, get_max_entries_per_device())
                    response.set_cookie(
                        cookie_name,
                        str(new_count),
                        max_age=max_age,
                        httponly=True,
                        samesite="Lax",
                    )

        return response

    @app.route("/loeschen", methods=["GET", "POST"])
    def loeschen():
        """Eintrag ueber Name + Loesch-PIN stornieren."""
        db = get_db()
        ctx_name = session.get("delete_pin_context_name", "").strip()
        name = request.form.get("name", "").strip() or ctx_name
        current_signup = None
        slot_closed = False

        if name:
            norm = normalize_name(name)
            current_signup = db.execute(
                """
                SELECT *
                FROM signups
                WHERE name_normalized = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (norm,),
            ).fetchone()

            slot_closed = False
            if current_signup:
                slot_row = db.execute(
                    "SELECT slot_key FROM slots WHERE id = ?",
                    (current_signup["slot_id"],),
                ).fetchone()
                close_cfg = slot_close_info()
                slot_closed = bool(
                    slot_row
                    and close_cfg["enabled"]
                    and close_cfg["slots"][slot_row["slot_key"]]["closed"]
                )

        if request.method == "POST":
            if _ip_rate_limited():
                flash(
                    "Zu viele Loeschversuche von dieser IP. "
                    "Bitte versuche es spaeter erneut.",
                    "danger",
                )
                return redirect(url_for("loeschen"))

            if not name or not current_signup:
                session["delete_pin_context_name"] = name
                flash("Kein passender Eintrag gefunden.", "danger")
                return redirect(url_for("loeschen"))

            slot_row = db.execute(
                "SELECT slot_key FROM slots WHERE id = ?",
                (current_signup["slot_id"],),
            ).fetchone()
            close_cfg = slot_close_info()
            if (
                slot_row
                and close_cfg["enabled"]
                and close_cfg["slots"][slot_row["slot_key"]]["closed"]
            ):
                session["delete_pin_context_name"] = ""
                flash(
                    "Die Anmeldefrist fuer diesen Slot ist abgelaufen. "
                    "Ein Loeschen ist nicht mehr moeglich. "
                    "Bitte wende dich an einen Administrator.",
                    "danger",
                )
                return redirect(url_for("loeschen"))

            if not current_signup["delete_pin_hash"]:
                session["delete_pin_context_name"] = name
                flash(
                    "Fuer diesen Eintrag wurde kein Loesch-PIN gesetzt. "
                    "Bitte wende dich an einen Administrator.",
                    "danger",
                )
                return redirect(url_for("loeschen"))

            if _is_delete_locked(current_signup["id"]):
                flash(
                    "Der Loesch-PIN ist voruebergehend gesperrt. "
                    "Bitte versuche es in ein paar Minuten erneut.",
                    "danger",
                )
                return redirect(url_for("loeschen"))

            pin_input = _normalize_pin(request.form.get("pin", ""))
            if not pin_input:
                return render_template(
                    "loeschen.html",
                    name=current_signup["name"],
                    current_signup=current_signup,
                    pin_set=True,
                    remaining=_remaining_pin_attempts(current_signup["id"]),
                    slot_closed=slot_closed,
                )

            pin_ok = check_password_hash(
                current_signup["delete_pin_hash"], pin_input
            )

            if pin_ok:
                slot_id = current_signup["slot_id"]
                was_confirmed = current_signup["status"] == "confirmed"
                signup_name = current_signup["name"]

                db.execute(
                    "DELETE FROM signups WHERE id = ?",
                    (current_signup["id"],),
                )
                db.commit()
                _clear_pin_attempts(current_signup["id"])
                session.pop("delete_pin_context_name", None)

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
                            "Eintrag von " + signup_name + " geloescht. "
                            + next_waiting["name"]
                            + " ist von der Warteliste nachgerueckt.",
                            "info",
                        )
                        return redirect(url_for("index"))

                flash("Eintrag geloescht.", "info")
                return redirect(url_for("index"))

            _record_pin_failure(current_signup["id"])
            remaining = _remaining_pin_attempts(current_signup["id"])
            session["delete_pin_context_name"] = name
            if remaining <= 0:
                flash(
                    "Zu viele Fehlversuche. Der Loesch-PIN ist jetzt gesperrt.",
                    "danger",
                )
            else:
                flash(
                    "Falsche PIN. "
                    + str(remaining)
                    + " Versuch(e) verbleiben.",
                    "danger",
                )
            return render_template(
                "loeschen.html",
                name=current_signup["name"],
                current_signup=current_signup,
                pin_set=True,
                remaining=remaining,
                slot_closed=slot_closed,
            )

        return render_template(
            "loeschen.html",
            name=name,
            current_signup=current_signup,
            pin_set=bool(current_signup and current_signup["delete_pin_hash"]),
            remaining=DELETE_PIN_MIN_ATTEMPTS,
            slot_closed=slot_closed,
        )

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

        db = get_db()
        contact_messages = db.execute(
            """
                    SELECT id, name, email, recipient, contact_channel, contact_value,
                           message, is_read, created_at
                    FROM contact_messages
                    ORDER BY is_read ASC, created_at DESC
                    """
                ).fetchall()
        unread_messages_count = db.execute(
            "SELECT COUNT(*) AS c FROM contact_messages WHERE is_read = 0"
        ).fetchone()["c"]

        faq_entries = db.execute(
            """
            SELECT id, question, answer, sort_order
            FROM faq_entries
            ORDER BY sort_order ASC, id ASC
            """
        ).fetchall()

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
            telegram_channel_url=get_telegram_channel_url(),
            homebrew_url=get_homebrew_url(),
            homebrew_image=get_homebrew_image(),
            paypal_url=get_paypal_url(),
            paypal_image=get_paypal_image(),
            americana_url=get_americana_url(),
            americana_text=get_americana_text(),
            contact_messages=contact_messages,
            unread_messages_count=unread_messages_count,
            faq_entries=faq_entries,
            slot_close=slot_close_info(),
            admin_status_list=get_admin_status_list(),
            admin_status_options=ADMIN_STATUS_OPTIONS,
        )

    @app.route("/admin/status/update", methods=["POST"])
    @admin_required
    def admin_update_status():
        name = request.form.get("name", "").strip()
        status = request.form.get("status", "").strip()
        note = request.form.get("note", "").strip()

        if not name:
            flash("Name fehlt.", "danger")
            return redirect(url_for("admin_dashboard"))

        if status not in ADMIN_STATUS_OPTIONS:
            status = ""

        name_normalized = normalize_name(name)
        db = get_db()
        db.execute(
            """
            INSERT INTO admin_status (name_normalized, name, status, note)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(name_normalized) DO UPDATE SET
                name = excluded.name,
                status = excluded.status,
                note = excluded.note,
                updated_at = CURRENT_TIMESTAMP
            """,
            (name_normalized, name, status, note),
        )
        db.commit()
        flash(f"Status fuer {name} aktualisiert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/telegram-channel/update", methods=["POST"])
    @admin_required
    def admin_update_telegram_channel():
        channel_url = request.form.get("telegram_channel_url", "").strip()
        set_setting_value("telegram_channel_url", channel_url)
        flash("Telegram-Kanal-Link aktualisiert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/links/update", methods=["POST"])
    @admin_required
    def admin_update_links():
        set_setting_value("homebrew_url", request.form.get("homebrew_url", "").strip())
        set_setting_value("homebrew_image", request.form.get("homebrew_image", "homebrew.png").strip())
        set_setting_value("paypal_url", request.form.get("paypal_url", "").strip())
        set_setting_value("paypal_image", request.form.get("paypal_image", "Designer_Paypal_2.jpeg").strip())
        set_setting_value("americana_url", request.form.get("americana_url", "").strip())
        set_setting_value("americana_text", request.form.get("americana_text", "").strip())
        flash("Links aktualisiert.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/messages/<int:message_id>/read", methods=["POST"])
    @admin_required
    def admin_mark_message_read(message_id):
        db = get_db()
        db.execute(
            "UPDATE contact_messages SET is_read = 1 WHERE id = ?",
            (message_id,),
        )
        db.commit()
        flash("Nachricht als gelesen markiert.", "info")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/messages/<int:message_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_message(message_id):
        db = get_db()
        db.execute("DELETE FROM contact_messages WHERE id = ?", (message_id,))
        db.commit()
        flash("Nachricht geloescht.", "info")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/faq/add", methods=["POST"])
    @admin_required
    def admin_faq_add():
        question = request.form.get("question", "").strip()
        answer = request.form.get("answer", "").strip()
        sort_order = request.form.get("sort_order", "0").strip()

        if not question or not answer:
            flash("Bitte Frage und Antwort angeben.", "danger")
            return redirect(url_for("admin_dashboard"))

        try:
            sort_order = int(sort_order)
        except ValueError:
            sort_order = 0

        db = get_db()
        db.execute(
            """
            INSERT INTO faq_entries (question, answer, sort_order)
            VALUES (?, ?, ?)
            """,
            (question, answer, sort_order),
        )
        db.commit()
        flash("FAQ-Eintrag hinzugefuegt.", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/faq/<int:faq_id>/delete", methods=["POST"])
    @admin_required
    def admin_faq_delete(faq_id):
        db = get_db()
        db.execute("DELETE FROM faq_entries WHERE id = ?", (faq_id,))
        db.commit()
        flash("FAQ-Eintrag geloescht.", "info")
        return redirect(url_for("admin_dashboard"))

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

    @app.route("/admin/waitlist/<int:signup_id>/confirm", methods=["POST"])
    @admin_required
    def admin_confirm_waitlist(signup_id):
        """Bestaetigt einen Wartelisten-Eintrag (bleibt auf der Warteliste)."""
        db = get_db()
        signup = db.execute(
            "SELECT * FROM signups WHERE id = ? AND status = 'waitlist'",
            (signup_id,),
        ).fetchone()

        if signup is None:
            flash("Wartelisten-Eintrag nicht gefunden.", "danger")
            return redirect(url_for("admin_dashboard"))

        db.execute(
            "UPDATE signups SET admin_confirmed = 1 WHERE id = ?",
            (signup_id,),
        )
        db.commit()
        flash(f"{signup['name']} wurde bestaetigt (bleibt auf der Warteliste).", "success")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/waitlist/<int:signup_id>/promote", methods=["POST"])
    @admin_required
    def admin_promote_waitlist(signup_id):
        """Bestaetigt einen Wartelisten-Eintrag und setzt ihn direkt auf die Liste."""
        db = get_db()
        signup = db.execute(
            "SELECT * FROM signups WHERE id = ? AND status = 'waitlist'",
            (signup_id,),
        ).fetchone()

        if signup is None:
            flash("Wartelisten-Eintrag nicht gefunden.", "danger")
            return redirect(url_for("admin_dashboard"))

        slot_row = db.execute(
            "SELECT * FROM slots WHERE id = ?",
            (signup["slot_id"],),
        ).fetchone()

        confirmed_count = db.execute(
            "SELECT COUNT(*) AS c FROM signups "
            "WHERE slot_id = ? AND status = 'confirmed'",
            (signup["slot_id"],),
        ).fetchone()["c"]

        db.execute(
            "UPDATE signups SET status = 'confirmed', admin_confirmed = 1 WHERE id = ?",
            (signup_id,),
        )
        db.commit()

        if slot_row and confirmed_count >= slot_row["max_players"]:
            flash(
                f"{signup['name']} wurde direkt auf die Liste gesetzt "
                f"(Achtung: Slot war bereits voll).",
                "info",
            )
        else:
            flash(f"{signup['name']} wurde direkt auf die Liste gesetzt.", "success")
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
            set_setting_value(
                "signup_lock_opened_at",
                datetime.now(APP_TZ).replace(tzinfo=None).isoformat(),
            )
            flash("Anmeldung manuell geoeffnet.", "success")
        elif action == "close":
            set_setting_value("signup_lock_manual_open", "0")
            set_setting_value("signup_lock_auto_open_at", "")
            set_setting_value("signup_lock_opened_at", "")
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
                set_setting_value("signup_lock_opened_at", "")
                flash("Automatische Oeffnung geplant.", "success")
            else:
                flash("Bitte ein Datum und Uhrzeit angeben.", "danger")
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/slot-close/update", methods=["POST"])
    @admin_required
    def admin_update_slot_close():
        """Anmeldeschluss je Slot (optional). Leer = Standardzeit (Slot-Start)."""
        enabled = "1" if request.form.get("slot_close_enabled") else "0"
        set_setting_value("slot_close_enabled", enabled)

        for slot in SLOT_DEFINITIONS:
            key = slot["key"]
            raw = request.form.get(f"slot_close_time_{key}", "").strip()
            hhmm = _parse_hhmm(raw) if raw else None
            if raw and hhmm is None:
                flash(
                    f"Ungueltige Anmeldefrist fuer {slot['label']}. "
                    "Bitte im Format HH:MM angeben.",
                    "danger",
                )
                return redirect(url_for("admin_dashboard"))
            set_setting_value(f"slot_close_time_{key}", raw)

        flash(
            "Anmeldefrist-Einstellungen gespeichert. Leere Felder = Standard.",
            "success",
        )
        return redirect(url_for("admin_dashboard"))

    @app.route("/admin/backup/download")
    @admin_required
    def admin_backup_download():
        return send_file(
            app.config["DATABASE"],
            as_attachment=True,
            download_name="matchtreff_backup.sqlite3",
        )

    @app.route("/admin/export/pdf")
    @admin_required
    def admin_export_pdf():
        slots_list = get_slots_with_counts()
        event_date = next_thursday().strftime("%d.%m.%Y")
        data = []
        for slot in slots_list:
            confirmed = [s["name"] for s in get_signups_for_slot(slot["id"], "confirmed")]
            waitlist = [s["name"] for s in get_signups_for_slot(slot["id"], "waitlist")]
            data.append({
                "label": slot["label"],
                "confirmed": confirmed,
                "waitlist": waitlist,
            })
        pdf = build_checklist_pdf(data, event_date)
        return send_file(
            BytesIO(pdf),
            mimetype="application/pdf",
            as_attachment=True,
            download_name="anmeldeliste.pdf",
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
