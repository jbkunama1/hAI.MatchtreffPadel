"""Tests fuer die Scheduler-Kernlogik (scheduler_new.py).

Alle Funktionen laufen gegen eine Temp-SQLite-DB - kein Netzwerk, kein Telegram.
Telegram-Aufrufe werden gemockt, wo noetig.
"""

import sqlite3
from pathlib import Path

import pytest

import scheduler_new


@pytest.fixture()
def db_path(tmp_path) -> Path:
    path = tmp_path / "matchtreff.sqlite3"
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_key TEXT UNIQUE NOT NULL,
                label TEXT NOT NULL,
                max_players INTEGER NOT NULL DEFAULT 8
            );
            CREATE TABLE signups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                name_normalized TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'confirmed',
                is_member INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE telegram_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_id INTEGER UNIQUE NOT NULL,
                username TEXT,
                first_name TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                is_member_default INTEGER NOT NULL DEFAULT 1,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO slots (slot_key, label, max_players)
            VALUES ('slot_a', 'Slot A', 8);
            """
        )
        conn.commit()
    finally:
        conn.close()
    return path


def _rows(path: Path, query: str, args=()):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(query, args).fetchall()
    finally:
        conn.close()


def test_normalize_name_collapses_whitespace_and_lowercases():
    assert scheduler_new.normalize_name("  Max   Mustermann ") == "max mustermann"
    assert scheduler_new.normalize_name("ALPHA") == "alpha"


def test_get_and_set_setting(db_path):
    conn = scheduler_new.get_conn(db_path)
    try:
        assert scheduler_new.get_setting(conn, "unbekannt", "fallback") == "fallback"
        scheduler_new.set_setting(conn, "mein_key", "mein_wert")
        conn.commit()
        assert scheduler_new.get_setting(conn, "mein_key", None) == "mein_wert"
        # Upsert: gleicher Key wird ueberschrieben
        scheduler_new.set_setting(conn, "mein_key", "neuer_wert")
        conn.commit()
        assert scheduler_new.get_setting(conn, "mein_key", None) == "neuer_wert"
    finally:
        conn.close()


def test_weekly_reset_deletes_signups_and_resets_lock(db_path):
    conn = scheduler_new.get_conn(db_path)
    try:
        conn.execute(
            "INSERT INTO signups (slot_id, name, name_normalized, status) "
            "VALUES (1, 'Spieler', 'spieler', 'confirmed')"
        )
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('signup_lock_manual_open', '1')"
        )
        conn.commit()
    finally:
        conn.close()

    scheduler_new.weekly_reset(db_path, "", [])

    assert _rows(db_path, "SELECT COUNT(*) FROM signups")[0][0] == 0
    assert (
        _rows(db_path, "SELECT value FROM settings WHERE key = 'signup_lock_manual_open'")[0][0]
        == "0"
    )
    assert _rows(
        db_path, "SELECT value FROM settings WHERE key = 'last_auto_reset_at'"
    )


def test_weekly_reset_skipped_when_disabled(db_path):
    conn = scheduler_new.get_conn(db_path)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('reset_enabled', '0')"
        )
        conn.execute(
            "INSERT INTO signups (slot_id, name, name_normalized, status) "
            "VALUES (1, 'Spieler', 'spieler', 'confirmed')"
        )
        conn.commit()
    finally:
        conn.close()

    scheduler_new.weekly_reset(db_path, "", [])

    assert _rows(db_path, "SELECT COUNT(*) FROM signups")[0][0] == 1


def test_digest_new_signups_collects_only_new(db_path, monkeypatch):
    conn = scheduler_new.get_conn(db_path)
    try:
        conn.execute(
            "INSERT INTO signups (slot_id, name, name_normalized, status, created_at) "
            "VALUES (1, 'Alt', 'alt', 'confirmed', '2026-01-01 10:00:00')"
        )
        conn.execute(
            "INSERT INTO signups (slot_id, name, name_normalized, status, created_at) "
            "VALUES (1, 'Neu', 'neu', 'confirmed', '2026-08-04 12:00:00')"
        )
        conn.execute(
            "INSERT INTO settings (key, value) VALUES "
            "('digest_last_sent_at', '2026-08-04 11:00:00')"
        )
        conn.commit()
    finally:
        conn.close()

    sent_messages = []

    def fake_api(method, payload, token):
        if method == "sendMessage":
            sent_messages.append(payload.get("text", ""))
        return {"ok": True}

    monkeypatch.setattr(scheduler_new, "telegram_api_call", fake_api)

    scheduler_new.digest_new_signups(db_path, "token", ["12345"])

    assert len(sent_messages) == 1
    assert "Neu" in sent_messages[0]
    assert "Alt" not in sent_messages[0]


def test_digest_no_new_signups_sends_nothing(db_path, monkeypatch):
    called = []

    def fake_api(method, payload, token):
        called.append(payload)
        return {"ok": True}

    monkeypatch.setattr(scheduler_new, "telegram_api_call", fake_api)

    scheduler_new.digest_new_signups(db_path, "token", ["12345"])
    assert called == []


def test_reminder_matches_telegram_user_and_sends(db_path, monkeypatch):
    conn = scheduler_new.get_conn(db_path)
    try:
        conn.execute(
            "INSERT INTO signups (slot_id, name, name_normalized, status) "
            "VALUES (1, 'Max Mustermann', 'max mustermann', 'confirmed')"
        )
        conn.execute(
            "INSERT INTO telegram_users (telegram_id, first_name) "
            "VALUES (999, 'Max Mustermann')"
        )
        conn.commit()
    finally:
        conn.close()

    sent = []

    def fake_api(method, payload, token):
        if method == "sendMessage":
            sent.append(payload.get("text", ""))
        return {"ok": True}

    monkeypatch.setattr(scheduler_new, "telegram_api_call", fake_api)

    scheduler_new.reminder_participants(db_path, "token", ["111"])
    assert len(sent) == 2  # 1x Teilnehmer + 1x Admin-Zusammenfassung
    assert "Max Mustermann" in sent[0]
