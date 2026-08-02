"""hAI.MatchtreffPadel Telegram-Bot.

Rollen:
  - admin: via ADMIN_TELEGRAM_IDS (env) oder per Verify-Code
           (TELEGRAM_ADMIN_VERIFY_CODE) in der Tabelle telegram_users.
  - user:  alle anderen. Kann sich anmelden, Status abfragen und
           Nachrichten an Admins senden.

Der Bot verhaelt sich bei der Anmeldung genauso wie die Web-App:
Slots zaehlen, Mitglieder-Vorrang, Warteliste. Gaeste werden wie in der
Web-App sofort eingetragen und der Admin bekommt die bestehende
Benachrichtigung mit Bestaetigen/Entfernen-Buttons.
"""

import csv
import io
import logging
import os
import sqlite3
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

DB_PATH = os.getenv("MATCHTREFF_DB_PATH", "instance/matchtreff.sqlite3")
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ADMIN_TELEGRAM_IDS = {
    item.strip()
    for item in os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",")
    if item.strip()
}
ADMIN_VERIFY_CODE = os.getenv("TELEGRAM_ADMIN_VERIFY_CODE", "")

DEFAULT_WAITLIST_LIMIT = 4
DEFAULT_SLOT_SELECTION = "both"
DEFAULT_WAITLIST_MODE = "with_waitlist"
WAITLIST_MODES = {"with_waitlist", "open_for_all", "no_waitlist", "guests_only"}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("matchtreff.telegram_bot")

# Conversation-States
(
    NAME,
    MEMBER,
    SLOTS,
    CONFIRM,
    MESSAGE_TEXT,
    DEL_SLOT,
    DEL_PERSON,
    MAX_SLOT,
    MAX_VALUE,
    BROADCAST_TEXT,
    VERIFY_CODE,
) = range(11)


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 8000")
    conn.execute("PRAGMA foreign_keys = ON")
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Stellt sicher, dass die telegram_users-Tabelle existiert."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER UNIQUE NOT NULL,
            username TEXT,
            first_name TEXT,
            role TEXT NOT NULL DEFAULT 'user',
            is_member_default INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def normalize_name(name: str) -> str:
    return " ".join(name.strip().split()).lower()


def get_setting(conn: sqlite3.Connection, key: str, default: str) -> str:
    row = conn.execute(
        "SELECT value FROM settings WHERE key = ?",
        (key,),
    ).fetchone()
    return row["value"] if row and row["value"].strip() else default


def get_waitlist_limit(conn: sqlite3.Connection) -> int:
    value = get_setting(conn, "waitlist_limit", str(DEFAULT_WAITLIST_LIMIT))
    return max(0, int(value)) if value.isdigit() else DEFAULT_WAITLIST_LIMIT


def get_slot_selection(conn: sqlite3.Connection) -> str:
    value = get_setting(conn, "slot_selection", DEFAULT_SLOT_SELECTION)
    return value if value in {"one", "both"} else DEFAULT_SLOT_SELECTION


def get_waitlist_mode(conn: sqlite3.Connection) -> str:
    value = get_setting(conn, "waitlist_mode", DEFAULT_WAITLIST_MODE)
    return value if value in WAITLIST_MODES else DEFAULT_WAITLIST_MODE


def set_setting(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO settings (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


def get_slots(conn: sqlite3.Connection):
    return conn.execute("SELECT * FROM slots ORDER BY id").fetchall()


def get_active_slots(conn: sqlite3.Connection):
    slots = get_slots(conn)
    if get_slot_selection(conn) == "one":
        slots = slots[:1]
    return slots


def get_role(telegram_id: int) -> str:
    if str(telegram_id) in ADMIN_TELEGRAM_IDS:
        return "admin"
    with get_conn() as conn:
        row = conn.execute(
            "SELECT role FROM telegram_users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
    if row and row["role"] == "admin":
        return "admin"
    return "user"


def is_admin(telegram_id: int) -> bool:
    return get_role(telegram_id) == "admin"


def register_user(update: Update) -> None:
    user = update.effective_user
    if not user:
        return
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO telegram_users (telegram_id, username, first_name, role)
            VALUES (?, ?, ?, 'user')
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name
            """,
            (user.id, user.username, user.first_name),
        )
        conn.commit()


def get_telegram_user(telegram_id: int):
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM telegram_users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()


def get_slot_label(conn: sqlite3.Connection, slot_id: int) -> Optional[str]:
    row = conn.execute(
        "SELECT label FROM slots WHERE id = ?",
        (slot_id,),
    ).fetchone()
    return row["label"] if row else None


def format_slot_status(conn: sqlite3.Connection, slot) -> str:
    confirmed = conn.execute(
        "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'confirmed'",
        (slot["id"],),
    ).fetchone()["c"]
    waitlisted = conn.execute(
        "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'waitlist'",
        (slot["id"],),
    ).fetchone()["c"]
    status = f"{confirmed}/{slot['max_players']} belegt"
    if waitlisted:
        status += f", {waitlisted} auf Warteliste"
    return status


def determine_signup_status(conn: sqlite3.Connection, slot_id: int, is_member: bool):
    """Spiegelt die Logik aus app.py /eintragen wider.

    Rueckgabe: (status | None, blocked_reason | None)
    """
    waitlist_mode = get_waitlist_mode(conn)
    waitlist_limit = get_waitlist_limit(conn)

    confirmed = conn.execute(
        "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'confirmed'",
        (slot_id,),
    ).fetchone()["c"]
    waitlisted = conn.execute(
        "SELECT COUNT(*) AS c FROM signups WHERE slot_id = ? AND status = 'waitlist'",
        (slot_id,),
    ).fetchone()["c"]

    slot = conn.execute(
        "SELECT * FROM slots WHERE id = ?", (slot_id,)
    ).fetchone()

    if waitlist_mode == "open_for_all":
        return "confirmed", None

    if waitlist_mode == "guests_only" and not is_member:
        if waitlist_limit <= 0 or waitlisted >= waitlist_limit:
            return None, "Gast-Warteliste voll"
        return "waitlist", None

    if confirmed < slot["max_players"]:
        return "confirmed", None

    if waitlist_mode == "no_waitlist":
        return None, "Slot voll"

    if waitlist_limit <= 0 or waitlisted >= waitlist_limit:
        return None, "Warteliste voll"

    return "waitlist", None


def promote_waiting_signup(conn: sqlite3.Connection, slot_id: int):
    waiting_signup = conn.execute(
        """
        SELECT id, name
        FROM signups
        WHERE slot_id = ? AND status = 'waitlist'
        ORDER BY created_at ASC, id ASC
        LIMIT 1
        """,
        (slot_id,),
    ).fetchone()

    if not waiting_signup:
        return None

    conn.execute(
        "UPDATE signups SET status = 'confirmed' WHERE id = ?",
        (waiting_signup["id"],),
    )
    return waiting_signup


def format_signups_list(conn: sqlite3.Connection) -> str:
    lines = []
    for slot in get_slots(conn):
        slot_label = slot["label"]
        status = format_slot_status(conn, slot)
        lines.append(f"{slot_label} ({status})")

        confirmed = conn.execute(
            "SELECT * FROM signups WHERE slot_id = ? AND status = 'confirmed' "
            "ORDER BY is_member DESC, created_at ASC",
            (slot["id"],),
        ).fetchall()
        waitlisted = conn.execute(
            "SELECT * FROM signups WHERE slot_id = ? AND status = 'waitlist' "
            "ORDER BY created_at ASC",
            (slot["id"],),
        ).fetchall()

        if confirmed:
            for s in confirmed:
                member = "Mitglied" if s["is_member"] else "Gast"
                lines.append(f"  - {s['name']} ({member})")
        else:
            lines.append("  - (noch niemand bestaetigt)")

        if waitlisted:
            lines.append("  Warteliste:")
            for s in waitlisted:
                member = "Mitglied" if s["is_member"] else "Gast"
                lines.append(f"    - {s['name']} ({member})")

        lines.append("")
    return "\n".join(lines).strip() or "Keine Anmeldungen vorhanden."


def build_csv_bytes() -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["ID", "Slot", "Name", "Status", "Mitglied", "Erstellt"]
    )
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT s.id, sl.label AS slot_label, s.name, s.status,
                   s.is_member, s.created_at
            FROM signups s
            JOIN slots sl ON sl.id = s.slot_id
            ORDER BY sl.id, s.created_at
            """
        ).fetchall()
        for row in rows:
            writer.writerow(
                [
                    row["id"],
                    row["slot_label"],
                    row["name"],
                    row["status"],
                    "ja" if row["is_member"] else "nein",
                    row["created_at"],
                ]
            )
    return buf.getvalue().encode("utf-8")


def get_admin_ids() -> list[str]:
    ids = set(ADMIN_TELEGRAM_IDS)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT telegram_id FROM telegram_users WHERE role = 'admin'"
        ).fetchall()
        ids.update(str(r["telegram_id"]) for r in rows)
    return sorted(ids)


def keyboard(buttons: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(text, callback_data=data) for text, data in row]
         for row in buttons]
    )


async def notify_admins_guest_signup(
    context: ContextTypes.DEFAULT_TYPE,
    signup_id: int,
    name: str,
    slot_label: str,
    status: str,
) -> None:
    admin_ids = get_admin_ids()
    if not admin_ids:
        return

    status_text = "Warteliste" if status == "waitlist" else "bestaetigt"
    text = (
        "Neue Gast-Anmeldung (kein TPCG-Mitglied)\n\n"
        f"Name: {name}\n"
        f"Slot: {slot_label}\n"
        f"Status: {status_text}\n\n"
        "Die Anmeldung ist bereits eingetragen. "
        "Du kannst sie jederzeit entfernen."
    )
    reply_markup = keyboard(
        [
            [
                ("Bestaetigen (ok)", f"ack_signup:{signup_id}"),
                ("Entfernen", f"reject_signup:{signup_id}"),
            ]
        ]
    )

    for admin_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=int(admin_id),
                text=text,
                reply_markup=reply_markup,
            )
        except Exception as exc:
            logger.warning("Benachrichtigung an %s fehlgeschlagen: %s", admin_id, exc)


# ---------------------------------------------------------------- /start


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    register_user(update)
    user = update.effective_user
    first_name = user.first_name if user else ""
    admin = is_admin(user.id) if user else False

    text = (
        f"Hallo {first_name}! Ich bin der hAIMatchtreff Bot.\n\n"
        "Hier kannst du dich fuer den naechsten Matchtreff anmelden, "
        "deinen Status abfragen oder dem Orga-Team eine Nachricht schicken."
    )

    buttons: list[list[tuple[str, str]]] = [
        [("Anmelden", "mm:signup")],
        [("Mein Status", "mm:status")],
        [("Nachricht an Admin", "mm:message")],
    ]

    if not admin and ADMIN_VERIFY_CODE:
        buttons.append([("Admin werden (Code)", "mm:verify")])

    if admin:
        buttons.append([("Admin-Bereich", "adm:menu")])

    if update.message:
        await update.message.reply_text(text, reply_markup=keyboard(buttons))
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text, reply_markup=keyboard(buttons)
        )


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    if update.message:
        await update.message.reply_text("Aktion abgebrochen.")
    return ConversationHandler.END


# ------------------------------------------------------------ Hauptmenue


async def callback_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data or ""
    user = update.effective_user

    if data.startswith("adm:"):
        return await callback_admin_menu(update, context)

    if data == "mm:status":
        return await cmd_my_status(update, context)

    if data == "mm:verify":
        if not ADMIN_VERIFY_CODE:
            await query.edit_message_text(
                "Admin-Verifizierung ist deaktiviert.",
                reply_markup=keyboard([[("Zurueck", "mm:menu")]]),
            )
            return
        await query.edit_message_text(
            "Bitte sende mir den Admin-Verify-Code als Textnachricht.\n"
            "Zum Abbrechen: /cancel"
        )
        context.user_data["verify"] = True
        return

    if data == "mm:menu":
        return await start_cmd(update, context)


async def verify_code_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.user_data.get("verify"):
        return
    context.user_data["verify"] = False

    code = (update.message.text or "").strip()
    if code != ADMIN_VERIFY_CODE:
        await update.message.reply_text(
            "Falscher Code. Zum Abbrechen: /cancel",
            reply_markup=keyboard([[("Zurueck zum Menue", "mm:menu")]]),
        )
        return

    user = update.effective_user
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO telegram_users (telegram_id, username, first_name, role)
            VALUES (?, ?, ?, 'admin')
            ON CONFLICT(telegram_id) DO UPDATE SET role = 'admin'
            """,
            (user.id, user.username, user.first_name),
        )
        conn.commit()

    await update.message.reply_text(
        "Du bist jetzt Admin! Der Admin-Bereich ist freigeschaltet.",
        reply_markup=keyboard([[("Admin-Bereich", "adm:menu")]]),
    )


# --------------------------------------------------------- Mein Status


async def cmd_my_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not user:
        return

    tg_user = get_telegram_user(user.id)
    name = tg_user["first_name"] if tg_user else None

    with get_conn() as conn:
        if name:
            rows = conn.execute(
                """
                SELECT s.label AS slot_label, su.status, su.is_member
                FROM signups su
                JOIN slots s ON s.id = su.slot_id
                WHERE su.name_normalized = ?
                ORDER BY su.created_at
                """,
                (normalize_name(name),),
            ).fetchall()
        else:
            rows = []

    if not rows:
        text = "Du bist aktuell noch fuer keinen Slot eingetragen."
    else:
        lines = []
        for row in rows:
            status_text = "bestaetigt" if row["status"] == "confirmed" else "Warteliste"
            member_text = "Mitglied" if row["is_member"] else "Gast"
            lines.append(f"• {row['slot_label']}: {status_text} ({member_text})")
        text = "Dein aktueller Status:\n\n" + "\n".join(lines)

    if query:
        await query.edit_message_text(
            text, reply_markup=keyboard([[("Zurueck", "mm:menu")]])
        )
    else:
        await update.message.reply_text(
            text, reply_markup=keyboard([[("Zurueck", "mm:menu")]])
        )


# ----------------------------------------------------- Nachricht an Admin


async def message_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "Schreibe mir deine Nachricht an das Orga-Team. "
            "Sie wird an alle Admins weitergeleitet.\n"
            "Zum Abbrechen: /cancel"
        )
    return MESSAGE_TEXT


async def message_received(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Bitte eine Nachricht senden oder /cancel.")
        return MESSAGE_TEXT

    user = update.effective_user
    sender = f"{user.first_name or ''} {user.last_name or ''}".strip() or (
        user.username or f"ID {user.id}"
    )

    admin_ids = get_admin_ids()
    sent = 0
    for admin_id in admin_ids:
        try:
            await context.bot.send_message(
                chat_id=int(admin_id),
                text=f"📩 Nachricht von {sender}:\n\n{text}",
            )
            sent += 1
        except Exception as exc:
            logger.warning("Weiterleitung an %s fehlgeschlagen: %s", admin_id, exc)

    await update.message.reply_text(
        f"Deine Nachricht wurde an {sent} Admin(s) weitergeleitet."
    )
    return ConversationHandler.END


# --------------------------------------------------- Anmeldung (Flow)


async def signup_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "Wie heisst du? Bitte sende mir deinen Namen "
            "(so wie in der Web-App).\nZum Abbrechen: /cancel"
        )
        return NAME

    # Namenseingabe
    name = (update.message.text or "").strip()
    if not name or len(name) > 60:
        await update.message.reply_text(
            "Bitte gib einen gueltigen Namen ein (max. 60 Zeichen)."
        )
        return NAME

    context.user_data["signup_name"] = name
    text = (
        f"Alles klar, {name}! Bist du TCG-Mitglied?\n"
        "Mitglieder haben Vorrang und zahlen 2 Euro."
    )
    await update.message.reply_text(
        text,
        reply_markup=keyboard(
            [
                [("Ja, ich bin Mitglied", "su:member:1")],
                [("Nein, ich bin Gast", "su:member:0")],
                [("Abbrechen", "su:abort")],
            ]
        ),
    )
    return MEMBER


async def signup_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()

    data = query.data or ""
    if data == "su:abort":
        await query.edit_message_text("Abgebrochen.")
        return ConversationHandler.END

    if data not in {"su:member:1", "su:member:0"}:
        return MEMBER

    context.user_data["signup_is_member"] = data == "su:member:1"
    context.user_data["signup_slots"] = []

    with get_conn() as conn:
        active_slots = get_active_slots(conn)

    if not active_slots:
        await query.edit_message_text("Keine Slots verfuegbar.")
        return ConversationHandler.END

    buttons = []
    for slot in active_slots:
        buttons.append([(f"{slot['label']}", f"su:slot:{slot['id']}")])
    buttons.append([("Fertig", "su:done"), ("Abbrechen", "su:abort")])

    await query.edit_message_text(
        "Fuer welche(n) Slot(s) moechtest du dich eintragen?\n"
        "Tippe auf die Buttons (mehrfach moeglich) und dann auf 'Fertig'.",
        reply_markup=keyboard(buttons),
    )
    return SLOTS


async def signup_slots(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return SLOTS
    await query.answer()

    data = query.data or ""
    if data == "su:abort":
        await query.edit_message_text("Abgebrochen.")
        return ConversationHandler.END

    if data.startswith("su:slot:"):
        try:
            slot_id = int(data.split(":", 2)[2])
        except (ValueError, IndexError):
            return SLOTS

        selected = context.user_data.get("signup_slots", [])
        if slot_id in selected:
            selected.remove(slot_id)
        else:
            selected.append(slot_id)
        context.user_data["signup_slots"] = selected

        with get_conn() as conn:
            slots = get_active_slots(conn)

        buttons = []
        for slot in slots:
            mark = "☑" if slot["id"] in selected else "☐"
            buttons.append([(f"{mark} {slot['label']}", f"su:slot:{slot['id']}")])
        buttons.append([("Fertig", "su:done"), ("Abbrechen", "su:abort")])

        await query.edit_message_text(
            "Fuer welche(n) Slot(s) moechtest du dich eintragen?",
            reply_markup=keyboard(buttons),
        )
        return SLOTS

    if data == "su:done":
        selected = context.user_data.get("signup_slots", [])
        if not selected:
            await query.answer("Bitte mindestens einen Slot waehlen.", show_alert=True)
            return SLOTS

        with get_conn() as conn:
            slot_rows = []
            for slot_id in selected:
                row = conn.execute(
                    "SELECT * FROM slots WHERE id = ?", (slot_id,)
                ).fetchone()
                if row:
                    slot_rows.append(row)

        context.user_data["signup_slot_rows"] = slot_rows
        lines = [
            "Bitte bestaetige deine Anmeldung:\n",
            f"Name: {context.user_data.get('signup_name')}",
            "Mitglied: "
            + ("ja" if context.user_data.get("signup_is_member") else "nein"),
        ]
        for row in slot_rows:
            lines.append(f"Slot: {row['label']}")

        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=keyboard(
                [
                    [("Ja, eintragen", "su:confirm:1")],
                    [("Nein, abbrechen", "su:abort")],
                ]
            ),
        )
        return CONFIRM

    return SLOTS


async def signup_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()

    data = query.data or ""
    if data == "su:abort":
        await query.edit_message_text("Abgebrochen.")
        return ConversationHandler.END

    if data != "su:confirm:1":
        return CONFIRM

    name = context.user_data.get("signup_name", "")
    is_member = context.user_data.get("signup_is_member", False)
    slot_rows = context.user_data.get("signup_slot_rows", [])

    added = []
    waitlisted = []
    blocked = []

    with get_conn() as conn:
        for slot in slot_rows:
            slot_id = slot["id"]

            existing = conn.execute(
                "SELECT id FROM signups WHERE slot_id = ? AND name_normalized = ?",
                (slot_id, normalize_name(name)),
            ).fetchone()
            if existing:
                blocked.append(f"{slot['label']} (Name bereits vorhanden)")
                continue

            status, reason = determine_signup_status(conn, slot_id, is_member)
            if status is None:
                blocked.append(f"{slot['label']} ({reason})")
                continue

            cursor = conn.execute(
                """
                INSERT INTO signups (slot_id, name, name_normalized, status, is_member)
                VALUES (?, ?, ?, ?, ?)
                """,
                (slot_id, name, normalize_name(name), status, int(is_member)),
            )
            conn.commit()
            signup_id = cursor.lastrowid

            if status == "confirmed":
                added.append((slot["label"], signup_id))
            else:
                waitlisted.append((slot["label"], signup_id))

    # Namen fuer "Mein Status" merken
    user = update.effective_user
    if user:
        with get_conn() as conn:
            conn.execute(
                """
                INSERT INTO telegram_users (telegram_id, username, first_name, role)
                VALUES (?, ?, ?, 'user')
                ON CONFLICT(telegram_id) DO UPDATE SET
                    first_name = excluded.first_name,
                    username = excluded.username
                """,
                (user.id, user.username, name),
            )
            conn.commit()

    lines = []
    if added:
        lines.append("✅ Eingetragen fuer:\n" + "\n".join(f"- {l}" for l, _ in added))
    if waitlisted:
        lines.append(
            "⏳ Auf der Warteliste:\n" + "\n".join(f"- {l}" for l, _ in waitlisted)
        )
    if blocked:
        lines.append("⚠️ Nicht moeglich:\n" + "\n".join(f"- {b}" for b in blocked))

    await query.edit_message_text(
        "\n\n".join(lines) if lines else "Keine Aenderung.",
        reply_markup=keyboard([[("Zurueck zum Menue", "mm:menu")]]),
    )

    # Gaeste an Admins melden (wie Web-App)
    if not is_member:
        for slot_label, signup_id in added + waitlisted:
            await notify_admins_guest_signup(
                context, signup_id, name, slot_label, "confirmed"
            )

    return ConversationHandler.END


# ------------------------------------------------------- Admin-Menue


async def cmd_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if not user or not is_admin(user.id):
        if query:
            await query.edit_message_text(
                "Du hast keine Admin-Rechte.",
                reply_markup=keyboard([[("Zurueck", "mm:menu")]]),
            )
        return

    buttons = [
        [("Liste ansehen", "adm:list")],
        [("Nutzer loeschen", "adm:delete")],
        [("Max. Spieler setzen", "adm:setmax")],
        [("Alle Anmeldungen zuruecksetzen", "adm:reset")],
        [("Export (CSV)", "adm:export")],
        [("Einstellungen", "adm:settings")],
        [("Broadcast an alle Nutzer", "adm:broadcast")],
        [("Zurueck", "mm:menu")],
    ]

    if query:
        await query.edit_message_text(
            "🛠 Admin-Bereich — was moechtest du tun?",
            reply_markup=keyboard(buttons),
        )
    else:
        await update.message.reply_text(
            "🛠 Admin-Bereich — was moechtest du tun?",
            reply_markup=keyboard(buttons),
        )


async def callback_admin_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    user = update.effective_user
    if not user or not is_admin(user.id):
        await query.edit_message_text(
            "Du hast keine Admin-Rechte.",
            reply_markup=keyboard([[("Zurueck", "mm:menu")]]),
        )
        return

    data = query.data or ""

    if data == "adm:list":
        with get_conn() as conn:
            text = format_signups_list(conn)
        await query.edit_message_text(
            f"📋 Anmeldungen:\n\n{text}",
            reply_markup=keyboard([[("Zurueck", "adm:menu")]]),
        )
        return

    if data == "adm:reset":
        with get_conn() as conn:
            conn.execute("DELETE FROM signups")
            conn.commit()
        await query.edit_message_text(
            "Alle Anmeldungen wurden zurueckgesetzt.",
            reply_markup=keyboard([[("Zurueck", "adm:menu")]]),
        )
        return

    if data == "adm:export":
        content = build_csv_bytes()
        await query.message.reply_document(
            document=("signups.csv", io.BytesIO(content)),
            caption="Export der Anmeldungen als CSV.",
        )
        return

    if data == "adm:settings":
        return await cmd_settings(update, context)

    if data.startswith("adm:wl_mode:"):
        mode = data.split(":", 2)[2]
        if mode in WAITLIST_MODES:
            with get_conn() as conn:
                set_setting(conn, "waitlist_mode", mode)
                conn.commit()
        return await cmd_settings(update, context)

    if data.startswith("adm:slot_sel:"):
        sel = data.split(":", 2)[2]
        if sel in {"one", "both"}:
            with get_conn() as conn:
                set_setting(conn, "slot_selection", sel)
                conn.commit()
        return await cmd_settings(update, context)

    if data == "adm:back" or data == "adm:menu":
        return await cmd_admin_menu(update, context)


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    with get_conn() as conn:
        wl_mode = get_waitlist_mode(conn)
        wl_limit = get_waitlist_limit(conn)
        slot_selection = get_slot_selection(conn)

    mode_labels = {
        "with_waitlist": "Mit Warteliste",
        "open_for_all": "Fuer alle offen",
        "no_waitlist": "Ohne Warteliste",
        "guests_only": "Nur Gaeste auf Warteliste",
    }

    text = (
        "⚙️ Einstellungen\n\n"
        f"Wartelisten-Modus: {mode_labels.get(wl_mode, wl_mode)}\n"
        f"Wartelisten-Limit: {wl_limit}\n"
        f"Slot-Auswahl: {'nur einer' if slot_selection == 'one' else 'beide'}"
    )

    buttons = [
        [("Wartelisten-Modus: " + mode_labels[mode], f"adm:wl_mode:{mode}")]
        for mode in sorted(WAITLIST_MODES)
    ]
    buttons.append(
        [
            ("Slot-Auswahl: nur einer", "adm:slot_sel:one"),
            ("Slot-Auswahl: beide", "adm:slot_sel:both"),
        ]
    )
    buttons.append([("Zurueck", "adm:menu")])

    await query.edit_message_text(text, reply_markup=keyboard(buttons))


# ------------------------------------------------- Admin: Nutzer loeschen


async def admin_delete_pick_slot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        with get_conn() as conn:
            slots = get_slots(conn)
        if not slots:
            await query.edit_message_text("Keine Slots vorhanden.")
            return ConversationHandler.END
        buttons = [[(s["label"], f"adm:del_slot:{s['id']}")] for s in slots]
        buttons.append([("Abbrechen", "su:abort")])
        await query.edit_message_text(
            "Welchen Slot moechtest du bearbeiten?", reply_markup=keyboard(buttons)
        )
        return DEL_SLOT
    return ConversationHandler.END


async def admin_delete_pick_person(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()

    data = query.data or ""
    if data == "su:abort":
        await query.edit_message_text("Abgebrochen.")
        return ConversationHandler.END

    try:
        slot_id = int(data.split(":", 2)[2])
    except (ValueError, IndexError):
        return DEL_SLOT

    context.user_data["del_slot_id"] = slot_id

    with get_conn() as conn:
        signups = conn.execute(
            "SELECT * FROM signups WHERE slot_id = ? ORDER BY created_at",
            (slot_id,),
        ).fetchall()

    if not signups:
        await query.edit_message_text(
            "In diesem Slot sind keine Anmeldungen.",
            reply_markup=keyboard([[("Zurueck", "adm:menu")]]),
        )
        return ConversationHandler.END

    buttons = [
        [
            (
                f"{s['name']} ({'Mitglied' if s['is_member'] else 'Gast'}, "
                f"{'best.' if s['status']=='confirmed' else 'Warteliste'})",
                f"adm:del:{s['id']}",
            )
        ]
        for s in signups
    ]
    buttons.append([("Abbrechen", "su:abort")])

    await query.edit_message_text(
        "Wen moechtest du loeschen?", reply_markup=keyboard(buttons)
    )
    return DEL_PERSON


async def admin_delete_person(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()

    data = query.data or ""
    if data == "su:abort":
        await query.edit_message_text("Abgebrochen.")
        return ConversationHandler.END

    try:
        signup_id = int(data.split(":", 2)[2])
    except (ValueError, IndexError):
        return DEL_PERSON

    with get_conn() as conn:
        signup = conn.execute(
            "SELECT * FROM signups WHERE id = ?", (signup_id,)
        ).fetchone()

        if not signup:
            await query.edit_message_text(
                "Eintrag nicht mehr vorhanden.",
                reply_markup=keyboard([[("Zurueck", "adm:menu")]]),
            )
            return ConversationHandler.END

        slot_id = signup["slot_id"]
        was_confirmed = signup["status"] == "confirmed"

        conn.execute("DELETE FROM signups WHERE id = ?", (signup_id,))

        promoted = None
        if was_confirmed:
            promoted = promote_waiting_signup(conn, slot_id)

        conn.commit()

    slot_label = get_slot_label(conn, slot_id) or "Unbekannter Slot"
    text = f"🗑 Geloescht: {signup['name']} ({slot_label})"
    if promoted:
        text += f"\n\nNachgerueckt: {promoted['name']} ist jetzt bestaetigt."

    await query.edit_message_text(
        text, reply_markup=keyboard([[("Zurueck", "adm:menu")]])
    )
    return ConversationHandler.END


# ------------------------------------------------- Admin: Max setzen


async def admin_setmax_pick_slot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        with get_conn() as conn:
            slots = get_slots(conn)
        buttons = [
            [(f"{s['label']} (aktuell: {s['max_players']})", f"adm:max_slot:{s['id']}")]
            for s in slots
        ]
        buttons.append([("Abbrechen", "su:abort")])
        await query.edit_message_text(
            "Fuer welchen Slot soll das Maximum gesetzt werden?",
            reply_markup=keyboard(buttons),
        )
        return MAX_SLOT
    return ConversationHandler.END


async def admin_setmax_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        data = query.data or ""
        if data == "su:abort":
            await query.edit_message_text("Abgebrochen.")
            return ConversationHandler.END
        try:
            slot_id = int(data.split(":", 2)[2])
        except (ValueError, IndexError):
            return MAX_SLOT
        context.user_data["max_slot_id"] = slot_id
        await query.edit_message_text(
            "Bitte sende die neue maximale Spielerzahl als Zahl.\n"
            "Zum Abbrechen: /cancel"
        )
        return MAX_VALUE
    return ConversationHandler.END


async def admin_setmax_save(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw = (update.message.text or "").strip()
    try:
        max_players = int(raw)
    except ValueError:
        await update.message.reply_text(
            "Bitte eine gueltige Zahl senden oder /cancel."
        )
        return MAX_VALUE

    if max_players <= 0:
        await update.message.reply_text("Die Zahl muss groesser als 0 sein.")
        return MAX_VALUE

    slot_id = context.user_data.get("max_slot_id")
    if not slot_id:
        await update.message.reply_text("Interner Fehler, bitte erneut versuchen.")
        return ConversationHandler.END

    with get_conn() as conn:
        conn.execute(
            "UPDATE slots SET max_players = ? WHERE id = ?",
            (max_players, slot_id),
        )
        conn.commit()

    await update.message.reply_text(
        f"Maximum auf {max_players} gesetzt.",
        reply_markup=keyboard([[("Zurueck", "adm:menu")]]),
    )
    return ConversationHandler.END


# -------------------------------------------------- Admin: Broadcast


async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text(
            "Sende mir den Text, den du an alle registrierten Nutzer "
            "broadcasten moechtest.\nZum Abbrechen: /cancel"
        )
    return BROADCAST_TEXT


async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    text = (update.message.text or "").strip()
    if not text:
        await update.message.reply_text("Bitte einen Text senden oder /cancel.")
        return BROADCAST_TEXT

    with get_conn() as conn:
        users = conn.execute(
            "SELECT telegram_id FROM telegram_users WHERE is_active = 1"
        ).fetchall()

    sent = 0
    for user_row in users:
        try:
            await context.bot.send_message(
                chat_id=int(user_row["telegram_id"]),
                text=f"📢 Mitteilung:\n\n{text}",
            )
            sent += 1
        except Exception as exc:
            logger.warning("Broadcast an %s fehlgeschlagen: %s", user_row["telegram_id"], exc)

    await update.message.reply_text(f"Broadcast an {sent} Nutzer gesendet.")
    return ConversationHandler.END


# ---------------------------------------------- Gast-Anmeldung (ack/reject)


async def callback_guest_signup(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return

    user = update.effective_user
    if not user or not is_admin(user.id):
        await query.answer("Keine Admin-Rechte.", show_alert=True)
        return

    await query.answer()

    data = query.data or ""
    logger.info("Callback empfangen: %s", data)

    if ":" not in data:
        await query.edit_message_text("Ungueltige Aktion.")
        return

    action, signup_id_raw = data.split(":", 1)

    try:
        signup_id = int(signup_id_raw)
    except ValueError:
        await query.edit_message_text("Ungueltige Signup-ID.")
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
            return

        slot_label = get_slot_label(conn, signup["slot_id"]) or "Unbekannter Slot"

        if action == "ack_signup":
            await query.edit_message_text(
                f"Zur Kenntnis genommen: {signup['name']} ({slot_label}) "
                "bleibt eingetragen."
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
            return

    await query.edit_message_text("Unbekannte Aktion.")


# ------------------------------------------------------- Sonstiges


async def fallback_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(
            "Ich verstehe das nicht. Nutze /start fuer das Hauptmenue."
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled bot error", exc_info=context.error)


async def post_init(application: Application) -> None:
    me = await application.bot.get_me()
    logger.info("Bot verbunden: @%s (id=%s)", me.username, me.id)


def main():
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN nicht gesetzt.")
        raise SystemExit(1)

    logger.info("Starte Telegram-Bot. DB_PATH=%s", DB_PATH)

    application = Application.builder().token(TOKEN).post_init(post_init).build()

    # /start und /cancel
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CommandHandler("cancel", cancel_cmd))

    # Anmeldung (Conversation)
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CallbackQueryHandler(signup_name, pattern="^mm:signup$")
            ],
            states={
                NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, signup_name)],
                MEMBER: [CallbackQueryHandler(signup_member, pattern="^su:")],
                SLOTS: [CallbackQueryHandler(signup_slots, pattern="^su:")],
                CONFIRM: [CallbackQueryHandler(signup_confirm, pattern="^su:")],
            },
            fallbacks=[CommandHandler("cancel", cancel_cmd)],
            allow_reentry=True,
        )
    )

    # Nachricht an Admin (Conversation)
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CallbackQueryHandler(message_start, pattern="^mm:message$")
            ],
            states={
                MESSAGE_TEXT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, message_received)
                ]
            },
            fallbacks=[CommandHandler("cancel", cancel_cmd)],
            allow_reentry=True,
        )
    )

    # Admin: Nutzer loeschen (Conversation)
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CallbackQueryHandler(admin_delete_pick_slot, pattern="^adm:delete$")
            ],
            states={
                DEL_SLOT: [
                    CallbackQueryHandler(
                        admin_delete_pick_person, pattern="^adm:del_slot:"
                    )
                ],
                DEL_PERSON: [
                    CallbackQueryHandler(admin_delete_person, pattern="^adm:del:")
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel_cmd)],
            allow_reentry=True,
        )
    )

    # Admin: Max setzen (Conversation)
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CallbackQueryHandler(admin_setmax_pick_slot, pattern="^adm:setmax$")
            ],
            states={
                MAX_SLOT: [
                    CallbackQueryHandler(admin_setmax_value, pattern="^adm:max_slot:")
                ],
                MAX_VALUE: [
                    MessageHandler(
                        filters.TEXT & ~filters.COMMAND, admin_setmax_save
                    )
                ],
            },
            fallbacks=[CommandHandler("cancel", cancel_cmd)],
            allow_reentry=True,
        )
    )

    # Admin: Broadcast (Conversation)
    application.add_handler(
        ConversationHandler(
            entry_points=[
                CallbackQueryHandler(broadcast_start, pattern="^adm:broadcast$")
            ],
            states={
                BROADCAST_TEXT: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_send)
                ]
            },
            fallbacks=[CommandHandler("cancel", cancel_cmd)],
            allow_reentry=True,
        )
    )

    # Menue-Navigation (Hauptmenue + Admin-Menue + Einstellungen)
    application.add_handler(
        CallbackQueryHandler(
            callback_main_menu,
            pattern="^(mm:|adm:menu|adm:list|adm:reset|adm:export|"
            "adm:settings|adm:wl_mode:|adm:slot_sel:|adm:back)",
        )
    )

    # Gast-Anmeldung ack/reject
    application.add_handler(
        CallbackQueryHandler(
            callback_guest_signup, pattern="^(ack_signup|reject_signup):"
        )
    )

    # Verify-Code-Eingabe
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, verify_code_cmd)
    )

    application.add_handler(MessageHandler(filters.ALL, fallback_message))

    application.add_error_handler(error_handler)

    logger.info("Telegram-Bot laeuft (Polling)...")
    application.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
