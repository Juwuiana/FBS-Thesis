

## Contents

1. [Who owns what](#1-who-owns-what)
2. [How to connect this branch to the nurse and patient branch](#2-how-to-connect-this-branch-to-the-nurse-and-patient-branch)
3. [Roles are wrong in this branch — what to change](#3-roles-are-wrong-in-this-branch--what-to-change)
4. [Not finished in this branch](#4-not-finished-in-this-branch)
5. [Recent work](#5-recent-work)
6. [Project structure](#6-project-structure)
7. [Setup and run](#7-setup-and-run)
8. [Account workflow](#8-account-workflow)
9. [Database migrations](#9-database-migrations)


---

## 1. Who owns what

| Area | Branch | Where it lives |
|---|---|---|
| Login, signup, logout, sessions, session timeout | admin | `app/views/auth_views.py`, `app/controllers/auth_controller.py` |
| `users` table, approval, Data Management, admin pages | admin | `app/models/user.py`, `app/views/admin_views.py`, `app/templates/admin/`, `app/templates/dashboard/` |
| Database connection + migration runner | admin | `app/db.py` |
| Nurse pages and `/api/...` endpoints | nurse-patient | `app/controllers/nurse_controller.py`, `app/templates/nurse/` |
| Patient portal | nurse-patient | `app/controllers/patient_controller.py`, `app/templates/patient/` |
| Patient / visit / lab / analytics queries | nurse-patient | `app/models/patient_model.py`, `visit_model.py`, `lab_model.py`, `health_analytics_model.py`, `patient_portal_model.py`, `lookup_model.py` |

How the pieces should fit together after the merge:

```
Browser ──► auth_bp   /login  /signup  /logout
              │   session: user_id, user_name, user_role
              │
              │   role decides where the user lands and what they may open
              ├── admin            ──► admin_bp    /admin/*
              ├── medical_officer ┐
              ├── health_worker   ┴──► nurse_bp    /nurse_*  and  /api/*
              └── patient (future) ──► patient_bp  /patient_*

All blueprints ──► app/db.py ──► ONE SQLite file ──► migrations 0001 … 00NN
```

---

## 2. How to connect this branch to the nurse and patient branch

> Checked by comparing the two branch snapshots and by doing a trial merge in a
> scratch copy: the merged app started on an empty database and on a copy of the
> nurse branch's `fbs_thesis.db`, applied every migration, and served the nurse,
> patient, and admin pages. Git itself may report conflicts slightly differently
> because the snapshots were compared, not the commit history.

### 2.1 Before you start

- Back up your local database file. Migration `0011` rebuilds the `patients`,
  `visits` and `lab_screenings` tables.
- Merge into a throwaway branch first:

```powershell
git checkout feature/admin-data-management
git pull
git checkout -b merge/admin-nurse-patient
git merge feature/nurse-patient-combine
```

### 2.2 Files that will conflict

| File | Resolution |
|---|---|
| `app/__init__.py` | Keep **this branch's** app factory (it has `Config`, `db.init_app`, the CLI commands and the session-timeout hook). Then add the nurse and patient blueprints and `safe_url_for` — see 2.3 step 2. Drop the nurse branch's `run_migrations()` call and its `@app.route('/')`. |
| `run.py` | Keep this branch's (`load_dotenv()` runs before `create_app`). |
| `requirements.txt` | Keep this branch's. The nurse branch's file is saved as UTF-16, so Git treats it as binary and cannot merge it. The only difference is `Flask-SQLAlchemy` and `SQLAlchemy`, and nothing in either branch imports them, so leave them out. |
| `.gitignore` | Keep this branch's (it also ignores `*.db`). |
| `README.md` | Keep this file. Move anything from the nurse README that is still true into section 1 or 2. |

Everything else that exists on both sides is an empty placeholder on one side
(`auth_controller.py`, `auth_views.py`, `login.html`, `signup.html`,
`dashboard/index.html`, `dashboard/records.html`, `metrics/green.html`,
`style.css`, `main.js`, `config.py`, `patient_controller.py`, and so on), so
Git should take the side that has the content. `0001`–`0008` are byte-identical
on both branches; `0009`–`0011` exist only here and come across in the merge.

### 2.3 Required changes after the merge (in this order)

**Step 1 — Make the nurse models use this branch's database layer.**
This is the step that is easiest to miss because Git will not flag it. The
nurse branch has its own `app/models/db.py` that hard-codes `fbs_thesis.db` in
the repo root, and seven nurse/patient files import from it
(`nurse_controller.py`, `patient_model.py`, `visit_model.py`, `lab_model.py`,
`lookup_model.py`, `health_analytics_model.py`, and `reset_data.py`). Left as
is, the merged app would by default keep **users in one database file and
patients in another**, with no error. Replace the contents of `app/models/db.py` with a
shim so the nurse code keeps working unchanged:

```python
# app/models/db.py
"""Compatibility shim: nurse/patient models import from here.
The real implementation is app/db.py."""
from app.db import get_connection, run_migrations  # noqa: F401
```

Also add `from dotenv import load_dotenv; load_dotenv()` at the top of
`reset_data.py`. It runs outside the Flask app, so it does not read `.env`
otherwise and can open a different database file.

**Step 2 — Register the blueprints and keep `safe_url_for`.**
The nurse and patient templates call `safe_url_for(...)`, which the nurse
branch defined inside its `create_app`. In this branch's `create_app`:

```python
    from app.views.auth_views import auth_bp
    from app.views.admin_views import admin_bp
    from app.controllers.nurse_controller import nurse_bp        # from nurse-patient-combine
    from app.controllers.patient_controller import patient_bp    # from nurse-patient-combine

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(nurse_bp)
    app.register_blueprint(patient_bp)

    from flask import url_for
    from werkzeug.routing.exceptions import BuildError

    def safe_url_for(endpoint, fallback="#", **values):
        try:
            return url_for(endpoint, **values)
        except BuildError:
            return fallback

    app.jinja_env.globals["safe_url_for"] = safe_url_for
```

Do **not** keep the nurse branch's `@app.route('/')`. `auth_bp` already owns
`/`. Migrations run from `db.init_db()` in this factory, so remove the nurse
branch's `run_migrations()` call.

**Step 3 — Point everyone at one database file.**
Inside the running app, `config["DATABASE"]` is always set, and it defaults to
`instance/fbs_thesis.sqlite3`. That means the "fall back to an existing
`fbs_thesis.db`" behaviour described in section 9 does **not** kick in when the
app runs. To keep using the nurse branch's existing test data, set this in
`.env`:

```env
DATABASE_PATH=fbs_thesis.db
```

On the next start, migrations `0009`–`0011` are applied on top of it
automatically. (That database has both `008_add_patient_soft_delete.sql` and
`0008_add_patient_soft_delete.sql` recorded; this is harmless.) Otherwise, use
the default `instance/fbs_thesis.sqlite3` and start fresh. Either way, agree on
one path as a team and put it in everyone's `.env`.

The nurse branch commits `fbs_thesis.db` (about 19 test patients and 73 visits).
After the merge, untrack it with `git rm --cached fbs_thesis.db` and keep a local
copy; database files should not be in Git.

**Step 4 — Run it and smoke-test.**

```powershell
$env:FLASK_APP = "run.py"
flask db-status      # every migration should show [x]
flask db-check       # "No foreign key violations."
.\venv\Scripts\python.exe run.py
```

| Check | Expected |
|---|---|
| `/login`, `/signup` | 200 |
| `/nurse_dashboard`, `/nurse_data_management` | 200 |
| `/patient_dashboard` | 200 **only if patient id 1 has a screening**. On an empty database it returns 500 because `patient_dashboard.html` does not handle `has_data = False`. This comes from the nurse/patient branch. |
| `/admin/dashboard` | redirects to `/login` when signed out |
| Sign out from a nurse page | works (`nurse_base.html` already calls `auth.logout`) |

### 2.4 Wiring login into the nurse and patient side

The nurse and patient branch has **no authentication at all** today: those pages
open without signing in, and every "who did this" value is `None`. This branch
provides the login. After signing in, the session contains:

| Session key | Meaning | Use it for |
|---|---|---|
| `user_id` | `users.id` | The `*_staff_id` columns (see below) |
| `user_name` | "First Last" | Sidebars, greetings |
| `user_role` | `admin`, `medical_officer`, `health_worker` (and `patient` if added) | Access checks and redirect after login |
| `last_active` | timestamp | Set by this branch's session-timeout hook. It already applies to every route once a user is signed in. |

**a) Protect every route.** Add this to `app/views/auth_views.py`. It replaces
the current pattern of putting `@login_required` on each admin route:

```python
ROLE_HOME = {
    "admin": "admin.dashboard",
    "medical_officer": "nurse.nurse_dashboard",
    "health_worker": "nurse.nurse_dashboard",
    "patient": "patient.patient_dashboard",
}


def role_guard(*allowed):
    """Blueprint-wide before_request: must be signed in AND have an allowed role."""
    def check():
        if "user_id" not in session:
            flash("Please sign in to continue.", "error")
            return redirect(url_for("auth.login"))
        if session.get("user_role") not in allowed:
            abort(403)
    return check
```

then, right after each blueprint is created:

```python
admin_bp.before_request(role_guard("admin"))
nurse_bp.before_request(role_guard("health_worker", "medical_officer"))
patient_bp.before_request(role_guard("patient"))     # add once patient accounts exist
```

This covers the nurse branch's `/api/...` routes too, because they belong to
`nurse_bp`.

**b) Send each role to the right home page.** `auth_views.py` currently
redirects everyone to `admin.dashboard` in `index()`, `login()` and `signup()`.
Replace each with
`redirect(url_for(ROLE_HOME.get(session.get("user_role"), "auth.login")))`.
Delete the leftover `auth/nurse_placeholder.html` (it is not used).

**c) Record who did what.** Migration `0011` repointed `created_by_staff_id`,
`recorded_by_staff_id` and `override_by_staff_id` to `users(id)`. In
`nurse_controller.py`, replace the hard-coded `None` with `session["user_id"]`:

- `staff_id = None` in the create-patient route (about line 84)
- `staff_id = None` in the follow-up record route (about line 124)
- `staff_id = None` in the CSV import route (about line 446)
- the screening submit route calls `lab_model.create_lab_screening(visit_id, data)`
  without a `staff_id`, so `override_by_staff_id` is never filled (about line 177)

**d) Patient logout.** `patient_base.html` POSTs to `auth.patient_logout`,
which does not exist, so the button currently goes to `#`. Either add that
route, or change the template to `auth.logout` and let `/logout` accept `POST`.

**e) Patient accounts (nobody has built this yet).**
`patient_portal_model.get_current_patient_id()` returns a hard-coded `1`. The
`users` table has no way to say "this account is patient X". The suggested
approach is a `patient` role plus a nullable `users.patient_id` column
referencing `patients(id)` (new migration), and
`get_current_patient_id()` looking that up from `session["user_id"]`. Decide as
a team. If the patient guard is added before patient accounts exist, nobody can
open the patient pages.

**f) Optional but cheap.** The nurse branch's `app/rate_limit.py` can be applied
to `/login`, for example `@rate_limit(max_calls=5, period_seconds=60)`.

### 2.5 Replacing the admin dashboard's sample data

The admin dashboard numbers are hard-coded. After the merge they can come from
the nurse branch's `app/models/health_analytics_model.py`, for example
`get_dashboard_summary()`, `get_risk_status_distribution()`,
`get_top_barangays()` and `get_recent_registries()`.

---

## 3. Roles are wrong in this branch — what to change

### What is wrong

The `users.role` column only allows `health_worker` and `medical_officer`
(`0009_create_users.sql`, `app/schema.sql`), so there is **no admin role**. The
admin was implemented as a **`medical_officer`**, labelled "Health Officer" in
the UI. But a Medical Officer is a **doctor**. As it stands:

- `admin_required` only lets `medical_officer` through, so a doctor is treated as the system admin.
- `flask create-admin` creates a `medical_officer`.
- `ROLE_MAP` and `db_role_from_display()` map `"Health Officer"` (and `"Admin"`) to `medical_officer`.
- `display_role_from_db()` falls back to `"Health Officer"` for any unknown role.
- `0011` maps an old `staff.role = 'admin'` to `medical_officer` (`staff` was empty, so nothing was affected, but the mapping is wrong).

### Target role model

| `users.role` | Who | How the account is created | Can open |
|---|---|---|---|
| `admin` | LHU system administrator | **`flask create-admin` only.** Never through signup, Add Employee, CSV import, or the role-edit page. | `/admin/*` only |
| `medical_officer` | Doctor | Signup (needs approval) or admin Add Employee / import | **Nurse side only** |
| `health_worker` | Barangay Health Worker / LHU Nurse | Signup (needs approval) or admin Add Employee / import | **Nurse side only** |
| `patient` (proposed) | Patient | To be decided (see 2.4e) | Patient side only |

`medical_officer` and `health_worker` must not be able to open anything under
`/admin`.

### What to change

1. **New migration `0012_add_admin_role.sql`.** SQLite cannot change a `CHECK`
   constraint, so rebuild `users` the same way `0011` rebuilds its tables:
   create `users_new` with `role IN ('admin', 'medical_officer', 'health_worker')`
   (add `'patient'` and `patient_id` here if you go with 2.4e), copy the rows,
   drop `users`, rename, and recreate `idx_users_email`. Wrap it in
   `PRAGMA foreign_keys = OFF`, because `patients`, `visits`, `lab_screenings`,
   `audit_log` and `login_events` all reference `users(id)`. Run `flask db-check`
   afterwards. **Do not edit `0009` or `0011`**; they may already be applied.
2. **Convert the existing admin account.** Any account made with
   `flask create-admin` is currently a `medical_officer`. Change it to `admin`
   after `0012` runs (or delete it and create a new one with the fixed command).
   The seeded demo user Linda Walker is also a `medical_officer`, so she stops
   being an admin.
3. **`app/__init__.py`, `create-admin`:** set `"role": "admin"`. On a fresh
   database nobody can open `/admin` until this command has been run, so put it
   in the setup steps.
4. **`app/constants.py`:** rename the `"Health Officer"` label to
   `"Medical Officer"`. Keep `admin` **out of `ROLE_MAP`**, because that map
   feeds the Add Employee dropdown and the CSV import.
5. **`app/controllers/auth_controller.py`:** keep `VALID_ROLES` as
   `("health_worker", "medical_officer")`. Signup, Add Employee and CSV import
   all validate against it, so this is what prevents an admin from being
   signed up or imported. Do not add `admin` here.
6. **`app/models/user.py`:**
   - `display_role_from_db()`: add `admin` → "Administrator", and stop
     defaulting unknown roles to "Health Officer".
   - `db_role_from_display()`: remove `"Admin": "medical_officer"`, and
     `"Encoder"` unless it is really used.
   - `update_user_role()`: refuse to change **to** or **from** `admin`.
7. **`app/views/auth_views.py`:** change `admin_required` to check
   `== "admin"`, and guard all of `/admin/*` (see 2.4a). Right now only the CSV
   import and template routes use `admin_required`; every other admin route
   accepts any signed-in user.
8. **Signup form (`signup.html`):** already offers only Barangay Health Worker
   and Medical Officer; leave it that way.
9. **Hard-coded "Health Officer" text to fix:** the `admin_base.html` sidebar
   (it should show the signed-in user's name and role), the `records.html`
   role filter and import help text, the `privacy.html` 2FA text, and the roles
   table in `admin_views.privacy_security()`.
10. **Labels:** the admin UI calls `health_worker` "LHU Nurse" while signup calls
    it "Barangay Health Worker". Pick one wording and keep it in
    `constants.py`.
11. **Delete `app/schema.sql`.** It is a leftover copy of the old `users` table
    with the same wrong role list.

---

## 4. Not finished in this branch

**Access control and accounts**

- Roles: see section 3.
- Only the CSV import and template routes use `admin_required`. Every other
  `/admin/*` route only needs a signed-in user. In a trial run, a
  `health_worker` could open all admin pages and reject accounts.
- Login sends every role to `/admin/dashboard`.
- Nothing stops an admin from deleting, rejecting or changing the role of their
  own account or the last admin.
- With `REQUIRE_ADMIN_APPROVAL=False`, `authenticate()` skips the status check
  entirely, so `rejected` and `pending` accounts can sign in. "Rejected accounts
  cannot log in" is only true while the flag is `True`.
- No CSRF protection on any POST form (approve, reject, delete, update role,
  import).
- "Forgot password?" (login page) and "Change Password" (admin menu) are dead
  links. There is no password change or reset flow. "Change Profile Photo" is
  saved only in the browser's `localStorage`.
- No rate limiting on login.
- When the database is empty, `seed_demo_users()` creates three approved
  accounts with the password `Password123!`. Remove it before any real
  deployment. `.env.example` also contains a concrete-looking `SECRET_KEY`;
  replace it with a placeholder and rotate it if it was ever used.

**Pages still using hard-coded sample data**

- Admin dashboard, Model Reliability, Green Computing, Audit Trails: all the
  numbers, charts and log rows are literals in `admin_views.py`.
- Privacy & Security: the roles table, LHU agreements and retention policy are
  literals. Only the session timeout is saved (`app_settings`). The 2FA option
  is text only. The 1-minute timeout option is for testing and should be removed.
- `audit_log` and `login_events` tables exist but nothing writes to them.
- The inactivity countdown (JS) is only in `admin_base.html`. The server-side
  timeout applies everywhere, but nurse and patient pages will not show the
  warning until they load `main.js` and the `data-session-timeout-minutes`
  attribute.
- The sidebar identity is hard-coded ("Health Officer", "LHU Cabuyao" here;
  "LHU Santa Rosa" on the nurse side) instead of using the signed-in user and
  the actual LHU.

**Empty placeholder files** (0 bytes): `controllers/dashboard_controller.py`,
`metrics_controller.py`, `model_controller.py`, `patient_controller.py` (the
nurse branch has the real one); `views/dashboard_views.py`, `metrics_views.py`,
`model_views.py`, `nurse_views.py`, `patient_views.py`; `models/patient.py`;
`ml/green_metrics.py`, `ml/predictor.py`;
`templates/patient/intake.html`, `list.html`, `result.html`;
`templates/dashboard/barangay.html` (there is no route for it either).
`auth/nurse_placeholder.html` is unused.

**Clean-up**

- `app/schema.sql` should be deleted (section 3, item 11).
- `das` in the repo root is pasted `git branch -r` output; delete it.
- There are two lists of barangays: `app/constants.BARANGAYS` (stored as a
  text slug in `users.barangay`) and the `barangays` table (used by patients via
  `barangay_id`). The 18 barangays match, but a few labels differ (for example
  "Kanluran (Poblacion Uno)" vs "Kanluran").

---

## 5. Recent work

The following account-management features were implemented:

- Connected Data Management staff records to the SQLite `users` table.
- Added database-backed employee view and role editing.
- Added account approval and rejection actions.
- New public signups are created with `pending` status when admin approval is enabled.
- Pending accounts cannot log in until an admin approves them.
- Rejected accounts cannot log in (only while `REQUIRE_ADMIN_APPROVAL=True`; see section 4).
- Added status labels and filters for `Approved`, `Rejected`, and `Pending`.
- Updated station filtering to use `LHU I` and `LHU II`.
- Added a database-backed Add Employee flow.
- Add Employee creates an account with an approved status and a hashed password.
- Add Employee currently offers `Health Officer` and `LHU Nurse`. **`Health Officer` is the `medical_officer` role and is being renamed to `Medical Officer` (section 3).**
- Added a database-backed Delete Employee action.
- Added CSV template download and all-or-nothing employee import in Data Management.
- Split employee View and Edit pages so read-only details cannot change account data.
- Login still sends every account to the admin dashboard. This is temporary until the merge (section 2.4b).
- Added browser-side inactivity timeout handling with a countdown warning.

## 6. Project structure

- `run.py` - application entry point
- `config.py` - application configuration
- `app/__init__.py` - Flask app factory, CLI commands, session-timeout hook
- `app/db.py` - SQLite connection management + numbered-migration runner
- `app/models/migrations/` - numbered `.sql` migrations
- `app/models/user.py` - user and staff database operations
- `app/models/settings.py` - key/value settings (session timeout)
- `app/constants.py` - barangay list, role and station maps, CSV columns
- `app/controllers/auth_controller.py` - signup and login logic
- `app/views/auth_views.py` - authentication routes and access decorators
- `app/views/admin_views.py` - dashboard and Data Management routes
- `app/templates/dashboard/records.html` - staff records table and filters
- `app/templates/admin/add_staff.html` - Add Employee form
- `app/templates/admin/staff_view.html` - read-only employee details page
- `app/templates/admin/staff_detail.html` - employee edit/approval/delete page
- `instance/fbs_thesis.sqlite3` - local SQLite database (default location)

After the merge, the nurse and patient files listed in section 1 are added
alongside these.

## 7. Setup and run

Requirements: Windows, Python 3, and the project virtual environment in `venv/`.
Dependencies are listed in `requirements.txt`.

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

Copy `.env.example` to `.env` and fill it in. Admin approval should be enabled
for normal testing:

```env
SECRET_KEY=<generate your own>
DATABASE_PATH=instance/fbs_thesis.sqlite3
REQUIRE_ADMIN_APPROVAL=True
```

Run:

```powershell
.\venv\Scripts\python.exe run.py
```

Then open `http://127.0.0.1:5000`.

## 8. Account workflow

### Public signup

1. A user submits the signup form (only `health_worker` and `medical_officer` can be chosen).
2. The account is stored with `pending` status when `REQUIRE_ADMIN_APPROVAL=True`.
3. The user cannot log in while pending.
4. An admin opens the account in Data Management.
5. The admin selects either `Approve Account` or `Reject Account`.

### Admin accounts

Admin accounts **cannot be signed up**. They are created only from the command
line (after the role fix in section 3):

```powershell
$env:FLASK_APP = "run.py"
flask create-admin
```

### Add Employee

Admin-created employee accounts are stored as `approved` immediately. The form
requires a temporary password, which is stored as a Werkzeug password hash, not
plain text.

Roles it may create: Medical Officer and LHU Nurse (health worker). It must
never create an admin.

Supported stations: LHU I, LHU II.

### Delete Employee

Available on the employee detail page. It uses a POST request, asks for browser
confirmation, deletes the matching user from SQLite, and returns to Data
Management.

### Import format

Employee imports are UTF-8 CSV files with these columns:

`first_name`, `middle_name`, `last_name`, `birthday`, `sex`, `email`, `phone`, `role`, `station`, `barangay`, `temporary_password`

Accepted values are `male`/`female` for sex, the two staff role labels for role
(currently `Health Officer`/`LHU Nurse`; `Health Officer` becomes
`Medical Officer` after section 3), `LHU I`/`LHU II` for station, and a
signup-list barangay name or slug. Birthday values should be `YYYY-MM-DD`; the
importer also accepts `MM-DD-YYYY` and `MM/DD/YYYY`, storing them as ISO dates.
Phone values must be 10 digits starting with `9`; a leading `0` or `+63` is
accepted. Files are limited to 1 MB and 500 data rows. Delete files with
temporary passwords after import.

### Status values

- `pending` - awaiting admin approval
- `approved` - allowed to log in
- `rejected` - denied access

### CLI commands

```powershell
$env:FLASK_APP = "run.py"
flask create-admin     # creates an approved administrator (see section 3 for the role fix)
flask approve-user     # sets a user's status to approved, by email
```

### Validation

```powershell
.\venv\Scripts\python.exe -m compileall app run.py config.py
```

The Add Employee flow was tested against an isolated temporary SQLite database:
the record, role, RHU assignment, approved status and hashed password were saved
correctly.

## 9. Database migrations

The schema is built by numbered migrations in `app/models/migrations/`, applied
in filename order and recorded once each in the `schema_migrations` table.
(`app/schema.sql` is the retired predecessor and should be deleted.)

`0001`–`0008` are **byte-identical** to the ones on
`feature/nurse-patient-combine`. `0009`–`0011` exist only on this branch. After
the merge there is one migration folder, so add every new migration there once.

| File | Purpose |
|---|---|
| `0001`–`0008` | barangays, staff (later dropped), patients, visits, condition catalog, CVD responses, lab screenings, patient soft-delete. Originated on the nurse/patient branch. |
| `0009_create_users.sql` | the accounts table that login/signup read and write |
| `0010_create_app_settings.sql` | key/value store behind the Privacy & Security page |
| `0011_unify_accounts_on_users.sql` | makes `users` the single accounts table (see below) |
| `0012` *(to be written)* | adds the `admin` role (section 3) |

### `users` is the only accounts table

`0002_create_staff.sql` created a second people table, `staff`, which `patients`,
`visits` and `lab_screenings` referenced as `created_by_staff_id`,
`recorded_by_staff_id` and `override_by_staff_id`. It had no rows and no login
code behind it, while `users` is what auth actually uses. `0011` repoints every
one of those foreign keys at `users(id)`, carries over any `staff` rows, and
drops `staff`.

The columns keep their `*_staff_id` names on purpose. Read `staff_id` as "the
`users.id` of the staff member who did this".

### Commands

| Command | What it does |
|---|---|
| `flask db-status` | lists every migration and whether it has run |
| `flask init-db` | applies pending migrations without starting the server |
| `flask db-check` | runs `PRAGMA foreign_key_check`; exits non-zero on violations |
| `flask db-baseline --all` | marks pending migrations applied **without** running them |

`create_app()` applies pending migrations on startup, so a normal `python run.py`
keeps the schema current.

`db-baseline` is for a database that already has the tables a migration would
create. Because startup migrates before the CLI command runs, set
`SKIP_AUTO_MIGRATE=1` when you use it:

```powershell
$env:SKIP_AUTO_MIGRATE = "1"
flask db-baseline 0009_create_users.sql
```

The same variable is the escape hatch if a migration fails partway and startup
keeps retrying the broken file.

### Adding a schema change

Create the next numbered file (for example `0013_add_users_last_seen.sql`).
**Never edit or rename a migration that has already been applied anywhere.** The
runner keys off the filename, so a rename makes the file run a second time.
(This already happened once: the nurse branch's database has both `008_` and
`0008_` recorded.)

Migrations that rebuild a table run with `PRAGMA foreign_keys = OFF`, which is
unavoidable in SQLite. Run `flask db-check` after writing one.

### Where the database file lives

`app/db.py:database_path()` is the only place a path is resolved:

1. `config["DATABASE"]`
2. `$DATABASE_PATH`
3. whichever of `instance/fbs_thesis.sqlite3` or `fbs_thesis.db` already exists
4. `instance/fbs_thesis.sqlite3`

Inside the running app, `create_app()` always fills in `config["DATABASE"]`
(defaulting to `instance/fbs_thesis.sqlite3`), so steps 3 and 4 only matter for
standalone scripts such as `check_tables.py`. **To use an existing
`fbs_thesis.db`, set `DATABASE_PATH` in `.env`** (section 2.3, step 3). Nothing
else in the codebase should hardcode a `.db` or `.sqlite3` path.

### Connections

`app/db.py` hands out two kinds, both with `foreign_keys` and `busy_timeout` set:

- `get_db()` - request-scoped, cached on `flask.g`, closed after the request.
  Use it from views and controllers running inside a request.
- `get_connection()` - a fresh standalone connection for CLI and maintenance
  scripts. The nurse/patient models call this same function, but they import it
  from `app.models.db`, so after the merge that file must be the small shim
  shown in section 2.3, step 1.

