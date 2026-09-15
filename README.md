# FBS-Based Diabetes Prediction System — Auth Feature

Flask backend for the FBS (Fasting Blood Sugar) diabetes risk prediction
system used by LHU (Local Health Unit) personnel. This branch implements
the authentication layer: sign up, log in, log out, session management,
and an admin-approval gate for new accounts.

## Tech stack

- **Flask** — web framework
- **sqlite3** (Python standard library) — database, accessed with **raw SQL**
  (no ORM — see [Why raw SQL + SQLite](#why-raw-sql--sqlite) below)
- **Werkzeug's `security` module** — password hashing (PBKDF2)
- **python-dotenv** — loads local config from `.env`

## Project structure

```
run.py                      # entry point: loads .env, creates the app, runs it
config.py                   # Config class, reads settings from env vars

app/
  __init__.py                # app factory: wires config, db, blueprints, CLI commands
  db.py                       # sqlite3 connection lifecycle (get_db / close_db / init_db)
  schema.sql                  # raw SQL table definitions

  models/
    user.py                   # raw, parameterized SQL queries for the users table

  controllers/
    auth_controller.py        # validation, password hashing, login/signup logic

  views/
    auth_views.py             # routes: /, /login, /signup, /logout, /home
                               # also defines the login_required decorator

  templates/auth/
    login.html
    signup.html
    home.html                 # placeholder landing page after login

  static/
    css/style.css
    js/signup.js, main.js
```

Other folders under `app/` (`dashboard`, `patient`, `ml`, `metrics`, etc.)
are placeholders for other feature branches and aren't touched here.

## Setup

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment variables**
   ```bash
   cp .env.example .env
   ```
   Then edit `.env`:
   - `SECRET_KEY` — generate one with:
     ```bash
     python -c "import secrets; print(secrets.token_hex(32))"
     ```
   - `REQUIRE_ADMIN_APPROVAL` — `True` (default) means new sign-ups can't
     log in until an admin approves them. Set to `False` while developing
     if you want new accounts usable right away.
   - `DATABASE_PATH` — optional; if left unset, the app stores the SQLite
     file at `instance/fbs_thesis.sqlite3` automatically.

3. **Create the database and a first admin account**
   ```bash
   export FLASK_APP=run.py        # Windows (PowerShell): $env:FLASK_APP="run.py"
   flask init-db
   flask create-admin
   ```
   `flask create-admin` prompts for an email/password and inserts an
   account with `status='approved'`, so you have a way to log in and
   approve everyone else.

4. **Run the app**
   ```bash
   python run.py
   ```
   Visit `http://localhost:5000`. 
  dummy account: admin1 - pass1

## CLI commands

| Command | What it does |
|---|---|
| `flask init-db` | (Re)creates tables from `schema.sql`. Safe to re-run — uses `CREATE TABLE IF NOT EXISTS`. |
| `flask create-admin` | Seeds one pre-approved account. |
| `flask approve-user --email <email>` | Flips a pending sign-up to `approved`. |

There's no admin UI yet — approving/rejecting accounts is done via these
CLI commands (or by editing the SQLite file directly) until an admin
dashboard is built on another branch.

## Auth flow

- **Sign up** (`/signup`) — validates all fields server-side (name format,
  email format, PH mobile number, minimum age 18, password ≥ 12 chars,
  passwords match, terms accepted, email not already registered), hashes
  the password, and inserts the user with `status='pending'`.
- **Log in** (`/login`) — looks up the user by email, checks the password
  hash, and rejects the login if the account isn't `approved` yet (when
  `REQUIRE_ADMIN_APPROVAL=True`). On success, stores `user_id`,
  `user_name`, and `user_role` in the Flask session.
- **Session protection** — `login_required` (in `app/views/auth_views.py`)
  is a decorator any future route can use to require an active session;
  it's already applied to the placeholder `/home` route.
- **Log out** (`/logout`) — clears the session.

## Database schema

```sql
CREATE TABLE users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name     TEXT NOT NULL,
    middle_name    TEXT,
    last_name      TEXT NOT NULL,
    birthday       TEXT NOT NULL,
    sex            TEXT NOT NULL CHECK (sex IN ('male', 'female')),
    email          TEXT NOT NULL UNIQUE,
    phone          TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('health_worker', 'medical_officer')),
    facility       TEXT NOT NULL,
    barangay       TEXT NOT NULL,
    password_hash  TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at  TEXT
);
```

Passwords are **never** stored in plaintext — only the PBKDF2 hash
produced by `werkzeug.security.generate_password_hash`.

## Why raw SQL + SQLite

This project runs as an edge module on Android devices and needs a local
database on-device, which shaped both decisions:

- **SQLite instead of MySQL/PostgreSQL/SQL Server** — those need a
  running server process and drivers with C extensions (`psycopg2`,
  `pyodbc`) that are difficult or impossible to cross-compile for Android.
  SQLite is a single file plus the `sqlite3` module already in Python's
  standard library, and it's the same engine Android's own local-storage
  APIs (Room / SQLiteOpenHelper) are built on.
- **Raw SQL instead of SQLAlchemy** — with a single fixed engine, the
  ORM's dialect-abstraction and session/identity-map machinery add memory
  and import overhead without adding value, which matters more on a
  resource-constrained device. The trade-off: there's no migration tool
  and no query-builder safety net, so schema changes are hand-written in
  `schema.sql` and every query **must** use `?` placeholders for
  parameters — never build SQL strings by formatting in user input.

## Security notes for future work

- Add CSRF protection to the login/signup forms (no `Flask-WTF` or manual
  token is wired in yet).
- Rotate `SECRET_KEY` and set real values in `.env` before any real
  deployment — the fallback in `config.py` is for local dev only.
- Consider rate-limiting `/login` to slow down brute-force attempts once
  this is network-reachable rather than fully on-device.
