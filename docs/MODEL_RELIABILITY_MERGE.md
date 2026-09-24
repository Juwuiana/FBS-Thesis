# Merge notes: feature/model-reliability → feature/second-merge

No git history was included with either branch (both were plain file-tree
exports), so this merge was done by diffing the two trees directly and
reconstructing which side had the real, wanted work.

## What actually came from feature/model-reliability

`model-reliability` had branched off *before* most of second-merge's own
work (nurse/patient portal, green computing, connectivity/sync, vendor
assets, CSS theming) existed, so it was missing all of that — not
deleting it on purpose. Its own real contribution was wiring the **Model
Reliability admin page and the dashboard's model-accuracy stat up to real
evaluated-model data**, instead of hardcoded placeholder numbers:

- `app/models/migrations/0018_create_model_performance_logs.sql` and
  `0019_adapt_model_performance_logs_for_multiclass.sql` — renumbered from
  that branch's `0009`/`0010`, which collided with second-merge's own
  `0009_create_users.sql` / `0010_create_app_settings.sql`.
- `app/models/model_performance_model.py` — `list_models()`,
  `get_best_model()`, `replace_all_models()`.
- `scripts/seed_model_performance.py` — placeholder demo rows. **Rewritten**
  during this merge: the original used the pre-migration-0019 binary-classifier
  field names (`cm_tn`/`cm_fp`/…, `diabetic_count`/`non_diabetic_count`),
  which the final schema no longer has. It now seeds the actual 3-class
  (Normal / Pre-Diabetic / Diabetic) shape.
- `scripts/import_phase4_results.py` — imports a real Phase-4 evaluation
  summary JSON. Copied over unchanged; it already targeted the right schema.
- `scripts/evaluate_models.py` — the real training/evaluation pipeline.
  Copied over unchanged, but note it's a **stub**: several functions
  (`load_test_set`, `get_cv_scores`, `get_feature_importance`) raise
  `NotImplementedError` until you plug in your actual training code, and it
  also still assumes a binary classifier (`predict_proba[:, 1]`,
  `cm_tn/fp/fn/tp`) rather than the 3-class schema. Not wired into app
  startup, so it can't break anything — just isn't finished.
- `reset_data.py` — dev utility to wipe patient/visit/screening data.
- `app/templates/model/reliability.html` — replaced second-merge's static
  binary-classifier template with model-reliability's version, which
  handles nulls/placeholders gracefully and renders an N-class confusion
  matrix instead of a fixed 2x2 grid.
- `app/static/css/reliability.css` — kept second-merge's themed
  (CSS-variable-based) version and added the small set of classes the new
  template needs (`confusion-grid-nxn`, `.cm-diag`, `.cm-offdiag`).
- `app/views/admin_views.py` — `dashboard()` and `reliability()` now call
  `get_best_model()` / `list_models()`. Both **fall back to placeholder
  data** (flagged with an on-page banner) when `model_performance_logs` is
  empty, rather than the original's `abort(404, ...)`, so the page is
  always viewable — including right after a fresh clone, before anyone
  has run `scripts/seed_model_performance.py`.

## Left out

- `app/models/screening.py` — unused dead code. It defines a SQLAlchemy
  `db.Model` class, but nothing in this codebase uses SQLAlchemy (everything
  else is raw `sqlite3`), and nothing imports this file. Importing it would
  raise an `AttributeError` (`app.db` has no `Model` attribute). The real
  screening flow lives in `app/models/lab_model.py` / the `lab_screenings`
  table, which both branches already share.
- `fix_buttons.py` — a one-off local dev script that string-replaces exact
  CSS snippets in `style.css`. `style.css` has changed too much between the
  branches for those exact strings to still match, so it wouldn't do
  anything if run. Harmless to leave out.

## Unrelated bug fixed along the way

`app/models/migrations/0015_backfill_patient_portal_auth.sql` re-added the
same 5 `patients` columns that `0014_add_patient_portal_auth.sql` already
adds. Its own comment explains it was written for one specific developer's
database where `0014` had been recorded as applied before its body was
written. On any normal/fresh database, `0014` adds the columns in full and
`0015` then failed with `duplicate column name`, which blocked
`flask init-db` / app startup entirely. This is a pre-existing bug in
`second-merge`, not something introduced by this merge — fixed here since it
otherwise stops the merged app from starting at all. `0015` is now a no-op
for everyone except that one developer, who should run its five
`ALTER TABLE` statements by hand if they still need them.

## Verified after merging

- `flask init-db` / `create_app()` — all 19 migrations apply cleanly on a
  fresh database, in order, no errors.
- `python scripts/seed_model_performance.py` — runs, populates
  `model_performance_logs` with the new 3-class shape.
- `python reset_data.py`, `python check_migrations.py`,
  `python check_tables.py` — all run cleanly.
- Routes smoke-tested with Flask's test client (session faked as a logged-in
  `medical_officer`): `/`, `/login`, `/health`, `/admin/dashboard`,
  `/admin/reliability` (both with and without seeded data — placeholder
  fallback banner confirmed on empty table), `/admin/data-management`,
  `/admin/privacy-security`, `/admin/green-computing`, `/admin/audit-trails`
  — all return 200.
- **Not** run: the existing `tests/` suite (`pytest` isn't installed in this
  environment and there's no network access to install it here), and
  `scripts/evaluate_models.py` (needs real trained `.joblib` models plus the
  TODOs filled in — not runnable as-is on either branch).
