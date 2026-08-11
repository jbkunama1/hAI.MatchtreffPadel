"""Datenbankzugriff (SQLite) und Schema-Initalisierung.

Wird von der Web-App genutzt und haelt die DB-Verbindung je Anfrage (Flask g).
Das Schema bleibt unveraendert, damit kein Datenverlust entsteht.
"""

import logging
import sqlite3

from flask import current_app, g

from werkzeug.security import generate_password_hash

from logic_settings import (
    DEFAULT_MAX_PLAYERS,
    SLOT_DEFINITIONS,
    get_setting_defaults,
)

logger = logging.getLogger("matchtreff.web.db")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
            timeout=10,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
        g.db.execute("PRAGMA journal_mode = WAL")
        g.db.execute("PRAGMA busy_timeout = 8000")
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(seed_admin_users):
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

                CREATE TABLE IF NOT EXISTS signup_delete_ip_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_hash TEXT NOT NULL,
                    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    columns = [row[1] for row in db.execute("PRAGMA table_info(signups)").fetchall()]
    if "delete_pin_hash" not in columns:
        db.execute(
            "ALTER TABLE signups ADD COLUMN delete_pin_hash TEXT"
        )

    columns = [row[1] for row in db.execute("PRAGMA table_info(signups)").fetchall()]
    if "is_member" not in columns:
        db.execute(
            "ALTER TABLE signups ADD COLUMN is_member INTEGER NOT NULL DEFAULT 1"
        )

    for key, value in get_setting_defaults().items():
        db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO NOTHING",
            (key, value),
        )

    for seed_name, seed_password in seed_admin_users.items():
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
