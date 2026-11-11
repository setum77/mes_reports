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
- Django apps: `src/accounts/`, `src/production/`, `src/uploads/`, `src/reports/`, `src/backup/`.
- Templates and static assets: `src/templates/`, `src/static/`.
- Tests: `tests/`.
- Docker configuration: `docker/`.

## Commands
- Install locked dependencies: `uv sync --frozen`.
- Run Django commands: `uv run python src/manage.py <command>`.
- Check migrations: `uv run python src/manage.py makemigrations --check --dry-run`.
- Show migration state: `uv run python src/manage.py showmigrations production`.
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
- Do not edit already-applied migrations; add a new migration instead.
- Keep `makemigrations --check --dry-run` clean after model changes.

## Data and behavior constraints
- Domain model: `Lot`, `Station`, `ControlUnit` (БУ), `Production`, `TestDataTranslation`,
  `FaultJournal`, `FaultAttachment`, `UnitPhoto`. `ControlUnit` may exist without
  `Production` (manual defect/SN).
- Station seed/reference data: `src/production/stations.py`; translations and
  `translate_test_data`: `src/production/testdata.py`.
- `ControlUnit.entry_date` is nullable; `ControlUnit.resolved_entry_date` falls back
  to the first production date, then `created_at`.
- Preserve uniqueness: `Production (unit, station, created_date)`,
  `ControlUnit.sn`, `Lot.number`, `Station.number`, `TestDataTranslation.source`.
- Preserve FK behavior: `Production.unit` `CASCADE`, `Production.station` `PROTECT`,
  `FaultJournal.station` `PROTECT`, `ControlUnit.lot` and `FaultJournal.unit/lot`
  `SET_NULL`.
- Preserve Excel import deduplication using `ignore_conflicts=True` and
  `bulk_create(..., batch_size=2000)`; do not overwrite existing `ControlUnit.defect`
  or `ControlUnit.comment`.
- Required Excel columns:
  `Lot no.`, `Production spec.`, `Subop no`, `subop name`, `PCSNo`, `CREATEDATE`, `result`, `testData`.
- `Production.test_data_ru` is generated from `TestDataTranslation`/`translate_test_data`;
  unknown fragments fall back to the original `test_data`.
- `production_productionrecord` is a read-only compatibility view for legacy report SQL.
  Do not write through it; use `Production`/`ControlUnit`/`Station`.
- `Production` is read-only in the admin; other business models are editable by `staff`.
- `FaultJournal` and its attachments are staff-only; the report No. 9 UI is not
  implemented yet (model/admin only).
- Preserve `Cache-Control: no-store` for HTML responses of reports No. 2, No. 3,
  No. 4, No. 6, No. 8, and for the No. 3 Excel export.
- Backup `database.json` must be written in UTF-8; restore order is child-first:
  `Production`, `FaultAttachment`, `FaultJournal`, `UnitPhoto`, `ControlUnit`,
  `Lot`, `Station`, `TestDataTranslation`.
- Database-backed tests require PostgreSQL.

## Validation
- Run the narrowest relevant test first.
- Run `uv run pytest` when the change affects application behavior.
- Report changed files and validation commands actually run.