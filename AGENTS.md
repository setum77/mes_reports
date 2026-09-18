# AGENTS.md

## Stack
- Python 3.12+ with uv.
- Django 5.x, PostgreSQL, Gunicorn.
- Key libraries: pandas, openpyxl, python-dotenv, django-widget-tweaks.
- Testing: pytest and pytest-django.
- No formatter or linter is configured; do not introduce one unless explicitly requested.

## Project structure
- Application entry point: `src/manage.py`.
- Django project configuration: `src/mes_report3/`.
- Django apps: `src/accounts/`, `src/production/`, `src/uploads/`, `src/reports/`.
- Templates and static assets: `src/templates/`, `src/static/`.
- Tests: `tests/`.
- Docker configuration: `docker/`.

## Commands
- Install locked dependencies: `uv sync --frozen`.
- Run Django commands: `uv run python src/manage.py <command>`.
- Run tests: `uv run pytest`.
- Docker entrypoint runs migrations, collects static files, and starts Gunicorn.

## Development rules
- Keep application source code under `src/`.
- Use `mes_report3.settings.dev` for local development and tests.
- Docker uses production settings.
- Do not change dependencies without explicit approval.
- Use Russian for explanations and technical comments when appropriate.
- Make focused, minimal changes; do not refactor unrelated code.
- Do not edit generated files, `.env` files, virtual environments, logs, `media/`, or files excluded by `.gitignore` unless explicitly requested.

## Data and behavior constraints
- Preserve the `ProductionRecord` uniqueness constraint:
  `(pcs_no, subop_no, created_date)`.
- Preserve Excel import deduplication using `ignore_conflicts=True`.
- Required Excel columns:
  `Lot no.`, `Subop no`, `PCSNo`, `CREATEDATE`, `result`.
- Preserve `Cache-Control: no-store` for HTML responses of reports No. 2 and No. 3, and for the No. 3 Excel export.
- Database-backed tests require PostgreSQL.

## Validation
- Run the narrowest relevant test first.
- Run `uv run pytest` when the change affects application behavior.
- Report changed files and validation commands actually run.