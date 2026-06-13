from flask import Blueprint, render_template

nurse_bp = Blueprint('nurse', __name__, url_prefix='/nurse')

@nurse_bp.route('/nurse_dashboard')
def nurse_dashboard():
    low = 77.1
    mod = 17.0
    high = 5.9
    return render_template('nurse/nurse_dashboard.html', risk_data=[low, mod, high], active_page='dashboard')

@nurse_bp.route('/nurse_intake')
def nurse_intake():
    return render_template('nurse/nurse_intake.html', active_page='intake')

@nurse_bp.route('/nurse_screening')
def nurse_screening():
    return render_template('nurse/nurse_screening.html', active_page='screening')

@nurse_bp.route('/nurse_health_results')
def nurse_health_results():
    return render_template('nurse/nurse_health_results.html', active_page='health_results')

@nurse_bp.route('/nurse_data_management')
def nurse_data_management():
    barangays = ["Aplaya", "Balibago", "Caingin", "Dila", "Dita", "Don Jose",
                 "Ibaba", "Kanluran (Poblacion Uno)", "Labas", "Macabling",
                 "Malitlit", "Malusak (Poblacion Dos)", "Market Area (Poblacion Tres)",
                 "Pooc (Pook)", "Pulong Santa Cruz", "Santo Domingo", "Sinalhan", "Tagapo"]

    patients = [
        {"id":"CAB-2025-0156","name":"Juan Dela Cruz","age":30,"sex":"M","fbs":142,"risk":"High","date":"May 27, 2025","barangay":"Calamba"},
        {"id":"CAB-2025-0155","name":"Maria Santos","age":32,"sex":"F","fbs":118,"risk":"Moderate","date":"May 27, 2025","barangay":"Sta. Rosa"},
        {"id":"CAB-2025-0154","name":"Pedro Reyes","age":34,"sex":"M","fbs":96,"risk":"Low","date":"May 27, 2025","barangay":"San Pedro"},
        {"id":"CAB-2025-0153","name":"Ana Garcia","age":36,"sex":"F","fbs":134,"risk":"Moderate","date":"May 27, 2025","barangay":"Cabuyao"},
        {"id":"CAB-2025-0152","name":"Jerome Elano","age":38,"sex":"M","fbs":155,"risk":"High","date":"May 26, 2025","barangay":"Biñan"},
        {"id":"CAB-2025-0151","name":"Maria Santos","age":32,"sex":"F","fbs":118,"risk":"Moderate","date":"May 26, 2025","barangay":"Calamba"},
        {"id":"CAB-2025-0150","name":"Juan Dela Cruz","age":30,"sex":"M","fbs":142,"risk":"High","date":"May 26, 2025","barangay":"Sta. Rosa"},
        {"id":"CAB-2025-0149","name":"Maria Santos","age":32,"sex":"F","fbs":118,"risk":"Moderate","date":"May 26, 2025","barangay":"San Pedro"},
        {"id":"CAB-2025-0148","name":"Pedro Reyes","age":34,"sex":"M","fbs":96,"risk":"Low","date":"May 26, 2025","barangay":"Cabuyao"},
        {"id":"CAB-2025-0147","name":"Ana Garcia","age":36,"sex":"F","fbs":134,"risk":"Moderate","date":"May 26, 2025","barangay":"Biñan"},
        {"id":"CAB-2025-0146","name":"Lisa Perez","age":45,"sex":"F","fbs":161,"risk":"High","date":"May 25, 2025","barangay":"Dila"},
        {"id":"CAB-2025-0145","name":"Ramon Cruz","age":52,"sex":"M","fbs":109,"risk":"Moderate","date":"May 25, 2025","barangay":"Dita"},
        {"id":"CAB-2025-0144","name":"Sofia Reyes","age":28,"sex":"F","fbs":88,"risk":"Low","date":"May 25, 2025","barangay":"Kanluran (Poblacion Uno)"},
        {"id":"CAB-2025-0143","name":"Carlo Mendoza","age":41,"sex":"M","fbs":147,"risk":"High","date":"May 25, 2025","barangay":"Malitlit"},
        {"id":"CAB-2025-0142","name":"Elena Flores","age":37,"sex":"F","fbs":103,"risk":"Moderate","date":"May 24, 2025","barangay":"Market Area (Poblacion Tres)"},
    ]
    return render_template('nurse/nurse_data_management.html', barangays=barangays, patients=patients, active_page='data_management')

@nurse_bp.route('/nurse_privacy_security')
def nurse_privacy_security():
    return render_template('nurse/nurse_privacy_security.html', active_page='privacy')