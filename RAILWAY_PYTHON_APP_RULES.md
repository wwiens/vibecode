# Rules for Generating a Railway-Ready Python App

**Purpose:** Use this document as a build specification for an AI coding agent (such as Codex). Generate a small, classroom-friendly Python web application that runs locally and deploys from GitHub to Railway with minimal manual setup. Assume the application may save data that must survive redeployments.

**Primary goal:** After the repository is pushed to GitHub, deployment should require only choosing the repository, attaching a preconfigured Railway volume at `/data`, clicking **Deploy**, and generating a public domain. Do not require the instructor to type environment variables, install a database service, edit build/start commands, or write a Dockerfile.

## 1. Mandatory architecture

1. Build a **web application**, not a desktop GUI or command-line-only program.
2. Use **Python 3.12**, **Flask**, and **Gunicorn**. Use built-in Python modules where practical.
3. Place `main.py` at the **root of the repository** and expose the Flask application as the top-level variable `app` (`app = Flask(__name__)`). This makes the import target `main:app`.
4. Include `requirements.txt` at the repository root with `flask` and `gunicorn` as installable dependencies. Pin tested package versions for reproducible classroom builds. Do not depend on undeclared packages.
5. Include `.python-version` at the repository root containing `3.12`.
6. Let Railway's **Railpack** builder detect Python, Flask, and Gunicorn. With these conventions, Railpack automatically starts Flask using Gunicorn and binds to Railway's assigned port.
7. **Do not** add a Dockerfile, a Procfile, custom Railway build/start commands, or `railway.json`/`railway.toml`. Railway's legacy Config as Code system is being retired for new services; its configuration files are not needed here.
8. Keep a **single web service**, with no worker process, background scheduler, Redis, or externally hosted database.
9. Avoid Node.js build steps and JavaScript frameworks that require a separate frontend build. Use Flask templates, plain HTML/CSS, and optional vanilla JavaScript.

## 2. Environment variables and networking

1. Require **zero manually configured Railway environment variables** for normal operation.
2. Do not hardcode a deployment port. Railway supplies `PORT` automatically; Railpack's Flask/Gunicorn start command uses it.
3. The production server must listen on `0.0.0.0` and the Railway-provided port. Do not use Flask's development server as the production entrypoint.
4. Do not require `DATABASE_URL`, `SECRET_KEY`, external API keys, OAuth credentials, mail credentials, or third-party service accounts for the basic demo.
5. If an optional feature would require a secret or service account, **leave it out** rather than making first deployment depend on additional configuration.
6. Do not enable Flask debug mode on the deployed app.
7. Provide a working `GET /` route that renders the user interface. A simple `GET /health` route returning HTTP 200 is also useful, but must not require Railway health-check setup.

## 3. Persistent storage — critical

1. Use **SQLite** via Python's built-in `sqlite3` module for small amounts of structured data. Do not use an external database for this class demo.
2. The instructor will attach a **Railway Volume mounted at `/data` before the first deployment**.
3. Railway automatically exposes `RAILWAY_VOLUME_MOUNT_PATH` at application runtime. **Read it; never ask the instructor to define it.**
4. On Railway, place the database, user uploads, and every other file that must survive redeployments **inside that mounted directory**. Example database path: `/data/app.db`.
5. During local development, use a repository-local `.localdata/` directory, excluded from Git.
6. If the app detects that it is running on Railway but `RAILWAY_VOLUME_MOUNT_PATH` is missing, **fail at startup with a clear error** rather than silently placing important data on the ephemeral filesystem.
7. The volume is mounted **only when the deployed service starts**. Never create, migrate, seed, or modify the persistent SQLite file during installation, build, or Railway pre-deploy.
8. Initialize or upgrade required SQLite tables **when the application starts**, using safe, idempotent logic such as `CREATE TABLE IF NOT EXISTS`. Never overwrite or reset existing records on startup.
9. Use parameterized SQL statements (`?` placeholders) for user-supplied values. Open a connection per operation/request and close it promptly; do not share a global SQLite connection across requests.
10. Keep the app small and operate as **one Railway replica**; SQLite on a single mounted volume is unsuitable for horizontally scaled, multi-instance writes. Avoid parallel heavy writers.
11. No saved data belongs in the Git repository. No persistent application data should rely on `/tmp`, `./app.db`, the app's source folder, or the container filesystem outside the mounted volume.

Use this storage-location pattern (or an equivalent that follows the same rules):

```python
import os
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
```

**Note:** A Railway volume persists through restarts and redeployments, but it is not a substitute for backups. Assume brief redeployment downtime is acceptable for this demo.

## 4. Application design restrictions

1. Favor a small, understandable application that can be explained to students in one class session.
2. Include a browser interface with at least one user input, a Python route that processes it, and a visible result.
3. If the app saves data, demonstrate **create, read, and optionally delete/edit**, backed by SQLite.
4. Validate submitted inputs and show helpful errors. Escape user content in HTML; use Jinja's default escaping rather than marking arbitrary user text as safe.
5. Do not require registration, login, email verification, payments, SMS, webhooks, or paid APIs.
6. The app may be publicly reachable. Use **fictitious classroom data only**, and make it clear in the README that without authentication anybody with the link can view or alter demo records. Do not collect sensitive or personal information.
7. Avoid expensive background work, long-running requests, native GUI libraries, OS-specific executables, browser automation, GPU dependencies, and large machine-learning models.
8. Keep runtime dependencies lightweight and compatible with Linux/Python 3.12.
9. Log useful startup information and errors to standard output/error so they are visible in Railway deployment logs. Do not print secrets or sensitive data.
10. If the app accepts file uploads, validate type and size, sanitize filenames, and store files only inside `DATA_DIR`.

## 5. Expected repository contents

```text
project-root/
├── main.py                 # Flask app exposed as `app`
├── requirements.txt        # Includes flask and gunicorn
├── .python-version         # Contains 3.12
├── .gitignore              # Excludes .venv/, .localdata/, *.db, .env, caches
├── README.md               # Local run + Railway deployment guide
├── templates/              # Optional Jinja HTML templates
├── static/                 # Optional CSS and small JS files
└── tests/                  # Optional lightweight tests
```

Do not generate extra deployment infrastructure or scaffolding unless necessary for the app itself.

## 6. Local verification before deployment

The generated app must run using these commands from the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
gunicorn --bind 127.0.0.1:8000 main:app
```

The user interface must be available at `http://127.0.0.1:8000`.

Verify all of the following:

- `main:app` imports successfully, and Flask/Gunicorn start without errors.
- The homepage renders successfully.
- A user can submit the main form or action and see the result.
- When applicable, saved records remain after stopping and restarting the app.
- The local `.localdata/app.db` path works and is excluded by `.gitignore`.
- There are no required `.env` entries or undocumented manual steps.
- If simulated Railway environment settings are present but no volume mount path is supplied, the app raises a useful error instead of losing data.

## 7. Railway deployment instructions to include in README

1. Push the completed project to a GitHub repository.
2. Create a Railway project and select **Deploy from GitHub Repo**. Select the repository.
3. **Before the first deployment of the data-saving application**, attach a Railway Volume to the web service, with mount path exactly `/data`.
4. Click **Deploy** (or apply pending project changes). Railway/Railpack should detect Python and run Gunicorn automatically; no start-command configuration should be needed.
5. Under the service's **Settings → Networking**, select **Generate Domain**.
6. Open the public URL, create a sample record, and verify it appears.
7. Redeploy the same GitHub-backed service and confirm the record is still present.
8. View the Railway deployment logs if anything fails.

Clarify that creating a volume and generating the public domain are **Railway UI actions**; they are not configured automatically by ordinary Python source code. The first deploy may be initiated when the repository service is created, so attach the volume before writing any data worth preserving.

## 8. Acceptance criteria for the coding agent

Consider the project complete **only when**:

- [ ] The code is a functioning Flask web app with `main.py` exporting `app`.
- [ ] Root `requirements.txt` includes Flask and Gunicorn.
- [ ] `.python-version` specifies Python 3.12.
- [ ] Railway can auto-detect the build and start command without custom configuration files.
- [ ] The app does not require manually entered environment variables or external services.
- [ ] Persistent SQLite data is written to `RAILWAY_VOLUME_MOUNT_PATH` on Railway.
- [ ] The app fails clearly on Railway if its required volume was not mounted.
- [ ] Schema creation is idempotent and happens at runtime, not build time.
- [ ] Local start, record creation, restart, and record retention have been tested.
- [ ] A concise README covers local setup, GitHub deployment, adding the `/data` volume, generating a domain, and verifying persistence.

## Reference documentation (verified October 17, 2026)

- Railway Flask deployment: https://docs.railway.com/guides/flask
- Railpack Python/Flask auto-detection: https://railpack.com/languages/python
- Railway volumes: https://docs.railway.com/volumes
- Railway-provided variables: https://docs.railway.com/variables/reference
- Railway public networking: https://docs.railway.com/networking/public-networking
- Railway legacy config-as-code deprecation: https://docs.railway.com/config-as-code
