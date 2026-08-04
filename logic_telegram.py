"""Telegram-API-Helfer fuer die Web-App (synchroner Aufruf, kein python-telegram-bot)."""

import json
import logging
import os
import urllib.request

logger = logging.getLogger("matchtreff.web.telegram")


def telegram_api_call(method, payload, token=None):
    if token is None:
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
        logger.warning("Telegram-API-Aufruf fehlgeschlagen: %s", exc)
        return None


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
