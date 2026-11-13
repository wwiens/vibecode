# Folio — Business Card Scanner

A responsive Flask app for scanning business cards with a built-in camera, reviewing recognized details, and collecting contacts by event. Dark forest and mint scanner UI, photo upload, manual entry, search, editing, duplicate email checks, CSV export and individual vCard downloads.

## Run locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
gunicorn --bind 127.0.0.1:8000 main:app
```

Open http://127.0.0.1:8000. Click **Enable camera** and allow camera access, hold a card inside the corners, then click **Capture card**. You can also upload a JPG, PNG or WebP (up to 12 MB), enter details manually, or try a generated sample card. Review recognized fields before saving; OCR is approximate and the initial model is English.

Text recognition runs on the device with [Tesseract.js](https://github.com/naptha/tesseract.js), downloaded on demand from jsDelivr. The first scan needs an internet connection to load the engine and English language data; offline use is not guaranteed. Card images are processed in memory and are not uploaded or saved. Contact details in the Flask edition are stored in `.localdata/app.db`, which Git ignores. Camera access works on localhost and HTTPS; it stops when you leave the scanning screen or put the app in the background. Use **Export CSV** to back up your collection.

The Flask app has no login: anyone with its URL can view or change the same collection. Use fictitious demo contacts on public classroom deployments. The separate private Sites edition uses browser-local storage instead of the shared SQLite API; its contacts stay in that browser and do not synchronize across devices. Clearing browser site data removes that edition’s contacts. Current event selection is also browser-local.

## Deploy the Flask app to Railway

1. Push the completed project to GitHub.
2. In Railway, create a project with **Deploy from GitHub Repo** and choose this repository.
3. **Before writing any data**, attach a **Volume** to the service with mount path `/data`. This is a Railway UI action; Python cannot provision it. An initial deploy may start immediately after creating the service. The app refuses to start on Railway without the volume.
4. Deploy. Railpack detects Python and starts Gunicorn automatically. Leave custom build/start commands empty. No manually configured environment variables are needed.
5. Under **Settings → Networking**, click **Generate Domain** (or attach a custom domain). Domain generation is a Railway UI action.
6. Check `/` and `/health`, create a fictitious contact, then redeploy and confirm it remains. The app reads `RAILWAY_VOLUME_MOUNT_PATH` automatically and stores its SQLite database in that volume.
7. Check Railway deployment logs if anything fails. Use a single replica for this SQLite app.

## Verification

```bash
python -m unittest discover -s tests -v
node --check static/app.js
```

Tests isolate their database in a temporary directory and check contact creation, reading, updates, deletion, schema reinitialization, duplicate emails, validation and handling of HTML/SQL-like input.

## Private static Sites edition

```bash
python scripts/prepare_site.py
```

This renders the same templates into `sites/folio-scanner/dist/` without starting the database and selects browser-local contact storage. The tracked manifest in `sites/folio-scanner/.openai/hosting.json` identifies its private Site. Use the Sites source workflow to synchronize, package and publish that directory after changes.

## Layout

- `main.py`: Flask app, `/health`, and contact CRUD API.
- `db.py`: SQLite schema and Railway volume handling.
- `templates/`: shared page structure.
- `static/`: responsive styles and camera/OCR/contact behavior.
- `scripts/prepare_site.py`: renders the static edition.
- `tests/`: isolated API checks.
