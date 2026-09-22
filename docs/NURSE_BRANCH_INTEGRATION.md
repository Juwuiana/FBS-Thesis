# Integrating the offline queue into the nurse/patient branch

**Status: done.** `app/models/visit_model.py::create_visit()` now calls this — see the merge
entry at the top of `CHANGELOG.md` for how it was verified end-to-end. The rest of this document
is kept as the reference for *why* the integration looks the way it does, and as a template for
testing it again if `create_visit()` is ever refactored.

The Green Computing module cannot see a screening until the nurse branch saves it. This is the
one call that branch needs to make.

## The call

```python
from app.services import sync_queue

def save_screening(db, ...):
    visit_id = db.execute("INSERT INTO visits (...) VALUES (...)", (...)).lastrowid
    # ... insert lab_screenings, clinical_measurement, etc. ...
    sync_queue.on_visit_saved(db, visit_id)   # <-- add this line
    db.commit()                                # on_visit_saved never commits; you control that
```

This is exactly what `visit_model.create_visit()` does today, right after the `INSERT INTO
visits` and before its own `conn.commit()`.

Call it **inside the same transaction** that saves the visit, right before your `commit()`.
- If the network link is currently down (per the connectivity monitor), the visit is added to
  `sync_queue_log` and shows up on the Green Computing page as pending sync.
- If the link is up, it does nothing.
- It never raises and never blocks a clinical save — a queueing failure is logged, not surfaced
  to the nurse.

## What "the link" means here
`on_visit_saved` reads the state the connectivity monitor (`app/services/connectivity.py`) has
already written to `network_event_log` — it does not itself check the network. The monitor must
be running (`flask --app run connectivity-monitor`, started by `scripts/termux_start.sh`) or
nothing will ever be queued. See the README's "Connectivity monitor and offline queue" section.

## If the model is run from the nurse branch
Use `metrics_controller.run_measured_prediction()` (or `POST /api/v1/predict`) so the run is
measured and logged. It returns `green_log_id`; once you have saved the `lab_screenings` row,
call `green.link_lab_screening(db, green_log_id, lab_screening_id)` so the energy log links back
to the screening it powered.

## What is NOT built yet (do not assume it exists)
- **No draft queue on the staff device itself.** If a nurse's own browser/tablet loses its
  connection to the server phone (not the phone's internet), the server never sees that record
  until the device resends it. That is a separate, larger piece (IndexedDB + resend, idempotent
  by a client-generated ID) that belongs in the nurse branch, not here.
- **No sync transport.** `flush_pending()` exists and is tested, but no `SyncTransport` is
  registered by default, so synced records simply stay `QUEUED` until one is. Register one with
  `sync_queue.register_transport(name, factory)` when an upstream (server, encrypted export, ...)
  exists — see the docstring in `app/services/sync_queue.py`.
- **No real patient login.** `patients` has no credential column and `users.role` only allows
  `health_worker`/`medical_officer`. `patient_bp` now fails closed (404) instead of 500ing, but
  that is a stopgap, not a design — see the note at the top of `app/controllers/patient_controller.py`.

## Testing your integration
`tests/test_connectivity.py::test_on_visit_saved_rules` and `test_on_visit_saved_does_not_commit`
show the expected behavior against a plain sqlite3 connection — a good template for a nurse-branch
test that saves a full visit + screening while the link is down and checks it appears in
`sync_queue_log`.
