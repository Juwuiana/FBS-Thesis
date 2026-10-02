# Admin privacy retention layout

- **Updated:** consolidated the Recycle Bin and active-patient retention controls into matching responsive cards in Data Privacy. Saving either policy now returns to that tab.

# Patient record retention

- **Added:** admin review confirmation with exact record-count and irreversible-action checks, archive-first selection binding, permanent deletion, consent-driven deletion, atomic batch processing, and one Critical audit event per successful batch.
- **Fixed:** patient anonymization now clears direct identifiers, portal credentials, login events, free-text identifying details, and assigns a collision-safe `ANON-<id>` code while retaining de-identified screening results for analytics.
- **Fixed:** anonymized patients are excluded from active patient, nurse workflow, export, sync, and portal-history lookups while remaining in aggregate health analytics.
- **Verified:** retention tests cover rollback in both modes, cascade deletion, confirmation failures, portal login rejection, audit details, and visibility behavior.

# Staff password recovery

- **Fixed:** Recycle Bin records now use a separate configurable 7-, 15-, or 30-day undo window (15 days by default), with hourly automatic purging, immediate purge on policy changes, and a system audit event for removals.
- **Fixed:** removed decorative Data Privacy controls and duplicate content-use text from the admin Privacy &amp; Security page.
- **Added:** replaced fictional municipality agreement rows with the two real LHU stations and a shared read-only Data Handling and Confidentiality Agreement modal.
- **Removed:** retired the redundant global all-role sign-out control from the privacy settings area; per-role Force Sign-Out remains available under Access Roles &amp; Permissions.
- **Fixed:** simplified the admin Access Roles &amp; Permissions table to the real Patient and LHU Nurse roles, and renamed the first Privacy &amp; Security tab from “Password &amp; Login” to “Password.”
- **Added:** wired the real patient portal login and personal-data export into the same role-control system as staff, including patient login/export toggles and patient-only force sign-out with role-scoped security versions.
- **Added:** rebuilt admin Data Privacy access controls around the two real staff roles, with role-scoped login enablement, nurse-only export permission, and isolated force-signout actions.
- **Fixed:** removed the fictional four-tier permissions table and duplicate decorative Data Retention Policy section from the admin Privacy & Security page.
- **Added:** a self-contained nurse dashboard "Patients by Barangay" widget with a capped AJAX patient list, barangay filter, compact risk table, and direct links to patient files; it reuses the existing latest-screening patient query.

- **Fixed:** made the admin recycle-bin retention control trigger the existing automatic purge, with 6-, 12-, 24-month, and manual-only policies persisted in `app_settings`.
- **Added:** replaced the decorative salt-cipher text with the actual Werkzeug password-hashing method (`scrypt`) and repurposed salt rotation as a real global session-invalidation action using a security-version counter; the UI is explicitly no longer presented as field-level AES-256-GCM encryption.
- **Added:** focused coverage for retention persistence and purge behavior, Never Purge, and invalidating other active sessions without signing out the initiating administrator.
- **Added:** real configurable failed-login tracking with 3-, 5-, and 10-attempt thresholds; accounts reaching the threshold enter the existing administrator password-recovery flow.
- **Fixed:** removed the decorative admin 2FA controls and fake recent-login implication from Privacy & Security; the admin Password & Login tab now contains only password change controls.

- **Fixed:** standardized staff facility codes and labels on `LHU I`/`LHU II`, including repair of existing accounts saved with the old codes.
- **Added:** functional admin and nurse password changes with shared validation, password hashing, and `Password changed` audit events.
- **Fixed:** admin and nurse flash messages are now visible after redirected actions.
- **Added:** persistent per-account avatar uploads with size/type validation, stored filenames, and migration `0022_add_user_avatar_filename.sql`.

- **Added:** staff-account password recovery for `health_worker` and `medical_officer` accounts, including anti-enumeration email handling, administrator reset, one-time temporary passwords, and audit events.
- **Added:** migration `0020_add_recovery_status.sql`, which widens `users.status` with the `recovery` value while preserving existing accounts and the email index.
- **Added:** Data Management recovery status filtering, reset action, and inline temporary-password handoff modal.
- **Verified:** focused recovery tests cover the recovery transition, login blocking, administrator reset, and rejection of non-recovery resets; `flask db-check` passes after migration.

# Green integration fix — nurse screening

- **Fixed:** `nurse_screening_submit()` now routes its model inference through `metrics_controller.run_measured_prediction()` instead of the legacy `app.models.ml_model.predict_risk()` path.
- **Fixed:** each nurse screening inference now creates a `green_computing_log` row and links it to the saved `lab_screenings.id`.
- **Preserved:** the existing nurse screening workflow, preliminary/final risk handling, and lab-screening persistence remain unchanged.
- **Added:** `tests/test_nurse_green_integration.py` verifies that a nurse screening submission creates a linked GREEN inference log and persists the stub prediction on Termux-compatible configurations without a battery sensor.
- **Validation note:** full pytest execution requires Flask/pytest dependencies in the validation environment; this build was statically compiled and inspected here. The existing phone environment already has the required runtime dependencies from `requirements-phone.txt`.

## Model-energy benchmark script (thesis Objective 3)
- **Added** `scripts/benchmark_models.py`: trains Random Forest / LightGBM / XGBoost plus a
  smaller "_optimized" variant of each, then benchmarks every candidate through the exact same
  `app/ml/green_metrics.measure()` wrapper the live app uses for real screenings, so the numbers
  are directly comparable to the Green Computing dashboard. Reports accuracy, F1(macro), model
  size, and latency/CPU/RAM/power/energy/carbon percentiles; `--csv`/`--json` output for the
  thesis write-up; `--dataset` to swap the synthetic placeholder for real training data once it
  exists; gracefully skips a model family if its library isn't installed.
- **Verified end-to-end**, not just written: ran it for real with scikit-learn/lightgbm/xgboost
  installed (all six candidates trained and benchmarked correctly), with a real CSV dataset via
  `--dataset`, with `--models` filtering, with CSV/JSON export, and against both a fake
  discharging-battery sysfs directory (`measurement_method: battery`) and no battery sensor
  (`measurement_method: estimated`) to confirm both code paths work.
- **Added** 5 tests (`tests/test_benchmark_models.py`); 42 total across the project.

## Merged: nurse/patient branch integrated + access-control and integration fixes
- **Merged** `feature/nurse-patient-combine` into this tree: `nurse_controller.py`, `patient_controller.py`,
  the `*_model.py` files, and the nurse/patient templates and static assets. Confirmed byte-identical
  shared files first (`app/db.py`, migrations 0001-0011) so this was a clean union, not a rewrite.
- **Fixed**: `nurse_bp` and `admin_bp` had no blueprint-wide role guard — any logged-in user of any role
  (or, for nurse routes, anyone at all) could reach them. Added `require_role_for_blueprint()` in
  `auth_views.py` and applied it: `admin_bp` -> `medical_officer` only, `nurse_bp` -> `health_worker`/
  `medical_officer`. Verified with real sessions: an anonymous request now gets redirected, a
  `health_worker` gets 403 from `/admin/*`, a `medical_officer` gets 200.
- **Fixed**: login always redirected to `admin.dashboard` regardless of role. Added `_home_for_role()`
  so a `health_worker` lands on `/nurse_dashboard` and a `medical_officer` on `/admin/dashboard`.
- **Superseded:** the earlier merge note described the patient portal as fail-closed because patient
  authentication was incomplete. The portal now has real patient credentials, login, and protected
  self-service routes; the current role-control entry above documents the active behavior.
- **Fixed**: `visit_model.create_visit()` — the nurse branch's actual save path — never called the
  Green Computing module's offline queue. Added the one-line integration from
  `docs/NURSE_BRANCH_INTEGRATION.md` (`sync_queue.on_visit_saved(conn, visit_id)`, same transaction,
  before `commit()`). Verified end-to-end: a visit saved while the link is down now lands in
  `sync_queue_log` and appears on the Green Computing page.
- **Fixed**: nurse/patient templates loaded Chart.js, Google Fonts and Font Awesome from CDNs
  (`nurse_base.html`, `nurse_dashboard.html`, `nurse_health_results.html`, `patient_base.html`) —
  the same offline-LAN violation already fixed on the admin side. Vendored Font Awesome into
  `app/static/vendor/fontawesome/`, pointed Chart.js at the already-vendored copy, dropped the
  Google Fonts link, and added a system-font fallback in `nurse_base.css`/`patient_style.css`.
- **Fixed**: nurse's own `create_app()` defined `@app.route('/')`, colliding with `auth_bp`'s `/`.
  Dropped nurse's copy; `auth.index` (role-aware) is now the only one.
- **Ported**: the `safe_url_for` Jinja global from nurse's `create_app()` — `nurse_base.html` and
  `patient_base.html` depend on it and would 500 without it.
- **Noted, not changed**: nurse's `requirements.txt` was UTF-16 and added `Flask-SQLAlchemy`/
  `SQLAlchemy`, neither of which is imported anywhere in its code. The merged tree keeps the
  existing UTF-8 `requirements.txt` and drops both as dead weight.
- **Verified**: all 37 existing tests still pass on the merged tree; booted the merged app for real
  (migrations, `create-admin`, a seeded `health_worker` account) and checked every fix above by
  hitting the running server, not by reading code.

# Changelog — feature/green-metrics

Newest first. Each entry says what changed and why, for anyone picking up this branch later.

## Connectivity monitor, offline queue, and "view all" pages
- **Added** `app/services/connectivity.py`: a debounced link-loss monitor (`flask --app run
  connectivity-monitor`, `connectivity-status`). Writes DISCONNECT/RECONNECT to
  `network_event_log`, back-dated and grouped by `gap_identifier`; state survives a restart by
  reading the event log; writes a heartbeat for the dashboard warning.
- **Added** `app/services/sync_queue.py`: `on_visit_saved(db, visit_id)` — the single call the
  nurse/patient branch makes to queue a record saved while offline — and `flush_pending(db,
  transport)` with a pluggable `SyncTransport` (no transport registered by default: there is no
  upstream yet, so records honestly stay `QUEUED`).
- **Added** `/admin/green-computing/events` and `/admin/green-computing/pending`: paginated,
  filterable "view all" pages for the Events Log and the offline-records table. Both were
  previously "today only" with a dead `View All` link.
- **Changed** `app/controllers/demo_controller.py` to drive these real services instead of
  writing rows by hand, so the presentation controls exercise the same code path production
  would use.
- **Added** `docs/NURSE_BRANCH_INTEGRATION.md`, `docs/CONVERSATION_SUMMARY.md`.
- **Added** 22 tests (`tests/test_connectivity.py`, `tests/test_green_pages.py`); 37 total.

## Phone testing support
- **Added** `requirements-phone.txt` (pure-Python subset); `requirements.txt` is a full desktop
  freeze that will not build on Termux.
- **Fixed**: battery readings taken while charging (current flowing *into* the battery) were
  previously reported as consumption. They are now labelled `estimated` and telemetry stores
  `NULL` power for those rows.
- **Added** `scripts/termux_setup.sh`, `scripts/termux_start.sh`, `scripts/battery_probe.py`,
  `docs/TERMUX_TEST.md`.

## Presentation / demo mode
- **Added** `FBS_DEMO_MODE`: a control bar on the Green Computing page (Run screening, Simulate
  connection loss, Restore & sync, Load/Clear demo history) for defenses and reviews, gated to
  medical officers and off by default.
- **Added** the Live Inference Log (latency, CPU, RAM, power, energy, carbon per run) and made
  the Energy Breakdown donut show active components only, with idle stated as a note (idle power
  is normally >99% of total phone energy — the donut was unreadable otherwise).

## Rebuilt on the real (admin-branch) schema
- **Replaced** the placeholder tables from the first draft with **`0012_create_green_metrics.sql`**
  on top of the actual `0001`–`0011` migrations. `green_computing_log.lab_screening_id` points at
  the real `lab_screenings` table (`ON DELETE SET NULL`) — the thesis's `Risk_Assessment` entity
  does not exist as a table; the model's output lives on `lab_screenings`.
- **Added** access control: `/api/v1/green/*` and the page require the `medical_officer` role
  (the page was previously open to any logged-in user).
- **Vendored** Bootstrap, Bootstrap Icons and Chart.js into `app/static/vendor/` — the admin pages
  previously loaded them from a CDN, which does not work on an offline LAN.
- **Fixed**: `run.py` ran with `debug=True` on `0.0.0.0`, exposing the Werkzeug debugger (remote
  code execution) to the whole LAN. Now opt-in via `FLASK_DEBUG=1`.
- **Added** `flask telemetry-loop` for `system_telemetry_log` sampling and an idle-baseline mode.

## First draft (superseded)
- Initial Flask skeleton filled in against the Green Computing Metrics plan derived from the
  thesis appendix — its own (placeholder) schema, predictor, measurement wrapper and dashboard.
  Rebuilt from scratch once the real admin-branch schema was provided (see above).
