# vibecode

A small Flask app that deploys from GitHub to Railway. It currently serves a placeholder page.

## Run locally

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
gunicorn --bind 127.0.0.1:8000 main:app
```

Open http://127.0.0.1:8000. Data is stored in `.localdata/app.db`, which Git ignores.

## Deploy to Railway

1. Push to GitHub.
2. In Railway, create a project with **Deploy from GitHub Repo** and pick this repository.
3. Attach a **Volume** to the service with mount path `/data`. Do this before the first deploy. The app refuses to start on Railway without it.
4. Deploy. Railpack detects Python and starts Gunicorn on its own. Leave the custom build and start commands empty, and set no environment variables.
5. Under **Settings → Networking**, click **Generate Domain** (or attach a custom domain).
6. Check that `/` loads and `/health` returns `{"status": "ok"}`.

If something fails, check the deploy logs. The build log should say Python was detected.

## Layout

| Path | Purpose |
| --- | --- |
| `main.py` | Flask app (`main:app`) and routes |
| `db.py` | SQLite connection and schema; stores data on the `/data` volume |
| `templates/` | Jinja templates; `base.html` holds the shared layout |
| `static/` | CSS and small JS files |

The app has no login, so anyone with the link can view or change its data. Use made-up demo data only.
