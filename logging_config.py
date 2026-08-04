import logging
import os
import sys


def setup_logging(
    name: str = "matchtreff",
    level: str | None = None,
) -> logging.Logger:
    """Zentrales Logging-Setup.

    Konfiguriert einen StreamHandler nach stdout (passt zu Docker-
    Logs) mit einem einheitlichen Format. Wird einmal pro Prozess
    aufgerufen (z.B. beim App-Start).
    """
    if level is None:
        level = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Verhindert doppelte Handler, wenn die Funktion mehrfach aufgerufen wird.
    root = logging.getLogger()
    if any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        return logging.getLogger(name)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.setLevel(level)
    root.setLevel(level)
    root.addHandler(handler)

    return logging.getLogger(name)
