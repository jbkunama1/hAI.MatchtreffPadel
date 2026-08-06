"""Smoke-Tests fuer die Flask-Web-App (app.py).

Deckt die Kernpfade ab: Seiten laden, Anmeldung, Warteliste,
Anmeldesperre, Admin-Login und Admin-Aktionen.

Jeder Test bekommt eine frische App mit eigener Temp-DB.
"""

import sqlite3
from pathlib import Path

import pytest

import app as app_module


@pytest.fixture()
def client(tmp_path):
    db_path = tmp_path / "matchtreff.sqlite3"
    app = app_module.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-key",
            "DATABASE": str(db_path),
        }
    )
    return app.test_client()


@pytest.fixture()
def admin_client(client):
    resp = client.post(
        "/admin/login",
        data={"username": "Admin", "password": "test-admin-pw"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    return client


def _db_rows(path: Path, query: str, args=()):
    conn = sqlite3.connect(path)
    try:
        return conn.execute(query, args).fetchall()
    finally:
        conn.close()


def test_index_page_loads(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Matchtreff" in resp.data


def test_info_page_loads(client):
    resp = client.get("/info")
    assert resp.status_code == 200


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_signup_without_name_is_rejected(client):
    resp = client.post("/eintragen", data={}, follow_redirects=False)
    assert resp.status_code == 302


def test_signup_requires_open_lock_for_normal_user(client, tmp_path):
    # Standard-Konfiguration: signup_lock_enabled=1, nicht manuell geoeffnet.
    resp = client.post(
        "/eintragen",
        data={"name": "Testspieler", "slots": ["slot_a"], "is_member": "1"},
        follow_redirects=True,
    )
    assert b"gesperrt" in resp.data


def test_signup_after_deadline_blocked_when_slot_close_enabled(client, tmp_path):
    # slot_close_enabled=1 (Default) und Deadline vorbei -> Block.
    db_path = str(tmp_path / "matchtreff.sqlite3")
    _set_setting(db_path, "signup_lock_manual_open", "1")

    resp = client.post(
        "/eintragen",
        data={"name": "Testspieler", "slots": ["slot_a"], "is_member": "1"},
        follow_redirects=True,
    )
    assert b"Anmeldefrist abgelaufen" in resp.data
    assert _db_rows(db_path, "SELECT COUNT(*) FROM signups")[0][0] == 0


def test_signup_open_lock_normal_user_can_signup(client, tmp_path):
    db_path = str(tmp_path / "matchtreff.sqlite3")

    def _open():
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('signup_lock_manual_open', '1') "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            )
            conn.commit()
        finally:
            conn.close()

    # App-Neustart noetig, da get_db() per Request eh frisch liest - es reicht,
    # das Setting zu setzen und dann ueber die Route zu signupen.
    _open()
    _disable_slot_close(db_path)

    resp = client.post(
        "/eintragen",
        data={"name": "Testspieler", "slots": ["slot_a"], "is_member": "1"},
        follow_redirects=True,
    )
    assert b"Eingetragen" in resp.data


def test_signup_adds_row_and_sets_cookie(client, tmp_path):
    db_path = str(tmp_path / "matchtreff.sqlite3")
    # Liste oeffnen
    _set_setting(db_path, "signup_lock_manual_open", "1")
    _disable_slot_close(db_path)

    resp = client.post(
        "/eintragen",
        data={"name": "Max Mustermann", "slots": ["slot_a"], "is_member": "1"},
    )
    assert resp.status_code == 302
    assert "mtp_signed_slot_a" in resp.headers.get("Set-Cookie", "")

    rows = _db_rows(
        db_path,
        "SELECT name, status FROM signups WHERE slot_id = "
        "(SELECT id FROM slots WHERE slot_key = 'slot_a')",
    )
    assert rows == [("Max Mustermann", "confirmed")]


def test_signup_duplicate_is_blocked(client, tmp_path):
    db_path = str(tmp_path / "matchtreff.sqlite3")
    _set_setting(db_path, "signup_lock_manual_open", "1")
    _disable_slot_close(db_path)

    client.post(
        "/eintragen",
        data={"name": "Max Mustermann", "slots": ["slot_a"], "is_member": "1"},
    )
    # Frischer Client (ohne mtp_signed_-Cookie), damit der zweite Versuch
    # nicht wegen "bereits von diesem Geraet" blockt, sondern wegen Duplikat.
    client2 = client.application.test_client()
    resp = client2.post(
        "/eintragen",
        data={"name": "Max Mustermann", "slots": ["slot_a"], "is_member": "1"},
        follow_redirects=True,
    )
    assert b"Name bereits vorhanden" in resp.data

    rows = _db_rows(
        db_path,
        "SELECT COUNT(*) FROM signups WHERE name = 'Max Mustermann'",
    )
    assert rows[0][0] == 1


def test_signup_moves_to_waitlist_when_slot_full(client, tmp_path):
    db_path = str(tmp_path / "matchtreff.sqlite3")
    _set_setting(db_path, "signup_lock_manual_open", "1")
    _disable_slot_close(db_path)
    # Maximal 1 Spieler pro Slot
    _set_slot_max(db_path, "slot_a", 1)

    client.post(
        "/eintragen",
        data={"name": "Spieler Eins", "slots": ["slot_a"], "is_member": "1"},
    )
    # Frischer Client, damit Spieler Zwei nicht durch das Cookie blockt
    client2 = client.application.test_client()
    resp = client2.post(
        "/eintragen",
        data={"name": "Spieler Zwei", "slots": ["slot_a"], "is_member": "1"},
        follow_redirects=True,
    )
    assert b"Warteliste" in resp.data

    rows = _db_rows(
        db_path,
        "SELECT name, status FROM signups WHERE slot_id = "
        "(SELECT id FROM slots WHERE slot_key = 'slot_a') ORDER BY name",
    )
    assert ("Spieler Eins", "confirmed") in rows
    assert ("Spieler Zwei", "waitlist") in rows


def test_admin_login_wrong_password_stays_on_login(client):
    resp = client.post(
        "/admin/login",
        data={"username": "Admin", "password": "falsches-passwort"},
        follow_redirects=False,
    )
    assert resp.status_code == 200
    assert b"falsch" in resp.data


def test_admin_login_correct_redirects_to_dashboard(client):
    resp = client.post(
        "/admin/login",
        data={"username": "Admin", "password": "test-admin-pw"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin" in resp.headers.get("Location", "")


def test_admin_dashboard_requires_login(client):
    resp = client.get("/admin", follow_redirects=False)
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers.get("Location", "")


def test_admin_dashboard_renders_after_login(admin_client):
    resp = admin_client.get("/admin")
    assert resp.status_code == 200


def test_admin_delete_confirmed_promotes_waiting(admin_client, tmp_path):
    db_path = str(tmp_path / "matchtreff.sqlite3")
    _set_setting(db_path, "signup_lock_manual_open", "1")
    _set_slot_max(db_path, "slot_a", 1)

    admin_client.post(
        "/eintragen",
        data={"name": "Erster", "slots": ["slot_a"], "is_member": "1"},
    )
    admin_client.post(
        "/eintragen",
        data={"name": "Zweiter", "slots": ["slot_a"], "is_member": "1"},
    )

    signup_id = _db_rows(
        db_path,
        "SELECT id FROM signups WHERE name = 'Erster'",
    )[0][0]

    resp = admin_client.post(
        f"/admin/signup/{signup_id}/delete",
        follow_redirects=True,
    )
    assert b"nachgerueckt" in resp.data

    rows = _db_rows(
        db_path,
        "SELECT name, status FROM signups WHERE slot_id = "
        "(SELECT id FROM slots WHERE slot_key = 'slot_a')",
    )
    assert rows == [("Zweiter", "confirmed")]


def test_admin_update_slot_max_players(admin_client, tmp_path):
    db_path = str(tmp_path / "matchtreff.sqlite3")
    slot_id = _db_rows(db_path, "SELECT id FROM slots WHERE slot_key = 'slot_a'")[0][0]

    resp = admin_client.post(
        f"/admin/slot/{slot_id}/update",
        data={"max_players": "6", "label": ""},
        follow_redirects=True,
    )
    assert b"Maximale Anzahl aktualisiert" in resp.data

    rows = _db_rows(db_path, "SELECT max_players FROM slots WHERE id = ?", (slot_id,))
    assert rows[0][0] == 6


def _set_setting(db_path: Path, key: str, value: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        conn.commit()
    finally:
        conn.close()


def _disable_slot_close(db_path: Path) -> None:
    """Disable slot-close deadlines so signup flow isn't blocked by time-based closures."""
    _set_setting(db_path, "slot_close_enabled", "0")


def _set_slot_max(db_path: Path, slot_key: str, max_players: int) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE slots SET max_players = ? WHERE slot_key = ?",
            (max_players, slot_key),
        )
        conn.commit()
    finally:
        conn.close()
