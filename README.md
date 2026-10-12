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

Live at https://vibecode-production-652a.up.railway.app

- Every push to `main` on GitHub triggers a new deploy. No CLI step needed.
- Railway detects Python from `requirements.txt` and uses the version in `.python-version`.
- Railway injects a `PORT` environment variable, and gunicorn binds to `0.0.0.0:$PORT`. Don't hardcode a port.
- Service settings (start command, `/health` check, restart policy, domain) are stored on the Railway service and described in [.railway/railway.py](.railway/railway.py). That file is **not** read on deploy. If you change it, push the change to Railway yourself:

  ```bash
  pip install railway-sdk
  railway config plan    # preview
  railway config apply   # apply
  ```

## Endpoints

| Path        | What it does                       |
|-------------|------------------------------------|
| `/`         | The vibe coding page               |
| `/api/vibe` | Returns a random vibe as JSON      |
| `/health`   | Health check used by Railway       |
