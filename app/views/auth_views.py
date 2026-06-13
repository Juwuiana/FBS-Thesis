from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app import db
from app.models.user import User

auth_bp = Blueprint('auth', __name__)

ROLE_REDIRECTS = {
    'admin':   'admin.dashboard',
    'nurse':   'nurse.nurse_dashboard',
    'patient': 'patient.patient_dashboard',
}

# ── LOGIN ──────────────────────────────────────────────────────────────────────
@auth_bp.route('/')
@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '').strip()

        user = User.query.filter_by(email=email).first()

        if not user or not user.check_password(password):
            flash('Invalid email or password.', 'error')
            return render_template('auth/login.html')

        # Store in session
        session.permanent   = True
        session['user_id']  = user.id
        session['role']     = user.role
        session['name']     = f"{user.first_name} {user.last_name}".strip()

        dest = ROLE_REDIRECTS.get(user.role)
        if not dest:
            flash('Your account role is not configured. Contact admin.', 'error')
            return render_template('auth/login.html')

        return redirect(url_for(dest))

    return render_template('auth/login.html')


# ── LOGOUT ─────────────────────────────────────────────────────────────────────
@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('auth.login'))


# ── SIGNUP ─────────────────────────────────────────────────────────────────────
@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name  = request.form.get('last_name',  '').strip()
        email      = request.form.get('email',      '').strip().lower()
        password   = request.form.get('password',   '').strip()
        confirm    = request.form.get('confirm_password', '').strip()
        role       = request.form.get('role', 'nurse')  # default to nurse for new signups

        # Basic validation
        if not all([first_name, last_name, email, password]):
            flash('Please fill in all required fields.', 'error')
            return render_template('auth/signup.html')

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return render_template('auth/signup.html')

        if len(password) < 12:
            flash('Password must be at least 12 characters.', 'error')
            return render_template('auth/signup.html')

        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'error')
            return render_template('auth/signup.html')

        # Map signup role values to DB role values
        role_map = {
            'health_worker':  'nurse',
            'medical_officer': 'admin',
        }
        db_role = role_map.get(role, 'nurse')

        user = User(
            email      = email,
            role       = db_role,
            first_name = first_name,
            last_name  = last_name,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('Account created! Please sign in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/signup.html')