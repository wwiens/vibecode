import os
import random

from flask import Flask, jsonify, render_template

app = Flask(__name__)

VIBES = [
    "Ship it! The tests are vibes-based anyway.",
    "Describe the feeling, let the model write the for-loop.",
    "It's not a bug, it's an emergent feature.",
    "Accept all. Run. Squint. Repeat.",
    "Your job is now taste. Keystrokes are optional.",
    "If it compiles on the first try, be suspicious. Then ship it.",
    "Prompt like you mean it.",
    "Read the diff. Seriously. Read the diff.",
    "Small commits, big vibes.",
    "The best code is the code you didn't have to type.",
]


@app.route("/")
def index():
    return render_template("index.html", vibe=random.choice(VIBES))


@app.route("/api/vibe")
def vibe():
    return jsonify(vibe=random.choice(VIBES))


@app.route("/health")
def health():
    return jsonify(status="ok")


if __name__ == "__main__":
    # Local dev only. In production, gunicorn serves the app (see railway.json).
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=True)
