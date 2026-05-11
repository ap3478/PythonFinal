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
  identically across SQLite (tests) and PostgreSQL (production)

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

### How to access Github and Docker Repo

- GitHub Repository:  https://github.com/ap3478/PythonFinal

- Docker Hub Image:   https://hub.docker.com/r/ap3478/pythonfinal
- Pull Command:       docker pull ap3478/pythonfinal:latest
---

## Project Structure

```
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
├── accounts.md
└── requirements.txt
```

---

## Quick Start

### Option 1: Docker Compose (recommended)

The fastest way to get a working app — Postgres, the web server, and
migrations all come up together:

```bash
git clone git@github.com:ap3478/PythonFinal.git
cd PythonFinal
docker compose up --build
```

Visit `http://localhost:8000`. To stop, `Ctrl+C` in the terminal, then
`docker compose down` to remove the containers.

### Option 2: Run locally with Uvicorn

If you'd rather run the FastAPI app directly (faster reload cycle during
development), follow these steps.

#### 1. Install Python 3.10+

This project requires Python 3.10 or higher. Verify:

```bash
python3 --version
```

If you're on 3.9 or older, install via Homebrew (Mac) or your package
manager.

#### 2. Install and start PostgreSQL

You need PostgreSQL 14+ running locally. On Mac:

```bash
brew install postgresql@17
brew services start postgresql@17
```

On Ubuntu/Debian:

```bash
sudo apt install postgresql
sudo systemctl start postgresql
```

#### 3. Create the databases

```bash
psql -U postgres -c "CREATE DATABASE fastapi_db;"
psql -U postgres -c "CREATE DATABASE fastapi_test_db;"
```

(`fastapi_test_db` is used by the test suite — see "Testing" below.)

#### 4. Clone the repo and set up a virtualenv

```bash
git clone git@github.com:ap3478/PythonFinal.git
cd PythonFinal

python3 -m venv venv
source venv/bin/activate          # macOS/Linux
# or: venv\Scripts\activate       # Windows

pip install --upgrade pip
pip install -r requirements.txt
```

#### 5. Apply database migrations

Set `DATABASE_URL` and run Alembic. This creates the `users`,
`calculations`, and `password_changes` tables:

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/fastapi_db"
alembic upgrade head
```

You should see output ending with `Running upgrade ... -> 0002_admin_and_password_audit`.

To verify, query the schema:

```bash
psql -U postgres -d fastapi_db -c "\dt"
```

You should see four tables: `alembic_version`, `users`, `calculations`,
`password_changes`.

#### 6. Start the Uvicorn server

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

You should see:

```
INFO:     Will watch for changes in [...]
INFO:     Uvicorn running on http://127.0.0.1:8000
INFO:     Started server process
INFO:     Application startup complete.
```

Now visit:
- `http://127.0.0.1:8000/` — landing page
- `http://127.0.0.1:8000/register` — create an account
- `http://127.0.0.1:8000/dashboard` — calculations (after login)
- `http://127.0.0.1:8000/docs` — interactive Swagger API docs
- `http://127.0.0.1:8000/redoc` — alternative API docs

The `--reload` flag restarts the server when you change code. Drop it for
production runs.

To stop the server, `Ctrl+C` in the terminal.

#### Useful flags

```bash
uvicorn app.main:app --reload --port 8001       # different port
uvicorn app.main:app --host 0.0.0.0 --port 8000 # bind to all interfaces
uvicorn app.main:app --workers 4                # production multi-worker
uvicorn app.main:app --log-level debug          # verbose logging
```

#### Troubleshooting local Uvicorn runs

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError: No module named 'fastapi'` | Venv not activated, or deps not installed | `source venv/bin/activate && pip install -r requirements.txt` |
| `psycopg2.OperationalError: could not connect` | Postgres isn't running | `brew services start postgresql@17` |
| `relation "users" does not exist` | Alembic migrations haven't run | `alembic upgrade head` |
| `Address already in use` | Another process on port 8000 | `lsof -i :8000` to find it, or use `--port 8001` |
| `ImportError: cannot import name ...` from `app.models` | Stale `__pycache__` | `find . -name __pycache__ -exec rm -rf {} +` |
| 500 errors on `/auth/login` | `JWT_SECRET_KEY` not set | `export JWT_SECRET_KEY=dev-secret-key-min-32-chars-long` |

---

## Configuration

Configuration comes from environment variables with sensible defaults in
`app/core/config.py`. The most important ones:

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

For local development, you can set them inline:

```bash
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/fastapi_db"
export JWT_SECRET_KEY="your-dev-secret-min-32-chars"
export JWT_REFRESH_SECRET_KEY="your-dev-refresh-secret-min-32-chars"
uvicorn app.main:app --reload
```

Or persist them in a `.env` file (already gitignored) and source it:

```bash
echo 'export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/fastapi_db"' >> .env
echo 'export JWT_SECRET_KEY="your-dev-secret-min-32-chars"' >> .env
source .env
```

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

## Accessing the Admin Dashboard

The admin dashboard at `/admin` is restricted to users with `is_admin = true`.
By default, no users are admins — including the first one you register.

### Step-by-step

1. **Register a normal account** as you would any other user, either through
   the `/register` page or the `POST /auth/register` API. This account will
   start with `is_admin = false`.

2. **Promote the account in the database.** This is a one-time operation
   per user:

   ```bash
   # If running via Docker Compose:
   docker compose exec db psql -U postgres -d fastapi_db \
     -c "UPDATE users SET is_admin = TRUE WHERE username = 'YOUR_USERNAME';"

   # If running locally with system Postgres:
   psql -U postgres -d fastapi_db \
     -c "UPDATE users SET is_admin = TRUE WHERE username = 'YOUR_USERNAME';"
   ```

   You should see `UPDATE 1` indicating the row was updated.

3. **Re-login** at `/login`. Your new JWT will reflect the updated admin
   status (though the admin guard reads `is_admin` from the database on
   every request, so an existing token works too).

4. **Click "Admin"** in the top navigation bar — the link only appears for
   admin users — or visit `/admin` directly.

5. The admin page has four tabs:
   - **Users** — every user with calculation count, last login, admin flag
   - **Calculations** — every calculation across all users; supports filter
     parameters (`?type=`, `?user_id=`, `?limit=`)
   - **Password Changes** — audit log of every password change
   - **Stats** — system-wide counters and per-type breakdown

### Verifying admin access via the API

```bash
# Get your JWT
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"YOUR_USERNAME","password":"YOUR_PASSWORD"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

# Hit an admin endpoint
curl -s http://localhost:8000/admin/stats \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

If the user isn't an admin, you'll get a 403 response. Promote them and try
again.

### Demoting an admin

```bash
psql -U postgres -d fastapi_db \
  -c "UPDATE users SET is_admin = FALSE WHERE username = 'YOUR_USERNAME';"
```

The demotion takes effect on the next request — no need to invalidate the
token, because the admin guard checks the database, not the JWT payload.

---

## Test User Accounts for Grading

A set of pre-made test accounts (one admin + three regular) is documented
separately to keep the README clean. See [`accounts.md`](accounts.md) for
credentials and a step-by-step seeding script.

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
# Unit tests only (no Postgres needed)
pytest tests/unit/

# Integration tests (require Postgres + the test DB)
export DATABASE_URL="postgresql://postgres:postgres@localhost:5432/fastapi_test_db"
pytest tests/integration/

# E2E tests (require Postgres + Playwright Chromium)
playwright install chromium
pytest tests/e2e/

# Everything with coverage
pytest --cov=app
```

The test suite has 130+ tests covering models, schemas, endpoints, and
end-to-end browser flows. CI runs all three layers on every push.


## License

MIT. See `LICENSE`.