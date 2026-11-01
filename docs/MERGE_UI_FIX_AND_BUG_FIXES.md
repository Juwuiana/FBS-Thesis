# Merge: `deploy-ui-fix` (base) + `fix-bugs`

This document records how the two zips `FBS-Thesis-deploy-ui-fix` and `FBS-Thesis-fix-bugs` were
combined, what was taken from each, what was deliberately **not** taken, what was fixed on top, and how it
was verified. The short version is in `CHANGELOG.md`; the README has a pointer to this file.

## 1. Rule used

`deploy-ui-fix` is the base for everything. The bug-fix zip was applied on top of it, but only where it
contains a real fix that the base does not already have.

Neither zip carried git history, so there was no common ancestor to run a mechanical three-way merge
against. Every differing file (31 shared files, plus files that exist in only one zip) was read and
classified by hand. The key finding:

> `fix-bugs` is **older** than `deploy-ui-fix` in the nurse, patient and staff-account code. Taking those
> files from it would have silently removed features and fixes that the UI zip already contains.

So "take the bug-fix zip's version" was only correct for the files listed in section 2.

## 2. What was taken from `fix-bugs`

| Area | Files | What it does |
|---|---|---|
| Password policy | `app/controllers/auth_controller.py`, `app/static/js/signup.js`, `app/templates/auth/signup.html`, `app/static/css/auth.css` | Strong password rules on public signup and on the staff/admin Change Password form (rules in section 4). Signup shows required-field stars, a live checklist, and keeps **Sign Up** disabled until the form is valid and the terms box is ticked. Also fixes `signup.js` reading an element id (`barangay`) that no longer exists in the template. |
| Admin dashboard | `app/templates/dashboard/index.html`, `app/static/css/style.css` (`.admin-dash` block), `app/static/js/main.js` | Compact layout with the same density as the nurse dashboard. Charts sit in fixed-height boxes and use `maintainAspectRatio: false`, so they no longer stretch the page. |
| Barangay list | `app/models/health_analytics_model.py` (`barangay_bars`, `at_risk_by_barangay`), one change in `app/views/admin_views.py` | The card titled "Barangay List by At-Risk Count" now counts at-risk (Moderate/High) patients per barangay from the same latest-screening-per-patient snapshot as the stat cards. Before, it counted every screening ever recorded. |
| Green Computing page | `app/templates/metrics/green.html`, `app/static/css/style.css` (`.gc-page` block) | Compact density; the duplicated heading block was removed (the title is already in the top bar). |
| Tests | `tests/test_admin_dashboard_ui.py`, `tests/test_barangay_bars.py`, `tests/test_green_page_ui.py`, `tests/test_password_policy.py` | Covers the four items above. |

`style.css` and `auth.css` from the bug zip were pure additions on top of the UI zip's files (nothing in
the UI zip's version was removed), so they were copied over whole.

## 3. What was NOT taken from `fix-bugs`, and why

| Item | Reason |
|---|---|
| `nurse_controller.py`, `visit_model.py`, `patient_model.py`, `patient_controller.py`, `patient_portal_model.py`, and the nurse/patient templates and scripts | Older copies. The UI zip has the newer duplicate-patient check, server-side vitals validation and BMI normalisation, single-select diet handling, patient PDF download, patient email in settings, and the FBS band fix. |
| `add_staff.html`, the CSV import code in `admin_views.py`, `records.html`, `constants.py` | Older. The UI zip generates temporary passwords and shows them once on a credentials page (`staff_credentials.html`); the bug zip still asks the admin to type one. |
| `requirements.txt` | Stale: it lacks `reportlab` (needed by the patient PDF download). The UI zip's file was kept. |
| Empty files `app/controllers/dashboard_controller.py`, `app/views/dashboard_views.py`, `app/ml/__init__.py`, `app/models/__init__.py` | Zero-byte placeholders with no content or imports. |

Only one hunk of `admin_views.py` came from the bug zip: the dashboard's barangay list (see section 2).

## 4. Behaviour after the merge

### Password policy (staff and admin accounts)

A new password must:

- be 12 to 128 characters,
- contain an uppercase letter, a lowercase letter, a number and a special character,
- contain no spaces,
- not repeat the same character three times in a row,
- not contain the user's first name, last name or the part of their email before `@` (3+ characters).

Where it applies: public signup, and Change Password for both admin and nurse accounts
(`auth_controller.change_own_password`). The server is authoritative; the browser checklists are guidance.

Where it does **not** apply:

- System-generated temporary passwords (admin-created accounts, CSV import, recovery reset). These are not
  validated, but the password the user sets to replace them is.
- The **patient portal**, which keeps its own 8-character minimum
  (`patient_auth_controller.MIN_NEW_PASSWORD_LENGTH`). This was not part of the bug zip. Applying the staff
  policy to patients is a policy decision for the team.

### Barangay list on the admin dashboard

Counts Moderate/High patients per barangay using each patient's most recent screening. Its total now equals
the "At Risk" stat card. Bars are scaled to the largest count in the list, with a 3% minimum so a non-zero
count is always visible.

## 5. Fixes made during the merge (not in either zip)

1. **Change Password checklist did not match the server.** The shared form
   (`partials/_change_password_form.html` + `static/js/change_password.js`) only checked length, so it could
   enable **Update Password** for a password the server then rejected. It now lists and evaluates every
   rule above except the name/email rule, which stays server-side. The rules were cross-checked against
   `PASSWORD_REGEX` on a 20-password corpus with Python and Node: no mismatches.
2. **Render deployment was missing `reportlab`.** `requirements-deploy.txt` did not list it, but
   `app/models/patient_pdf.py` imports it. In a clean install of only the deploy requirements, the patient
   PDF download failed with `ModuleNotFoundError`. Added `reportlab==5.1.0`. This problem existed in the UI
   zip before the merge.
3. **`geoip2==5.3.0` added to `requirements.txt`**, as the existing CHANGELOG already says it should be.
   The code imports it defensively, so the app runs without it; login-activity locations need it.
4. **Three stale tests.** `test_predict_writes_log_and_dashboard_reads_it`, `test_empty_database_renders`
   and `test_nurse_screening_submit_creates_and_links_green_log` were written for the placeholder predictor
   and started failing once the real trained model shipped in `app/ml/artifacts`. They now set `MODEL_PATH`
   to an empty folder so they always exercise the placeholder, and the nurse test no longer asserts a
   "Diabetic" label (the nurse flow deliberately does not send FBS to the model). A new test,
   `test_shipped_model_loads_and_predicts`, covers the real model using the default path.

## 6. Verification

| Check | Result |
|---|---|
| UI zip alone, before any change | 217 passed, 3 failed (the three stale tests above) |
| Merged tree, full suite, in a clean virtualenv built only from `requirements-deploy.txt` (what Render installs) | **249 passed, 1 skipped** (the skip is the scikit-learn benchmark module) |
| Merged tree, full suite, full development environment (with scikit-learn) | **254 passed, 0 failed** |
| `signup.js` and `change_password.js` | `node --check` passes; every element id used by `signup.js` exists in `signup.html` |
| Password rules, browser vs server | identical result on 20 sample passwords |
| Headless Chromium, merged app vs UI zip app on identical seeded data | No JavaScript errors on dashboard, Green Computing, Privacy & Security or signup. Sidebar 68px and content offset 68px in both. Barangay list sums to 15, matching the "At Risk 15" card (the UI zip's list summed to 32). |
| Patients with several past screenings (63 rows, 33 patients, scratch DB) | Admin total 33, nurse total 33, barangay list sums to 15 = "At Risk" card |
| Signup form, driven in the browser | Submit stays disabled for four weak passwords; enabled for a strong one; checklist ticks each rule correctly |
| Change Password form, driven in the browser | Submit enabled only when all rules, match, and "different from current" are met |

To reproduce:

```powershell
python -m venv .venv-check
.\.venv-check\Scripts\python.exe -m pip install -r requirements-deploy.txt pytest
.\.venv-check\Scripts\python.exe -m pytest tests -q
```

`test_benchmark_models.py` is skipped in that environment because it needs scikit-learn, which the deploy
requirements intentionally leave out.

## 7. Notes for whoever tests this next

- The app blocks a second login for the same account while the first session is still active
  (`FBS_SINGLE_SESSION_POLICY=block`, the default). When scripting browser tests, set it to `replace` or
  you will be bounced back to the login page.
- A full-page screenshot can show the collapsed sidebar expanded over the content. That is the sidebar's
  hover state and appears in the pre-merge UI zip too; it is not a layout bug.
- **Why the nurse and admin dashboards once disagreed (20 vs 78).** In the earlier `third-merge` tree the
  admin dashboard counted `SELECT COUNT(*) FROM lab_screenings` (every screening ever recorded) while the
  nurse dashboard counted one row per patient (their latest screening). In this merged tree both use the
  latest-screening-per-patient snapshot, so they agree. Checked with a scratch database holding 63
  screening rows for 33 patients: admin total 33, nurse total 33, barangay list sums to 15 = the "At Risk"
  card. Only the raw table count (63) differs, and no dashboard uses it any more. If a number labelled
  "screenings" should count every screening rather than every patient, that is a separate wording or
  metric decision.

## 8. Open items

- Patient portal password policy (section 4).
- The Green Computing figures on a hosted deployment still need the measurement approach agreed for the
  thesis (edge/phone measurements vs. hosted); this merge does not change that.
