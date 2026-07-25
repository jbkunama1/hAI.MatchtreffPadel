import os
import sys
import sqlite3
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

DB_PATH = os.path.join(os.getcwd(), "instance", "matchtreff.sqlite3")

SLOT_DEFINITIONS = [
    {"key": "slot_a", "label": "Temprano: 18:00 - 20:00 Uhr"},
    {"key": "slot_b", "label": "Tarde: 20:00 - 22:00 Uhr"},
]
SLOT_LABEL = {s["key"]: s["label"] for s in SLOT_DEFINITIONS}
SLOT_ALIASES = {
    "a": "slot_a", "18": "slot_a", "slot_a": "slot_a",
    "b": "slot_b", "20": "slot_b", "slot_b": "slot_b",
    "beide": "beide", "both": "beide",
}
WAITLIST_LIMIT = 4
ORGA_TEAM = ["Daniel", "Cosme", "Sascha", "Patrick"]


def normalize_name(name: str) -> str:
    return " ".join(name.strip().split()).lower()


ORGA_TEAM_NORMALIZED = {normalize_name(n) for n in ORGA_TEAM}


def format_player_name(name: str) -> str:
    if normalize_name(name) in ORGA_TEAM_NORMALIZED:
        return f"*{name} \u2605*"
    return name


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_key TEXT UNIQUE NOT NULL,
            label TEXT NOT NULL,
            max_players INTEGER NOT NULL DEFAULT 8
        );

        CREATE TABLE IF NOT EXISTS signups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slot_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            name_normalized TEXT NOT NULL,
            telegram_user_id INTEGER,
            status TEXT NOT NULL DEFAULT \'confirmed\',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(slot_id) REFERENCES slots(id),
            UNIQUE(slot_id, name_normalized)
        );
        """
    )
    cols = [r[1] for r in conn.execute("PRAGMA table_info(signups)").fetchall()]
    if "telegram_user_id" not in cols:
        conn.execute("ALTER TABLE signups ADD COLUMN telegram_user_id INTEGER")
    if "status" not in cols:
        conn.execute("ALTER TABLE signups ADD COLUMN status TEXT NOT NULL DEFAULT \'confirmed\'")

    for s in SLOT_DEFINITIONS:
        existing = conn.execute(
            "SELECT id FROM slots WHERE slot_key = ?", (s["key"],)
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO slots (slot_key, label, max_players) VALUES (?, ?, ?)",
                (s["key"], s["label"], 8),
            )
    conn.commit()
    conn.close()


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def is_admin(update: Update) -> bool:
    admin_ids_raw = os.environ.get("ADMIN_TELEGRAM_IDS", "")
    admin_ids = {int(x.strip()) for x in admin_ids_raw.split(",") if x.strip().isdigit()}
    return update.effective_user.id in admin_ids


def next_thursday_str() -> str:
    today = datetime.today().date()
    days_ahead = (3 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return (today + timedelta(days=days_ahead)).strftime("%d.%m.%Y")


def get_slot_row(conn, slot_key):
    return conn.execute("SELECT * FROM slots WHERE slot_key = ?", (slot_key,)).fetchone()


def count_status(conn, slot_id, status):
    return conn.execute(
        "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = ?",
        (slot_id, status),
    ).fetchone()["c"]


# ---------------------------- Befehle ----------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    admin_hint = ""
    if is_admin(update):
        admin_hint = (
            "\n\n[Admin] Admin-Befehle:\n"
            "/admin_liste - alle Anmeldungen anzeigen\n"
            "/admin_max <a|b> <zahl> - max. Plaetze setzen\n"
            "/admin_loeschen <id> - Anmeldung loeschen\n"
            "/admin_reset - alle Anmeldungen loeschen"
        )
    text = (
        "Padel Matchtreff Bot\n"
        "------------------------------\n\n"
        "Naechster Donnerstag: " + next_thursday_str() + "\n\n"
        "Befehle:\n"
        "/slots - aktuelle Belegung anzeigen\n"
        "/eintragen <Name> <a|b|beide> - fuer Slot(s) anmelden (pro Slot nur 1x pro Telegram-Account)\n"
        "/status - eigene Anmeldung anzeigen (nach Name)\n"
        "/help - diese Hilfe" + admin_hint
    )
    await update.message.reply_text(text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def slots_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn = get_conn()
    lines = ["Belegung Donnerstag " + next_thursday_str() + ":\n"]
    for s in SLOT_DEFINITIONS:
        row = get_slot_row(conn, s["key"])
        confirmed = count_status(conn, row["id"], "confirmed")
        waitlist = count_status(conn, row["id"], "waitlist")
        status = "VOLL" if confirmed >= row["max_players"] else "frei"
        line = f"{row['label']}: {confirmed}/{row['max_players']} ({status})"
        if waitlist:
            line += f", Warteliste {waitlist}/{WAITLIST_LIMIT}"
        lines.append(line)
    conn.close()
    await update.message.reply_text("\n".join(lines))


async def eintragen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if len(context.args) < 2:
        await update.message.reply_text(
            "Verwendung: /eintragen <Name> <a|b|beide>\n"
            "Beispiel: /eintragen MaxMustermann a"
        )
        return

    slot_arg = context.args[-1].lower()
    name = " ".join(context.args[:-1]).strip()

    if slot_arg not in SLOT_ALIASES:
        await update.message.reply_text("Slot muss a, b oder beide sein.")
        return

    if not name:
        await update.message.reply_text("Bitte einen gueltigen Namen angeben.")
        return

    user_id = update.effective_user.id
    name_norm = normalize_name(name)
    target_keys = ["slot_a", "slot_b"] if SLOT_ALIASES[slot_arg] == "beide" else [SLOT_ALIASES[slot_arg]]

    conn = get_conn()
    added, waitlisted, blocked = [], [], []

    for key in target_keys:
        row = get_slot_row(conn, key)

        already = conn.execute(
            "SELECT id FROM signups WHERE slot_id = ? AND telegram_user_id = ?",
            (row["id"], user_id),
        ).fetchone()
        if already:
            blocked.append(row["label"] + " (bereits eingetragen)")
            continue

        confirmed = count_status(conn, row["id"], "confirmed")
        waitlist = count_status(conn, row["id"], "waitlist")
        status = "confirmed" if confirmed < row["max_players"] else "waitlist"

        if status == "waitlist" and waitlist >= WAITLIST_LIMIT:
            blocked.append(row["label"] + " (Warteliste voll)")
            continue

        try:
            conn.execute(
                "INSERT INTO signups (slot_id, name, name_normalized, telegram_user_id, status) "
                "VALUES (?, ?, ?, ?, ?)",
                (row["id"], name, name_norm, user_id, status),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            blocked.append(row["label"] + " (Name bereits vorhanden)")
            continue

        if status == "confirmed":
            added.append(row["label"])
        else:
            waitlisted.append(row["label"])

    conn.close()

    reply = []
    if added:
        reply.append("Eingetragen fuer: " + ", ".join(added))
    if waitlisted:
        reply.append("Auf Warteliste fuer: " + ", ".join(waitlisted))
    if blocked:
        reply.append("Nicht moeglich: " + ", ".join(blocked))
    await update.message.reply_text("\n".join(reply) if reply else "Keine Aenderung.")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Verwendung: /status <Name>")
        return
    name = " ".join(context.args).strip()

    conn = get_conn()
    rows = conn.execute(
        """
        SELECT s.label AS slot_label, su.status AS status
        FROM signups su
        JOIN slots s ON s.id = su.slot_id
        WHERE su.name = ?
        ORDER BY s.id
        """,
        (name,),
    ).fetchall()
    conn.close()

    if not rows:
        await update.message.reply_text(f"Keine Anmeldung fuer '{name}' gefunden.")
        return

    lines = [f"Anmeldungen fuer {format_player_name(name)}:"]
    for r in rows:
        tag = "Warteliste" if r["status"] == "waitlist" else "Bestaetigt"
        lines.append(f"- {r['slot_label']} [{tag}]")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


# ---------------------------- Admin ----------------------------

async def admin_liste(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.message.reply_text("Keine Admin-Rechte.")
        return

    conn = get_conn()
    lines = ["Alle Anmeldungen Donnerstag " + next_thursday_str() + ":\n"]
    for s in SLOT_DEFINITIONS:
        row = get_slot_row(conn, s["key"])
        confirmed = conn.execute(
            "SELECT id, name FROM signups WHERE slot_id = ? AND status = \'confirmed\' ORDER BY created_at",
            (row["id"],),
        ).fetchall()
        waitlist = conn.execute(
            "SELECT id, name FROM signups WHERE slot_id = ? AND status = \'waitlist\' ORDER BY created_at",
            (row["id"],),
        ).fetchall()
        lines.append(f"{row['label']} ({len(confirmed)}/{row['max_players']}):")
        for su in confirmed:
            lines.append(f"  #{su['id']} {format_player_name(su['name'])}")
        if not confirmed:
            lines.append("  (noch niemand)")
        lines.append(f"  Warteliste ({len(waitlist)}/{WAITLIST_LIMIT}):")
        for su in waitlist:
            lines.append(f"  #{su['id']} {format_player_name(su['name'])} [Warteliste]")
        lines.append("")
    conn.close()
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def admin_max(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.message.reply_text("Keine Admin-Rechte.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Verwendung: /admin_max <a|b> <zahl>")
        return

    slot_arg = context.args[0].lower()
    if slot_arg not in ("a", "b"):
        await update.message.reply_text("Slot muss a oder b sein.")
        return

    try:
        max_players = int(context.args[1])
    except ValueError:
        await update.message.reply_text("Zahl ungueltig.")
        return

    if max_players <= 0:
        await update.message.reply_text("Zahl muss groesser als 0 sein.")
        return

    slot_key = "slot_a" if slot_arg == "a" else "slot_b"
    conn = get_conn()
    conn.execute("UPDATE slots SET max_players = ? WHERE slot_key = ?", (max_players, slot_key))
    conn.commit()

    row = get_slot_row(conn, slot_key)
    confirmed = conn.execute(
        "SELECT * FROM signups WHERE slot_id = ? AND status = \'confirmed\'", (row["id"],)
    ).fetchall()
    waitlist = conn.execute(
        "SELECT * FROM signups WHERE slot_id = ? AND status = \'waitlist\' ORDER BY created_at ASC",
        (row["id"],),
    ).fetchall()
    free = row["max_players"] - len(confirmed)
    moved = 0
    for su in waitlist:
        if free <= 0:
            break
        conn.execute("UPDATE signups SET status = \'confirmed\' WHERE id = ?", (su["id"],))
        free -= 1
        moved += 1
    conn.commit()
    conn.close()

    msg = f"Max. Plaetze fuer {SLOT_LABEL[slot_key]} auf {max_players} gesetzt."
    if moved:
        msg += f" {moved} Spieler von der Warteliste nachgerueckt."
    await update.message.reply_text(msg)


async def admin_loeschen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.message.reply_text("Keine Admin-Rechte.")
        return
    if not context.args:
        await update.message.reply_text("Verwendung: /admin_loeschen <id>")
        return
    try:
        signup_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("ID muss eine Zahl sein.")
        return

    conn = get_conn()
    row = conn.execute("SELECT * FROM signups WHERE id = ?", (signup_id,)).fetchone()
    if row is None:
        await update.message.reply_text("Anmeldung nicht gefunden.")
        conn.close()
        return

    was_confirmed = row["status"] == "confirmed"
    slot_id = row["slot_id"]
    conn.execute("DELETE FROM signups WHERE id = ?", (signup_id,))
    conn.commit()

    reply = f"Anmeldung #{signup_id} geloescht."
    if was_confirmed:
        next_waiting = conn.execute(
            "SELECT * FROM signups WHERE slot_id = ? AND status = \'waitlist\' ORDER BY created_at ASC LIMIT 1",
            (slot_id,),
        ).fetchone()
        if next_waiting:
            conn.execute("UPDATE signups SET status = \'confirmed\' WHERE id = ?", (next_waiting["id"],))
            conn.commit()
            reply += f" {next_waiting['name']} ist von der Warteliste nachgerueckt."

    conn.close()
    await update.message.reply_text(reply)


async def admin_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not is_admin(update):
        await update.message.reply_text("Keine Admin-Rechte.")
        return
    conn = get_conn()
    conn.execute("DELETE FROM signups")
    conn.commit()
    conn.close()
    await update.message.reply_text("Alle Anmeldungen wurden zurueckgesetzt.")


# ---------------------------- Main ----------------------------

def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("[FEHLER] TELEGRAM_BOT_TOKEN ist nicht gesetzt.", file=sys.stderr)
        sys.exit(1)

    init_db()
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("slots", slots_cmd))
    app.add_handler(CommandHandler("eintragen", eintragen))
    app.add_handler(CommandHandler("status", status_cmd))

    app.add_handler(CommandHandler("admin_liste", admin_liste))
    app.add_handler(CommandHandler("admin_max", admin_max))
    app.add_handler(CommandHandler("admin_loeschen", admin_loeschen))
    app.add_handler(CommandHandler("admin_reset", admin_reset))

    app.run_polling()


if __name__ == "__main__":
    main()
