"""Persistent video library and resumable, bounded uploads. No external services."""
import errno
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
from uuid import uuid4
from urllib.parse import urlsplit
from datetime import datetime, timezone

from flask import Blueprint, abort, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

CHUNK_BYTES = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 2 * 1024 ** 3
MAX_POSTER_BYTES = 5 * 1024 ** 2
LIBRARY_BYTES = 8 * 1024 ** 3
DISK_RESERVE_BYTES = 64 * 1024 ** 2
VIDEO_TYPES = {'.mp4': 'video/mp4', '.m4v': 'video/mp4', '.webm': 'video/webm'}
RATINGS = ('G', 'PG', 'PG-13', 'R', 'TV-Y', 'TV-Y7', 'TV-G', 'TV-14', 'TV-MA', 'NR')
FAMILY_RATINGS = ('G', 'PG', 'TV-Y', 'TV-Y7', 'TV-G')

class MediaError(Exception):
    def __init__(self, message, status=400, **extra):
        self.status, self.extra = status, extra
        super().__init__(message)

def initialize_schema(db):
    db.executescript('''
        CREATE TABLE IF NOT EXISTS media_titles (
            id TEXT PRIMARY KEY, title TEXT NOT NULL, year INTEGER NOT NULL,
            type TEXT NOT NULL CHECK(type IN ('movie','series')), genres TEXT NOT NULL,
            rating TEXT NOT NULL, description TEXT NOT NULL, cast TEXT NOT NULL,
            family INTEGER NOT NULL DEFAULT 0, poster_name TEXT, poster_mime TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS media_videos (
            id TEXT PRIMARY KEY, title_id TEXT NOT NULL REFERENCES media_titles(id) ON DELETE CASCADE,
            season INTEGER NOT NULL, episode INTEGER NOT NULL, episode_title TEXT NOT NULL,
            file_name TEXT NOT NULL UNIQUE, original_name TEXT NOT NULL, size INTEGER NOT NULL,
            mime TEXT NOT NULL, duration REAL NOT NULL,
            UNIQUE(title_id, season, episode)
        );
        CREATE TABLE IF NOT EXISTS upload_sessions (
            id TEXT PRIMARY KEY, metadata TEXT NOT NULL, original_name TEXT NOT NULL,
            size INTEGER NOT NULL, offset INTEGER NOT NULL DEFAULT 0,
            fingerprint TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'uploading',
            title_id TEXT, video_id TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS media_garbage (
            folder TEXT NOT NULL, file_name TEXT NOT NULL, PRIMARY KEY(folder,file_name)
        );
        CREATE INDEX IF NOT EXISTS media_videos_title ON media_videos(title_id);
    ''')

def duration_label(seconds):
    seconds = round(seconds)
    if seconds >= 3600:
        return f'{seconds // 3600}h {(seconds % 3600) // 60}m'
    return f'{seconds // 60}m' if seconds >= 60 else f'{seconds}s'

def uploaded_titles(db):
    videos = {}
    for row in db.execute('SELECT * FROM media_videos ORDER BY season,episode'):
        value = dict(row)
        value['key'] = (value['season'] - 1) * 1000 + value['episode']
        value['video_url'] = f"/media/videos/{value['id']}"
        value['download_url'] = value['video_url'] + '?download=1'
        value.pop('file_name')
        videos.setdefault(value['title_id'], []).append(value)
    result = []
    for row in db.execute('SELECT * FROM media_titles ORDER BY created_at DESC, rowid DESC'):
        item = dict(row)
        episodes = videos.get(item['id'], [])
        if not episodes:
            continue
        poster = f"/media/posters/{item['id']}?v={item['poster_name']}" if item['poster_name'] else '/static/images/upload-placeholder.svg'
        item.update(genres=json.loads(item['genres']), family=bool(item['family']), uploaded=True,
                    image=poster, backdrop=poster, match=100, episodes=episodes,
                    seasons=max(e['season'] for e in episodes),
                    duration=duration_label(episodes[0]['duration']) if item['type'] == 'movie' else f"{len(episodes)} episodes",
                    video_url=episodes[0]['video_url'], total_bytes=sum(e['size'] for e in episodes))
        item.pop('poster_name')
        item.pop('poster_mime')
        result.append(item)
    return result

def mp4_boxes(handle, start, end):
    count = 0
    while start < end:
        count += 1
        if count > 10000 or end - start < 8:
            raise MediaError('The MP4 container is incomplete or invalid.')
        handle.seek(start)
        size, kind = struct.unpack('>I4s', handle.read(8))
        header = 8
        if size == 1:
            if end - start < 16:
                raise MediaError('The MP4 container is incomplete.')
            size, header = struct.unpack('>Q', handle.read(8))[0], 16
        elif size == 0:
            size = end - start
        if size < header or start + size > end:
            raise MediaError('The MP4 container is truncated. Please upload the complete file.')
        yield kind, start + header, start + size
        start += size

def ebml_elements(handle, start, end):
    """Read EBML element boundaries, skipping large video clusters without loading them."""
    count = 0
    while start < end:
        count += 1
        if count > 100000:
            raise MediaError('The WebM container has too many elements.')
        handle.seek(start)
        first = handle.read(1)
        if not first or first[0] == 0:
            raise MediaError('The WebM container is invalid.')
        id_len = 9 - first[0].bit_length()
        if id_len > 4:
            raise MediaError('The WebM element identifier is invalid.')
        identifier = first + handle.read(id_len - 1)
        first = handle.read(1)
        if not first or first[0] == 0:
            raise MediaError('The WebM element size is invalid.')
        size_len = 9 - first[0].bit_length()
        rest = handle.read(size_len - 1)
        if len(rest) != size_len - 1:
            raise MediaError('The WebM file is truncated.')
        size = int.from_bytes(bytes([first[0] & (0xff >> size_len)]) + rest, 'big')
        payload = handle.tell()
        finish = end if size == (1 << (7 * size_len)) - 1 else payload + size
        if finish > end or payload > finish:
            raise MediaError('The WebM file is truncated.')
        yield int.from_bytes(identifier, 'big'), payload, finish
        start = finish

def inspect_video(path, extension, fallback_duration):
    """Check container structure and a video track; codecs are decoded by the browser."""
    size = path.stat().st_size
    if size < 64:
        raise MediaError('This is not a complete video file.')
    duration = 0
    with path.open('rb') as handle:
        if extension in ('.mp4', '.m4v'):
            kinds, video = set(), False
            for kind, start, end in mp4_boxes(handle, 0, size):
                kinds.add(kind)
                if kind == b'ftyp':
                    handle.seek(start)
                    if end - start < 8 or handle.read(4) == b'qt  ':
                        raise MediaError('Use an MP4 video, rather than a QuickTime MOV file.')
                if kind == b'moov':
                    for child, a, b in mp4_boxes(handle, start, end):
                        if child == b'mvhd':
                            handle.seek(a)
                            data = handle.read(min(32, b-a))
                            offset = 20 if data and data[0] == 1 else 12
                            width = 8 if data and data[0] == 1 else 4
                            if len(data) >= offset + 4 + width:
                                scale = int.from_bytes(data[offset:offset+4], 'big')
                                ticks = int.from_bytes(data[offset+4:offset+4+width], 'big')
                                duration = ticks / scale if scale else 0
                        if child == b'trak':
                            for track, c, d in mp4_boxes(handle, a, b):
                                if track == b'mdia':
                                    for field, e, f in mp4_boxes(handle, c, d):
                                        if field == b'hdlr' and f-e >= 12:
                                            handle.seek(e+8)
                                            video = video or handle.read(4) == b'vide'
            if not {b'ftyp', b'moov', b'mdat'} <= kinds or not video:
                raise MediaError('The file must be a complete MP4 containing a video track.')
        else:
            roots = list(ebml_elements(handle, 0, size))
            if not roots or roots[0][0] != 0x1A45DFA3:
                raise MediaError('The file is not a WebM video.')
            webm, video, cluster = False, False, False
            scale, ticks = 1000000, 0
            for kind, a, b in ebml_elements(handle, roots[0][1], roots[0][2]):
                if kind == 0x4282:
                    handle.seek(a)
                    webm = b-a == 4 and handle.read(4) == b'webm'
            for kind, a, b in roots:
                if kind != 0x18538067:
                    continue
                for child, c, d in ebml_elements(handle, a, b):
                    if child == 0x1F43B675:
                        cluster = True
                    elif child == 0x1549A966:
                        for field, e, f in ebml_elements(handle, c, d):
                            if field == 0x2AD7B1 and f-e <= 8:
                                handle.seek(e); scale = int.from_bytes(handle.read(f-e), 'big')
                            elif field == 0x4489 and f-e in (4, 8):
                                handle.seek(e); ticks = struct.unpack('>f' if f-e == 4 else '>d', handle.read(f-e))[0]
                    elif child == 0x1654AE6B:
                        for entry, e, f in ebml_elements(handle, c, d):
                            if entry == 0xAE:
                                for field, g, h in ebml_elements(handle, e, f):
                                    if field == 0x83 and h-g <= 8:
                                        handle.seek(g); video = video or int.from_bytes(handle.read(h-g), 'big') == 1
            if not webm or not video or not cluster:
                raise MediaError('The file must be a WebM container with a video track and video data.')
            duration = ticks * scale / 1e9
    duration = duration if math.isfinite(duration) and 0 < duration <= 86400 else fallback_duration
    if not math.isfinite(duration) or not 0 < duration <= 86400:
        raise MediaError('Could not read the duration. Choose a playable video up to 24 hours long.')
    return duration

def poster_type(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n') and data[12:16] == b'IHDR' and b'IEND' in data[-16:]:
        width, height = struct.unpack('>II', data[16:24]) if len(data) >= 24 else (0, 0)
        if 0 < width <= 12000 and 0 < height <= 12000:
            return '.png', 'image/png'
    if data.startswith(b'\xff\xd8\xff') and data.endswith(b'\xff\xd9') and (b'\xff\xc0' in data or b'\xff\xc2' in data):
        return '.jpg', 'image/jpeg'
    if len(data) > 20 and data[:4] == b'RIFF' and data[8:12] == b'WEBP' and data[12:16] in (b'VP8 ', b'VP8L', b'VP8X') and int.from_bytes(data[4:8], 'little') + 8 == len(data):
        return '.webp', 'image/webp'
    raise MediaError('Choose a valid JPEG, PNG, or WebP image. SVG and renamed files are not supported.')

def register_media(app, database, data_root, get_profile, integer, body):
    bp = Blueprint('media', __name__)

    @app.errorhandler(MediaError)
    def media_error(error):
        return jsonify(error=str(error), **error.extra), error.status

    @bp.before_request
    def same_origin():
        if request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('Origin')
            if origin and (urlsplit(origin).scheme not in ('http','https') or urlsplit(origin).netloc != request.host):
                raise MediaError('Please upload from this website, rather than another origin.', 403)

    def directories():
        root = data_root() / 'media'
        for name in ('videos', 'posters', 'pending'):
            (root / name).mkdir(parents=True, exist_ok=True)
        return root

    def queue_removal(db, path):
        relative = path.relative_to(directories())
        db.execute('INSERT OR IGNORE INTO media_garbage(folder,file_name) VALUES (?,?)',relative.parts)

    def collect_garbage(db):
        # Persist deletion intent before touching files; failed cleanup is retried next time.
        root = directories()
        for row in db.execute('SELECT folder,file_name FROM media_garbage').fetchall():
            try:
                (root/row['folder']/row['file_name']).unlink(missing_ok=True)
            except OSError:
                app.logger.warning('Deferred cleanup of media file %s',row['file_name'])
            else:
                db.execute('DELETE FROM media_garbage WHERE folder=? AND file_name=?',tuple(row))

    def manager(db):
        profile = get_profile(db)
        if profile['kids']:
            raise MediaError('Switch to an adult profile to manage the shared video library.', 403)
        return profile

    def session_row(db, id):
        row = db.execute('SELECT * FROM upload_sessions WHERE id=?', (id,)).fetchone()
        if not row:
            raise MediaError('This upload no longer exists. Start a new upload.', 404)
        return dict(row)

    def public_session(row):
        result = {k: row[k] for k in ('id','original_name','size','offset','fingerprint','status','title_id','video_id','created_at')}
        metadata = json.loads(row['metadata'])
        result.update(title=metadata['title'], season=metadata['season'], episode=metadata['episode'])
        return result

    def capacity(db):
        collect_garbage(db)
        root = directories()
        used = db.execute('SELECT COALESCE(SUM(size),0) FROM media_videos').fetchone()[0]
        used += sum(p.stat().st_size for p in (root / 'posters').iterdir() if p.is_file())
        reserved, received = db.execute("SELECT COALESCE(SUM(size),0),COALESCE(SUM(offset),0) FROM upload_sessions WHERE status='uploading'").fetchone()
        free = shutil.disk_usage(root).free
        available = max(0, min(LIBRARY_BYTES-used-reserved, free-DISK_RESERVE_BYTES-(reserved-received)))
        return dict(used_bytes=used+received, reserved_bytes=reserved-received, available_bytes=available,
                    limit_bytes=LIBRARY_BYTES, disk_free_bytes=max(0, free-DISK_RESERVE_BYTES),
                    max_video_bytes=MAX_VIDEO_BYTES, max_poster_bytes=MAX_POSTER_BYTES, chunk_bytes=CHUNK_BYTES)

    def title_metadata(data, existing=None):
        def string(key, maximum, default=''):
            value = data.get(key, existing[key] if existing else default)
            if not isinstance(value, str) or len(value.strip()) > maximum:
                raise MediaError(f'{key.title()} must be text up to {maximum} characters.')
            return value.strip()
        name = string('title', 120)
        if not name:
            raise MediaError('Give your video a title.')
        kind = data.get('type', existing['type'] if existing else 'movie')
        if kind not in ('movie', 'series') or (existing and kind != existing['type']):
            raise MediaError('Choose movie or series. An existing title’s type cannot be changed.')
        genres = data.get('genres', json.loads(existing['genres']) if existing else ['Independent'])
        if not isinstance(genres, list) or not 1 <= len(genres) <= 6 or any(not isinstance(g,str) or not 1 <= len(g.strip()) <= 30 for g in genres):
            raise MediaError('Choose one to six genres, each up to 30 characters.')
        rating = data.get('rating', existing['rating'] if existing else 'NR')
        family = data.get('family', bool(existing['family']) if existing else False)
        if rating not in RATINGS or not isinstance(family, bool):
            raise MediaError('Choose a valid rating and family setting.')
        if family and rating not in FAMILY_RATINGS:
            raise MediaError('Family titles need a G, PG, TV-Y, TV-Y7, or TV-G rating.')
        return dict(title=name, type=kind, genres=list(dict.fromkeys(g.strip() for g in genres)),
                    year=integer(data.get('year', existing['year'] if existing else datetime.now(timezone.utc).year),'Year',1888,2100),
                    rating=rating, family=family, description=string('description',3000), cast=string('cast',500))

    @bp.get('/api/library')
    def library():
        with database() as db:
            manager(db)
            return jsonify(titles=uploaded_titles(db), storage=capacity(db),
                           uploads=[public_session(dict(r)) for r in db.execute("SELECT * FROM upload_sessions WHERE status='uploading' ORDER BY created_at DESC")])

    @bp.post('/api/uploads')
    def begin_upload():
        data = body()
        filename = data.get('filename')
        if not isinstance(filename,str) or not filename.strip() or len(filename) > 255:
            raise MediaError('Choose a video file with a filename up to 255 characters.')
        extension = Path(filename).suffix.lower()
        filename = (secure_filename(Path(filename).stem) or 'video')[:180] + extension
        if extension not in VIDEO_TYPES:
            raise MediaError('Supported videos are MP4, M4V, and WebM. Use H.264/AAC for the widest MP4 support.')
        size = integer(data.get('size'), 'File size',64,MAX_VIDEO_BYTES)
        fingerprint = data.get('fingerprint','')
        if not isinstance(fingerprint,str) or not re.fullmatch('[a-f0-9]{64}',fingerprint):
            raise MediaError('The video fingerprint is missing. Select the file again.')
        try:
            duration = float(data.get('duration',0))
            if not math.isfinite(duration) or not 0 < duration <= 86400:
                raise ValueError
        except (ValueError,TypeError):
            raise MediaError('Choose a browser-playable video up to 24 hours long.')
        pending = directories() / 'pending'
        id = uuid4().hex
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            manager(db)
            target = data.get('title_id')
            existing = db.execute('SELECT * FROM media_titles WHERE id=?',(target,)).fetchone() if isinstance(target,str) else None
            if target and not existing:
                raise MediaError('The selected title no longer exists.',404)
            metadata = title_metadata(dict(existing) | {'genres':json.loads(existing['genres']), 'family':bool(existing['family'])} if existing else data)
            season = integer(data.get('season',1),'Season',1,100)
            episode = integer(data.get('episode',1),'Episode',1,999)
            if metadata['type'] == 'movie' and (season,episode) != (1,1):
                raise MediaError('Movies have one video. Choose a series to add episodes.')
            replace = data.get('replace',False)
            if not isinstance(replace,bool):
                raise MediaError('Replace must be true or false.')
            if existing and db.execute('SELECT 1 FROM media_videos WHERE title_id=? AND season=? AND episode=?',(target,season,episode)).fetchone() and not replace:
                raise MediaError('A video already exists here. Choose Replace video to overwrite it.',409)
            if db.execute("SELECT COUNT(*) FROM upload_sessions WHERE status='uploading'").fetchone()[0] >= 20:
                raise MediaError('Finish or cancel an unfinished upload before starting another.',409)
            if size > capacity(db)['available_bytes']:
                raise MediaError('There is not enough available storage. Remove a video or cancel an unfinished upload.',507)
            episode_title = data.get('episode_title','')
            if not isinstance(episode_title,str) or len(episode_title.strip()) > 160:
                raise MediaError('Episode titles may contain up to 160 characters.')
            metadata.update(target=target, extension=extension, duration=duration, season=season,
                            episode=episode, episode_title=episode_title.strip(), replace=replace)
            path = pending / f'{id}.part'
            path.touch(exist_ok=False)
            try:
                db.execute('INSERT INTO upload_sessions(id,metadata,original_name,size,fingerprint) VALUES (?,?,?,?,?)',
                           (id,json.dumps(metadata),filename,size,fingerprint))
            except Exception:
                path.unlink(missing_ok=True)
                raise
            row = session_row(db,id)
        return jsonify(upload=public_session(row),chunk_bytes=CHUNK_BYTES),201

    @bp.get('/api/uploads/<id>')
    def upload_status(id):
        with database() as db:
            manager(db)
            return jsonify(upload=public_session(session_row(db,id)),chunk_bytes=CHUNK_BYTES)

    @bp.patch('/api/uploads/<id>')
    def append_chunk(id):
        if request.mimetype != 'application/octet-stream':
            raise MediaError('Upload chunks must use application/octet-stream.',415)
        request.max_content_length = CHUNK_BYTES
        payload = request.get_data(cache=False)
        if not payload:
            raise MediaError('The upload chunk is empty.')
        checksum = request.headers.get('X-Chunk-SHA256','')
        if not re.fullmatch('[a-f0-9]{64}',checksum) or hashlib.sha256(payload).hexdigest() != checksum:
            raise MediaError('The chunk checksum did not match. Retry this chunk.',422)
        offset = integer(request.headers.get('Upload-Offset'),'Upload offset',0,MAX_VIDEO_BYTES)
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            manager(db)
            row = session_row(db,id)
            if row['status'] != 'uploading' or offset != row['offset']:
                raise MediaError('Upload position changed. Resume from the server’s saved offset.',409,offset=row['offset'])
            if offset + len(payload) > row['size']:
                raise MediaError('The chunk exceeds the declared file size.')
            path = directories() / 'pending' / f'{id}.part'
            if not path.exists() or path.stat().st_size < offset:
                raise MediaError('The stored partial file is missing or incomplete. Cancel this upload and start again.',409)
            if shutil.disk_usage(path.parent).free < len(payload) + DISK_RESERVE_BYTES:
                raise MediaError('The storage volume is full. Free space before resuming.',507)
            try:
                with path.open('r+b') as handle:
                    handle.truncate(offset)  # Repair bytes written before an interrupted DB commit.
                    handle.seek(offset)
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                db.execute('UPDATE upload_sessions SET offset=? WHERE id=?',(offset+len(payload),id))
            except OSError as error:
                if error.errno == errno.ENOSPC:
                    raise MediaError('The storage volume is full. Free space before resuming.',507)
                raise
        return jsonify(offset=offset+len(payload))

    @bp.post('/api/uploads/<id>/complete')
    def complete_upload(id):
        root = directories()
        old_file = None
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            manager(db)
            row = session_row(db,id)
            if row['status'] == 'completed':
                return jsonify(title_id=row['title_id'],video_id=row['video_id'])
            if row['offset'] != row['size']:
                raise MediaError('The upload is incomplete. Resume uploading before publishing.',409,offset=row['offset'])
            metadata = json.loads(row['metadata'])
            partial = root / 'pending' / f'{id}.part'
            moved = root / 'videos' / (id + metadata['extension'])
            if not partial.exists() and moved.exists():
                moved.replace(partial)  # Recover a process interrupted between rename and DB commit.
            if not partial.exists() or partial.stat().st_size < row['size']:
                raise MediaError('The uploaded file is missing or incomplete.',409)
            with partial.open('r+b') as handle:
                handle.truncate(row['size'])
                if hashlib.sha256(handle.read(65536)).hexdigest() != row['fingerprint']:
                    raise MediaError('This file does not match the original selection. Cancel and upload the correct file.',422)
            duration = inspect_video(partial,metadata['extension'],metadata['duration'])
            title_id = metadata['target'] or 'upload-' + uuid4().hex
            if metadata['target'] and not db.execute('SELECT 1 FROM media_titles WHERE id=?',(title_id,)).fetchone():
                raise MediaError('The target title was removed. Cancel this upload and start again.',409)
            existing = db.execute('SELECT * FROM media_videos WHERE title_id=? AND season=? AND episode=?',
                                  (title_id,metadata['season'],metadata['episode'])).fetchone()
            if existing and not metadata['replace']:
                raise MediaError('This episode was uploaded by someone else. Cancel or start a replacement upload.',409)
            if not metadata['target']:
                db.execute('INSERT INTO media_titles(id,title,year,type,genres,rating,description,cast,family) VALUES (?,?,?,?,?,?,?,?,?)',
                           (title_id,metadata['title'],metadata['year'],metadata['type'],json.dumps(metadata['genres']),metadata['rating'],metadata['description'],metadata['cast'],int(metadata['family'])))
            if existing:
                old_file = root / 'videos' / existing['file_name']
                db.execute('DELETE FROM media_videos WHERE id=?',(existing['id'],))
                key = (metadata['season']-1)*1000+metadata['episode']
                db.execute('DELETE FROM progress WHERE title_id=? AND episode=?',(title_id,key))
            filename = id + metadata['extension']
            destination = root / 'videos' / filename
            partial.replace(destination)
            try:
                db.execute('INSERT INTO media_videos(id,title_id,season,episode,episode_title,file_name,original_name,size,mime,duration) VALUES (?,?,?,?,?,?,?,?,?,?)',
                           (id,title_id,metadata['season'],metadata['episode'],metadata['episode_title'],filename,row['original_name'],row['size'],VIDEO_TYPES[metadata['extension']],duration))
                db.execute("UPDATE upload_sessions SET status='completed',title_id=?,video_id=? WHERE id=?",(title_id,id,id))
                if old_file:
                    queue_removal(db,old_file)
                db.commit()
            except Exception:
                destination.replace(partial)
                raise
        if old_file:
            with database() as db:
                collect_garbage(db)
        app.logger.info('Published uploaded video %s (%s bytes)',id,row['size'])
        return jsonify(title_id=title_id,video_id=id),201

    @bp.delete('/api/uploads/<id>')
    def cancel_upload(id):
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            manager(db)
            row = session_row(db,id)
            if row['status'] != 'uploading':
                raise MediaError('This upload is already published. Remove its video from the library instead.',409)
            metadata=json.loads(row['metadata'])
            files=[directories()/'pending'/f'{id}.part',directories()/'videos'/(id+metadata['extension'])]
            delete_files_and_rows(db,files,lambda: db.execute('DELETE FROM upload_sessions WHERE id=?',(id,)))
        return jsonify(ok=True)

    @bp.patch('/api/library/<id>')
    def edit_title(id):
        data = body()
        with database() as db:
            manager(db)
            row = db.execute('SELECT * FROM media_titles WHERE id=?',(id,)).fetchone()
            if not row:
                raise MediaError('This uploaded title no longer exists.',404)
            metadata = title_metadata(data,dict(row))
            db.execute('UPDATE media_titles SET title=?,year=?,genres=?,rating=?,description=?,cast=?,family=? WHERE id=?',
                       (metadata['title'],metadata['year'],json.dumps(metadata['genres']),metadata['rating'],metadata['description'],metadata['cast'],int(metadata['family']),id))
        return jsonify(ok=True)

    @bp.post('/api/library/<id>/poster')
    def upload_poster(id):
        request.max_content_length = MAX_POSTER_BYTES + 65536
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            manager(db)
            row = db.execute('SELECT * FROM media_titles WHERE id=?',(id,)).fetchone()
            if not row:
                raise MediaError('This uploaded title no longer exists.',404)
            file = request.files.get('file')
            if not file or not file.filename:
                raise MediaError('Choose a poster image.')
            payload = file.stream.read(MAX_POSTER_BYTES+1)
            if len(payload) > MAX_POSTER_BYTES:
                raise MediaError('Poster images must be 5 MiB or smaller.',413)
            extension, mime = poster_type(payload)
            if len(payload) > capacity(db)['available_bytes']:
                raise MediaError('There is not enough storage for this poster.',507)
            root = directories() / 'posters'
            filename = uuid4().hex + extension
            path = root / filename
            path.write_bytes(payload)
            try:
                db.execute('UPDATE media_titles SET poster_name=?,poster_mime=? WHERE id=?',(filename,mime,id))
                if row['poster_name']:
                    queue_removal(db,root/row['poster_name'])
                db.commit()
            except Exception:
                path.unlink(missing_ok=True)
                raise
            collect_garbage(db)
        return jsonify(ok=True)

    @bp.delete('/api/library/<id>/poster')
    def remove_poster(id):
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            manager(db)
            row = db.execute('SELECT poster_name FROM media_titles WHERE id=?',(id,)).fetchone()
            if not row:
                raise MediaError('This uploaded title no longer exists.',404)
            files = [directories()/'posters'/row['poster_name']] if row['poster_name'] else []
            delete_files_and_rows(db,files,lambda: db.execute('UPDATE media_titles SET poster_name=NULL,poster_mime=NULL WHERE id=?',(id,)))
        return jsonify(ok=True)

    def delete_files_and_rows(db, files, operation):
        # A restart can safely retry queued removals; live DB rows never lose their files.
        for path in files:
            queue_removal(db,path)
        operation()
        db.commit()
        collect_garbage(db)

    @bp.delete('/api/library/<id>')
    def delete_title(id):
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            manager(db)
            title = db.execute('SELECT * FROM media_titles WHERE id=?',(id,)).fetchone()
            if not title:
                raise MediaError('This uploaded title no longer exists.',404)
            pending = [dict(r) for r in db.execute("SELECT * FROM upload_sessions WHERE status='uploading'") if json.loads(r['metadata']).get('target') == id]
            root = directories()
            files = [root/'videos'/r['file_name'] for r in db.execute('SELECT file_name FROM media_videos WHERE title_id=?',(id,))]
            files += [root/'pending'/f"{r['id']}.part" for r in pending]
            if title['poster_name']:
                files.append(root/'posters'/title['poster_name'])
            def remove():
                db.execute('DELETE FROM saved WHERE title_id=?',(id,))
                db.execute('DELETE FROM progress WHERE title_id=?',(id,))
                db.execute('DELETE FROM upload_sessions WHERE title_id=?',(id,))
                for row in pending:
                    db.execute('DELETE FROM upload_sessions WHERE id=?',(row['id'],))
                db.execute('DELETE FROM media_titles WHERE id=?',(id,))
            delete_files_and_rows(db,files,remove)
        return jsonify(ok=True)

    @bp.delete('/api/library/<title_id>/videos/<video_id>')
    def delete_episode(title_id,video_id):
        with database() as db:
            db.execute('BEGIN IMMEDIATE')
            manager(db)
            video = db.execute('SELECT * FROM media_videos WHERE id=? AND title_id=?',(video_id,title_id)).fetchone()
            if not video:
                raise MediaError('This episode no longer exists.',404)
            count = db.execute('SELECT COUNT(*) FROM media_videos WHERE title_id=?',(title_id,)).fetchone()[0]
            if count <= 1:
                raise MediaError('This is the last video. Remove the title to delete it.',409)
            def remove():
                key = (video['season']-1)*1000+video['episode']
                db.execute('DELETE FROM progress WHERE title_id=? AND episode=?',(title_id,key))
                db.execute('DELETE FROM upload_sessions WHERE video_id=?',(video_id,))
                db.execute('DELETE FROM media_videos WHERE id=?',(video_id,))
            delete_files_and_rows(db,[directories()/'videos'/video['file_name']],remove)
        return jsonify(ok=True)

    @bp.get('/media/videos/<id>')
    def serve_video(id):
        with database() as db:
            profile = get_profile(db)
            row = db.execute('SELECT v.*,t.family FROM media_videos v JOIN media_titles t ON t.id=v.title_id WHERE v.id=?',(id,)).fetchone()
            if not row or (profile['kids'] and not row['family']):
                abort(404)
        response = send_from_directory(directories()/'videos',row['file_name'],mimetype=row['mime'],conditional=True,
                                       as_attachment=request.args.get('download') == '1', download_name=row['original_name'])
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Cache-Control'] = 'private, no-cache'
        return response

    @bp.get('/media/posters/<id>')
    def serve_poster(id):
        with database() as db:
            row = db.execute('SELECT poster_name,poster_mime FROM media_titles WHERE id=?',(id,)).fetchone()
            if not row or not row['poster_name']:
                abort(404)
        response = send_from_directory(directories()/'posters',row['poster_name'],mimetype=row['poster_mime'],conditional=True)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        return response

    @bp.errorhandler(OSError)
    def storage_error(error):
        app.logger.error('Media storage operation failed: %s',error)
        return jsonify(error='The storage volume is full.' if error.errno == errno.ENOSPC else 'Storage is temporarily unavailable. Retry this operation.'), 507 if error.errno == errno.ENOSPC else 503

    with database() as db:
        collect_garbage(db)
    app.register_blueprint(bp)
