#!/bin/bash
set -e

export DJANGO_SETTINGS_MODULE=mes_report3.settings.prod

echo "Running database migrations..."
uv run python src/manage.py migrate --noinput

echo "Collecting static files..."
uv run python src/manage.py collectstatic --noinput

echo "Creating superuser (if not exists)..."
uv run python src/manage.py shell -c "
import os
from django.contrib.auth import get_user_model
u = get_user_model()
if not u.objects.filter(username='admin').exists():
    u.objects.create_superuser('admin', 'admin@localhost', os.environ.get('DJANGO_ADMIN_PASSWORD', 'admin123'))
"

echo "Starting server..."
exec uv run gunicorn mes_report3.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 120 --max-requests 1000 --max-requests-jitter 50 --preload
