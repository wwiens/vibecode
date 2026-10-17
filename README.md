# Netflix — a world of stories

A polished Netflix-inspired classroom streaming app, built with **Python 3.12, Flask, Gunicorn, SQLite, and vanilla JavaScript**. No frontend build, API keys, registration, or external database is required.

## What works

- Cinematic featured-title carousel, responsive artwork collections, ranked Top 10, and movie/TV browsing.
- Server-side search by title, actor, and genre; genre filtering and a surprise-me picker.
- Detailed title dialogs with cast, recommendations, likes, season selection, and demo episode navigation.
- Create, rename, customize, switch, and delete up to five profiles; separate favorites, watchlists, and viewing history.
- Kids profiles with family-only catalogs enforced by Python routes as well as the interface. Kids mode is a classroom demonstration, not a password-protected parental control.
- Add/remove My List entries, personalized picks based on likes, and Continue Watching with removal.
- Working HTML5 player with seeking, volume, fullscreen, playback speeds, per-episode progress, and resume. Uploaded titles play their actual stored video; built-in demo titles use the Sintel trailer. Autoplay after pressing Play can be disabled per profile.
- A complete video Library: upload movies and real series episodes, pause/resume interrupted transfers, add or replace cover art, edit details, replace videos, download originals, remove episodes, and delete titles with their files.
- SQLite persistence across restarts and redeployments, a database-aware `/health` route, input validation, and keyboard-accessible dialogs. Press `/` to search and Escape to dismiss a dialog.

The built-in catalog is a fixed demo collection, not a live availability or popularity feed. **Built-in commercial titles play the bundled open Sintel trailer** and use simulated episodes. **Your uploaded library plays the actual uploaded videos and real episode files.** The interface distinguishes these sources. There is no subscription billing, DRM, transcoding, or account authentication.

Use **fictional classroom profile names only**. This is a shared demo with no authentication: **anyone with the link can view, upload, download, edit, or delete shared videos, profiles, and records**. A selected profile is a browsing preference, not a security boundary. Upload only non-sensitive classroom videos that you have permission to share. Kids mode is a UI/content filter, not authentication or an upload-management security boundary.

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

## Video storage and uploads

Open **Library** in the header, or visit `/#uploads` on an adult profile.

1. Click **Upload video**, then select or drop an MP4, M4V, or WebM file. The browser checks that it can read the video and its duration.
2. Choose movie or series; enter a title, genres, rating, description, and optional creator/cast and cover image. Series uploads also include a season, episode number, and optional episode title. The first episode may start at any valid season/episode number.
3. Start the upload. The progress bar reports bytes sent. **Pause upload** retains completed chunks on the volume; **Resume** continues at the offset confirmed by the server. After a refresh, browser restart, or service restart, select the same file to resume. File size and a SHA-256 fingerprint of the first 64 KiB prevent accidentally selecting a different file.
4. When all chunks arrive, the server validates the container and video track, then publishes the title to the catalog. A failed validation keeps the pending upload visible so it can be canceled, releasing its storage.
5. Uploaded titles appear in **From your library**, normal movie/TV browsing, search, My List, and Continue Watching. Their player reads the uploaded file, with HTTP byte ranges for seeking.
6. Use **Edit details** to rename a title, change metadata, update or remove its cover, or adjust its family setting. Family titles require a G/PG/TV-Y/TV-Y7/TV-G rating.
7. For series, **Add episode** uploads another real file; expand **Manage episodes** to play, download, replace, or remove individual episodes. The last episode is removed by deleting the title. Movies have one replaceable video.
8. Replacing a video resets viewing progress for that movie/episode while preserving the title and watchlists. Deleting a title removes all associated files, unfinished uploads, likes, watchlists, and progress. Deletion requires a second explicit click in the interface and is permanent.

Videos are stored as files, not SQLite blobs. **All upload data lives inside the persistent data directory:**

```text
/data/                        # .localdata/ when running locally
├── app.db                    # Profiles, titles, episodes, upload offsets, lists, progress
└── media/
    ├── pending/              # Resumable .part files
    ├── videos/               # Validated, published original files
    └── posters/              # Uploaded JPEG, PNG, or WebP covers
```

Defaults are **2 GiB per video**, **5 MiB per cover**, **8 GiB total library reservations**, up to **20 unfinished uploads**, and **24 hours maximum video duration**. The available-space display also respects the actual volume’s free space and leaves a 64 MiB reserve. A smaller Railway volume therefore has a smaller effective capacity. Pending uploads reserve their full declared file size; canceling them releases the reservation and partial file. These limits are constants in `media_store.py`, not required environment variables.

The client sends 2 MiB chunks; the API accepts chunks up to 8 MiB and verifies a SHA-256 checksum for each. SQLite transactions serialize competing chunk writes, and a resumed write truncates any uncommitted tail left by an interrupted process. Server offsets are authoritative. A finalize request is idempotent, so a lost response can be retried safely. An interrupted final rename can be recovered on retry. Deletions are recorded in a persistent cleanup queue before unlinking files; cleanup retries at startup and on later library/storage requests if the filesystem was temporarily unavailable.

Container validation checks MP4 structure and a video track, or WebM EBML structure and a video track/cluster. It does not decode every frame or transcode codecs. Use **H.264/AAC in MP4** for broad browser compatibility, or a browser-supported WebM codec. Unsupported codecs can still produce a browser playback error. Original files are served with their fixed detected media type and `nosniff`; submitted filenames never become filesystem paths. Same-origin checks apply to library mutations. HTTPS or localhost is required by the browser’s checksum API.

The automatically discovered `gunicorn.conf.py` uses **one process and four threads** so a video stream can run alongside uploads and other requests. It does not change Railpack’s startup command or bind address/port. Keep one Railway replica. This is a volume-backed classroom library, not a CDN or adaptive-bitrate streaming service.

### Media API

All APIs accept `?profile=<id>` (default 1). Management requires a non-Kids profile; profile selection is not authentication. JSON errors use an `error` field. File bytes never appear in JSON or SQLite.

| Method and path | Purpose |
| --- | --- |
| `GET /api/library` | Titles, real episodes, unfinished uploads, storage usage and limits |
| `POST /api/uploads` | Create a persistent upload session from JSON metadata |
| `GET /api/uploads/<id>` | Read saved offset, status, fingerprint, and final IDs |
| `PATCH /api/uploads/<id>` | Append binary chunk with `Upload-Offset` and `X-Chunk-SHA256` headers |
| `POST /api/uploads/<id>/complete` | Validate and publish a fully uploaded video (safe to retry) |
| `DELETE /api/uploads/<id>` | Cancel an unfinished upload and reclaim its partial file |
| `PATCH /api/library/<title_id>` | Edit title, year, genres, rating, description, cast, family flag |
| `POST /api/library/<title_id>/poster` | Upload a cover as multipart form field `file` |
| `DELETE /api/library/<title_id>/poster` | Remove the cover |
| `DELETE /api/library/<title_id>/videos/<video_id>` | Remove a series episode (except the last one) |
| `DELETE /api/library/<title_id>` | Delete the title and all its files/records |
| `GET/HEAD /media/videos/<video_id>` | Conditional/range-aware playback; add `download=1` to download |
| `GET /media/posters/<title_id>` | Serve uploaded cover art |

Create-session JSON requires `filename`, `size`, `fingerprint` (lowercase SHA-256 of the first 65,536 bytes, or whole file if shorter), and `duration` (browser-read seconds). For a new title, also supply `title`; optional fields include `type` (`movie`/`series`), `year`, `genres` (1–6 strings), `rating`, `description`, `cast`, and `family`. For an existing title, supply `title_id`. Series accept `season` (1–100), `episode` (1–999), and `episode_title`. Set `replace: true` explicitly to replace an existing movie/episode. Every chunk’s checksum is SHA-256 of exactly that chunk. A stale offset returns 409 with the server’s `offset`; re-read session status before retrying. Storage shortages return 507; invalid checksums return 422; size limits return 413 or a validation error.

## Deploy from GitHub to Railway

1. Push the completed project to a GitHub repository.
2. Create a Railway project and select **Deploy from GitHub Repo**, then select the repository.
3. **Before the first deployment, attach a Railway Volume to the web service with mount path exactly `/data`.** The first deployment may start when the service is created; attach the volume before saving anything worth preserving. The app deliberately refuses to start on Railway without the volume.
4. Click **Deploy**, or apply pending project changes. Railpack detects Python 3.12, Flask, and Gunicorn and automatically starts `main:app` on Railway's assigned port. No custom build/start command, manually entered environment variables, Dockerfile, Procfile, or Railway config file is needed. If reusing a service with a previously overridden start command, restore its automatic start-command setting in the Railway UI.
5. In the service's **Settings → Networking**, select **Generate Domain**.
6. Open the public URL, create a fictional profile, and upload a small MP4 through **Library**. Play it, seek within the video, and add it to My List.
7. Redeploy the same GitHub-backed service and verify that the uploaded video still plays and that its details, profile, list, and viewing progress remain present.
8. If deployment fails, check the Railway deployment logs. A missing-volume error means the web service needs the `/data` volume attached before restart.

Attaching a volume and generating a public domain are **Railway UI actions**; Python source code cannot perform them automatically. Do not add manual environment variables: Railway supplies `PORT` and `RAILWAY_VOLUME_MOUNT_PATH`. All persistent records live in `RAILWAY_VOLUME_MOUNT_PATH/app.db`, or `.localdata/app.db` locally. Schema initialization happens idempotently at app runtime, never as a build or pre-deploy step.

Use **one Railway replica** with its attached volume. SQLite is for this small demo, not horizontally scaled streaming traffic. Volumes survive redeployments but are not backups; expect brief deployment downtime.

## Verification

```bash
python -m unittest discover -s tests -v
```

The standard-library test suite uses isolated temporary databases and media directories and checks the homepage, catalog artwork, video byte-range delivery, search/filtering, profile CRUD and limits, profile isolation, watchlists/likes, progress validation and episode resume records, Kids restrictions, persistence in a fresh Python process, the missing-Railway-volume startup error, actual MP4 uploads and HTTP byte ranges, resume in a fresh Python process, competing chunk retries, checksums/offsets, file spoofing, storage reservations, poster replacement, real series episodes, replacement progress resets, and complete file cleanup.

## Source map

- `main.py`: Flask routes, validation, runtime SQLite setup, and volume handling.
- `catalog.py`: the curated film/series metadata and local asset paths.
- `media_store.py`: upload sessions, storage limits, validation, library metadata, and media serving.
- `gunicorn.conf.py`: automatically discovered single-process threaded media serving.
- `templates/index.html`: accessible page structure and dialogs.
- `static/style.css`, `static/app.js`, `static/uploads.js`: responsive design, playback, and the upload manager.
- `static/images/`: bundled catalog artwork; the app needs no artwork API account.
- `static/video/`: locally served open trailer and demo credit captions.
- `tests/test_app.py`, `tests/test_media.py`: isolated application, media lifecycle, and deployment-contract checks.

## Credits

An independent educational interface; not affiliated with or endorsed by Netflix. Netflix and film/series titles and marks belong to their respective owners. Film/series artwork is from [The Movie Database](https://www.themoviedb.org/); the Dune hero still is from [IMAX](https://www.imax.com/movie/dune-part-two). Artwork is used for the classroom demonstration, and no license to commercially redistribute third-party artwork is implied.

Bundled video: **Sintel trailer**, © Blender Foundation, from [Blender Studio](https://studio.blender.org/films/sintel/), licensed under [Creative Commons Attribution 3.0](https://creativecommons.org/licenses/by/3.0/). Unmodified trailer source: [W3C-hosted MP4](https://media.w3.org/2010/05/sintel/trailer_hd.mp4). The optional caption track contains demo credit labels, not a full dialogue transcription. DM Sans and Manrope fonts load from Google Fonts with system-font fallbacks; catalog art and playback are bundled locally.
