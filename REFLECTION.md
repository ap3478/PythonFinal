# Reflection

## What I built

The project began as a FastAPI calculator with auth and basic CRUD on
calculations. The final-project requirement was to extend it across four
dimensions: new operation types, profile management, per-user statistics,
and an admin view of the whole system. I added all four, plus migrated
the database setup from `Base.metadata.create_all` to Alembic and shipped
a three-job GitHub Actions pipeline (test, Trivy scan, Docker Hub push).

The polymorphic `Calculation` model gained `Power`, `Modulus`, and
`SquareRoot` subclasses with type-aware validation — square_root is unary
and rejects negative inputs, modulus rejects zero divisors, power rejects
the 0 ** negative-exponent case. The dashboard select dropdown picks up
these types automatically and the input form switches to single-field mode
when square_root is selected.

The profile area added two endpoints (`GET/PUT /users/me`) and a password
change endpoint that writes to a new `password_changes` audit table. The
audit captures `user_id`, `changed_at`, `ip_address`, and `user_agent` —
deliberately no password material, because the audit log's job is to tell
you *that* a password changed and from where, not what it changed to.

Stats is a single endpoint (`GET /users/me/stats`) with the breakdown
calculated in Python rather than SQL. That kept the same code path working
across SQLite and PostgreSQL and avoided dialect-specific window functions
that would have made testing harder.

Admin is gated by an `is_admin` boolean on the `users` table. The guard
reads `is_admin` from the database on every request, not from the JWT
payload — a stale token can't elevate after a demotion. Four endpoints
expose the system: users, calculations (with filters), the password-change
audit, and aggregate stats.

## What was harder than I expected

**SQLAlchemy relationship resolution.** When I sliced the work into
feature branches, branch 1 needed `User` but not `PasswordChange` yet.
SQLAlchemy resolves `relationship("PasswordChange")` strings lazily at
mapper-bake time, which means importing `User` succeeded fine but the
first test that actually queried the DB exploded because the PasswordChange
class wasn't in the registry. The fix was to keep the relationship out
of `User` until the audit model existed (branch 4), then put it back.

**Alembic + the test conftest.** Tests use `create_all` for speed, while
production uses Alembic. Keeping these in sync is fragile — if I add a
column to a model and forget to also write a migration, tests pass but
production blows up. I addressed this by running `alembic upgrade head`
in CI against a fresh Postgres, so any drift between models and migrations
fails the pipeline.

**Branch slicing on already-finished work.** I built the project end-to-end
in one shot first, then realized the rubric expected proper feature-branch
hygiene. Reconstructing nine clean PRs after the fact required carefully
reverse-engineering which files belonged to which feature, working through
each branch's code in isolation, and verifying tests passed at each step.
The lesson: branch first, code second.

## Design tradeoffs

- **Audit log without password hashes.** Storing only metadata makes the
  audit table safe to share with an admin without leaking material an
  attacker could brute-force later.
- **DB-fetched admin guard.** Reading `is_admin` from the database on
  every admin request costs one extra query, but means admin demotion
  takes effect immediately rather than waiting for the JWT to expire.
- **Python-side stats aggregation.** Slower than SQL `GROUP BY` but
  database-agnostic. Acceptable for a calculator where users typically
  have hundreds of rows, not millions.

## What I'd improve

- **Token revocation on password change.** Currently, changing your
  password doesn't invalidate existing access tokens. A small Redis-backed
  blacklist (or shorter token TTL plus refresh-rotation) would close that
  gap.
- **Admin promotion endpoint.** Right now you promote via psql, which
  works but isn't operationally clean. A protected `/admin/users/{id}/promote`
  endpoint with audit logging would be better.
- **More e2e coverage of the admin page.** The Playwright tests cover the
  happy paths but don't exercise the filter dropdowns or the `?user_id=`
  query parameters on the admin pages.

## Branching workflow

Every feature shipped as a separate PR squashed into `main`:

1. `feature/auth-and-users` — User model, JWT, login/register
2. `feature/calculations-bread` — BREAD endpoints, dashboard
3. `feature/new-calc-types` — power, modulus, square_root tests
4. `feature/profile-and-password` — /users/me + audit log
5. `feature/stats-report` — /users/me/stats + page
6. `feature/admin-dashboard` — is_admin + admin endpoints + page
7. `feature/alembic-migrations` — migrations replacing create_all
8. `feature/ci-cd` — GitHub Actions workflow
9. `chore/docs-and-reflection` — this README + REFLECTION + e2e tests

Each branch passed local tests before push; each PR ran CI before merge.
The squash strategy keeps `main`'s history readable as a list of features
rather than a noisy stream of work-in-progress commits.
