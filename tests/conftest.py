import os
import sys

# Make the repo root importable before app/scheduler_new are imported.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# app.py exits at import time when these are missing. Provide safe test values.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ADMIN_PASSWORD_ADMIN", "test-admin-pw")
os.environ.setdefault("ADMIN_PASSWORD_DANIEL", "test-daniel-pw")
