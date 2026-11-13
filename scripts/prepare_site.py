"""Render the browser-local Sites edition without starting a database."""
from pathlib import Path
import shutil
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / 'sites' / 'folio-scanner' / 'dist'
OUT.mkdir(parents=True, exist_ok=True)
env = Environment(loader=FileSystemLoader(ROOT / 'templates'), autoescape=select_autoescape(['html']))
env.globals['url_for'] = lambda endpoint, filename: 'static/' + filename
html = env.get_template('index.html').render().replace('data-storage="sqlite"', 'data-storage="local"')
(OUT / 'index.html').write_text(html)
shutil.copytree(ROOT / 'static', OUT / 'static', dirs_exist_ok=True)
print('Static edition ready at', OUT)
