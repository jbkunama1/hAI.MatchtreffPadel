"""
Optionaler Telegram-Bot fuer Admin-Benachrichtigungen bei Gast-Anmeldungen.

Start (separat neben der Flask-App, gleiche instance/-DB per Volume mounten):
    python telegram_bot.py

Benoetigt TELEGRAM_BOT_TOKEN in der Umgebung. Die App selbst sendet die
Erst-Benachrichtigung bereits per HTTP (siehe app.py -> notify_admins_guest_signup).
Dieser Bot ist nur fuer die Inline-Buttons ("Bestaetigen" / "Entfernen") zustaendig.
"""
import os
import sqlite3
import sys

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

DB_PATH = os.environ.get("MATCHTREFF_DB_PATH", os.path.join("instance", "matchtreff.sqlite3"))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if ":" not in data:
        return
    action, signup_id_raw = data.split(":", 1)
    try:
        signup_id = int(signup_id_raw)
    except ValueError:
        return

    conn = get_conn()
    row = conn.execute("SELECT * FROM signups WHERE id = ?", (signup_id,)).fetchone()

    if row is None:
        await query.edit_message_text(text=query.message.text + "\n\n(Bereits bearbeitet oder nicht mehr vorhanden.)")
        conn.close()
        return

    if action == "reject_signup":
        was_confirmed = row["status"] == "confirmed"
        slot_id = row["slot_id"]
        conn.execute("DELETE FROM signups WHERE id = ?", (signup_id,))
        conn.commit()

        if was_confirmed:
            next_waiting = conn.execute(
                "SELECT * FROM signups WHERE slot_id = ? AND status = 'waitlist' ORDER BY created_at ASC LIMIT 1",
                (slot_id,),
            ).fetchone()
            if next_waiting:
                conn.execute("UPDATE signups SET status = 'confirmed' WHERE id = ?", (next_waiting["id"],))
                conn.commit()

        await query.edit_message_text(text=query.message.text + f"\n\nEntfernt von {update.effective_user.first_name}.")

    elif action == "ack_signup":
        await query.edit_message_text(text=query.message.text + f"\n\nBestaetigt von {update.effective_user.first_name}.")

    conn.close()


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[FEHLER] TELEGRAM_BOT_TOKEN nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    app = Application.builder().token(token).build()
    app.add_handler(CallbackQueryHandler(handle_callback))
    print("Telegram-Bot laeuft (Polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
