

## Recent Work

The following account-management features were implemented:

- Connected Data Management staff records to the SQLite `users` table.
- Added database-backed employee view and role editing.
- Added account approval and rejection actions.
- New public signups are created with `pending` status when admin approval is enabled.
- Pending accounts cannot log in until an admin approves them.
- Rejected accounts cannot log in.
- Added status labels and filters for `Approved`, `Rejected`, and `Pending`.
- Updated station filtering to use `RHU I` and `RHU II`.
- Added a database-backed Add Employee flow.
- Add Employee creates an account with an approved status and a hashed password.
- Add Employee supports the `Health Officer` and `LHU Nurse` roles.
- Added a database-backed Delete Employee action.
- Restored the existing login behavior where nurse accounts redirect to the admin dashboard until the nurse branch is merged.
- Added browser-side inactivity timeout handling with a countdown warning.

## Project Structure

- `run.py` - application entry point
- `config.py` - application configuration
- `app/__init__.py` - Flask app factory and database initialization
- `app/db.py` - connection factory + numbered-migration runner
- `app/models/migrations/` - numbered `.sql` migrations (schema.sql was retired)
- `app/db.py` - SQLite connection management
- `app/models/user.py` - user and staff database operations
- `app/controllers/auth_controller.py` - signup and login logic
- `app/views/auth_views.py` - authentication routes
- `app/views/admin_views.py` - dashboard and Data Management routes
- `app/templates/dashboard/records.html` - staff records table and filters
- `app/templates/admin/add_staff.html` - Add Employee form
- `app/templates/admin/staff_detail.html` - employee view/edit/approval/delete page
- `instance/fbs_thesis.sqlite3` - local SQLite database

## Requirements

- Windows
- Python 3
- The project virtual environment in `venv/`

Dependencies are listed in `requirements.txt`.

## Setup

From the project root in PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

If the virtual environment does not exist yet:

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create or update `.env` as needed. Admin approval should be enabled for normal testing:

```env
REQUIRE_ADMIN_APPROVAL=True
```

## Run the Application

```powershell
.\venv\Scripts\python.exe run.py
```

Then open:

```text
http://127.0.0.1:5000
```

## Account Workflow

### Public signup

1. A user submits the signup form.
2. The account is stored with `pending` status when `REQUIRE_ADMIN_APPROVAL=True`.
3. The user cannot log in while pending.
4. An admin opens the account in Data Management.
5. The admin selects either `Approve Account` or `Reject Account`.

### Add Employee

Admin-created employee accounts are stored as `approved` immediately. The form requires a temporary password, which is stored as a Werkzeug password hash rather than plain text.

Supported roles:

- Health Officer
- LHU Nurse

Supported stations:

- RHU I
- RHU II

### Delete Employee

The Delete Employee action is available on the employee detail page. It uses a POST request, asks for browser confirmation, deletes the matching user from SQLite, and returns to Data Management.

## Status Values

The database supports only these user statuses:

- `pending` - awaiting admin approval
- `approved` - allowed to log in
- `rejected` - denied access

## Admin CLI Commands

The application also includes Flask CLI commands for creating and approving accounts:

```powershell
$env:FLASK_APP = "run.py"
flask create-admin
flask approve-user
```

The `create-admin` command creates an approved administrator account. The `approve-user` command changes a user's status to `approved` by email.

## Validation

The recent changes were checked with:

```powershell
.\venv\Scripts\python.exe -m compileall app run.py config.py
```

The Add Employee flow was also tested against an isolated temporary SQLite database. The test confirmed that the employee record, role, RHU assignment, approved status, and hashed password were saved correctly.

## Notes for the Team

- Do not commit real passwords, secret keys, or personal user data.
- The local SQLite database is environment-specific and should be backed up before destructive testing.
- The nurse branch is not yet merged. Nurse accounts currently follow the existing dashboard redirect until that branch is integrated.
- The Add Employee route uses placeholder birthday, sex, and barangay values because the current form does not collect those fields. These should be replaced when the employee form is expanded.

## Database migrations

The schema is no longer defined by a single `app/schema.sql` (that file is
gone). It is built by numbered migrations in `app/models/migrations/`, applied
in filename order and recorded once each in the `schema_migrations` table.

The migration set is **identical, byte for byte, to the one on the
`feature/nurse-patient-combine` branch**. The two branches still develop
separately, but they now build the same tables, so merging them later is a
code merge rather than a schema reconciliation. Keep it that way: a migration
added on one branch should be copied to the other in the same commit.

| | |
|---|---|
| `0001`-`0008` | barangays, patients, visits, condition catalog, CVD responses, lab screenings, patient soft-delete. Originated on the nurse/patient branch. |
| `0009_create_users.sql` | the accounts table that login/signup read and write. Was `app/schema.sql`. |
| `0010_create_app_settings.sql` | key/value store behind the Privacy & Security page. Was `app/schema.sql`. |
| `0011_unify_accounts_on_users.sql` | makes `users` the single accounts table (see below). |

### `users` is the only accounts table

`0002_create_staff.sql` created a second people table, `staff`, which
`patients`, `visits` and `lab_screenings` referenced as `created_by_staff_id`,
`recorded_by_staff_id` and `override_by_staff_id`. It had no rows and no login
code behind it, while `users` is what auth actually uses. Two account tables in
one database is a bug waiting to happen, so `0011` repoints every one of those
foreign keys at `users(id)`, carries over any `staff` rows, and drops `staff`.

The columns keep their `*_staff_id` names on purpose — renaming them would mean
editing every INSERT in the nurse-branch models for no schema benefit. Read
`staff_id` as "the `users.id` of the staff member who did this".

### Commands

| command | what it does |
|---|---|
| `flask db-status` | lists every migration and whether it has run |
| `flask init-db` | applies pending migrations without starting the server |
| `flask db-check` | runs `PRAGMA foreign_key_check`; exits non-zero on violations |
| `flask db-baseline --all` | marks pending migrations applied **without** running them |

`create_app()` applies pending migrations on startup, so a normal
`python run.py` keeps the schema current and none of the above is required
day to day.

`db-baseline` is for a database that already has the tables a migration would
create — e.g. an `instance/fbs_thesis.sqlite3` built by the retired
`schema.sql`. Because startup migrates before the CLI command runs, set
`SKIP_AUTO_MIGRATE=1` when you use it:

```
SKIP_AUTO_MIGRATE=1 flask db-baseline 0009_create_users.sql
```

The same variable is the escape hatch if a migration ever fails partway and
startup just retries the broken file.

### Adding a schema change

Create the next numbered file, e.g. `0012_add_users_last_seen.sql`, and copy it
to the nurse/patient branch too. **Never edit or rename a migration that has
already been applied anywhere** — the runner keys off the filename, so a rename
makes the file run a second time. (There was already one of these: the nurse
branch's database had both `008_` and `0008_` recorded from exactly that.)

Migrations that rebuild a table run with `PRAGMA foreign_keys = OFF`, which is
unavoidable in SQLite. Run `flask db-check` after writing one.

### Where the database file lives

`app/db.py:database_path()` is the only place a path is resolved:

1. `config["DATABASE"]`
2. `$DATABASE_PATH`
3. whichever of `instance/fbs_thesis.sqlite3` or `fbs_thesis.db` already exists
4. `instance/fbs_thesis.sqlite3`

Step 3 exists so neither branch has to move its working database. Set
`DATABASE_PATH` in `.env` if you want it unambiguous. Nothing else in the
codebase should hardcode a `.db`/`.sqlite3` path.

### Connections

`app/db.py` hands out two kinds, both with `foreign_keys` and `busy_timeout`
set:

- `get_db()` — request-scoped, cached on `flask.g`, closed after the request.
  Use it from views, controllers and models running inside a request.
- `get_connection()` — a fresh standalone connection for CLI and maintenance
  scripts. Same function the nurse/patient branch's models import, so model
  code moves between branches unchanged.
