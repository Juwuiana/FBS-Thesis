# Conversation summary — Green Computing module (feature/green-metrics)

Compressed record of the design conversation, for anyone (including future you) picking this
branch back up. Newest decisions last where it matters; otherwise grouped by topic.

## Context
- **Thesis**: FBS (fasting blood sugar) diabetes-risk screening system for a single Local Health
  Unit — the Santa Rosa City Health Office — which has **wattage/power problems** and **no
  reliable internet**. Dedicated desktop server units are not usable there.
- **Chosen architecture**: a **repurposed Android phone runs the server** (Flask, under Termux),
  serving CHO workstations over a local Wi-Fi/hotspot LAN. The phone's own battery is the power
  plan — it keeps serving through a mains outage, which a plugged-in desktop could not.
- **Objective**: a Green Computing Metrics Interface (admin dashboard) showing energy/carbon per
  inference, connectivity status, and an offline/sync indicator, per the thesis draft (Ch. 1–3,
  Appendices G/I/K).

## How the branch evolved
1. **First pass**: built the Green Computing module against an *empty skeleton* zip and the
   thesis's own Appendix G sketch (a `Green_Computing_Log` with only `log_details`). Invented a
   full schema (`users`, `screening_record`, `risk_assessment`, ...) to make it runnable.
2. **Schema correction**: the user supplied the *real* admin-branch zip with an actual working
   schema (migrations 0001–0011: `patients`, `visits`, `lab_screenings`, `users.role` =
   `health_worker`/`medical_officer`, soft-deleted patients, etc.) and an already-built (but
   hard-coded) Green Computing page. Everything was **rebuilt from scratch** on that schema:
   - One new migration, `0012_create_green_metrics.sql`, adds `green_computing_log` (linked to
     `lab_screenings`, not a nonexistent `Risk_Assessment` table), `system_telemetry_log`,
     `sync_queue_log`, `network_event_log`.
   - The existing hard-coded `green.html` page was wired to real queries instead of building a
     second dashboard.
   - Access control added: the page and API require `medical_officer` (previously open to any
     logged-in user).
   - Vendored Bootstrap/Icons/Chart.js locally — the admin UI was loading them from a CDN, which
     contradicts "offline LAN, no WAN required."
   - Found and fixed `run.py` running `debug=True` on `0.0.0.0` (remote-code-execution exposure
     on the LAN); made it opt-in via `FLASK_DEBUG`.
3. **Interface-first request**: the user asked to get the *interface* working and presentable
   before the rest of the edge/offline plumbing. Added `FBS_DEMO_MODE` — a control bar (Run
   screening, Simulate connection loss, Restore & sync, Load/Clear demo history) driving real
   code paths — plus a Live Inference Log (latency/CPU/RAM/power/energy/carbon per run) and made
   the Energy Breakdown donut show active components only (idle is normally >99% of phone energy
   and made the ring unreadable otherwise). Verified end-to-end in a headless browser.
4. **Termux/phone testing**: added `requirements-phone.txt` (the full `requirements.txt` is a
   desktop freeze — numba/opencv/matplotlib — that won't build on Termux), `battery_probe.py`,
   `termux_setup.sh` / `termux_start.sh`, and `docs/TERMUX_TEST.md`. **Bug fixed here**: battery
   readings taken *while charging* were being reported as consumption; the sensor actually shows
   charge current in that state. Now labelled `estimated` and telemetry stores `NULL` power for
   those rows.
5. **Thesis cross-check**: read the actual thesis PDF (Ch. 1–3 + appendices). Confirmed: single
   facility, phone-as-server, CodeCarbon cited (the build uses direct battery-node sampling
   instead, with CodeCarbon as an optional benchmark cross-check), and that "sync" in the paper
   means a **browser-side offline queue with a status indicator**, not phone-to-central-server
   sync — there is no central server in scope. This ruled out an earlier multi-site/roll-up
   design direction as future work, not thesis scope.
6. **Success-indicator audit**: checked the module against the client's stated indicators (Green
   Score, Energy Today/Carbon cards, real-time tracker, energy breakdown, events log, pending
   table, queued/synced summary). All seven UI elements existed and read real data, **except**
   that connectivity/sync rows were only ever produced by the demo buttons — nothing in
   production code wrote them. Three gaps were named and then closed (this session):
   - "View All" pages for the events log and pending table → done
     (`/admin/green-computing/events`, `/admin/green-computing/pending`, paginated + filterable).
   - A function the nurse branch calls when a record is saved during an outage → done
     (`app/services/sync_queue.on_visit_saved`; see `docs/NURSE_BRANCH_INTEGRATION.md`).
   - Real link-loss detection → done (`app/services/connectivity.py`, a debounced TCP-probe
     monitor with `flask connectivity-monitor` / `connectivity-status`).
7. **Online/offline design for a power-constrained clinic** (this session's design discussion):
   - Nurses ideally work **on the server phone itself** (`localhost`) so nothing depends on the
     clinic router; other devices join the phone's own hotspot, so a mains outage only has to
     keep the phone alive, not a router too.
   - A device that loses the server phone should keep a local draft and resend once reachable
     (client-side; **not built** — belongs to the nurse branch, needs a client-generated ID for
     idempotent resend).
   - The admin dashboard should only ever show **counts**, never patient data, for anything still
     sitting on a device the server can't see.
   - Decision still open: do nurses work directly on the server phone, or on their own separate
     devices? This determines whether the client-side draft queue is actually needed.

## Current state of the offline/connectivity system
- `flask --app run connectivity-monitor`: probes `FBS_PROBE_TARGETS` (default: the public
  internet — change this to the router's address to watch the *local* Wi-Fi link instead, since a
  site with no internet at all would otherwise read "offline" permanently) every
  `FBS_PROBE_INTERVAL_S` seconds; debounced up/down after `FBS_PROBE_FAIL_THRESHOLD` /
  `FBS_PROBE_OK_THRESHOLD` consecutive results (~45 s detection delay by default); writes
  DISCONNECT/RECONNECT to `network_event_log`, back-dated to the first failing/succeeding probe;
  state is derived from that log so a restart continues an open gap; writes a heartbeat so the
  dashboard can warn if the monitor itself isn't running.
- `sync_queue.on_visit_saved(db, visit_id)`: the one integration point for the nurse branch.
  Queues a visit in `sync_queue_log` if the link is currently down; never commits, never raises.
- `sync_queue.flush_pending(db, transport)`: sends queued records through a pluggable
  `SyncTransport` after reconnect, marks each `SYNCED`/`FAILED` (with attempts/last error), logs
  `SYNC_*` events. **No transport is registered by default** — there is no upstream server in
  scope yet, so records honestly stay `QUEUED` until one exists.
- 37 tests pass (`pytest`), including the monitor's debounce/backdating/restart behavior and the
  queue's commit boundary and failure/retry handling.

## Branch merge (nurse/patient + admin + green-metrics)
The user later supplied fresh zips of the admin and nurse/patient branches and asked whether all
three could merge and work together. Investigation approach: diffed files across all three trees
first (not guesswork) — found migrations 0001-0011 and `app/db.py` byte-identical between admin
and nurse (nurse's own comments confirm this was deliberate, to keep merges clean), and found
that many "shared" files in each branch's zip are 0-byte placeholders for paths the branch didn't
touch (a real convention, not corruption — confirmed because nothing in either branch's own
`create_app()` imports those particular empty files).

Then actually built the merge, booted it, and tested it with real HTTP requests (not just static
reading), which surfaced concrete bugs:
- `admin_bp`/`nurse_bp` had no blueprint-wide role guard (nurse routes had none at all).
- Login always redirected to `admin.dashboard` regardless of role (the admin branch's own README
  even flagged this as "until the nurse branch is merged").
- `visit_model.create_visit()` (the nurse branch's actual save path) never called
  `sync_queue.on_visit_saved()` — the offline queue existed but wasn't wired to real screenings.
- Root URL (`/`) was defined by both `auth_bp` and nurse's own `create_app()`.
- nurse/patient templates loaded Chart.js/Font Awesome/Google Fonts from CDNs (same offline-LAN
  issue already fixed on the admin side).
- Patient portal has no auth of any kind — not a merge bug, a pre-existing gap the nurse branch's
  own code labels `TODO(auth): ... once the auth branch merges` (patients aren't in `users` and
  have no credential column at all).

All of the above except patient login were fixed (real patient auth is a schema-level feature,
explicitly out of scope — not something to fabricate). Every fix was verified by booting the
merged app and hitting it with curl/sqlite3, not just by reading the diff. See the merge entry at
the top of `CHANGELOG.md` for the exact list, and `README.md`'s "Merged branches" section.

## Model-energy benchmark script
Added `scripts/benchmark_models.py` (thesis Objective 3): trains Random Forest/LightGBM/XGBoost
plus a smaller "_optimized" variant of each, benchmarks every candidate through the same
`measure()` wrapper the live app uses (so numbers are directly comparable to the dashboard),
and reports accuracy/F1/size alongside latency/CPU/RAM/power/energy/carbon percentiles. Verified
by actually running it (installed scikit-learn/lightgbm/xgboost and confirmed real output,
CSV/JSON export, `--dataset` with a real CSV, and both the `battery` and `estimated` code paths).
Uses a synthetic placeholder dataset until the thesis's real training data/model exists.

## Open items / explicitly not built
- Client-side draft queue on individual nurse devices (IndexedDB + idempotent resend) — depends
  on the phone-vs-own-device decision above.
- Any `SyncTransport` implementation (there is nowhere to sync *to* yet).
- Device-side "N drafts pending" reporting to the admin dashboard.
- Low-battery alerting tied to the phone-as-power-plan design.
- Hotspot energy measurement as its own line item.
- Model-energy benchmark script comparing candidate models (Random Forest/XGBoost/LightGBM +
  optimized variant) — done, see "Model-energy benchmark script" above.

## Key files
- Schema: `app/models/migrations/0012_create_green_metrics.sql`
- Services: `app/services/connectivity.py`, `app/services/sync_queue.py`
- Controllers/views: `app/controllers/metrics_controller.py`, `app/controllers/demo_controller.py`,
  `app/views/metrics_views.py`, `app/views/admin_views.py` (routes for the page + both "view all"
  pages)
- Templates: `app/templates/metrics/green.html`, `events_log.html`, `pending_sync.html`
- Phone tooling: `requirements-phone.txt`, `scripts/termux_setup.sh`, `scripts/termux_start.sh`,
  `scripts/battery_probe.py`, `docs/TERMUX_TEST.md`
- Integration contract for the nurse branch: `docs/NURSE_BRANCH_INTEGRATION.md`
- Full history of changes: `CHANGELOG.md`
