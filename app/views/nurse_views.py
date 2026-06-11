from flask import Blueprint, render_template

nurse_bp = Blueprint('nurse', __name__)


@nurse_bp.route('/nurse_dashboard')
def nurse_dashboard():
    # 1. First, calculate your actual data from the database here
    # For now, these are placeholders. Later, you'll query your SQL database.
    low = 77.1
    mod = 17.0
    high = 5.9
    
    # 2. Then, pass that data into your template
    return render_template('nurse/nurse_dashboard.html', risk_data=[low, mod, high])

@nurse_bp.route('/nurse_intake')
def nurse_intake():
    return render_template('nurse/nurse_intake.html')

@nurse_bp.route('/nurse_screening')
def nurse_screening():
    return render_template('nurse/nurse_screening.html')

@nurse_bp.route('/nurse_health_results')
def nurse_health_results():
    return render_template('nurse/nurse_health_results.html')

@nurse_bp.route('/nurse_data_management')
def nurse_data_management():
    barangays = ["Aplaya", "Balibago", "Caingin", "Dila", "Dita", "Don Jose", 
                 "Ibaba", "Kanluran (Poblacion Uno)", "Labas", "Macabling", 
                 "Malitlit", "Malusak (Poblacion Dos)", "Market Area (Poblacion Tres)", 
                 "Pooc (Pook)", "Pulong Santa Cruz", "Santo Domingo", "Sinalhan", "Tagapo"]
    return render_template('nurse/nurse_data_management.html', barangays=barangays)

@nurse_bp.route('/nurse_privacy_security')
def nurse_privacy_security():
    return render_template('nurse/nurse_privacy_security.html')