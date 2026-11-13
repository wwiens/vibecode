import logging

from flask import Flask, render_template

import db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")

app = Flask(__name__)

db.init_db()
log.info("Database ready at %s", db.DATABASE_PATH)


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    db.check_db()
    return {"status": "ok"}
