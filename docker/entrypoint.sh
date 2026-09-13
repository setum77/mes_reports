#!/bin/bash
set -e

echo "Running database migrations..."
uv run python src/manage.py migrate --noinput

echo "Collecting static files..."
uv run python src/manage.py collectstatic --noinput

echo "Starting server..."
exec uv run gunicorn mes_report3.wsgi:application --bind 0.0.0.0:8000
