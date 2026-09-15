# FBS Thesis

Flask and SQLite application for the LHU diabetes risk screening system.

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
- `app/schema.sql` - SQLite schema
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
