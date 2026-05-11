# Test User Accounts

These are pre-made test accounts for the FastAPI Calculator final project.
Use them to log in, exercise calculations, and demonstrate the admin
dashboard. **The passwords here are intentionally weak — these accounts
exist for grading and local development only and should never be used
in production.**

## Credentials

| Username | Password     | First Name | Last Name | Email                 | Role    |
|----------|--------------|------------|-----------|-----------------------|---------|
| admin    | Admin123!    | Admin      | User      | admin@example.com     | Admin   |
| alice    | Alice123!    | Alice      | Anderson  | alice@example.com     | Regular |
| bob      | Bob12345!    | Bob        | Brown     | bob@example.com       | Regular |
| charlie  | Charlie123!  | Charlie    | Carter    | charlie@example.com   | Regular |

## Notes

- All passwords meet the validation rules: at least 8 characters, one
  uppercase, one lowercase, and one digit.
- The `admin` account starts as a regular user. To grant admin access,
  run this once after registration (see README for details):

  ```bash
  docker compose exec db psql -U postgres -d fastapi_db \
    -c "UPDATE users SET is_admin = TRUE WHERE username = 'admin';"
  ```

- See `README.md` for the full registration walkthrough and how to log
  into the admin dashboard.
