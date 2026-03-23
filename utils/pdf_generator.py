import os
import uuid
import asyncio
import logging
from pathlib import Path
from datetime import date, datetime
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch, cm
from reportlab.lib.colors import HexColor, white, black, lightgrey
from reportlab.lib import colors

logger = logging.getLogger(__name__)

# ─── COLOURS ──────────────────────────────────────────────────────────
BRAND_BLUE  = HexColor("#1a3a5c")
BRAND_LIGHT = HexColor("#e8f0fe")
ACCENT_GOLD = HexColor("#c9a84c")
ROW_ALT     = HexColor("#f5f7fa")
TEXT_DARK    = HexColor("#1f2937")
TEXT_GREY    = HexColor("#6b7280")


def get_pdf_input_details(state: dict) -> dict:
    """Map Master Agent state → PDF-ready data."""
    entities = state.get('entities', {})
    loan_amount = entities.get('loan_amount', 0)
    processing_charges = loan_amount * 0.01

    return {
        'cust_name':    entities.get('name', 'Loan Applicant'),
        'cust_add':     entities.get('address', 'Address N/A'),
        'pincode':      entities.get('pincode', 'N/A'),
        'phone':        entities.get('phone', 'N/A'),
        'email':        entities.get('email', 'N/A'),
        'pan':          entities.get('pan', 'N/A'),
        'aadhaar':      _mask_aadhaar(entities.get('aadhaar', '')),
        'amt':          loan_amount,
        'tenure':       entities.get('tenure', 36),
        'roi':          state.get('interest_rate', 15.0),
        'processing_charges': processing_charges,
        'coborrower':   entities.get('coborrower', 'NIL'),
        'purpose':      entities.get('purpose', 'Personal'),
        'employment':   entities.get('employment_type', 'N/A'),
    }


def _mask_aadhaar(aadhaar: str) -> str:
    if aadhaar and len(aadhaar) >= 8:
        return 'XXXX-XXXX-' + aadhaar[-4:]
    return 'N/A'


def _fmt_inr(amount) -> str:
    try:
        amount = int(round(float(amount)))
        s = str(amount)
        if len(s) <= 3:
            return s
        last = s[-3:]
        rest = s[:-3]
        parts = []
        while rest:
            parts.insert(0, rest[-2:])
            rest = rest[:-2]
        return ','.join(parts) + ',' + last
    except Exception:
        return str(amount)


# ─── PDF GENERATION ───────────────────────────────────────────────────

def _draw_header(c, width, height, sanction_no, issue_date):
    """Blue banner + branding + reference box."""
    # Banner
    c.setFillColor(BRAND_BLUE)
    c.rect(0, height - 2.2 * cm, width, 2.2 * cm, fill=1, stroke=0)

    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(2 * cm, height - 1.6 * cm, "CredGen Financial Services")
    c.setFont("Helvetica", 9)
    c.drawString(2 * cm, height - 2.0 * cm, "NBFC Reg. No. XX-XXXXX  |  CIN: U65999MH2024PLC000000")

    # Gold accent line
    c.setStrokeColor(ACCENT_GOLD)
    c.setLineWidth(2)
    c.line(0, height - 2.2 * cm, width, height - 2.2 * cm)

    # Reference box
    box_y = height - 3.8 * cm
    c.setStrokeColor(BRAND_BLUE)
    c.setLineWidth(0.5)
    c.roundRect(2 * cm, box_y, width - 4 * cm, 1.3 * cm, 4, stroke=1, fill=0)

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(BRAND_BLUE)
    c.drawString(2.3 * cm, box_y + 0.8 * cm, f"Sanction No: {sanction_no}")
    c.drawRightString(width - 2.3 * cm, box_y + 0.8 * cm, f"Date: {issue_date}")
    c.setFont("Helvetica", 8)
    c.setFillColor(TEXT_GREY)
    c.drawString(2.3 * cm, box_y + 0.3 * cm, "PERSONAL LOAN SANCTION LETTER")


def _draw_table(c, x, y, headers, rows, col_widths, width):
    """Generic alternating-row table."""
    row_h = 0.55 * cm
    header_h = 0.65 * cm

    # Header row
    c.setFillColor(BRAND_BLUE)
    c.rect(x, y - header_h, sum(col_widths), header_h, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 8)
    cx = x
    for i, hdr in enumerate(headers):
        c.drawString(cx + 0.2 * cm, y - header_h + 0.2 * cm, hdr)
        cx += col_widths[i]

    # Data rows
    cy = y - header_h
    for idx, row in enumerate(rows):
        cy -= row_h
        if idx % 2 == 0:
            c.setFillColor(ROW_ALT)
            c.rect(x, cy, sum(col_widths), row_h, fill=1, stroke=0)

        c.setFillColor(TEXT_DARK)
        c.setFont("Helvetica", 8)
        cx = x
        for i, cell in enumerate(row):
            c.drawString(cx + 0.2 * cm, cy + 0.15 * cm, str(cell))
            cx += col_widths[i]

    return cy


def _draw_terms(c, y, margin):
    """Terms & conditions numbered list."""
    terms = [
        "This sanction letter is valid for 30 days from the date of issue.",
        "The sanctioned amount is subject to completion of all documentation and KYC verification.",
        "Interest rate is fixed for the tenure and will not change post-disbursal.",
        "Prepayment is allowed after 6 months with applicable charges as per RBI guidelines.",
        "EMI will be debited on the 5th of every month via NACH/ECS mandate.",
        "Any misrepresentation of information may result in immediate recall of the loan.",
        "This letter does not constitute a commitment to disburse unless all conditions precedent are fulfilled.",
    ]

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(BRAND_BLUE)
    c.drawString(margin, y, "Terms & Conditions")
    y -= 0.4 * cm

    c.setFont("Helvetica", 7)
    c.setFillColor(TEXT_GREY)
    for i, term in enumerate(terms, 1):
        c.drawString(margin + 0.3 * cm, y, f"{i}. {term}")
        y -= 0.35 * cm

    return y


def _draw_footer(c, width, height, margin):
    """Footer with contact info."""
    y = 1.5 * cm
    c.setStrokeColor(BRAND_BLUE)
    c.setLineWidth(0.5)
    c.line(margin, y + 0.3 * cm, width - margin, y + 0.3 * cm)

    c.setFont("Helvetica", 6.5)
    c.setFillColor(TEXT_GREY)
    c.drawCentredString(width / 2, y - 0.1 * cm,
                        "CredGen Financial Services  |  support@credgen.in  |  1800-XXX-XXXX  |  www.credgen.in")
    c.drawCentredString(width / 2, y - 0.45 * cm,
                        "This is a system-generated document and does not require a physical signature.")


def _create_pdf(out_path: str, details: dict, sanction_no: str):
    """Build the entire PDF."""
    width, height = A4
    margin = 2 * cm
    usable = width - 2 * margin
    c_pdf = canvas.Canvas(out_path, pagesize=A4)

    issue_date = date.today().strftime("%B %d, %Y")

    # ── HEADER ──
    _draw_header(c_pdf, width, height, sanction_no, issue_date)

    # ── ADDRESSEE ──
    y = height - 4.6 * cm
    c_pdf.setFont("Helvetica", 9)
    c_pdf.setFillColor(TEXT_DARK)
    c_pdf.drawString(margin, y, f"To,")
    y -= 0.4 * cm
    c_pdf.setFont("Helvetica-Bold", 10)
    c_pdf.drawString(margin, y, details['cust_name'])
    y -= 0.4 * cm
    c_pdf.setFont("Helvetica", 9)
    c_pdf.drawString(margin, y, f"{details['cust_add']}, Pincode: {details['pincode']}")
    y -= 0.4 * cm
    c_pdf.drawString(margin, y, f"Phone: {details['phone']}  |  Email: {details['email']}")

    # ── SALUTATION ──
    y -= 0.8 * cm
    c_pdf.setFont("Helvetica", 9)
    c_pdf.drawString(margin, y, f"Dear {details['cust_name']},")
    y -= 0.5 * cm
    c_pdf.drawString(margin, y, "We are pleased to inform you that your application for a Personal Loan has been approved.")
    y -= 0.3 * cm
    c_pdf.drawString(margin, y, "The details of the sanctioned loan are as follows:")

    # ── LOAN DETAILS TABLE ──
    y -= 0.8 * cm
    loan_rows = [
        ("Loan Amount",            f"₹ {_fmt_inr(details['amt'])}"),
        ("Tenure",                 f"{details['tenure']} Months"),
        ("Interest Rate (p.a.)",   f"{details['roi']:.2f} %"),
        ("Processing Fee (1%)",    f"₹ {_fmt_inr(details['processing_charges'])}"),
        ("Purpose",                details['purpose'].title()),
        ("Co-Borrower",            details['coborrower']),
    ]

    col_w = [usable * 0.45, usable * 0.55]
    y = _draw_table(c_pdf, margin, y, ["Parameter", "Sanctioned Value"], loan_rows, col_w, width)

    # ── APPLICANT DETAILS TABLE ──
    y -= 0.8 * cm
    c_pdf.setFont("Helvetica-Bold", 9)
    c_pdf.setFillColor(BRAND_BLUE)
    c_pdf.drawString(margin, y, "Applicant Details")
    y -= 0.1 * cm

    app_rows = [
        ("PAN",            details['pan']),
        ("Aadhaar",        details['aadhaar']),
        ("Employment",     details['employment'].replace('_', ' ').title()),
    ]
    y = _draw_table(c_pdf, margin, y, ["Field", "Value"], app_rows, col_w, width)

    # ── TERMS ──
    y -= 0.8 * cm
    y = _draw_terms(c_pdf, y, margin)

    # ── SIGNATURE BLOCK ──
    y -= 1.2 * cm
    c_pdf.setFont("Helvetica", 9)
    c_pdf.setFillColor(TEXT_DARK)
    c_pdf.drawString(margin, y, "For CredGen Financial Services,")
    y -= 0.8 * cm
    c_pdf.setFont("Helvetica-Bold", 10)
    c_pdf.drawString(margin, y, "Authorized Signatory")
    c_pdf.setFont("Helvetica", 8)
    c_pdf.drawString(margin, y - 0.35 * cm, "CredGen AI Agent System")

    # Customer acceptance on right side
    c_pdf.drawString(width - margin - 5 * cm, y, "Applicant Signature")
    c_pdf.line(width - margin - 5 * cm, y + 0.6 * cm,
               width - margin, y + 0.6 * cm)

    # ── WATERMARK ──
    c_pdf.saveState()
    c_pdf.setFillColor(HexColor("#e8f0fe"))
    c_pdf.setFont("Helvetica-Bold", 50)
    c_pdf.translate(width / 2, height / 2)
    c_pdf.rotate(45)
    c_pdf.drawCentredString(0, 0, "CREDGEN")
    c_pdf.restoreState()

    # ── FOOTER ──
    _draw_footer(c_pdf, width, height, margin)

    c_pdf.save()


# ─── PUBLIC API ───────────────────────────────────────────────────────

def generate_sanction_letter(master_agent_state: dict) -> str:
    """
    Synchronous entry point called by workflow_routes.py.
    Returns path to generated PDF.
    """
    details = get_pdf_input_details(master_agent_state)
    sanction_no = f"CG-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    safe_name = details['cust_name'].replace(' ', '_').replace('.', '')

    # Ensure output directory exists
    root = Path(__file__).resolve().parent.parent
    upload_dir = root / "uploads"
    upload_dir.mkdir(exist_ok=True)

    out_path = upload_dir / f"SL_{sanction_no}_{safe_name}.pdf"

    try:
        _create_pdf(str(out_path), details, sanction_no)
        logger.info(f"Sanction letter generated: {out_path}")
        return str(out_path)
    except Exception as e:
        logger.error(f"PDF generation error: {e}")
        return f"ERROR: {e}"
