# Third-party components

| Component | Pinned version | License | Use and provenance |
|---|---:|---|---|
| Django | 5.2.17 | BSD-3-Clause | Sessions, auth, CSRF, forms, ORM, migrations, templates, admin; PyPI dependency. |
| aiogram | 3.31.0 | MIT | Telegram Bot API client and update dispatcher; PyPI dependency. |
| django-axes | 8.3.1 | MIT | Login-attempt throttling; PyPI dependency. |
| psycopg[binary] | 3.3.6 | LGPL-3.0-or-later / PSF-2.0 | PostgreSQL driver; PyPI dependency; packaged binary distribution. |
| gunicorn | 26.2.0 | MIT | WSGI production process. |
| WhiteNoise | 6.12.0 | MIT | Local static asset serving. |
| htmx | 2.0.4 | 0BSD | Local HTMX browser asset at `static/vendor/htmx.min.js`; official pinned `unpkg.com/htmx.org@2.0.4` package path. SHA-256: `e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447`. Matching license saved beside the asset. |
| Tabler core | 1.6.1 | MIT | Local compiled CSS at `static/vendor/tabler.min.css`; only core styles and Bootstrap components used by the interface, no bundled optional plugin directory. The upstream CSS's trailing optional source-map pointer was removed; all CSS declarations are unchanged. Result SHA-256: `09c0ad77d135f90fd8cbc583824b2fdbd247adbc001234d27a36f284bfecab5e`. Upstream license saved beside the file. |
| PostgreSQL | 16.15 | PostgreSQL License | Docker Official Image tag `postgres:16.15-alpine3.23`. |

Python direct dependencies are pinned in `requirements.txt`; the transitive environment snapshot is recorded in `requirements.lock`. Review package transitive licences if the dependency set changes. The theme overrides are original; Tabler core CSS is used locally and vendor source files are not modified.
