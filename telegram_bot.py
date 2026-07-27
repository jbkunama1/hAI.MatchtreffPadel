import os
import sys
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

START_TEXT = (
    "Matchtreff Padel Bot\n\n"
    "Befehle:\n"
    "/slots - Aktuelle Belegung anzeigen\n"
    "/eintragen - Fuer Slot eintragen\n"
    "/status - Status abfragen\n\n"
    "Admin (nur Orga):\n"
    "/admin_liste - Alle Anmeldungen\n"
    "/admin_max - Max. Plaetze setzen\n"
    "/admin_loeschen - Anmeldung loeschen\n"
    "/admin_reset - Alle Anmeldungen zuruecksetzen\n"
    "/admin_eintragen - Spieler eintragen"
)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(START_TEXT)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f"Telegram-Fehler: {context.error}", file=sys.stderr)

def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[FEHLER] TELEGRAM_BOT_TOKEN nicht gesetzt.", file=sys.stderr)
        sys.exit(1)
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_error_handler(error_handler)
    print("Telegram-Bot laeuft (Polling)...")
    app.run_polling()

if __name__ == "__main__":
    main()
