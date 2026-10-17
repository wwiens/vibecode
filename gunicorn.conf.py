"""Automatically read by Gunicorn. Keep one process and allow concurrent media I/O.

Railpack still chooses the command, interface and PORT; do not set bind here.
"""
workers = 1
worker_class = 'gthread'
threads = 4
timeout = 60
