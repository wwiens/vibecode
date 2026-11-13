# Project notes for Claude

This repo is used for a live vibe-coding demo. It deploys to Railway from GitHub on every push to `main`.

- Follow `RAILWAY_PYTHON_APP_RULES.md` for every change.
- The deploy setup already works. Keep `main.py` exporting `app`, keep `requirements.txt` and `.python-version`, and do not add a Dockerfile, Procfile or Railway config file.
- Store data through `db.py`. Add tables to `SCHEMA` with `CREATE TABLE IF NOT EXISTS`, and use `?` placeholders in SQL.
- Keep `GET /health` working, because Railway's health check uses it.
- Build pages from `templates/base.html` and `static/style.css`. Always link static files with `url_for('static', ...)`, which adds a cache-busting `?v=` hash. Cloudflare caches static files for hours.
- Before pushing, run the app locally with `gunicorn --bind 127.0.0.1:8000 main:app` and check it.
