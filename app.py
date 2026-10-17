"""Compatibility with an existing Railway service configured to use app:app.
New services auto-detect the canonical main:app entrypoint.
"""
from main import app

if __name__ == '__main__':
    import os
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', '8000')), debug=False)
