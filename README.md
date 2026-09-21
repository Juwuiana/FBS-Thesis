# FBS-Thesis — Patient Portal Branch

`feature/nurse-patient-combine` merges `feature/nurse-intake` and `feature/patient-results`. It adds the patient-facing side of the app 
(dashboard, health results, settings) on top of the existing nurse app, sharing the same Flask project, database, and migration runner.

## Project structure 

```
app/
  controllers/
    nurse_controller.py       nurse-facing routes
    patient_controller.py     patient-facing routes (this branch)
    auth_controller.py        empty — owned by the auth branch
  models/
    patient_model.py          patients table reads/writes
    patient_portal_model.py   assembles dashboard/history data for a patient
    visit_model.py            visits, conditions, CVD responses
    lab_model.py               lab_screenings reads/writes
  templates/
    nurse/
    patient/
  __init__.py                  app factory, blueprint registration
run.py                          entry point
```

## Merge conflicts based sa pag merge ko ng patient at nurse

### `app/__init__.py`

Every branch that adds a controller edits this file — each one adds an
import and a `register_blueprint` call. The conflict is almost always
resolved by keeping both sides:

```python
from app.controllers.nurse_controller import nurse_bp
from app.controllers.patient_controller import patient_bp
app.register_blueprint(nurse_bp)
app.register_blueprint(patient_bp)
```

Do not delete either side unless a blueprint was intentionally removed.

## Authentication is not implemented on this branch

This is intentional. Patient login/session handling is
being built on a separate branch. 

`patient_portal_model.get_current_patient_id()` is hardcoded:

```python
def get_current_patient_id():
    return 1  # Danilo Aquino (CAB-2026-0001) in the local test DB
```

Search for `TODO(auth)` to find every place written to expect
the auth branch's work.

## unfinished

- Patient Settings, Contact Details tab: only `address` and `contact_number`
  are okay on `patients`. City, province, ZIP, and landline fields
  are UI only
- Patient Settings, Password & Security
- Patient Settings, Account tab: data export, deactivate account, and sign
  out all devices are UI only, no backend logic.
