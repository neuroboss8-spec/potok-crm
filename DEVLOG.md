# Public release checks

## Interface screenshots 2026-10-30

- Captured the actual Django funnel and inbox views in headless Chromium at 1600 × 1000 px. Both screens used a temporary, localhost-only preview server and a separate SQLite database populated by the unchanged fictional seed command.
- The demo user had no usable password. Preview authentication existed only in the temporary screenshot server; no authentication bypass was added to application source or published.
- Visually inspected both PNG files, confirmed that contacts use example.com, and embedded them in README. The temporary server and database were removed after capture. No live server or customer data was used.

## 2026-10-30

- Prepared an independent source distribution using an explicit allowlist: Django config and app, migrations, tests, static assets with vendor notices, requirements, Docker files and generic documentation.
- Replaced instance-specific branding and the project description with generic Potok CRM text. The fictional `seed_demo.py` dataset was preserved byte-for-byte.
- Excluded databases, runtime logs, environment files, session files, credentials, backups and internal deployment/submission documents. Compared the proposed publication against locally configured secrets without printing their values, and scanned for token formats and private infrastructure identifiers: no matches in 62 release files before this log was added.
- Added MIT licensing for original code, retained third-party notices, and added a localhost configuration generator. A temporary-directory smoke check confirmed fresh generated values, matching database credentials and refusal to overwrite an existing `.env`.
- `python manage.py check` against the release with isolated in-memory SQLite: no issues.
- `python manage.py test crm.tests --verbosity 1` against the release: 25 tests passed. Tests used isolated in-memory SQLite and no bot token.
- Docker Compose configuration validated with a newly generated temporary `.env`; that generated file was then removed. JavaScript syntax check passed. A fresh temporary SQLite installation applied migrations and seeded the unchanged fictional dataset; `makemigrations --check --dry-run` detected no model drift.
- These checks do not establish a working Telegram integration or PostgreSQL concurrency on someone else's server. Follow the manual installation acceptance steps in README with your own bot, database and HTTPS configuration.
