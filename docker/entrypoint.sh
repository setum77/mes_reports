#!/bin/bash
set -e

export DJANGO_SETTINGS_MODULE=mes_report3.settings.prod

echo "Running database migrations..."
uv run python src/manage.py migrate --noinput

echo "Collecting static files..."
uv run python src/manage.py collectstatic --noinput

echo "Starting server..."
exec uv run gunicorn mes_report3.wsgi:application --bind 0.0.0.0:8000
