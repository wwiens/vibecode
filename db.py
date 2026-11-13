"""SQLite storage.

On Railway, data lives on the volume mounted at /data so it survives redeploys.
Locally, it lives in .localdata/ (git-ignored).
"""

import os
import sqlite3
from contextlib import closing
from pathlib import Path

railway_volume = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")
on_railway = bool(os.getenv("RAILWAY_ENVIRONMENT_ID"))

if on_railway and not railway_volume:
    raise RuntimeError(
        "Persistent storage is not configured: attach a Railway volume at /data."
    )

DATA_DIR = (
    Path(railway_volume)
    if railway_volume
    else Path(__file__).resolve().parent / ".localdata"
)
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = DATA_DIR / "app.db"

# Add CREATE TABLE IF NOT EXISTS statements here. Runs on every startup,
# so it must be idempotent and must never drop or reset existing data.
SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    company TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    website TEXT NOT NULL DEFAULT '',
    event TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS contacts_unique_email
ON contacts (lower(email)) WHERE email != '';
"""


def get_connection():
    """Open a new connection. Use one per request and close it promptly."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_connection()) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def check_db():
    with closing(get_connection()) as conn:
        conn.execute("SELECT 1")
