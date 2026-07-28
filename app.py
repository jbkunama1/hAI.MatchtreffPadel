import os
import sys
import sqlite3
import json
import urllib.request
from datetime import datetime, timedelta
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, g, flash, make_response, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash

_REQUIRED_ENV = ["SECRET_KEY", "ADMIN_PASSWORD_ADMIN", "ADMIN_PASSWORD_DANIEL"]
_missing = [v for v in _REQUIRED_ENV if not os.environ.get(v, "").strip()]
if _missing:
    missing_list = ", ".join(_missing)
    print(
        f"[FEHLER] Fehlende Pflicht-Umgebungsvariablen: {missing_list}\n"
        "Bitte in der .env auf dem Host setzen. Anwendung wird beendet.",
        file=sys.stderr,
    )
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
SLOT_LABEL = {s["key"]: s["label"] for s in SLOT_DEFINITIONS}
WAITLIST_LIMIT = 4
DEFAULT_MAX_PLAYERS = 14
DEFAULT_INTRO_TEXT = (
    "Anmeldung fuer Donnerstag, {next_thursday}. Trag einfach deinen Namen ein "
    "und waehle einen oder beide Slots. Pro Geraet kann man sich pro Slot nur einmal eintragen."
)