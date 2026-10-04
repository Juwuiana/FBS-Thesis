from flask import Blueprint, abort, current_app, flash, jsonify, render_template, request, session, redirect, url_for
from app.models import patient_portal_model, patient_model, visit_model, lookup_model, patient_fbs_model, settings as settings_model
from app.controllers import patient_auth_controller
from flask import Response
from datetime import date as date_cls, datetime
from app.rate_limit import rate_limit


patient_bp = Blueprint('patient', __name__)



try:
    import geoip2.database
    _geo = geoip2.database.Reader('instance/GeoLite2-City.mmdb')
except Exception:          # file missing: the app still runs, locations just show as unavailable
    _geo = None


def lookup_location(ip):
    if not _geo or not ip:
        return None
    try:
        r = _geo.city(ip)
        return ', '.join(p for p in [r.city.name, r.subdivisions.most_specific.name, r.country.name] if p) or None
    except Exception:      # private/local/unknown IPs
        return None


@patient_bp.app_template_filter('mask_ip')
def mask_ip(ip):
    p = (ip or '').split('.')
    return '.'.join(p[:2] + ['x', 'x']) if len(p) == 4 else (ip or '')[:9] + '…'


def _with_locations(events):
    out = []
    for e in events:
        e = dict(e)
        e['location'] = lookup_location(e.get('ip_address'))
        out.append(e)
    return out

# Allowed values for the patient "Add New Record" form. Single source of truth:
# passed to the template (so the form renders from it) and used to validate the POST.
PATIENT_RECORD_OPTIONS = {
    "smoking_status": ["Never smoked", "Stopped > 1 year", "Stopped < 1 year", "Current Smoker", "Passive Smoker"],
    "alcohol_intake": ["Never Consumed", "Yes", "Yes (Binge: 5+ drinks in one occasion past month)"],
    "illicit_drug_use": ["No", "Yes"],
    "physical_activity": ["Does NOT meet 2.5 hours/week", "Meets at least 2.5 hours/week moderate activity"],
    "diabetes_diagnosis": ["No / Do not know", "Yes (with medications)", "Yes (without medications)"],
    "pmh": ["Allergy", "Asthma", "Cancer", "Cerebrovascular Disease", "Coronary Artery Disease",
            "Diabetes Mellitus", "Emphysema", "Epilepsy/Seizure Disease", "Hepatitis", "Hyperlipidemia",
            "Hypertension", "Peptic Ulcer Disease", "Pneumonia", "Thyroid Disease", "Tuberculosis",
            "Urinary Tract Infection"],
    "family_history": ["Hypertension", "Stroke/Cerebrovascular Disease", "Coronary Artery Disease",
                       "Diabetes Mellitus", "Asthma", "Cancer", "Kidney Disease"],
    "diet": ["High Fat/Salt", "3+ servings vegetables daily", "2-3 servings fruits daily"],
    "immunization": ["BCG", "OPV/IPV Series", "DPT Series", "Measles", "Hepatitis A/B Series", "HPV",
                     "MMR", "Tetanus Toxoid", "Pneumococcal Vaccine", "Flu Vaccine"],
    "dm_symptom": ["Polyphagia", "Polydipsia", "Polyuria"],
    "cvd": [
        ("q1_chest_discomfort", "1. Pain/discomfort/pressure in chest?"),
        ("q2_pain_center_left_arm", "2. Pain in center/left chest or left arm?"),
        ("q3_occurs_uphill_hurrying", "3. Occurs when walking uphill or hurrying?"),
        ("q4_slows_down_if_occurs", "4. Do you slow down if you get it while walking?"),
        ("q5_relieved_by_rest_tablet", "5. Does pain go away standing still or under-tongue tablet?"),
        ("q6_relieved_under_10min", "6. Does pain go away in less than 10 minutes?"),
        ("q7_severe_pain_30min_plus", "7. Severe chest pain lasting half an hour or more?"),
        ("q8_tia_stroke_symptoms", "8. TIA/Stroke: Difficulty talking, weakness or numbness?"),
    ],
}


@patient_bp.before_request
def _require_patient_login():
    if current_app.config.get("DEV_NO_AUTH"):
        return
    if request.endpoint in ("patient.patient_login", "patient.patient_account_help"):
        return
    if (session.get("patient_id") and
            session.get("security_version") != settings_model.get_security_version("patient")):
        session.clear()
        flash("You've been signed out for security reasons. Please log in again.", "error")
        return redirect(url_for("patient.patient_login"))
    if not session.get("patient_id"):
        return redirect(url_for('patient.patient_login'))


@patient_bp.app_context_processor
def inject_current_patient():
    patient_id = patient_portal_model.get_current_patient_id()
    return {"patient": patient_model.get_patient_by_id(patient_id) if patient_id else None}


# ---------------------------------------------------------------------------
# Follow-up reminders (bell icon, top right of every patient page)
# ---------------------------------------------------------------------------
FOLLOW_UP_SOON_DAYS = 7  # "near" = due within this many days


def _parse_follow_up_date(raw):
    """Follow-up dates are stored as text; accept ISO (YYYY-MM-DD) and DD/MM/YYYY."""
    if not raw:
        return None
    text = str(raw).strip()
    for fmt, size in (("%Y-%m-%d", 10), ("%d/%m/%Y", 10)):
        try:
            return datetime.strptime(text[:size], fmt).date()
        except ValueError:
            continue
    return None


def _plural_days(n):
    return f"{n} day" + ("" if n == 1 else "s")


def build_follow_up_notifications(history, today=None):
    """
    Reminder for the patient's most recent COMPLETED screening's follow-up date
    (a newer draft with no FBS yet does not replace it). Returns a list of
    {key, level, title, message}; empty when nothing is due soon.
      overdue -> date already passed
      today   -> due today
      soon    -> due within FOLLOW_UP_SOON_DAYS
    `key` changes whenever the level/date changes, so the browser can treat a
    reminder that gets more urgent as new (unread) again.
    """
    today = today or date_cls.today()
    latest = next((v for v in (history or []) if v.get("fbs_score") is not None), None)
    due = _parse_follow_up_date(latest.get("follow_up_date")) if latest else None
    if due is None:
        return []

    nice = f"{due:%b} {due.day}, {due.year}"
    delta = (due - today).days
    if delta < 0:
        level, title = "overdue", "Follow-up overdue"
        msg = f"Your follow-up was due on {nice} ({_plural_days(-delta)} ago). Please visit your LHU as soon as you can."
    elif delta == 0:
        level, title = "today", "Follow-up today"
        msg = "Your follow-up is scheduled for today. Please visit your LHU."
    elif delta <= FOLLOW_UP_SOON_DAYS:
        level, title = "soon", "Follow-up coming up"
        when = "tomorrow" if delta == 1 else f"in {_plural_days(delta)}"
        msg = f"Your follow-up is {when} ({nice})."
    else:
        return []
    return [{"key": f"followup:{due.isoformat()}:{level}", "level": level, "title": title, "message": msg}]


@patient_bp.context_processor
def inject_patient_notifications():
    """Makes `patient_notifications` available to every patient template (the bell in patient_base)."""
    patient_id = patient_portal_model.get_current_patient_id()
    if not patient_id:
        return {"patient_notifications": []}
    try:
        patient = patient_model.get_patient_by_id(patient_id)
        history = patient_portal_model.get_full_screening_history(patient_id, (patient or {}).get("sex"))
        return {"patient_notifications": build_follow_up_notifications(history)}
    except Exception:  # a reminder must never break the page
        current_app.logger.exception("Could not build patient notifications")
        return {"patient_notifications": []}


@patient_bp.route('/patient_login', methods=['GET', 'POST'])
def patient_login():
    if request.method == 'GET':
        return render_template('auth/patient_login.html')

    patient, error = patient_auth_controller.authenticate_patient(
        request.form.get('patient_code', ''), request.form.get('password', '')
    )
    if error:
        return render_template('auth/patient_login.html', error=error)

    if not settings_model.is_role_login_enabled("patient"):
        return render_template(
            'auth/patient_login.html',
            error="Patient portal access is temporarily disabled. Please contact your LHU.",
        )

    session.clear()
    session['patient_id'] = patient['id']
    session['security_version'] = settings_model.get_security_version("patient")
    patient_model.record_login_event(
        patient['id'],
        user_agent=request.headers.get('User-Agent'),
        ip_address=request.remote_addr,
    )
    return redirect(url_for('patient.patient_dashboard'))

@patient_bp.route('/patient_account_help', methods=['POST'])
@rate_limit(max_calls=5, period_seconds=300)
def patient_account_help():
    """
    Unauthenticated: a patient who can't log in has no session to work
    with. Flags their account (if the Patient ID they gave is real) for a
    nurse to follow up on and reissue credentials in person/by phone --
    this never sends a password or a reset link itself.

    The flash message is identical whether or not patient_code matched a
    real account, on purpose: a different response here would let someone
    enumerate valid Patient IDs. patient_model.request_account_help()
    already no-ops silently on no match, so there is nothing else to
    branch on.
    """
    raw_code = (request.form.get('patient_code') or '').strip()
    patient_code = patient_auth_controller.normalize_patient_code(raw_code)
    reason = (request.form.get('reason') or '').strip()

    if patient_code:
        patient_model.request_account_help(patient_code, reason)

    flash(
        "If that Patient ID matches our records, your health worker has "
        "been notified and will follow up with you.",
        "success",
    )
    return redirect(url_for('patient.patient_login'))


@patient_bp.route('/patient_logout', methods=['GET', 'POST'])
def patient_logout():
    session.pop('patient_id', None)
    return redirect(url_for('patient.patient_login'))


@patient_bp.route('/patient_dashboard')
def patient_dashboard():
    patient_id = patient_portal_model.get_current_patient_id()
    patient = patient_model.get_patient_by_id(patient_id)
    result = patient_portal_model.get_patient_dashboard_data(patient_id)
    extras = patient_portal_model.get_dashboard_extras(patient_id, patient.get("sex"))
    return render_template('patient/patient_dashboard.html', result=result, **extras)


@patient_bp.route('/patient_health_results')
def patient_health_results():
    patient_id = patient_portal_model.get_current_patient_id()
    patient = patient_model.get_patient_by_id(patient_id)
    history = patient_portal_model.get_full_screening_history(patient_id, patient.get("sex"))
    trend = patient_portal_model.build_trend(history)
    return render_template(
        'patient/patient_health_results.html', history=history, trend=trend,
        location_has_provinces=lookup_model.psgc_has_provinces(),
        record_options=PATIENT_RECORD_OPTIONS,
        today=date_cls.today().isoformat(),
        self_fbs_entries=patient_portal_model.get_self_reported_fbs(patient_id),
    )


@patient_bp.route('/patient_settings', methods=['GET', 'POST'])
def patient_settings():
    patient_id = patient_portal_model.get_current_patient_id()
    patient = patient_model.get_patient_by_id(patient_id)
    login_events = patient_model.get_recent_login_events(patient_id)

    if request.method == 'GET':
        return render_template(
            'patient/patient_settings.html',
            patient=patient,
            login_events=login_events,
            force_change=bool(patient.get('must_change_password')),
        )

    errors = patient_auth_controller.change_patient_password(patient, request.form)
    if errors:
        return render_template('patient/patient_settings.html', patient=patient,
                                login_events=login_events, message=errors[0], success=False)
    return render_template('patient/patient_settings.html', patient=patient,
                            login_events=login_events, message="Password updated.", success=True)

@patient_bp.route('/patient_download_data')
def patient_download_data():
    if not settings_model.is_role_export_enabled("patient"):
        flash("Data export is temporarily disabled by an administrator.", "error")
        return redirect(url_for('patient.patient_dashboard'))

    patient_id = patient_portal_model.get_current_patient_id()
    patient = patient_model.get_patient_by_id(patient_id)
    csv_data = patient_model.export_single_patient_csv(patient['patient_code'], all_visits=True)
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={patient["patient_code"]}_health_data.csv'}
    )

@patient_bp.route('/patient_health_results/<int:visit_id>/edit', methods=['POST'])
def patient_edit_visit(visit_id):
    """
    Lets a patient correct any field a nurse can edit on one of their own
    past visits, except status/assessment_date/pe_*/clinical_notes, which
    stay nurse-only -- see visit_model.PATIENT_EDITABLE_VISIT_FIELDS.
    FBS and the risk result are never editable here. Flags the visit so
    nurses see it in their notification bell.
    """
    # Dropdown fields post "" for their "— No change —" placeholder option --
    # that means "field left alone", not "clear this field". Free-text
    # fields (past_surgical_history, lmp_date) have no such placeholder, so
    # an empty value there is the patient deliberately blanking it out.
    _SELECT_FIELDS = {"smoking_status", "alcohol_intake", "illicit_drug_use",
                       "physical_activity", "diabetes_diagnosis"}

    patient_id = patient_portal_model.get_current_patient_id()
    fields = {}
    for key in visit_model.PATIENT_EDITABLE_VISIT_FIELDS:
        if key not in request.form:
            continue  # field wasn't part of this particular edit form at all
        raw = (request.form.get(key) or "").strip()
        if key in visit_model._NUMERIC_VISIT_FIELDS:
            if not raw:
                continue  # blank numeric field -- nothing submitted, don't clear it
            try:
                fields[key] = float(raw)
            except ValueError:
                flash(f"{key.replace('_', ' ').title()} must be a number.", "error")
                return redirect(url_for('patient.patient_health_results'))
        elif key in _SELECT_FIELDS:
            if raw:  # skip the "— No change —" placeholder entirely
                fields[key] = raw
        else:
            # free text (past_surgical_history, lmp_date, ...): "" is a
            # deliberate clear and goes through as-is.
            fields[key] = raw

    result = visit_model.patient_update_visit_vitals(visit_id, patient_id, fields)
    if result["ok"]:
        flash("Your changes were saved. Your health worker will review them.", "success")
    else:
        flash(result["error"], "error")
    return redirect(url_for('patient.patient_health_results'))


@patient_bp.route('/patient_add_record', methods=['POST'])
def patient_add_record():
    """
    Patient adds a new (follow-up) record for themselves. Same sections as the
    nurse's Add New Record, but anthropometrics / vitals are OPTIONAL. A home FBS 
    reading is optional and saved separately as self-reported. The screening FBS 
    and risk result are only ever recorded by a nurse.
    The visit is saved as a "draft" so it shows up for the nurse as a
    record still awaiting screening (the nurse screening step marks it submitted).
    """
    patient_id = patient_portal_model.get_current_patient_id()
    patient = patient_model.get_patient_by_id(patient_id)
    back = url_for('patient.patient_health_results', view='add')
    opts = PATIENT_RECORD_OPTIONS

    def fail(msg):
        flash(msg, "error")
        return redirect(back)

    # --- assessment date: today by default, never in the future -------------
    today = date_cls.today()
    raw_date = (request.form.get('assessment_date') or '').strip()
    try:
        assessment_date = date_cls.fromisoformat(raw_date) if raw_date else today
    except ValueError:
        return fail("Please enter a valid date.")
    if assessment_date > today:
        return fail("The date of the record cannot be in the future.")

    # --- required single-choice fields --------------------------------------
    visit = {"assessment_date": assessment_date.isoformat(), "status": "draft"}
    for key, label in (("smoking_status", "Smoking"), ("alcohol_intake", "Alcohol Intake"),
                       ("illicit_drug_use", "Illicit Drug Use")):
        val = (request.form.get(key) or '').strip()
        if val not in opts[key]:
            return fail(f"Please choose an option for {label}.")
        visit[key] = val
    for key in ("physical_activity", "diabetes_diagnosis"):
        val = (request.form.get(key) or '').strip()
        if val and val not in opts[key]:
            return fail("One of the options you chose is not valid.")
        visit[key] = val or None

    visit["past_surgical_history"] = (request.form.get('past_surgical_history') or '').strip()[:200] or None

    # --- required checkbox groups (or "None reported") ----------------------
    conditions = {}
    for cat, none_field in (("pmh", "pmh_none"), ("family_history", "fh_none")):
        picked = [v for v in request.form.getlist(cat) if v in opts[cat]]
        if not picked and not request.form.get(none_field):
            label = "Past Medical History" if cat == "pmh" else "Family History"
            return fail(f'{label}: select at least one, or check "None reported".')
        conditions[cat] = picked
    for cat in ("diet", "immunization", "dm_symptom"):
        conditions[cat] = [v for v in request.form.getlist(cat) if v in opts[cat]]

    # --- optional numeric fields (anthropometrics, vitals, female history) --
    def num(name, label, lo, hi, as_int=False):
        raw = (request.form.get(name) or '').strip()
        if not raw:
            return None, None
        try:
            val = float(raw)
        except ValueError:
            return None, f"{label} must be a number."
        if not (lo <= val <= hi):
            return None, f"{label} looks out of range."
        return (int(val) if as_int else round(val, 1)), None

    numeric = [
        ("bp_systolic", "Systolic BP", 50, 300, True),
        ("bp_diastolic", "Diastolic BP", 30, 200, True),
        ("heart_rate", "Heart rate", 20, 250, True),
        ("respiratory_rate", "Respiratory rate", 5, 80, True),
        ("height_cm", "Height", 50, 250, False),
        ("weight_kg", "Weight", 10, 400, False),
        ("waist_cm", "Waist circumference", 20, 250, False),
    ]
    if patient.get("sex") == "Female":
        numeric += [("menarche_age", "Age at menarche", 5, 25, True),
                    ("gravida", "Gravida", 0, 30, True),
                    ("para", "Para", 0, 30, True)]
    for name, label, lo, hi, as_int in numeric:
        val, err = num(name, label, lo, hi, as_int)
        if err:
            return fail(err)
        visit[name] = val

        # --- optional home FBS reading (self-reported, saved separately) ---------
    self_fbs = None
    raw_fbs = (request.form.get('self_fbs_value') or '').strip()
    if raw_fbs:
        unit = (request.form.get('self_fbs_unit') or 'mg_dl').strip()
        fasted = (request.form.get('self_fbs_fasted') or '').strip()
        if unit not in patient_fbs_model.VALID_UNITS or fasted not in patient_fbs_model.VALID_FASTED:
            return fail("Please choose a unit and answer the fasting question for your FBS reading.")
        try:
            val = float(raw_fbs)
        except ValueError:
            return fail("FBS must be a number.")
        if not (20 <= patient_fbs_model.to_mg_dl(val, unit) <= 600):
            return fail("FBS looks out of range.")
        self_fbs = {"entered_value": val, "entered_unit": unit, "fasted": fasted}

    # BMI + class only when both height and weight were given (same cut-offs as the nurse form)
    visit["bmi"], visit["obesity_class"] = None, None
    if visit.get("height_cm") and visit.get("weight_kg"):
        bmi = visit["weight_kg"] / ((visit["height_cm"] / 100) ** 2)
        visit["bmi"] = round(bmi, 1)
        visit["obesity_class"] = ("Underweight" if bmi < 18.5 else "Normal" if bmi < 23
                                  else "Overweight (At Risk)" if bmi < 25
                                  else "Obese I" if bmi < 30 else "Obese II")

    # LMP only applies to female patients
    lmp = (request.form.get('lmp_date') or '').strip() if patient.get("sex") == "Female" else ''
    if lmp:
        try:
            date_cls.fromisoformat(lmp)
        except ValueError:
            return fail("Please enter a valid last menstrual period date.")
    visit["lmp_date"] = lmp or None

    # nurse-only fields stay empty
    for key in ("pe_skin", "pe_heent", "pe_chest", "pe_heart", "pe_abdomen", "pe_extremities", "clinical_notes"):
        visit[key] = None
    for key in ("menarche_age", "gravida", "para"):
        visit.setdefault(key, None)

    # --- CVD questionnaire ---------------------------------------------------
    cvd = {key: (request.form.get(key) or '').lower().startswith("yes") for key, _ in opts["cvd"]}

    # --- save ---------------------------------------------------------------
    visit_id = visit_model.create_visit(patient_id, "follow_up", visit, staff_id=None)
    for category, codes in conditions.items():
        if codes:
            visit_model.save_visit_conditions(visit_id, category, codes)
    visit_model.save_cvd_responses(visit_id, cvd)
    visit_model.flag_patient_submitted_record(visit_id)
    if self_fbs:
        patient_fbs_model.create_entry(patient_id, visit_id, self_fbs["entered_value"],
                                       self_fbs["entered_unit"], self_fbs["fasted"])
    flash("Your new record was submitted. A health worker will complete your screening and FBS.", "success")
    return redirect(url_for('patient.patient_health_results', view='history'))


@patient_bp.route('/patient_location_options')
def patient_location_options():
    """Dropdown data for the address cascade (codes + names only).
    ?level=region | province&parent=<region code> | city&parent=<province or region code>
    | barangay&parent=<city code>"""
    level = request.args.get('level', 'region')
    if level not in lookup_model.LOCATION_LEVELS:
        return jsonify({"error": "Unknown level."}), 400
    parent = (request.args.get('parent') or '').strip() or None
    if level != 'region' and parent is None:
        return jsonify({"level": level, "options": []})
    try:
        options = lookup_model.psgc_location_options(level, parent)
    except (OSError, ValueError):
        return jsonify({"error": "Address options are unavailable right now."}), 503
    return jsonify({"level": level, "options": options})


@patient_bp.route('/patient_update_consent', methods=['POST'])
def patient_update_consent():
    patient_id = patient_portal_model.get_current_patient_id()
    consent = request.json.get('consent', False)
    patient_model.update_patient_consent(patient_id, consent)
    return {"ok": True}

@patient_bp.route('/patient_update_demographics', methods=['POST'])
def patient_update_demographics():
    """Patient corrects civil status, occupation and/or address. Name, ID,
    sex, age and assessment date are not accepted here. Each changed field
    flags the nurse through record_patient_profile_edit."""
    patient_id = patient_portal_model.get_current_patient_id()
    patient = patient_model.get_patient_by_id(patient_id)
    back = url_for('patient.patient_health_results')

    allowed_status = {'Single', 'Married', 'Annulled', 'Widow/Widower', 'Separated'}
    civil = (request.form.get('civil_status') or '').strip()
    occupation = (request.form.get('occupation') or '').strip()
    if civil not in allowed_status:
        flash("Please choose a valid civil status.", "error")
        return redirect(back)
    if len(occupation) > 100:
        flash("Occupation must be 100 characters or fewer.", "error")
        return redirect(back)

    changes, flagged = {}, {}
    if civil != (patient.get('civil_status') or ''):
        changes['civil_status'] = civil
        flagged['civil_status'] = patient.get('civil_status')
    if occupation != (patient.get('occupation') or ''):
        changes['occupation'] = occupation or None
        flagged['occupation'] = patient.get('occupation')

    before_loc = patient_model.format_location(patient)
    region_code = (request.form.get('region_code') or '').strip()
    if region_code:
        barangay_id, error = lookup_model.resolve_psgc_location(
            region_code,
            (request.form.get('city_code') or '').strip(),
            (request.form.get('barangay_code') or '').strip(),
            (request.form.get('province_code') or '').strip() or None,
        )
        address = (request.form.get('address') or '').strip()
        if not error and len(address) > 200:
            error = "Street / house address must be 200 characters or fewer."
        if error:
            flash(error, "error")
            return redirect(back)
        changes['barangay_id'] = barangay_id
        changes['address'] = address or None

    if not changes:
        flash("Nothing to update.", "success")
        return redirect(back)

    patient_model.update_patient(patient_id, changes)

    after_loc = patient_model.format_location(patient_model.get_patient_by_id(patient_id))
    if after_loc != before_loc:
        flagged['location'] = before_loc

    if not flagged:
        flash("Everything is already up to date.", "success")
    else:
        for key, previous in flagged.items():
            visit_model.record_patient_profile_edit(patient_id, key, previous)
        flash("Your details were updated. Your health worker will be notified.", "success")
    return redirect(back)