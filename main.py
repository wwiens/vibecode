import hashlib
import logging
import re
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from flask import Flask, render_template, request

import db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

app = Flask(__name__)


@lru_cache(maxsize=None)
def _static_version(filename):
    data = (Path(app.static_folder) / filename).read_bytes()
    return hashlib.sha256(data).hexdigest()[:10]


@app.url_defaults
def _bust_static_cache(endpoint, values):
    # Cloudflare tells browsers to cache static files for hours. Adding a
    # content hash (?v=...) gives every changed file a new URL, so each
    # deploy's CSS/JS shows up right away.
    if endpoint == "static" and "filename" in values:
        try:
            values["v"] = _static_version(values["filename"])
        except OSError:
            pass

db.init_db()
log.info("Database ready at %s", db.DATABASE_PATH)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    db.check_db()
    return {"status": "ok"}


FIELDS = {"name": 150, "company": 150, "title": 150, "email": 254,
          "phone": 80, "website": 250, "event": 120, "notes": 2000}
app.config["MAX_CONTENT_LENGTH"] = 32 * 1024


def validate_contact():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, "Please provide contact details."
    clean = {}
    for key, limit in FIELDS.items():
        value = data.get(key, "")
        if not isinstance(value, str) or len(value) > limit:
            return None, f"{key.capitalize()} must be text, up to {limit} characters."
        clean[key] = value.strip()
    if not clean["name"]:
        return None, "Please enter a name."
    if clean["email"] and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", clean["email"]):
        return None, "Please enter a valid email address."
    return clean, None


@app.get("/api/contacts")
def list_contacts():
    with closing(db.get_connection()) as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM contacts ORDER BY created_at DESC")]


@app.post("/api/contacts")
def create_contact():
    contact, error = validate_contact()
    if error:
        return {"error": error}, 400
    contact["id"] = str(uuid.uuid4())
    contact["created_at"] = datetime.now(timezone.utc).isoformat()
    keys = ["id", *FIELDS, "created_at"]
    with closing(db.get_connection()) as conn:
        try:
            conn.execute("INSERT INTO contacts (" + ", ".join(keys) + ") VALUES (" + ", ".join("?" for _ in keys) + ")", [contact[k] for k in keys])
            conn.commit()
        except sqlite3.IntegrityError:
            return {"error": "A connection with this email already exists."}, 409
    return contact, 201


@app.put("/api/contacts/<contact_id>")
def update_contact(contact_id):
    contact, error = validate_contact()
    if error:
        return {"error": error}, 400
    with closing(db.get_connection()) as conn:
        try:
            result = conn.execute("UPDATE contacts SET " + ", ".join(k + " = ?" for k in FIELDS) + " WHERE id = ?", [contact[k] for k in FIELDS] + [contact_id])
            if result.rowcount == 0:
                return {"error": "This connection no longer exists."}, 404
            conn.commit()
        except sqlite3.IntegrityError:
            return {"error": "A connection with this email already exists."}, 409
    return {"status": "saved"}


@app.delete("/api/contacts/<contact_id>")
def delete_contact(contact_id):
    with closing(db.get_connection()) as conn:
        result = conn.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        conn.commit()
        if result.rowcount == 0:
            return {"error": "This connection no longer exists."}, 404
    return {"status": "deleted"}
