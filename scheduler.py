"""
Eigener, dritter Container fuer die Automatik-Jobs (Reset + Digest).

Laeuft komplett unabhaengig von matchtreff_web und matchtreff_bot, nutzt aber
dieselbe SQLite-Datenbank ueber das gemeinsame Docker-Volume 'matchtreff_data'.

Start (im Container, siehe docker-compose.yml):
    python scheduler.py

Die Automatik-Einstellungen (aktiviert/deaktiviert, Wochentag, Uhrzeit,
Digest-Intervall) werden NICHT mehr fest ueber Umgebungsvariablen gesetzt,
sondern aus der Tabelle 'settings' gelesen -- Admins koennen sie also direkt
im Web-Dashboard unter "Automatik" aendern, ohne den Container neu zu starten.
Die Werte werden bei jedem Job-Lauf frisch aus der DB gelesen.
"""

import os
import sys
import json
import sqlite3
import urllib.request
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

DB_PATH = os.environ.get("MATCHTREFF_DB_PATH", os.path.join("instance", "matchtreff.sqlite3"))

# Fallback-Defaults, falls in der DB noch keine Werte existieren
# (z.B. beim allerersten Start, bevor app.py init_db() gelaufen ist).
DEFAULT_RESET_ENABLED = "1"
DEFAULT_RESET_WEEKDAY = "4"
DEFAULT_RESET_HOUR = "6"
DEFAULT_RESET_MINUTE = "0"
DEFAULT_NOTIFY_INTERVAL_MINUTES = "60"


def get_conn():
    conn = sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES, timeout=10)
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


def notify_admins(text: str):
    """Digests und Reset-Meldungen gehen NUR an Telegram-Admins
    (ADMIN_TELEGRAM_IDS), keine E-Mail-Vorbereitung."""
    admin_ids_raw = os.environ.get("ADMIN_TELEGRAM_IDS", "")
    admin_ids = [x.strip() for x in admin_ids_raw.split(",") if x.strip()]
    for admin_id in admin_ids:
        telegram_api_call("sendMessage", {"chat_id": admin_id, "text": text})


def weekly_reset():
    """Loescht ALLE Anmeldungen (signups) -> neue Woche, neuer Anfang.
    Cookies auf den Nutzer-Geraeten und Telegram-User-IDs bleiben davon
    unberuehrt (das ist so gewuenscht: die naechste Anmeldung in der neuen
    Woche funktioniert trotzdem normal, da die Cookie-Sperre nur verhindert,
    dass man sich fuer denselben, bereits laufenden Slot doppelt eintraegt --
    nach dem Reset gibt es ja wieder frische Slots)."""
    conn = get_conn()

    reset_enabled = get_setting(conn, "reset_enabled", DEFAULT_RESET_ENABLED) == "1"
    if not reset_enabled:
        print("[Scheduler] Automatischer Reset ist deaktiviert (reset_enabled=0) - uebersprungen.")
        conn.close()
        return

    conn.execute("DELETE FROM signups")

    now_str = datetime.now().isoformat(timespec="seconds")
    set_setting(conn, "last_auto_reset_at", now_str)
    conn.commit()
    conn.close()

    notify_admins(f"Automatischer Reset ausgefuehrt am {now_str} - alle Anmeldungen wurden geloescht.")
    print(f"[Scheduler] Reset ausgefuehrt am {now_str}")


def digest_new_signups():
    """Sammelt alle Anmeldungen seit dem letzten Digest und schickt EINE
    Zusammenfassung an die Telegram-Admins (nicht an Gaeste, die bekommen
    weiterhin sofort ihre eigene Nachricht aus app.py)."""
    conn = get_conn()

    last_value = get_setting(conn, "digest_last_sent_at")
    if last_value:
        try:
            last_ts = datetime.fromisoformat(last_value)
        except ValueError:
            last_ts = datetime.min
    else:
        last_ts = datetime.min

    new_signups = conn.execute(
        """
        SELECT s.id, s.name, s.status, s.created_at, sl.label AS slot_label
        FROM signups s
        JOIN slots sl ON sl.id = s.slot_id
        WHERE s.created_at > ?
        ORDER BY s.created_at ASC
        """,
        (last_ts,),
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

    notify_admins("\n".join(lines))

    latest_created = max(r["created_at"] for r in new_signups)
    latest_str = (
        latest_created.isoformat(timespec="seconds")
        if isinstance(latest_created, datetime)
        else str(latest_created)
    )
    set_setting(conn, "digest_last_sent_at", latest_str)
    conn.commit()
    conn.close()
    print(f"[Scheduler] Digest gesendet, {len(new_signups)} neue Anmeldung(en) bis {latest_str}")


def load_schedule_config():
    """Liest die aktuelle Job-Konfiguration aus der DB (mit Fallback auf
    Defaults). Wird beim Start des Schedulers einmal gelesen; Aenderungen,
    die der Admin waehrend des Betriebs im Dashboard macht, wirken erst nach
    einem Neustart des scheduler-Containers (z.B. per Portainer-Redeploy)."""
    conn = get_conn()
    cfg = {
        "reset_weekday": int(get_setting(conn, "reset_weekday", DEFAULT_RESET_WEEKDAY)),
        "reset_hour": int(get_setting(conn, "reset_hour", DEFAULT_RESET_HOUR)),
        "reset_minute": int(get_setting(conn, "reset_minute", DEFAULT_RESET_MINUTE)),
        "notify_interval_minutes": int(
            get_setting(conn, "notify_interval_minutes", DEFAULT_NOTIFY_INTERVAL_MINUTES)
        ),
    }
    conn.close()
    return cfg


def main():
    cfg = load_schedule_config()

    scheduler = BlockingScheduler(timezone="Europe/Berlin")

    scheduler.add_job(
        weekly_reset,
        "cron",
        day_of_week=cfg["reset_weekday"],
        hour=cfg["reset_hour"],
        minute=cfg["reset_minute"],
        id="weekly_reset",
        replace_existing=True,
    )

    scheduler.add_job(
        digest_new_signups,
        "interval",
        minutes=cfg["notify_interval_minutes"],
        id="digest",
        replace_existing=True,
    )

    print(
        "[Scheduler] gestartet. "
        f"Reset: Wochentag={cfg['reset_weekday']} {cfg['reset_hour']:02d}:{cfg['reset_minute']:02d} Uhr, "
        f"Digest alle {cfg['notify_interval_minutes']} Minuten."
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("[Scheduler] beendet.")


if __name__ == "__main__":
    main()
