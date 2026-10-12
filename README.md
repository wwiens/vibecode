# Vibe Coding

A tiny Flask app about vibe coding. Its real job is to prove the pipeline works: push to GitHub, and Railway deploys automatically.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py               # http://localhost:8000
```

To run it the same way Railway does:

```bash
PORT=8000 gunicorn app:app --bind 0.0.0.0:$PORT
```

## Deployment (Railway)

- Railway detects Python from `requirements.txt` and uses the version in `.python-version`.
- `railway.json` sets the start command (gunicorn) and the health check (`/health`).
- Railway injects a `PORT` environment variable, and the app binds to `0.0.0.0:$PORT`. Don't hardcode a port.
- Every push to `main` triggers a new deploy.

## Endpoints

| Path        | What it does                       |
|-------------|------------------------------------|
| `/`         | The vibe coding page               |
| `/api/vibe` | Returns a random vibe as JSON      |
| `/health`   | Health check used by Railway       |
