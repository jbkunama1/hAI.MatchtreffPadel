import json
import logging
import os
import sqlite3
import urllib.request
from typing import Optional

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

DB_PATH = os.getenv("MATCHTREFF_DB_PATH", "instance/matchtreff.sqlite3")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("matchtreff.telegram_bot")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_slot_label(slot_id: int) -> Optional[str]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT label FROM slots WHERE id = ?",
            (slot_id,),
        ).fetchone()
        return row["label"] if row else None


def promote_waiting_signup(conn: sqlite3.Connection, slot_id: int):
    waiting_signup = conn.execute(
        """
        SELECT id, name
        FROM signups
        WHERE slot_id = ? AND status = 'waiting'
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (slot_id,),
    ).fetchone()

    if not waiting_signup:
        return None

    conn.execute(
        """
        UPDATE signups
        SET status = 'confirmed'
        WHERE id = ?
        """,
        (waiting_signup["id"],),
    )

    return waiting_signup


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "Hallo! Ich bin der hAIMatchtreff Bot.\n\n"
            "Ich verarbeite Admin-Aktionen fuer Gast-Anmeldungen."
        )


async def callback_guest_signup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    await query.answer()

    data = query.data or ""
    logger.info("Callback empfangen: %s", data)

    if ":" not in data:
        await query.edit_message_text("Ungueltige Aktion.")
        logger.warning("Ungueltige Callback-Daten: %s", data)
        return

    action, signup_id_raw = data.split(":", 1)

    try:
        signup_id = int(signup_id_raw)
    except ValueError:
        await query.edit_message_text("Ungueltige Signup-ID.")
        logger.warning("Ungueltige Signup-ID in Callback: %s", signup_id_raw)
        return

    with get_conn() as conn:
        signup = conn.execute(
            """
            SELECT id, name, slot_id, status, is_member
            FROM signups
            WHERE id = ?
            """,
            (signup_id,),
        ).fetchone()

        if not signup:
            await query.edit_message_text("Eintrag nicht mehr vorhanden.")
            logger.info("Signup nicht gefunden: id=%s", signup_id)
            return

        slot_label = get_slot_label(signup["slot_id"]) or "Unbekannter Slot"

        if action == "ack_signup":
            await query.edit_message_text(
                f"Zur Kenntnis genommen: {signup['name']} ({slot_label}) bleibt eingetragen."
            )
            logger.info(
                "Gast-Anmeldung bestaetigt/acknowledged: signup_id=%s name=%s slot_id=%s",
                signup["id"],
                signup["name"],
                signup["slot_id"],
            )
            return

        if action == "reject_signup":
            removed_name = signup["name"]
            removed_slot_id = signup["slot_id"]
            removed_status = signup["status"]

            conn.execute("DELETE FROM signups WHERE id = ?", (signup_id,))

            promoted_signup = None
            if removed_status == "confirmed":
                promoted_signup = promote_waiting_signup(conn, removed_slot_id)

            conn.commit()

            message = f"Gast-Anmeldung entfernt: {removed_name} ({slot_label})"

            if promoted_signup:
                message += (
                    f"\nNachgerueckt: {promoted_signup['name']} "
                    f"({slot_label}) ist jetzt bestaetigt."
                )

            await query.edit_message_text(message)

            logger.info(
                "Gast-Anmeldung entfernt: signup_id=%s name=%s slot_id=%s status=%s",
                signup["id"],
                removed_name,
                removed_slot_id,
                removed_status,
            )

            if promoted_signup:
                logger.info(
                    "Warteliste nachgerueckt: signup_id=%s name=%s slot_id=%s",
                    promoted_signup["id"],
                    promoted_signup["name"],
                    removed_slot_id,
                )
            return

    await query.edit_message_text("Unbekannte Aktion.")
    logger.warning("Unbekannte Callback-Aktion: %s", action)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled bot error", exc_info=context.error)


def clear_webhook(token: str) -> None:
    url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=false"
    try:
        with urllib.request.urlopen(url, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            logger.info("deleteWebhook response: %s", payload)
    except Exception:
        logger.exception("deleteWebhook fehlgeschlagen")


async def post_init(application: Application) -> None:
    me = await application.bot.get_me()
    logger.info("Bot verbunden: @%s (id=%s)", me.username, me.id)


def main():
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN nicht gesetzt.")
        raise SystemExit(1)

    logger.info("Starte Telegram-Bot. DB_PATH=%s", DB_PATH)

    clear_webhook(TOKEN)

    application = Application.builder().token(TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CallbackQueryHandler(callback_guest_signup))
    application.add_error_handler(error_handler)

    logger.info("Telegram-Bot laeuft (Polling)...")
    application.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
