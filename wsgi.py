"""WSGI entrypoint for Flask and production servers."""

from banlist import create_app

app = create_app()
