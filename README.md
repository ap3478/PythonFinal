# IS601 Final Project — FastAPI Calculator

![CI](https://github.com/ap3478/PythonFinal/actions/workflows/test.yml/badge.svg)

A FastAPI-based calculator with JWT authentication, polymorphic calculation
models, profile management, per-user usage stats, and an admin dashboard.

Built as the term project for IS601 — extends an earlier assignment
(`assignment14`) with new operation types, a profile area, a stats report,
admin-only views, Alembic migrations, and a full GitHub Actions pipeline.

---

## Features

### Authentication
- JWT access + refresh tokens, bcrypt-hashed passwords (cost 12)
- Register, login (JSON), and form-encoded `/auth/token` for Swagger
- OAuth2 bearer dependency on every protected endpoint

### Calculations (BREAD)
- Polymorphic SQLAlchemy model with seven operation types:
  - `addition`, `subtraction`, `multiplication`, `division`
  - `power` — sequential, left-associative exponentiation
  - `modulus` — sequential remainder
  - `square_root` — unary, requires a single non-negative input
- Per-user scoping on every endpoint (you can only see your own rows)
- Type-aware validation: zero divisors rejected, negative roots rejected,
  zero-to-negative-power rejected — all at the schema layer

### Profile Management
- `GET /users/me` and `PUT /users/me` — read and update profile fields
- `POST /users/me/change-password` with `current_password` proof
- Username/email collisions return 400 instead of 500
- Every password change writes an audit row (user_id, ip_address, user_agent,
  changed_at) to `password_changes` — no actual passwords stored in audit

### Stats / Report
- `GET /users/me/stats` — total calculations, per-type breakdown,
  most-used type, average operands, average result, first/last timestamps
- Powered by Python aggregation rather than dialect-specific SQL — works
  identically against SQLite (tests) and PostgreSQL (production)

### Admin Dashboard
- `is_admin` boolean column on the `users` table, default false
- `get_current_admin_user` dependency reads `is_admin` from the DB on every
  request — a stale JWT can't elevate after a demotion
- `/admin/users`, `/admin/calculations`, `/admin/password-changes`,
  `/admin/stats` — system-wide views with filter parameters
- Tabbed admin page UI

### Database
- Alembic migrations replace the original `Base.metadata.create_all`
- Two migrations: baseline (users + calculations), then `is_admin` +
  password_changes
- Both `dockerfile` and `docker-compose.yml` run `alembic upgrade head`
  before starting Uvicorn, so schema is current automatically

### CI/CD
- GitHub Actions pipeline with three jobs:
  - **test** — Postgres service container, install deps + Playwright,
    `alembic upgrade head`, then unit/integration/e2e suites
  - **security** — Build Docker image, scan with Trivy, fail on CRITICAL
    vulnerabilities
  - **deploy** — On push to `main`, multi-arch Docker Hub push to
    `ap3478/pythonfinal:latest` and `:${{ github.sha }}`

---

## Quick Start

### Run with Docker Compose (recommended)

```bash
git clone git@github.com:ap3478/PythonFinal.git
cd PythonFinal
docker compose up --build
```

Then visit `http://localhost:8000`. Postgres comes up alongside the app and
Alembic runs migrations automatically before Uvicorn starts.

### Run locally with a system-installed Postgres

```bash
psql -U postgres -c "CREATE DATABASE fastapi_db;"

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

DATABASE_URL=postgresql://postgres:postgres@localhost:5432/fastapi_db \
  alembic upgrade head

DATABASE_URL=postgresql://postgres:postgres@localhost:5432/fastapi_db \
  uvicorn app.main:app --reload --port 8000
```

---

## Configuration

Configuration comes from environment variables with sensible defaults in
`app/core/config.py`. Critical ones:

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql://postgres:postgres@db:5432/fastapi_db` | Connection string |
| `JWT_SECRET_KEY` | dev fallback | HS256 signing key for access tokens |
| `JWT_REFRESH_SECRET_KEY` | dev fallback | HS256 signing key for refresh tokens |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `30` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | Refresh token TTL |
| `BCRYPT_ROUNDS` | `12` | Password hashing cost factor |

Override the JWT secrets in production via your secrets manager. The
in-code defaults are deliberately weak.

---

## Endpoints

### Auth
- `POST /auth/register` — create a new account
- `POST /auth/login` — JSON username + password → access + refresh tokens
- `POST /auth/token` — form-encoded login (Swagger Authorize)

### User
- `GET /users/me` — current user profile
- `PUT /users/me` — update first/last name, username, email
- `POST /users/me/change-password` — verify current password and set a new one
- `GET /users/me/stats` — usage breakdown for the current user

### Calculations
- `POST /calculations` — create + compute a new calculation
- `GET /calculations` — list current user's calculations
- `GET /calculations/{id}` — fetch a specific calculation
- `PUT /calculations/{id}` — update inputs and recompute
- `DELETE /calculations/{id}` — delete a calculation

### Admin (requires `is_admin = true`)
- `GET /admin/users` — every user with calculation count
- `GET /admin/calculations?type=&user_id=&limit=` — filtered global list
- `GET /admin/password-changes?user_id=&limit=` — audit log
- `GET /admin/stats` — system-wide counters

### Web pages
- `/` `/login` `/register` `/dashboard` `/profile` `/stats` `/admin`

Full API docs: `http://localhost:8000/docs` (Swagger) or `/redoc`.

---

## Promoting a User to Admin

There is no public "make me admin" endpoint, by design. Promote manually:

```bash
docker compose exec db psql -U postgres -d fastapi_db \
  -c "UPDATE users SET is_admin = TRUE WHERE username = 'YOUR_USERNAME';"
```

Re-login afterward to refresh the JWT (though the admin guard reads from
the DB, so an existing token will work too).

---

## Migrations

```bash
alembic upgrade head             # apply all pending
alembic downgrade -1             # roll back one
alembic current                  # show current revision
alembic history --verbose        # full history
```

Tests use `Base.metadata.create_all` for speed; production and dev use Alembic.

---

## Testing

```bash
pytest tests/unit/                              # unit tests only
pytest tests/integration/                       # require Postgres
playwright install chromium && pytest tests/e2e/  # require Chromium too
pytest --cov=app                                # everything with coverage
```

The test suite has 130+ tests covering models, schemas, endpoints, and
end-to-end browser flows. CI runs all three layers on every push.

---

## Project Structure
.
├── alembic/                    # Database migrations
│   ├── env.py
│   └── versions/
│       ├── 0001_baseline.py
│       └── 0002_admin_and_password_audit.py
├── app/
│   ├── auth/                   # JWT, password hashing, dependencies
│   ├── core/                   # Settings (pydantic-settings)
│   ├── models/                 # SQLAlchemy models
│   ├── operations/             # Pure-function arithmetic helpers
│   ├── schemas/                # Pydantic request/response models
│   ├── database.py
│   └── main.py                 # FastAPI app, all routes
├── static/                     # CSS, JS
├── templates/                  # Jinja2 HTML
├── tests/
│   ├── unit/
│   ├── integration/
│   └── e2e/
├── alembic.ini
├── docker-compose.yml
├── dockerfile
├── pytest.ini
├── README.md
├── REFLECTION.md
└── requirements.txt
---

## License

MIT. See `LICENSE`.
