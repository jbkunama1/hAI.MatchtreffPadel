"""Auth-Hilfen: Admin-Login-Check und admin_required-Deocorator."""

import logging
from functools import wraps

from flask import flash, redirect, session, url_for

from logic_db import get_db

from werkzeug.security import check_password_hash

logger = logging.getLogger("matchtreff.web.auth")


def authenticate_admin(username, password):
    """Prueft die Zugangsdaten gegen die admin_users-Tabelle.

    Gibt bei Erfolg den Admin-Namen zurueck, sonst None.
    """
    db = get_db()
    row = db.execute(
        "SELECT * FROM admin_users WHERE username = ?",
        (username,),
    ).fetchone()

    if row and check_password_hash(row["password_hash"], password):
        return row["username"]

    return None


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin-Login erforderlich.", "danger")
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped
