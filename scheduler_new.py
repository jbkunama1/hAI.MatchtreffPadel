"""Scheduler-Kern (importiert von scheduler.py).

Enthaelt alle Job-Funktionen des Automatik-Containers. Die tatsaechliche
Einplanung und der Config-Watcher laufen in scheduler.py::main().
"""

import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from logging_config import setup_logging
from logic_settings import normalize_name
from logic_telegram import telegram_api_call

logger = setup_logging(name="matchtreff.scheduler_jobs")

# Zeitzone des Schedulers (matches APScheduler-Konfiguration).
SCHED_TZ = ZoneInfo("Europe/Berlin")

# SQLite CURRENT_TIMESTAMP-Format: "2026-08-02 17:00:00"
SQLITE_TS_FMT = "%Y-%m-%d %H:%M:%S"


def get_conn(db_path):
    conn = sqlite3.connect(db_path, detect_types=sqlite3.PARSE_DECLTYPES, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 8000")
    return conn


def get_setting(conn, key, default=None):
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value):
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def notify_admins(text, token, admin_ids):
    for admin_id in admin_ids:
        telegram_api_call("sendMessage", {"chat_id": admin_id, "text": text}, token)


def weekly_reset(db_path, token, admin_ids):
    """Loescht ALLE Anmeldungen (signups) -> neue Woche, neuer Anfang."""
    conn = get_conn(db_path)

    reset_enabled = get_setting(conn, "reset_enabled", "1") == "1"
    if not reset_enabled:
        logger.info("Automatischer Reset ist deaktiviert (reset_enabled=0) - uebersprungen.")
        conn.close()
        return

    conn.execute("DELETE FROM signups")

    # Nach dem Reset: Anmeldesperre zuruecksetzen auf Standard (geschlossen).
    # Manuelle Oeffnung und geplante Auto-Oeffnung werden entfernt, sodass die
    # neue Woche wieder standardmaessig (manuell durch Admin) freigeschaltet wird.
    set_setting(conn, "signup_lock_manual_open", "0")
    set_setting(conn, "signup_lock_auto_open_at", "")
    set_setting(conn, "signup_lock_opened_at", "")

    now_str = datetime.now(SCHED_TZ).strftime(SQLITE_TS_FMT)
    set_setting(conn, "last_auto_reset_at", now_str)
    conn.commit()
    conn.close()

    notify_admins(
        f"Automatischer Reset ausgefuehrt am {now_str} - alle Anmeldungen wurden geloescht.",
        token,
        admin_ids,
    )
    logger.info("Reset ausgefuehrt am %s", now_str)


def digest_new_signups(db_path, token, admin_ids):
    """Sammelt alle Anmeldungen seit dem letzten Digest und schickt EINE
    Zusammenfassung an die Telegram-Admins."""
    conn = get_conn(db_path)

    last_value = get_setting(conn, "digest_last_sent_at")
    if not last_value:
        last_ts = datetime.min
    else:
        try:
            last_ts = datetime.strptime(last_value, SQLITE_TS_FMT)
        except ValueError:
            last_ts = datetime.min

    # created_at ist SQLite TEXT im Format "%Y-%m-%d %H:%M:%S" -> konsistent
    # vergleichen (kein isoformat() mit 'T', sonst schlaeft der Vergleich fehl).
    new_signups = conn.execute(
        """
        SELECT s.id, s.name, s.status, s.created_at, sl.label AS slot_label
        FROM signups s
        JOIN slots sl ON sl.id = s.slot_id
        WHERE s.created_at > ?
        ORDER BY s.created_at ASC
        """,
        (last_ts.strftime(SQLITE_TS_FMT),),
    ).fetchall()

    if not new_signups:
        conn.close()
        return

    lines = ["Neue Anmeldungen (Digest):", ""]
    by_slot = {}
    for row in new_signups:
        key = (row["slot_label"], row["status"])
        by_slot.setdefault(key, []).append(row["name"])

    for (slot_label, status), names in by_slot.items():
        status_txt = "bestaetigt" if status == "confirmed" else "Warteliste"
        lines.append(f"- {slot_label} ({status_txt}): {', '.join(names)}")

    notify_admins("\n".join(lines), token, admin_ids)

    latest_created = max(r["created_at"] for r in new_signups)
    set_setting(conn, "digest_last_sent_at", latest_created)
    conn.commit()
    conn.close()
    logger.info("Digest gesendet, %s neue Anmeldung(en) bis %s", len(new_signups), latest_created)


def reminder_participants(db_path, token, admin_ids):
    """Sendet Reminder an angemeldete Teilnehmer (per Telegram) und eine
    Zusammenfassung an die Admins."""
    conn = get_conn(db_path)

    reminder_enabled = get_setting(conn, "reminder_enabled", "1") == "1"
    if not reminder_enabled:
        logger.info("Reminder ist deaktiviert (reminder_enabled=0) - uebersprungen.")
        conn.close()
        return

    # Telegram-ID je Signup: Name aus telegram_users.first_name (beim Signup
    # im Bot gespeichert) normalisiert mit name_normalized matchen.
    rows = conn.execute(
        """
        SELECT s.id, s.name, s.status, sl.label AS slot_label,
               tu.telegram_id
        FROM signups s
        JOIN slots sl ON sl.id = s.slot_id
        LEFT JOIN telegram_users tu
               ON tu.first_name IS NOT NULL
                      AND replace(lower(trim(tu.first_name)), ' ', '')
                          = replace(s.name_normalized, ' ', '')
        ORDER BY sl.id, s.status, s.name
        """
    ).fetchall()

    if not rows:
        logger.info("Keine Anmeldungen fuer den Reminder vorhanden.")
        conn.close()
        return

    # Zusammenfassung fuer Admins
    summary_lines = ["Erinnerung: Anmeldestand fuer den Matchtreff", ""]
    by_slot = {}
    for row in rows:
        by_slot.setdefault(row["slot_label"], []).append(row)

    for slot_label, entries in by_slot.items():
        confirmed = [e["name"] for e in entries if e["status"] == "confirmed"]
        waitlisted = [e["name"] for e in entries if e["status"] == "waitlist"]
        line = f"{slot_label}: {len(confirmed)} bestaetigt"
        if waitlisted:
            line += f", {len(waitlisted)} auf der Warteliste"
        summary_lines.append(f"- {line}")
        if confirmed:
            summary_lines.append("   " + ", ".join(confirmed))

    notify_admins("\n".join(summary_lines), token, admin_ids)

    # Individuelle Reminder an Teilnehmer mit Telegram-ID
    sent = 0
    for row in rows:
        if not row["telegram_id"]:
            continue
        if row["status"] == "confirmed":
            text = (
                f"Hallo {row['name']}! 🏓\n\n"
                f"Kurze Erinnerung: Du bist fuer den Slot '{row['slot_label']}' "
                "am Donnerstag angemeldet.\n"
                "Wir freuen uns auf dich!"
            )
        else:
            text = (
                f"Hallo {row['name']}! 🏓\n\n"
                f"Du stehst fuer den Slot '{row['slot_label']}' aktuell auf der "
                "Warteliste.\n"
                "Falls ein Platz frei wird, wirst du benachrichtigt."
            )
        result = telegram_api_call(
            "sendMessage",
            {"chat_id": row["telegram_id"], "text": text},
            token,
        )
        if result and result.get("ok"):
            sent += 1

    conn.close()
    logger.info("Reminder gesendet: %s/%s Teilnehmer, Status an Admins.", sent, len(rows))
