"""Railway-ready streaming classroom demo. Run with gunicorn main:app."""
import logging
import math
import os
from contextlib import contextmanager
from pathlib import Path
import sqlite3

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
from catalog import BY_ID, CATALOG, DEMO_VIDEO, GENRES

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024
volume = os.getenv('RAILWAY_VOLUME_MOUNT_PATH')
if (os.getenv('RAILWAY_ENVIRONMENT_ID') or os.getenv('RAILWAY_PROJECT_ID')) and not volume:
    raise RuntimeError('Persistent storage is not configured: attach a Railway volume at /data before deploying.')
DATA_DIR = Path(volume) if volume else Path(__file__).resolve().parent / '.localdata'
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_PATH = DATA_DIR / 'app.db'

@contextmanager
def database():
    conn = sqlite3.connect(DATABASE_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    try:
        with conn:
            yield conn
    finally:
        conn.close()

def initialize():
    with database() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS profiles (
                id INTEGER PRIMARY KEY, name TEXT NOT NULL, color TEXT NOT NULL DEFAULT 'blue',
                kids INTEGER NOT NULL DEFAULT 0, autoplay INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS saved (
                profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
                title_id TEXT NOT NULL, liked INTEGER NOT NULL DEFAULT 0,
                in_list INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(profile_id, title_id)
            );
            CREATE TABLE IF NOT EXISTS progress (
                profile_id INTEGER REFERENCES profiles(id) ON DELETE CASCADE,
                title_id TEXT NOT NULL, episode INTEGER NOT NULL DEFAULT 1,
                position REAL NOT NULL DEFAULT 0, duration REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(profile_id, title_id, episode)
            );
        ''')
        if not db.execute('SELECT 1 FROM profiles LIMIT 1').fetchone():
            db.execute("INSERT OR IGNORE INTO profiles(id,name,color) VALUES (1,'Alex','blue')")
            db.execute("INSERT OR IGNORE INTO profiles(id,name,color) VALUES (2,'Movie night','purple')")
            db.execute("INSERT OR IGNORE INTO profiles(id,name,color,kids) VALUES (3,'Kids','orange',1)")
    app.logger.info('SQLite ready at %s', DATABASE_PATH)

initialize()

class InputError(Exception):
    pass

@app.errorhandler(InputError)
def input_error(error):
    return jsonify(error=str(error)), 400

@app.errorhandler(HTTPException)
def http_error(error):
    if request.path.startswith('/api/'):
        return jsonify(error=error.description), error.code
    return error

def body():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise InputError('Please send a JSON object.')
    return data

def integer(value, label, minimum=1, maximum=1000000):
    if isinstance(value, bool):
        raise InputError(f'{label} must be a whole number.')
    try:
        number = int(value)
        if str(number) != str(value) or not minimum <= number <= maximum:
            raise ValueError
        return number
    except (TypeError, ValueError):
        raise InputError(f'{label} must be a whole number between {minimum} and {maximum}.')

def get_profile(db, value=None):
    id = integer(value if value is not None else request.args.get('profile', '1'), 'Profile')
    profile = db.execute('SELECT * FROM profiles WHERE id=?', (id,)).fetchone()
    if not profile:
        raise InputError('That profile no longer exists. Please choose another profile.')
    return dict(profile)

def allowed(profile, item):
    return not profile['kids'] or item.get('family', False)

def get_title(profile, id):
    item = BY_ID.get(id)
    if not item or not allowed(profile, item):
        raise InputError('This title is not available for this profile.')
    return item

@app.get('/')
def index():
    return render_template('index.html')

@app.get('/health')
def health():
    with database() as db:
        db.execute('SELECT 1').fetchone()
    return jsonify(status='ok')

@app.get('/api/catalog')
def catalog():
    with database() as db:
        profile = get_profile(db)
    query = request.args.get('q', '').strip().casefold()[:100]
    kind, genre = request.args.get('type', ''), request.args.get('genre', '')
    items = [item for item in CATALOG if allowed(profile, item)
             and (not kind or item['type'] == kind)
             and (not genre or genre in item['genres'])
             and (not query or query in ' '.join([item['title'], item['cast'], *item['genres']]).casefold())]
    return jsonify(titles=items, genres=GENRES, demo_video=DEMO_VIDEO)

@app.get('/api/profiles')
def profiles():
    with database() as db:
        return jsonify(profiles=[dict(row) for row in db.execute('SELECT * FROM profiles ORDER BY id')])

@app.post('/api/profiles')
def create_profile():
    data = body()
    name = data.get('name', '')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 20:
        raise InputError('Choose a profile name between 1 and 20 characters.')
    color = data.get('color', 'blue')
    if color not in ('blue', 'purple', 'orange', 'green', 'red'):
        raise InputError('Choose one of the available avatar colors.')
    if 'kids' in data and not isinstance(data['kids'], bool):
        raise InputError('Kids mode must be on or off.')
    with database() as db:
        if db.execute('SELECT COUNT(*) FROM profiles').fetchone()[0] >= 5:
            raise InputError('You can have up to five profiles. Edit an existing profile instead.')
        cursor = db.execute('INSERT INTO profiles(name,color,kids) VALUES (?,?,?)',
                            (name.strip(), color, int(data.get('kids', False))))
        id = cursor.lastrowid
    return jsonify(id=id), 201

@app.patch('/api/profiles/<int:id>')
def update_profile(id):
    data = body()
    with database() as db:
        profile = get_profile(db, id)
        name = data.get('name', profile['name'])
        color = data.get('color', profile['color'])
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 20:
            raise InputError('Choose a profile name between 1 and 20 characters.')
        if color not in ('blue', 'purple', 'orange', 'green', 'red'):
            raise InputError('Choose one of the available avatar colors.')
        for key in ('kids', 'autoplay'):
            if key in data and not isinstance(data[key], bool):
                raise InputError(f'{key.title()} must be on or off.')
        db.execute('UPDATE profiles SET name=?,color=?,kids=?,autoplay=? WHERE id=?',
                   (name.strip(), color, int(data.get('kids', profile['kids'])), int(data.get('autoplay', profile['autoplay'])), id))
    return jsonify(ok=True)

@app.delete('/api/profiles/<int:id>')
def delete_profile(id):
    with database() as db:
        get_profile(db, id)
        if db.execute('SELECT COUNT(*) FROM profiles').fetchone()[0] <= 1:
            raise InputError('Keep at least one profile.')
        db.execute('DELETE FROM profiles WHERE id=?', (id,))
    return jsonify(ok=True)

@app.get('/api/state')
def state():
    with database() as db:
        profile = get_profile(db)
        saved = [dict(r) for r in db.execute('SELECT * FROM saved WHERE profile_id=?', (profile['id'],))]
        progress = [dict(r) for r in db.execute('SELECT * FROM progress WHERE profile_id=? ORDER BY updated_at DESC, rowid DESC', (profile['id'],))]
    ids = {item['id'] for item in CATALOG if allowed(profile, item)}
    return jsonify(profile=profile, saved=[r for r in saved if r['title_id'] in ids],
                   progress=[r for r in progress if r['title_id'] in ids])

@app.put('/api/saved/<id>')
def save(id):
    data = body()
    with database() as db:
        profile = get_profile(db)
        get_title(profile, id)
        current = db.execute('SELECT * FROM saved WHERE profile_id=? AND title_id=?', (profile['id'], id)).fetchone()
        values = dict(current) if current else dict(in_list=0, liked=0)
        for key in ('in_list', 'liked'):
            if key in data:
                if not isinstance(data[key], bool):
                    raise InputError('List and like selections must be true or false.')
                values[key] = int(data[key])
        db.execute('INSERT INTO saved(profile_id,title_id,in_list,liked) VALUES (?,?,?,?) '
                   'ON CONFLICT(profile_id,title_id) DO UPDATE SET in_list=excluded.in_list,liked=excluded.liked',
                   (profile['id'], id, values['in_list'], values['liked']))
    return jsonify(ok=True, **{k: bool(values[k]) for k in ('in_list', 'liked')})

@app.put('/api/progress/<id>')
def save_progress(id):
    data = body()
    with database() as db:
        profile = get_profile(db)
        item = get_title(profile, id)
        episode = integer(data.get('episode', 1), 'Episode', maximum=item.get('seasons', 1) * 6 if item['type'] == 'series' else 1)
        try:
            position, duration = float(data.get('position', 0)), float(data.get('duration', 0))
            if not all(math.isfinite(v) for v in (position, duration)) or not 0 <= position <= duration <= 86400:
                raise ValueError
        except (TypeError, ValueError):
            raise InputError('Playback position and duration must be valid, positive times.')
        db.execute("INSERT INTO progress(profile_id,title_id,episode,position,duration,updated_at) VALUES (?,?,?,?,?,strftime('%Y-%m-%d %H:%M:%f','now')) "
                   'ON CONFLICT(profile_id,title_id,episode) DO UPDATE SET position=excluded.position,'
                   'duration=excluded.duration,updated_at=excluded.updated_at', (profile['id'], id, episode, position, duration))
    return jsonify(ok=True)

@app.delete('/api/progress/<id>')
def clear_progress(id):
    with database() as db:
        profile = get_profile(db)
        db.execute('DELETE FROM progress WHERE profile_id=? AND title_id=?', (profile['id'], id))
    return jsonify(ok=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8000')), debug=False)
