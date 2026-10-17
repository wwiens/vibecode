# Netflix — a world of stories

A polished Netflix-inspired classroom streaming app, built with **Python 3.12, Flask, Gunicorn, SQLite, and vanilla JavaScript**. No frontend build, API keys, registration, or external database is required.

## What works

- Cinematic featured-title carousel, responsive artwork collections, ranked Top 10, and movie/TV browsing.
- Server-side search by title, actor, and genre; genre filtering and a surprise-me picker.
- Detailed title dialogs with cast, recommendations, likes, season selection, and demo episode navigation.
- Create, rename, customize, switch, and delete up to five profiles; separate favorites, watchlists, and viewing history.
- Kids profiles with family-only catalogs enforced by Python routes as well as the interface. Kids mode is a classroom demonstration, not a password-protected parental control.
- Add/remove My List entries, personalized picks based on likes, and Continue Watching with removal.
- Working HTML5 player with seeking, volume, fullscreen, playback speeds, demo credit captions, per-episode progress, and resume. Autoplay after pressing Play can be disabled per profile.
- SQLite persistence across restarts and redeployments, a database-aware `/health` route, input validation, and keyboard-accessible dialogs. Press `/` to search and Escape to dismiss a dialog.

The catalog is a fixed demo collection, not a live availability or popularity feed. **Every commercial catalog title plays the bundled open Sintel trailer**, and episode navigation is simulated. This is clearly labeled in the player and title dialogs. There is no commercial movie streaming, subscription billing, DRM, or account authentication.

Use **fictional classroom profile names only**. This is a shared demo with no authentication: **anyone with the link can view, edit, or delete demo profiles and records**. A selected profile is a browsing preference, not a security boundary. Do not collect sensitive or personal information.

## Run locally

From the repository root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
gunicorn --bind 127.0.0.1:8000 main:app
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The first startup creates three fictional profiles and `.localdata/app.db`. The data directory and database files are ignored by Git. Choose a profile in the upper-right corner; save a title to My List or play a preview to create a record. Stop Gunicorn with Ctrl+C, run the same command again, and confirm the list and progress remain.

For development only, `python main.py` also works, with debug disabled. Production uses Gunicorn. `app.py` is a small compatibility shim for an older service already configured with `app:app`; new deployments use the canonical `main:app` entrypoint.

## Deploy from GitHub to Railway

1. Push the completed project to a GitHub repository.
2. Create a Railway project and select **Deploy from GitHub Repo**, then select the repository.
3. **Before the first deployment, attach a Railway Volume to the web service with mount path exactly `/data`.** The first deployment may start when the service is created; attach the volume before saving anything worth preserving. The app deliberately refuses to start on Railway without the volume.
4. Click **Deploy**, or apply pending project changes. Railpack detects Python 3.12, Flask, and Gunicorn and automatically starts `main:app` on Railway's assigned port. No custom build/start command, manually entered environment variables, Dockerfile, Procfile, or Railway config file is needed. If reusing a service with a previously overridden start command, restore its automatic start-command setting in the Railway UI.
5. In the service's **Settings → Networking**, select **Generate Domain**.
6. Open the public URL, add a title to My List, create a fictional profile, and play part of a preview.
7. Redeploy the same GitHub-backed service and verify that the profile, list, and playback progress are still present.
8. If deployment fails, check the Railway deployment logs. A missing-volume error means the web service needs the `/data` volume attached before restart.

Attaching a volume and generating a public domain are **Railway UI actions**; Python source code cannot perform them automatically. Do not add manual environment variables: Railway supplies `PORT` and `RAILWAY_VOLUME_MOUNT_PATH`. All persistent records live in `RAILWAY_VOLUME_MOUNT_PATH/app.db`, or `.localdata/app.db` locally. Schema initialization happens idempotently at app runtime, never as a build or pre-deploy step.

Use **one Railway replica** with its attached volume. SQLite is for this small demo, not horizontally scaled streaming traffic. Volumes survive redeployments but are not backups; expect brief deployment downtime.

## Verification

```bash
python -m unittest discover -s tests -v
```

The standard-library test suite uses isolated temporary databases and checks the homepage, catalog artwork, video byte-range delivery, search/filtering, profile CRUD and limits, profile isolation, watchlists/likes, progress validation and episode resume records, Kids restrictions, persistence in a fresh Python process, and the missing-Railway-volume startup error.

## Source map

- `main.py`: Flask routes, validation, runtime SQLite setup, and volume handling.
- `catalog.py`: the curated film/series metadata and local asset paths.
- `templates/index.html`: accessible page structure and dialogs.
- `static/style.css`, `static/app.js`: responsive design and browser interactions.
- `static/images/`: bundled catalog artwork; the app needs no artwork API account.
- `static/video/`: locally served open trailer and demo credit captions.
- `tests/test_app.py`: isolated behavior and deployment-contract checks.

## Credits

An independent educational interface; not affiliated with or endorsed by Netflix. Netflix and film/series titles and marks belong to their respective owners. Film/series artwork is from [The Movie Database](https://www.themoviedb.org/); the Dune hero still is from [IMAX](https://www.imax.com/movie/dune-part-two). Artwork is used for the classroom demonstration, and no license to commercially redistribute third-party artwork is implied.

Bundled video: **Sintel trailer**, © Blender Foundation, from [Blender Studio](https://studio.blender.org/films/sintel/), licensed under [Creative Commons Attribution 3.0](https://creativecommons.org/licenses/by/3.0/). Unmodified trailer source: [W3C-hosted MP4](https://media.w3.org/2010/05/sintel/trailer_hd.mp4). The optional caption track contains demo credit labels, not a full dialogue transcription. DM Sans and Manrope fonts load from Google Fonts with system-font fallbacks; catalog art and playback are bundled locally.
