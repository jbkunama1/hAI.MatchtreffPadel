import os
import sys
import sqlite3
import json
import urllib.request
from datetime import datetime, timedelta
from flask import Flask, g
from werkzeug.security import generate_password_hash

_REQUIRED_ENV = ["SECRET_KEY", "ADMIN_PASSWORD_ADMIN", "ADMIN_PASSWORD_DANIEL"]
_missing = [v for v in _REQUIRED_ENV if not os.environ.get(v, "").strip()]
if _missing:
    missing_list = ", ".join(_missing)
    print(f"[FEHLER] Fehlende Pflicht-Umgebungsvariablen: {missing_list}\nBitte in der .env auf dem Host setzen. Anwendung wird beendet.", file=sys.stderr)
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
DEFAULT_MAX_PLAYERS = 14
DEFAULT_THEME = "night"
DEFAULT_CUSTOM_IMAGE = "Racketfire.png"

def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        DATABASE=os.path.join(app.instance_path, "matchtreff.sqlite3"),
    )
    if test_config is not None:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    def next_thursday():
        today = datetime.today().date()
        days_ahead = (3 - today.weekday()) % 7
        if days_ahead == 0:
            days_ahead = 7
        return today + timedelta(days=days_ahead)

    def get_db():
        if "db" not in g:
            g.db = sqlite3.connect(app.config["DATABASE"], detect_types=sqlite3.PARSE_DECLTYPES, timeout=10)
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

    def ensure_current_event(db):
        event_date = next_thursday()
        row = db.execute("SELECT id FROM events WHERE event_date = ?", (event_date,)).fetchone()
        if row:
            return row["id"]
        db.execute("INSERT INTO events (title, event_date, is_default) VALUES (?, ?, 1)", (f"Matchtreff {event_date.strftime('%d.%m.%Y')}", event_date))
        event_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        for s in SLOT_DEFINITIONS:
            db.execute("INSERT INTO slots (event_id, slot_key, label, max_players) VALUES (?, ?, ?, ?)", (event_id, s["key"], s["label"], DEFAULT_MAX_PLAYERS))
        db.commit()
        return event_id

    def init_db():
        db = get_db()
        db.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            event_date DATE NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            slot_key TEXT NOT NULL,
            label TEXT NOT NULL,
            max_players INTEGER NOT NULL DEFAULT 8,
            FOREIGN KEY(event_id) REFERENCES events(id),
            UNIQUE(event_id, slot_key)
        );
        CREATE TABLE IF NOT EXISTS signups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            name_normalized TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'confirmed',
            is_member INTEGER NOT NULL DEFAULT 1,
            telegram_user_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(slot_id) REFERENCES slots(id),
            UNIQUE(slot_id, name_normalized)
        );
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            signup_id INTEGER NOT NULL,
            text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(signup_id) REFERENCES signups(id) ON DELETE CASCADE
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
        """)
        cols = [r[1] for r in db.execute("PRAGMA table_info(signups)").fetchall()]
        if "is_member" not in cols:
            db.execute("ALTER TABLE signups ADD COLUMN is_member INTEGER NOT NULL DEFAULT 1")
        cols = [r[1] for r in db.execute("PRAGMA table_info(signups)").fetchall()]
        if "telegram_user_id" not in cols:
            db.execute("ALTER TABLE signups ADD COLUMN telegram_user_id INTEGER")
        ensure_current_event(db)
        if not db.execute("SELECT value FROM settings WHERE key = 'theme'").fetchone():
            db.execute("INSERT INTO settings (key, value) VALUES ('theme', ?)", (DEFAULT_THEME,))
        if not db.execute("SELECT value FROM settings WHERE key = 'custom_bg_image'").fetchone():
            db.execute("INSERT INTO settings (key, value) VALUES ('custom_bg_image', ?)", (DEFAULT_CUSTOM_IMAGE,))
        for seed_name, seed_password in SEED_ADMIN_USERS.items():
            if seed_password and not db.execute("SELECT id FROM admin_users WHERE username = ?", (seed_name,)).fetchone():
                db.execute("INSERT INTO admin_users (username, password_hash, created_by) VALUES (?, ?, ?)", (seed_name, generate_password_hash(seed_password), "system"))
        db.commit()

    with app.app_context():
        init_db()

    @app.route("/")
    def index():
        return {"ok": True}

    return app

app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "1905"))
    app.run(host="0.0.0.0", port=port)
