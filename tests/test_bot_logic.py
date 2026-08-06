"""Tests fuer die Telegram-Bot-Kernlogik (telegram_bot.py).

Getestet werden nur die reinen DB-/Statusfunktionen (kein Netzwerk).
Die Funktionen akzeptieren eine sqlite3.Connection - wir bauen eine eigene
Temp-DB auf, damit DB_PATH nicht global umgestellt werden muss.
"""

import sqlite3
from pathlib import Path

import pytest

import telegram_bot


@pytest.fixture()
def conn(tmp_path) -> sqlite3.Connection:
    path: Path = tmp_path / "matchtreff.sqlite3"
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.executescript(
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
        VALUES ('slot_a', 'Slot A', 2);
        """
    )
    c.commit()
    return c


def _add_signup(conn, name, status="confirmed", is_member=1):
    conn.execute(
        """
        INSERT INTO signups (slot_id, name, name_normalized, status, is_member)
        VALUES (1, ?, ?, ?, ?)
        """,
        (name, telegram_bot.normalize_name(name), status, is_member),
    )
    conn.commit()


def _set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()


def test_normalize_name():
    assert telegram_bot.normalize_name("  Test   Person ") == "test person"


def test_determine_status_free_slot_is_confirmed(conn):
    status, reason = telegram_bot.determine_signup_status(conn, 1, True)
    assert status == "confirmed"
    assert reason is None


def test_determine_status_full_slot_with_waitlist(conn):
    _add_signup(conn, "Spieler Eins")
    _add_signup(conn, "Spieler Zwei")  # max_players = 2 -> voll

    status, reason = telegram_bot.determine_signup_status(conn, 1, True)
    assert status == "waitlist"
    assert reason is None


def test_determine_status_no_waitlist_mode_blocks(conn):
    _set_setting(conn, "waitlist_mode", "no_waitlist")
    _add_signup(conn, "Spieler Eins")
    _add_signup(conn, "Spieler Zwei")

    status, reason = telegram_bot.determine_signup_status(conn, 1, True)
    assert status is None
    assert reason == "Slot voll"


def test_determine_status_guests_only_mode_puts_guest_on_waitlist(conn):
    _set_setting(conn, "waitlist_mode", "guests_only")
    _add_signup(conn, "Mitglied Eins")  # Slot voll (2/2)
    _add_signup(conn, "Mitglied Zwei")

    status, reason = telegram_bot.determine_signup_status(conn, 1, False)
    assert status == "waitlist"
    assert reason is None


def test_determine_status_open_for_all_ignores_capacity(conn):
    _set_setting(conn, "waitlist_mode", "open_for_all")
    _add_signup(conn, "Spieler Eins")
    _add_signup(conn, "Spieler Zwei")

    status, reason = telegram_bot.determine_signup_status(conn, 1, True)
    assert status == "confirmed"
    assert reason is None


def test_promote_waiting_signup_moves_oldest(conn):
    _add_signup(conn, "Erster")
    _add_signup(conn, "Zweiter")
    _add_signup(conn, "Dritter", status="waitlist")  # Slot voll -> Warteliste

    promoted = telegram_bot.promote_waiting_signup(conn, 1)
    assert promoted is not None
    assert promoted["name"] == "Dritter"

    row = conn.execute(
        "SELECT status FROM signups WHERE name = 'Dritter'"
    ).fetchone()
    assert row["status"] == "confirmed"


def test_promote_waiting_signup_none_when_empty(conn):
    assert telegram_bot.promote_waiting_signup(conn, 1) is None
