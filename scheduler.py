"""
Eigener, dritter Container fuer die Automatik-Jobs (Reset + Digest + Reminder).

Laeuft komplett unabhaengig von matchtreff_web und matchtreff_bot, nutzt aber
dieselbe SQLite-Datenbank ueber das gemeinsame Docker-Volume 'matchtreff_data'.

Start (im Container, siehe docker-compose.yml):
    python scheduler.py

Die Automatik-Einstellungen werden aus der Tabelle 'settings' gelesen -- Admins
koennen sie im Web-Dashboard unter "Automatik" aendern. Die Job-Planung wird
laufend beobachtet und an Aenderungen angepasst, sodass kein Container-Neustart
noetig ist, wenn die Zeiten im Dashboard angepasst werden.
"""

import os
import time

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

import scheduler_new as jobs

DB_PATH = os.environ.get(
    "MATCHTREFF_DB_PATH", os.path.join("instance", "matchtreff.sqlite3")
)
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_IDS = [
    x.strip()
    for x in os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",")
    if x.strip()
]

INTERVAL_CONFIG_KEY = "notify_interval_minutes"


def read_config():
    """Liest die aktuellen Einstellungen frisch aus der DB."""
    import sqlite3

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    result = {
        "reset_enabled": True,
        "reset_weekday": 4,
        "reset_hour": 6,
        "reset_minute": 0,
        "notify_interval_minutes": 60,
        "reminder_enabled": True,
        "reminder_weekday": 3,
        "reminder_hour": 12,
        "reminder_minute": 0,
    }
    try:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        for row in rows:
            key = row["key"]
            if key in result:
                if key in ("reset_enabled", "reminder_enabled"):
                    result[key] = row["value"].strip() == "1"
                else:
                    try:
                        result[key] = int(row["value"])
                    except (TypeError, ValueError):
                        pass
    except sqlite3.Error as exc:
        print(f"[Scheduler] Fehler beim Lesen der DB: {exc}", flush=True)
    finally:
        conn.close()
    return result


def _wrap(job_func):
    def wrapper():
        try:
            job_func(DB_PATH, TOKEN, ADMIN_IDS)
        except Exception as exc:  # pragma: no cover - defensive
            print(f"[Scheduler] Fehler im Job: {exc}", flush=True)

    return wrapper


def reschedule(scheduler, cfg, wl_mode_text):
    """(Re-)Plant die Jobs anhand der aktuellen Config."""
    # Wochen-Reset
    if scheduler.get_job("weekly_reset"):
        scheduler.remove_job("weekly_reset")
    if cfg["reset_enabled"]:
        scheduler.add_job(
            _wrap(jobs.weekly_reset),
            CronTrigger(
                day_of_week=str(cfg["reset_weekday"]),
                hour=cfg["reset_hour"],
                minute=cfg["reset_minute"],
                timezone="Europe/Berlin",
            ),
            id="weekly_reset",
            replace_existing=True,
        )

    # Digest (interval) - Intervall kann sich aendern
    if scheduler.get_job("digest"):
        interval = scheduler.get_job("digest").trigger.interval
        current_min = int(getattr(interval, "total_seconds", lambda: 0)() / 60)
    else:
        current_min = None

    if current_min != cfg["notify_interval_minutes"]:
        if scheduler.get_job("digest"):
            scheduler.remove_job("digest")
        scheduler.add_job(
            _wrap(jobs.digest_new_signups),
            "interval",
            minutes=cfg["notify_interval_minutes"],
            id="digest",
            replace_existing=True,
        )

    # Reminder (cron)
    if scheduler.get_job("reminder_participants"):
        scheduler.remove_job("reminder_participants")
    if cfg["reminder_enabled"]:
        scheduler.add_job(
            _wrap(jobs.reminder_participants),
            CronTrigger(
                day_of_week=str(cfg["reminder_weekday"]),
                hour=cfg["reminder_hour"],
                minute=cfg["reminder_minute"],
                timezone="Europe/Berlin",
            ),
            id="reminder_participants",
            replace_existing=True,
        )

    print(
        "[Scheduler] Jobs geplant. "
        f"Reset={'AN' if cfg['reset_enabled'] else 'AUS'} "
        f"(Wochentag {cfg['reset_weekday']} {cfg['reset_hour']:02d}:{cfg['reset_minute']:02d}), "
        f"Digest alle {cfg['notify_interval_minutes']} Min., "
        f"Reminder={'AN' if cfg['reminder_enabled'] else 'AUS'} "
        f"(Wochentag {cfg['reminder_weekday']} {cfg['reminder_hour']:02d}:{cfg['reminder_minute']:02d}).",
        flush=True,
    )


def monitor_config(scheduler):
    """Beobachtet die DB und plant Jobs neu, wenn sich Einstellungen aendern."""
    last_signature = None
    while True:
        cfg = read_config()
        signature = tuple(
            (k, str(v)) for k, v in cfg.items() if k.startswith(("reset", "notify", "reminder"))
        )
        sig = str(signature)
        if sig != last_signature:
            reschedule(scheduler, cfg, "")
            last_signature = sig
        time.sleep(30)


def main():
    if not TOKEN:
        print(
            "[Scheduler] WARNUNG: TELEGRAM_BOT_TOKEN nicht gesetzt - "
            "Benachrichtigungen deaktiviert.",
            flush=True,
        )

    scheduler = BlockingScheduler(timezone="Europe/Berlin")

    # Jobs einmal initial aus DB konfigurieren
    cfg = read_config()
    reschedule(scheduler, cfg, "")

    # Konfig-aenderungen im Hintergrund beobachten
    # Da BlockingScheduler den Main-Thread haelt, laeuft der Monitor hier
    # zusaetzlich als eigener Prozess/Thread - wir nutzen den Hintergrund-Thread.
    import threading

    t = threading.Thread(target=monitor_config, args=(scheduler,), daemon=True)
    t.start()

    print("[Scheduler] gestartet.", flush=True)
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("[Scheduler] beendet.")


if __name__ == "__main__":
    main()

