import hashlib
import logging
from functools import lru_cache
from pathlib import Path

from flask import Flask, render_template

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
