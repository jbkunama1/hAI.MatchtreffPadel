"""
Telegram-Bot fuer Matchtreff Padel - vollstaendiger Bot mit Event-System.

Start:
    python telegram_bot.py

Benoetigt:
    TELEGRAM_BOT_TOKEN
    ADMIN_TELEGRAM_IDS (kommagetrennt)
    MATCHTREFF_DB_PATH (optional, default: instance/matchtreff.sqlite3)
"""
import os
import sqlite3
import sys
from datetime import datetime, timedelta

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

DB_PATH = os.environ.get("MATCHTREFF_DB_PATH", os.path.join("instance", "matchtreff.sqlite3"))
ORGA_TEAM = ["Daniel", "Cosme", "Sascha", "Patrick"]


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def get_admin_ids():
    raw = os.environ.get("ADMIN_TELEGRAM_IDS", "")
    return [x.strip() for x in raw.split(",") if x.strip()]


def is_admin(user_id):
    return str(user_id) in get_admin_ids()


def next_thursday():
    today = datetime.today().date()
    days_ahead = (3 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def get_current_event_id(conn):
    active = conn.execute("SELECT value FROM settings WHERE key = 'active_event_id'").fetchone()
    if active:
        return int(active["value"])
    event_date = next_thursday()
    row = conn.execute("SELECT id FROM events WHERE event_date = ?", (event_date,)).fetchone()
    if row:
        return row["id"]
    # Create default event
    conn.execute("INSERT INTO events (title, event_date, is_default) VALUES (?, ?, 1)",
                 (f"Matchtreff {event_date.strftime('%d.%m.%Y')}", event_date))
    event_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for key in ['slot_a', 'slot_b']:
        label = 'Temprano' if key == 'slot_a' else 'Tarde'
        conn.execute("INSERT INTO slots (event_id, slot_key, label, max_players) VALUES (?, ?, ?, ?)",
                     (event_id, key, label, 14))
    conn.commit()
    return event_id


def get_slots(conn, event_id):
    return conn.execute("SELECT * FROM slots WHERE event_id = ? ORDER BY id", (event_id,)).fetchall()


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "\ud83c\udfd3 *Matchtreff Padel Bot*\n\n"
        "Befehle:\n"
        "/slots - Aktuelle Belegung anzeigen\n"
        "/eintragen <Name> <a|b|beide> - Fuer Slot eintragen\n"
        "/status <Name> - Status abfragen\n\n"
        "Admin (nur Orga):\n"
        "/admin_liste - Alle Anmeldungen\n"
        "/admin_max <a|b> <zahl> - Max. Plaetze setzen\n"
        "/admin_loeschen <id> - Anmeldung loeschen\n"
        "/admin_reset - Alle Anmeldungen zuruecksetzen\n"
        "/admin_eintragen <Name> <a|b> - Spieler eintragen",
        parse_mode="Markdown"
    )


async def cmd_slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = get_conn()
    event_id = get_current_event_id(conn)
    event = conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    slots = get_slots(conn, event_id)

    lines = [f"\ud83d\udcc5 *{event['title']}*\n"]
    for slot in slots:
        confirmed = conn.execute(
            "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'confirmed'",
            (slot["id"],)
        ).fetchone()["c"]
        waitlist = conn.execute(
            "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'waitlist'",
            (slot["id"],)
        ).fetchone()["c"]
        full = confirmed >= slot["max_players"]
        lines.append(f"\n*{slot['label']}* ({slot['slot_key']})")
        lines.append(f"{confirmed}/{slot['max_players']} belegt")
        if full:
            lines.append("\u26a0\ufe0f SLOT VOLL")
        if waitlist > 0:
            lines.append(f"Warteliste: {waitlist}")

    conn.close()
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_eintragen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Syntax: /eintragen <Name> <a|b|beide>")
        return

    name = args[0]
    slot_choice = args[1].lower()

    conn = get_conn()
    event_id = get_current_event_id(conn)
    name_normalized = name.lower().strip()
    user_id = update.effective_user.id

    selected = []
    if slot_choice in ['a', 'temprano']:
        selected = ['slot_a']
    elif slot_choice in ['b', 'tarde']:
        selected = ['slot_b']
    elif slot_choice == 'beide':
        selected = ['slot_a', 'slot_b']
    else:
        await update.message.reply_text("Ungueltige Slot-Auswahl. Nutze a, b oder beide.")
        conn.close()
        return

    added = []
    waitlisted = []
    blocked = []

    for slot_key in selected:
        slot = conn.execute(
            "SELECT * FROM slots WHERE event_id = ? AND slot_key = ?",
            (event_id, slot_key)
        ).fetchone()
        if not slot:
            continue

        # Check duplicate
        existing = conn.execute(
            "SELECT * FROM signups WHERE slot_id = ? AND name_normalized = ?",
            (slot["id"], name_normalized)
        ).fetchone()
        if existing:
            blocked.append(f"{slot['label']}: bereits eingetragen")
            continue

        confirmed = conn.execute(
            "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'confirmed'",
            (slot["id"],)
        ).fetchone()["c"]

        if confirmed < slot["max_players"]:
            status = 'confirmed'
            added.append(slot["label"])
        else:
            waitlist_count = conn.execute(
                "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'waitlist'",
                (slot["id"],)
            ).fetchone()["c"]
            if waitlist_count < 4:
                status = 'waitlist'
                waitlisted.append(slot["label"])
            else:
                blocked.append(f"{slot['label']}: Warteliste voll")
                continue

        conn.execute(
            "INSERT INTO signups (slot_id, name, name_normalized, status, is_member) VALUES (?, ?, ?, ?, ?)",
            (slot["id"], name, name_normalized, status, 1)
        )

    conn.commit()
    conn.close()

    messages = []
    if added:
        messages.append(f"\u2705 Eingetragen: {', '.join(added)}")
    if waitlisted:
        messages.append(f"\ud83d\udcdc Warteliste: {', '.join(waitlisted)}")
    if blocked:
        messages.append(f"\u26a0\ufe0f {', '.join(blocked)}")

    await update.message.reply_text("\n".join(messages) if messages else "Nichts geaendert.")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Syntax: /status <Name>")
        return

    name = context.args[0].lower().strip()
    conn = get_conn()
    event_id = get_current_event_id(conn)

    signups = conn.execute(
        """SELECT s.*, sl.label, sl.slot_key FROM signups s
           JOIN slots sl ON s.slot_id = sl.id
           WHERE sl.event_id = ? AND s.name_normalized = ?""",
        (event_id, name)
    ).fetchall()

    conn.close()

    if not signups:
        await update.message.reply_text("Keine Anmeldung unter diesem Namen gefunden.")
        return

    lines = [f"\ud83d\udccc *Status fuer {signups[0]['name']}*"]
    for s in signups:
        status = "\u2705 Bestaetigt" if s["status"] == "confirmed" else "\ud83d\udcdc Warteliste"
        lines.append(f"\n{s['label']}: {status}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# Admin commands
async def cmd_admin_liste(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Keine Admin-Rechte.")
        return

    conn = get_conn()
    event_id = get_current_event_id(conn)
    slots = get_slots(conn, event_id)

    lines = ["\ud83d\udccb *Admin: Alle Anmeldungen*"]
    for slot in slots:
        lines.append(f"\n\n*{slot['label']}*")
        confirmed = conn.execute(
            "SELECT * FROM signups WHERE slot_id = ? AND status = 'confirmed' ORDER BY created_at",
            (slot["id"],)
        ).fetchall()
        for i, s in enumerate(confirmed, 1):
            member = "\u2705" if s["is_member"] else "\ud83d\udc64"
            lines.append(f"{i}. {member} {s['name']} (ID: {s['id']})")

        waitlist = conn.execute(
            "SELECT * FROM signups WHERE slot_id = ? AND status = 'waitlist' ORDER BY created_at",
            (slot["id"],)
        ).fetchall()
        if waitlist:
            lines.append("\n*Warteliste:*")
            for i, s in enumerate(waitlist, 1):
                lines.append(f"{i}. {s['name']} (ID: {s['id']})")

    conn.close()
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_admin_max(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Keine Admin-Rechte.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Syntax: /admin_max <a|b> <zahl>")
        return

    slot_key = 'slot_a' if context.args[0].lower() in ['a', 'temprano'] else 'slot_b'
    try:
        max_p = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Zahl ungueltig.")
        return

    conn = get_conn()
    event_id = get_current_event_id(conn)
    conn.execute(
        "UPDATE slots SET max_players = ? WHERE event_id = ? AND slot_key = ?",
        (max_p, event_id, slot_key)
    )
    conn.commit()

    # Auto-promote from waitlist
    slot = conn.execute(
        "SELECT * FROM slots WHERE event_id = ? AND slot_key = ?",
        (event_id, slot_key)
    ).fetchone()

    confirmed = conn.execute(
        "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'confirmed'",
        (slot["id"],)
    ).fetchone()["c"]

    new_spots = max_p - confirmed
    if new_spots > 0:
        waitlist = conn.execute(
            "SELECT * FROM signups WHERE slot_id = ? AND status = 'waitlist' ORDER BY created_at ASC LIMIT ?",
            (slot["id"], new_spots)
        ).fetchall()
        for w in waitlist:
            conn.execute("UPDATE signups SET status = 'confirmed' WHERE id = ?", (w["id"],))
            # Notify user
            if w["telegram_user_id"]:
                await notify_waitlist_promotion(context, w["telegram_user_id"], w["name"], slot["label"])

    conn.commit()
    conn.close()
    await update.message.reply_text(f"Max. Plaetze fuer {slot['label']} auf {max_p} gesetzt.")





async def cmd_admin_loeschen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Keine Admin-Rechte.")
        return

    if not context.args:
        await update.message.reply_text("Syntax: /admin_loeschen <id>")
        return

    try:
        signup_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID muss eine Zahl sein.")
        return

    conn = get_conn()
    row = conn.execute("SELECT * FROM signups WHERE id = ?", (signup_id,)).fetchone()
    if not row:
        await update.message.reply_text("Anmeldung nicht gefunden.")
        conn.close()
        return

    was_confirmed = row["status"] == "confirmed"
    slot_id = row["slot_id"]
    conn.execute("DELETE FROM signups WHERE id = ?", (signup_id,))
    conn.commit()

    if was_confirmed:
        next_waiting = conn.execute(
            "SELECT * FROM signups WHERE slot_id = ? AND status = 'waitlist' ORDER BY created_at ASC LIMIT 1",
            (slot_id,)
        ).fetchone()
        if next_waiting:
            conn.execute("UPDATE signups SET status = 'confirmed' WHERE id = ?", (next_waiting["id"],))
            conn.commit()
            # Notify user
            slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
            if next_waiting["telegram_user_id"]:
                await notify_waitlist_promotion(context, next_waiting["telegram_user_id"], next_waiting["name"], slot["label"])

    conn.close()
    await update.message.reply_text(f"Anmeldung {signup_id} geloescht.")


async def cmd_admin_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Keine Admin-Rechte.")
        return

    conn = get_conn()
    event_id = get_current_event_id(conn)
    conn.execute("DELETE FROM signups WHERE slot_id IN (SELECT id FROM slots WHERE event_id = ?)", (event_id,))
    conn.commit()
    conn.close()
    await update.message.reply_text("Alle Anmeldungen fuer das aktuelle Event zurueckgesetzt.")


async def cmd_admin_eintragen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("Keine Admin-Rechte.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Syntax: /admin_eintragen <Name> <a|b>")
        return

    name = context.args[0]
    slot_choice = context.args[1].lower()
    slot_key = 'slot_a' if slot_choice in ['a', 'temprano'] else 'slot_b'

    conn = get_conn()
    event_id = get_current_event_id(conn)
    slot = conn.execute(
        "SELECT * FROM slots WHERE event_id = ? AND slot_key = ?",
        (event_id, slot_key)
    ).fetchone()

    if not slot:
        await update.message.reply_text("Slot nicht gefunden.")
        conn.close()
        return

    name_normalized = name.lower().strip()

    # Check if already exists
    existing = conn.execute(
        "SELECT * FROM signups WHERE slot_id = ? AND name_normalized = ?",
        (slot["id"], name_normalized)
    ).fetchone()
    if existing:
        await update.message.reply_text(f"{name} ist bereits in {slot['label']} eingetragen.")
        conn.close()
        return

    confirmed = conn.execute(
        "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'confirmed'",
        (slot["id"],)
    ).fetchone()["c"]

    status = 'confirmed' if confirmed < slot["max_players"] else 'waitlist'
    conn.execute(
        "INSERT INTO signups (slot_id, name, name_normalized, status, is_member) VALUES (?, ?, ?, ?, ?)",
        (slot["id"], name, name_normalized, status, 1)
    )
    conn.commit()
    conn.close()

    status_text = "bestaetigt" if status == "confirmed" else "Warteliste"
    await update.message.reply_text(f"\u2705 {name} in {slot['label']} eingetragen ({status_text}).")


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
                slot = conn.execute("SELECT * FROM slots WHERE id = ?", (slot_id,)).fetchone()
                if next_waiting["telegram_user_id"]:
                    await notify_waitlist_promotion(context, next_waiting["telegram_user_id"], next_waiting["name"], slot["label"])

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

    # User commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("slots", cmd_slots))
    app.add_handler(CommandHandler("eintragen", cmd_eintragen))
    app.add_handler(CommandHandler("status", cmd_status))

    # Admin commands
    app.add_handler(CommandHandler("admin_liste", cmd_admin_liste))
    app.add_handler(CommandHandler("admin_max", cmd_admin_max))
    app.add_handler(CommandHandler("admin_loeschen", cmd_admin_loeschen))
    app.add_handler(CommandHandler("admin_reset", cmd_admin_reset))
    app.add_handler(CommandHandler("admin_eintragen", cmd_admin_eintragen))

    # Callback handler
    app.add_handler(CallbackQueryHandler(handle_callback))

    print("Telegram-Bot laeuft (Polling)...")
    app.run_polling()


if __name__ == "__main__":
    main()
