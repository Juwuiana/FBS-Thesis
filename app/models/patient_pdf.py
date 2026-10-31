"""
Server-side PDF of one screening result, so "Save as PDF" downloads a file
directly instead of opening the browser print dialog. Needs: pip install reportlab
"""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, KeepTogether

_GREEN, _AMBER, _RED, _GREY, _INK = "#27ae60", "#d97706", "#dc2626", "#64748b", "#1e293b"
_BAND_COLOR = {"Normal": _GREEN, "Pre-Diabetic": _AMBER, "Diabetic": _RED}
_RISK_COLOR = {"Low Risk": _GREEN, "Moderate Risk": _AMBER, "High Risk": _RED}

_CVD_LABELS = {
    "q1_chest_discomfort": "Pain/discomfort/pressure in chest",
    "q2_pain_center_left_arm": "Pain in center/left chest or left arm",
    "q3_occurs_uphill_hurrying": "Occurs when walking uphill or hurrying",
    "q4_slows_down_if_occurs": "Slows down if it occurs while walking",
    "q5_relieved_by_rest_tablet": "Goes away standing still or with under-tongue tablet",
    "q6_relieved_under_10min": "Goes away in less than 10 minutes",
    "q7_severe_pain_30min_plus": "Severe chest pain lasting half an hour or more",
    "q8_tia_stroke_symptoms": "TIA/Stroke: difficulty talking, weakness or numbness",
}


def _t(value, unit=""):
    """Plain text for a possibly-missing value (Helvetica can't draw the em dash)."""
    if value is None or value == "":
        return "-"
    return escape(f"{value:g}" if isinstance(value, float) else str(value)) + (f" {unit}" if unit else "")


def build_result_pdf(patient: dict, v: dict) -> bytes:
    ss = getSampleStyleSheet()
    base = ParagraphStyle("b", parent=ss["Normal"], fontName="Helvetica", fontSize=9.5, leading=13, textColor=colors.HexColor(_INK))
    small = ParagraphStyle("s", parent=base, fontSize=8, textColor=colors.HexColor(_GREY))
    h_title = ParagraphStyle("t", parent=base, fontName="Helvetica-Bold", fontSize=18, leading=22)
    h_sec = ParagraphStyle("h", parent=base, fontName="Helvetica-Bold", fontSize=9, textColor=colors.HexColor(_GREY), spaceBefore=10, spaceAfter=3)

    def section(title, flowables):
        return KeepTogether([Paragraph(title.upper(), h_sec),
                             Table([[""]], colWidths=[174 * mm], rowHeights=[0.4],
                                   style=[("LINEABOVE", (0, 0), (-1, 0), 0.6, colors.HexColor("#e2e8f0"))]),
                             Spacer(1, 3), *flowables])

    def grid(pairs):
        rows, row = [], []
        for k, val in pairs:
            row.append([Paragraph(escape(k), small), Paragraph(f"<b>{val}</b>", base)])
            if len(row) == 2:
                rows.append(row); row = []
        if row:
            rows.append(row + [""])
        tbl = Table(rows, colWidths=[87 * mm, 87 * mm])
        tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 5), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        return [tbl]

    def pills(items, empty):
        return [Paragraph(", ".join(escape(i) for i in items) if items else escape(empty), base)]

    story = []
    name = f"{patient.get('first_name', '')} {patient.get('last_name', '')}".strip()
    story += [Paragraph(escape(str(v["date"])), h_title),
              Paragraph(f"Assessment No. {escape(str(patient.get('patient_code', '')))}-{v['visit_id']} &nbsp;|&nbsp; {escape(name)}", small),
              Spacer(1, 8)]

    # FBS reading + risk
    fbs, band, risk = v.get("fbs_score"), v.get("fbs_band"), v.get("risk_level")
    t = (v.get("trend") or {}).get("fbs_score")
    trend_txt = f" &nbsp;({'up' if t['dir'] == 'up' else 'down'} {t['diff']:g} since {escape(str(t['prev_date']))})" if t else ""
    box = Table([[Paragraph("FBS READING", small), Paragraph("RISK LEVEL", small)],
                 [Paragraph(f'<font size="20"><b>{_t(fbs)}</b></font> mg/dL{trend_txt}', base),
                  Paragraph(f'<font size="14" color="{_RISK_COLOR.get(risk, _GREY)}"><b>{escape(risk or "Pending")}</b></font>', base)],
                 [Paragraph(f'<font color="{_BAND_COLOR.get(band, _GREY)}"><b>{escape(band or "Pending")}</b></font> '
                            f'<font size="8" color="{_GREY}">(Normal below 100, Pre-diabetic 100-125, Diabetic 126 or higher)</font>', base), ""]],
                colWidths=[110 * mm, 64 * mm])
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor(_BAND_COLOR.get(band, "#e2e8f0"))),
                             ("SPAN", (0, 2), (1, 2)), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("TOPPADDING", (0, 0), (-1, -1), 4),
                             ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    story.append(box)

    if v.get("reasons"):
        story.append(section("Why this result", [Paragraph("&bull; " + escape(r), base) for r in v["reasons"]]))

    sex = patient.get("sex")
    story.append(section("Patient", grid([
        ("Full Name", escape(name)), ("Patient ID", _t(patient.get("patient_code"))),
        ("Sex", _t(sex)), ("Civil Status", _t(patient.get("civil_status"))),
        ("Occupation", _t(patient.get("occupation"))), ("Email", _t(patient.get("email"))),
    ])))

    cond = v.get("conditions") or {}
    story.append(section("Past Medical History", pills(cond.get("pmh"), "None reported")))
    story.append(section("Family History (1st degree relative)", pills(cond.get("family_history"), "None reported")))

    cvd = v.get("cvd_responses") or {}
    yes = [lbl for k, lbl in _CVD_LABELS.items() if cvd.get(k)]
    story.append(section("CVD Questionnaire", pills(yes, "All answers: No") if yes else [Paragraph("All answers: No", base)]))
    if yes:
        story.append(Paragraph("Questions answered Yes are listed above.", small))

    story.append(section("Lifestyle Factors", grid([
        ("Smoking Status", _t(v.get("smoking_status"))), ("Alcohol Intake", _t(v.get("alcohol_intake"))),
        ("Illicit Drug Use", _t(v.get("illicit_drug_use"))), ("Physical Activity", _t(v.get("physical_activity"))),
    ]) + [Paragraph("Dietary factors: " + (escape(", ".join(cond.get("diet", []))) or "none reported"), base)]))

    story.append(section("Diabetes History", grid([("Previously Diagnosed with Diabetes", _t(v.get("diabetes_diagnosis")))])
                         + [Paragraph("Symptoms: " + (escape(", ".join(cond.get("dm_symptom", []))) or "none reported"), base)]))
    story.append(section("Past Surgical History", [Paragraph(_t(v.get("past_surgical_history")), base)]))

    if (sex or "").lower() == "female":
        story.append(section("Menstrual & Pregnancy History", grid([
            ("Age at Menarche", _t(v.get("menarche_age"))), ("Last Menstrual Period", _t(v.get("lmp_date"))),
            ("Gravida", _t(v.get("gravida"))), ("Para", _t(v.get("para"))),
        ])))

    bp = f"{v['bp_systolic']:g}/{v['bp_diastolic']:g} mmHg" if v.get("bp_systolic") is not None and v.get("bp_diastolic") is not None else "-"
    story.append(section("Anthropometric Measurements & Vitals", grid([
        ("Blood Pressure", bp), ("Heart Rate", _t(v.get("heart_rate"), "bpm")),
        ("Respiratory Rate", _t(v.get("respiratory_rate"), "/min")), ("Height", _t(v.get("height_cm"), "cm")),
        ("Weight", _t(v.get("weight_kg"), "kg")), ("BMI", _t(v.get("bmi"))),
        ("Weight Class", _t(v.get("obesity_class"))), ("Waist", _t(v.get("waist_cm"), "cm")),
    ])))

    story.append(section("Follow-up & Referral", grid([
        ("Next Follow-up", _t(v.get("follow_up_date") or "Not scheduled")), ("Referred To", _t(v.get("referred_to"))),
    ])))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5); canvas.setFillColor(colors.HexColor(_GREY))
        canvas.drawString(18 * mm, 10 * mm, "FBS Diabetes Risk System - confidential health record. For reference only; your health worker makes the final assessment.")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                      title=f"Assessment Report {v['date']}").build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
