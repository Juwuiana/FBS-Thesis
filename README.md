

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
- Added browser-side inactivity timeout handling with a countdown warning.

## Merged branches (nurse/patient + admin + green-metrics)

This tree is the union of three feature branches: admin-data-management (accounts, privacy,
audit trails), nurse-patient-combine (screening intake, nurse workspace, patient portal), and
this branch's own Green Computing module. `docs/CONVERSATION_SUMMARY.md` has the full history;
the short version:

- `health_worker` accounts now land on `/nurse_dashboard` and cannot reach `/admin/*`;
  `medical_officer` accounts land on `/admin/dashboard` and can also use the nurse workspace.
  (The note above about nurse accounts redirecting to the admin dashboard "until the nurse
  branch is merged" is what this fixes — see the merge entry at the top of `CHANGELOG.md`.)
- Every nurse route requires a signed-in `health_worker` or `medical_officer`; every admin route
  requires `medical_officer`. Neither was gated before the merge.
- `visit_model.create_visit()` now feeds the Green Computing offline queue
  (`docs/NURSE_BRANCH_INTEGRATION.md`) — a screening saved during a real outage is queued
  automatically, no nurse-branch code changes needed.
- The nurse/patient pages no longer load Chart.js, Font Awesome or Google Fonts from a CDN
  (vendored into `app/static/vendor/`, matching the admin pages).
- **Still open**: there is no real patient login (patients aren't `users` and have no
  credential). The patient portal fails closed — every `/patient_*` route 404s — until that
  design exists; see the note at the top of `app/controllers/patient_controller.py`.

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

Run from project root to populate model:

```powershell
python scripts/import_phase4_results.py data/enns_only_phase5_summary.json
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

## Green metrics (Android edge server)

The Energy & Green Metrics page (`/admin/green-computing`, medical officers only) and its JSON API
(`/api/v1/green/*`) read real data from four tables added by **`0012_create_green_metrics.sql`**:
`green_computing_log`, `system_telemetry_log`, `sync_queue_log`, `network_event_log`.
**Copy `0012` to the nurse/patient branch in the same commit**, like every other migration.

| Page element | Source |
|---|---|
| Energy Today / Carbon | `system_telemetry_log` (whole phone) when telemetry exists, else model-run energy only. The card says which. |
| Green Score + breakdown | see definitions below; 7-day window, compared with the previous 7 days |
| Energy & Carbon Tracker | same source as Energy Today, hourly (24 h) or daily (7/30/90 d) |
| Energy Breakdown | ML inference, web/LAN and DB I/O from `green_computing_log` (device power x time in each); "Idle & Other" = telemetry energy minus those |
| Offline & Sync, Embedded Screening Display | `sync_queue_log` joined to `visits` / `patients` / `lab_screenings` (soft-deleted patients hidden); "View All" opens `/admin/green-computing/pending` |
| Connectivity Timeline, Offline Events | `network_event_log` (a DISCONNECT and the RECONNECT sharing its `gap_identifier`); "View full events log" opens `/admin/green-computing/events` |
| Connectivity monitor warning | `app_settings` heartbeat written by `flask connectivity-monitor`; the page warns when it has never run or is stale |

Score definitions: **Energy Efficiency** = latency vs `FBS_TARGET_LATENCY_MS`; **Carbon per Screen** =
attributed energy per screening vs `FBS_TARGET_KWH_PER_SCREEN`; **Idle Power Usage** = `FBS_TARGET_IDLE_W`
vs measured idle draw; **Renewable Usage** = share of telemetry samples on `SOLAR_UPS`. Score = mean of the
available parts; Renewable counts only when `FBS_POWER_FEED=solar_ups`.

The model is called through `metrics_controller.run_measured_prediction()` (or `POST /api/v1/predict`),
which returns `green_log_id`; the nurse flow links it with `green.link_lab_screening(db, log_id, lab_screening_id)`
after saving. Until `app/ml/artifacts/model.joblib` (or `FBS_MODEL_PATH`) exists a flagged stub runs and
`/health` shows `model_loaded: false`.

### Connectivity monitor and offline queue
Three parts, all in `app/services/`:

1. **`connectivity.py` - link-loss detection.** `flask --app run connectivity-monitor` tries a TCP connect to
   each `FBS_PROBE_TARGETS` entry every `FBS_PROBE_INTERVAL_S` seconds (nothing is sent). The link goes
   **down after `FBS_PROBE_FAIL_THRESHOLD` consecutive failures** and **up after `FBS_PROBE_OK_THRESHOLD`
   consecutive successes** (debounced, so a single dropped probe is ignored). Defaults detect a loss in about
   45 s. Transitions are written to `network_event_log` as `DISCONNECT` / `RECONNECT`, back-dated to the first
   failed / first good probe and tied together by a `gap_identifier`. State is derived from the event log, so
   restarting the monitor continues an open gap. It writes a heartbeat so the dashboard can warn when the
   monitor itself is not running. `flask --app run connectivity-status` does one probe and prints what the
   database currently believes.
2. **`sync_queue.on_visit_saved(db, visit_id)` - the integration point.** The nurse/patient branch calls it
   when it saves a visit. If the link is down the visit is queued in `sync_queue_log`; if the link is up it
   does nothing. It never commits and never raises. See `docs/NURSE_BRANCH_INTEGRATION.md`.
3. **`sync_queue.flush_pending(db, transport)`** hands queued records to a `SyncTransport` after a
   reconnect, updates each row (`SYNCED` / `FAILED` with attempts and last error) and logs `SYNC_*` events.
   **No transport is configured by default** (`FBS_SYNC_TRANSPORT=none`): there is no upstream server yet, so
   queued records honestly stay `QUEUED`. Register one with `register_transport()` when an upstream exists.

**What does "online" mean here?** That is a deployment decision (`FBS_PROBE_TARGETS`). Default = the internet
(public DNS). Point it at the clinic router (for example `192.168.1.1:80`) to watch the phone's Wi-Fi link
instead, or at an upstream server. A site with no internet at all reads "offline" permanently with the
default, so choose a target that matches what you want to monitor.

### On the phone
- `flask --app run connectivity-monitor` (started for you by `scripts/termux_start.sh`).
- `flask telemetry-loop` (run beside the web server; `--idle` for a few minutes with no traffic to measure
  the baseline, then set `FBS_IDLE_POWER_W`).
- Set `FBS_EMISSION_FACTOR` (0.6 is a placeholder), `FBS_POWER_FEED`, and check `FBS_CURRENT_UNIT`.
- Never run with `FLASK_DEBUG=1` on the phone. `run.py` now enables debug only when that variable is set.
- Bootstrap, Bootstrap Icons and Chart.js are vendored in `app/static/vendor/` so the admin pages work
  with no internet. (`auth/login.html` and `auth/signup.html` still request Google Fonts.)
- Demo data: `python -m scripts.seed_green_demo` and `--purge` to remove it.
- Tests: `pip install pytest` then `pytest` (37 tests: measurement, API, demo flow, monitor state machine,
  queue/flush, view-all pages, CLI).

### Known limits (write these in the thesis)
- Per-inference energy comes from one battery sample before and one after; it is whole-phone power
  attributed to the inference, not a per-process meter. Inference energy is tiny next to idle draw.
- `db_io_ms` is estimated from earlier commits, not timed per query.
- Renewable share counts samples, and SOLAR_UPS can't be detected from sysfs; it comes from `FBS_POWER_FEED`.
- Link-loss detection has a delay of about `FBS_PROBE_FAIL_THRESHOLD x FBS_PROBE_INTERVAL_S` (45 s by default);
  the DISCONNECT is back-dated to the first failed probe. If the monitor process itself is down, gaps are not
  recorded (the dashboard warns after ~3 minutes without a heartbeat).
- The monitor sees the *phone's* network link. It cannot see records still held in a staff device's browser
  during a device-to-phone outage; that needs the client draft queue (not built).
- Records stay `QUEUED` until a sync transport is registered.

### Presenting the Green Computing page
    set FBS_DEMO_MODE=1            (use `export` on Linux/Termux)
    flask --app run create-admin
    python run.py                  -> sign in -> Green Computing
With `FBS_DEMO_MODE=1` the page shows demo controls (medical officers only): **Load 3-day history**,
**Run screening / Run 10** (real measured inferences), **Simulate connection loss** (new screenings queue),
**Restore connection & sync** (queue flushes, gap and events are logged), **Clear demo data**. The page reloads
itself every 30 s. Demo data is labelled `seeded`/`DEMO-` and is removed by Clear. On the phone the
Live Inference Log's Source column reads `battery`; on a laptop it reads `estimated`.
Turn demo mode off for real use: the demo routes then return 404 and Retry Sync is disabled. Do not use the
simulate/restore buttons while the real connectivity monitor is running ("Run screening" is fine).

### Model benchmark (thesis Objective 3: accuracy vs. on-device efficiency)
    pip install scikit-learn lightgbm xgboost      # training-machine or phone, not the app's own runtime deps
    python -m scripts.benchmark_models             # synthetic placeholder data, all models, 30 runs each
    python -m scripts.benchmark_models --dataset real_data.csv --features age,bmi,fbs_mg_dl,bp_systolic,bp_diastolic --label risk_level
    python -m scripts.benchmark_models --runs 100 --csv results.csv --json results.json

Trains Random Forest / LightGBM / XGBoost plus a smaller "_optimized" variant of each (fewer,
shallower trees — a pruning-style efficiency comparison that will actually run on the phone,
unlike GPU-only quantization toolchains), then times **each one exactly the way the live app
would run it**: one screening = one call to `model.predict()`, wrapped in the same
`app/ml/green_metrics.measure()` the Green Computing module uses, so latency/CPU/RAM/power/
energy/carbon numbers are directly comparable to what the dashboard reports for real
screenings. Prints a table sorted by energy per inference; `--csv`/`--json` for the thesis
write-up. Skips a model family gracefully if its library isn't installed. Uses a synthetic
placeholder dataset until the real training data / trained model exists (per
`docs/CONVERSATION_SUMMARY.md`) — pass `--dataset` once it does. This script is standalone: it
does not write to the app's database (see the controlled-test-run protocol in
`docs/TERMUX_TEST.md` for logging real production inferences instead).

### Documentation
`docs/TERMUX_TEST.md` (phone test guide), `docs/NURSE_BRANCH_INTEGRATION.md` (what the nurse branch must
call), `docs/CONVERSATION_SUMMARY.md` (decisions and open items), `CHANGELOG.md`.

### Testing on a phone
See `docs/TERMUX_TEST.md` (Termux install, battery check, demo run, idle baseline, test protocol).
Use `requirements-phone.txt` on the phone; `requirements.txt` is a full desktop freeze.
