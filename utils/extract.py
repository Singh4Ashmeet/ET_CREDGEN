import os
import pdfplumber
import json
import re
from datetime import datetime
from groq import Groq
from dotenv import load_dotenv

# ── OCR imports ───────────────────────────────────────────────────────────────
try:
    from pdf2image import convert_from_path
    import pytesseract
    pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("⚠️  OCR not available. Install pdf2image + pytesseract for image PDFs.")

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

# ──────────────────────────────────────────────────────────────────────────────
# STEP 1: TEXT EXTRACTION (text layer first, OCR fallback)
# ──────────────────────────────────────────────────────────────────────────────

def preprocess_for_ocr(img):
    from PIL import ImageFilter, ImageEnhance
    img = img.convert("L")
    img = ImageEnhance.Contrast(img).enhance(2.5)
    img = img.filter(ImageFilter.SHARPEN)
    return img


def extract_text(pdf_path):
    text = ""
    with pdfplumber.open(pdf_path) as doc:
        for page in doc.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"

    if not text.strip():
        if not OCR_AVAILABLE:
            print(f"  ⚠️  No text layer in {pdf_path} and OCR is not installed.")
            return ""
        print(f"  📷 No text layer — running OCR on {pdf_path}...")
        images = convert_from_path(pdf_path, dpi=300, poppler_path=r"C:\poppler\Library\bin")
        for img in images:
            img = preprocess_for_ocr(img)
            text += pytesseract.image_to_string(img, config="--psm 6") + "\n"

    return text.strip()


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2: CLASSIFY DOCUMENT BY CONTENT (not filename)
# ──────────────────────────────────────────────────────────────────────────────

CLASSIFY_PROMPT = """You are a document classifier for a loan processing system.
Read the following document text and classify it into exactly ONE of these types:
- aadhaar   → Aadhaar card issued by UIDAI / Unique Identification Authority of India
- pan       → PAN card issued by Income Tax Department / Permanent Account Number
- form16    → Form 16 or Form 16A, TDS certificate, Certificate of Deduction of Tax at Source
- itr       → Income Tax Return document (ITR-1, ITR-2, ITR-3, ITR-4 etc.)
- bank      → Bank account statement or passbook
- unknown   → Cannot be determined

Reply with ONLY one word from the list above. No explanation, no punctuation.

Document text:
"""

def classify_document(text):
    preview = text[:800]  # first 800 chars is enough to classify
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        max_tokens=10,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": "You are a document classifier. Reply with exactly one word."
            },
            {
                "role": "user",
                "content": CLASSIFY_PROMPT + preview
            }
        ]
    )
    result = response.choices[0].message.content.strip().lower()
    # Sanitize — only accept known types
    valid = {"aadhaar", "pan", "form16", "itr", "bank"}
    return result if result in valid else "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# STEP 3: PER-DOCUMENT EXTRACTION PROMPTS
# ──────────────────────────────────────────────────────────────────────────────

PROMPTS = {
    "aadhaar": """
Extract information from this Aadhaar card and return ONLY a JSON object with EXACTLY these keys:
{
  "name": "full name",
  "date_of_birth": "DD-MM-YYYY",
  "gender": "Male/Female/Other",
  "aadhaar_number": "12 digit number as string",
  "house_number": "house/flat number",
  "sector": "sector/area/street name",
  "city": "city name",
  "state": "state name",
  "pincode": "6 digit pincode as string"
}
IMPORTANT:
- "aadhaar_number": look for any 12-digit number in the text, often written as groups like "1234 5678 9012". It may appear anywhere including near the bottom or footer. Remove spaces and return as a 12-digit string.
- Ignore Hindi/Devanagari script — extract only from the English text portions.
Return null for any field not found. Return ONLY the JSON, no explanation, no markdown.
Document text:
""",

    "pan": """
Extract information from this PAN card and return ONLY a JSON object with EXACTLY these keys:
{
  "name": "full name",
  "date_of_birth": "DD-MM-YYYY",
  "pan_number": "10 character PAN"
}
Return null for any field not found. Return ONLY the JSON, no explanation, no markdown.
Document text:
""",

    "form16": """
Extract information from this Form 16 / TDS certificate and return ONLY a JSON object with EXACTLY these keys:
{
  "employee_name": "full name of employee/taxpayer from the Name field",
  "pan_number": "10 character PAN of the employee",
  "aadhaar_number": "12 digit Aadhaar number of the employee if mentioned",
  "employer_name": "name of the employer or deductor company — must be a company/org name, NOT an address",
  "assessment_year": "assessment year e.g. 2022-23",
  "gross_salary": 0,
  "net_taxable_income": 0,
  "tds_deducted": 0
}
IMPORTANT:
- "employer_name": must be a company or organization name. If you only see an address, return null.
- "aadhaar_number": look for "Aadhaar Number of the Employee". Remove spaces, return 12-digit string.
- "gross_salary": use ONLY Part B line 1 "Gross Salary" value. Do NOT use subtotals or totals.
- "net_taxable_income": use Part B line 5 "Total income" or "Income Chargeable". Do NOT use Balance or Deductions lines.
- "tds_deducted": use the final "Total TDS" or Part A Total from the last row.
- INDIAN NUMBER FORMAT: numbers like 12,40,000 use Indian formatting (lakhs). 12,40,000 = 1240000. 1,00,000 = 100000. Always parse correctly — do NOT treat Indian commas as thousands separators.
- Remove all commas from numbers after parsing. Return pure integers.
Return null for any field not found. Return ONLY the JSON, no explanation, no markdown.
Document text:
""",

    "itr": """
Extract information from this ITR (Income Tax Return) and return ONLY a JSON object with EXACTLY these keys:
{
  "name": "full name",
  "pan_number": "10 character PAN",
  "assessment_year": "assessment year e.g. 2024-25",
  "business_name": "name of business or occupation",
  "gross_receipts": 0,
  "net_profit": 0,
  "total_income": 0,
  "tax_paid": 0
}
IMPORTANT:
- "gross_receipts": "Gross Annual Income", "Gross Receipts", "Turnover"
- "net_profit": "Net Profit", "Net Taxable Income", "Net Income", "Taxable Income"
- "total_income": "Total Income"
- "tax_paid": "Tax Paid", "Advance Tax", "TDS", "Total Tax Deducted"
- INDIAN NUMBER FORMAT: numbers use Indian formatting (lakhs/crores). 9,60,000 = 960000. 1,00,000 = 100000. Parse correctly — do NOT treat Indian commas as thousands separators.
- Remove all commas from numbers after parsing. Return pure integers.
Return null for any field not found. Return ONLY the JSON, no explanation, no markdown.
Document text:
""",

    "bank": """
Extract information from this bank statement and return ONLY a JSON object with EXACTLY these keys:
{
  "bank_name": "bank name from the top of the document — a brand/institution name, NOT an address",
  "account_holder_name": "account holder full name",
  "account_number": "account number as string",
  "statement_period": "period string",
  "opening_balance": 0,
  "closing_balance": 0,
  "average_balance": 0
}
IMPORTANT:
- "bank_name": the institution name at the top (e.g. "Horizon Bank", "HDFC Bank"). Never use an address.
- "opening_balance": look for "Opening Balance" at the start of the statement.
- "closing_balance": look for "Closing Balance" or "Ending Balance" at the end of the statement.
- "average_balance": use the explicitly labeled "Average Balance" field ONLY if present. Otherwise return null — it will be calculated from opening and closing.
- Remove all commas from numbers. Return pure integers or floats.
Return null for any field not found. Return ONLY the JSON, no explanation, no markdown.
Document text:
"""
}


# ──────────────────────────────────────────────────────────────────────────────
# STEP 4: ROBUST JSON PARSER
# ──────────────────────────────────────────────────────────────────────────────

def clean_nulls(data):
    if isinstance(data, dict):
        return {k: clean_nulls(v) for k, v in data.items()}
    if isinstance(data, list):
        return [clean_nulls(i) for i in data]
    if isinstance(data, str) and data.strip().lower() in ("null", "none", "n/a", ""):
        return None
    return data


def parse_json_response(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?", "", text, flags=re.MULTILINE).strip()
    text = re.sub(r"```$", "", text, flags=re.MULTILINE).strip()
    try:
        return clean_nulls(json.loads(text))
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return clean_nulls(json.loads(match.group()))
        except json.JSONDecodeError:
            pass
    print("  ⚠️  Could not parse JSON from response.")
    return {}


# ──────────────────────────────────────────────────────────────────────────────
# STEP 5: EXTRACT STRUCTURED DATA
# ──────────────────────────────────────────────────────────────────────────────

def extract_structured(text, doc_type):
    prompt = PROMPTS.get(doc_type, "Extract all key information as JSON:\n")
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        max_tokens=2048,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a document data extraction assistant for a financial institution. "
                    "Extract structured data from KYC documents. Always respond with the requested "
                    "JSON format only. Never refuse — this is a legitimate loan processing workflow."
                )
            },
            {
                "role": "user",
                "content": prompt + text
            }
        ]
    )
    raw = response.choices[0].message.content
    print("\n🔹 RAW AI RESPONSE:\n", raw)
    parsed = parse_json_response(raw)
    print("\n🔸 PARSED DATA:\n", json.dumps(parsed, indent=2))
    return parsed


# ──────────────────────────────────────────────────────────────────────────────
# STEP 6: PROCESSORS — write to unified profile
# ──────────────────────────────────────────────────────────────────────────────

def calculate_age(dob):
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(dob, fmt)
            t = datetime.today()
            return t.year - d.year - ((t.month, t.day) < (d.month, d.day))
        except:
            continue
    return None


def set_if_missing(profile, key, value):
    """Only write to profile if field is not already set."""
    if value and not profile.get(key):
        profile[key] = value


def set_dob(profile, dob):
    if dob and not profile.get("date_of_birth"):
        dob = dob.replace("/", "-")
        profile["date_of_birth"] = dob
        profile["age"] = calculate_age(dob)


def process_aadhaar(data, profile):
    set_if_missing(profile, "name", data.get("name"))
    set_if_missing(profile, "gender", data.get("gender"))
    set_if_missing(profile, "aadhaar_number", data.get("aadhaar_number"))
    set_if_missing(profile, "city", data.get("city"))
    set_if_missing(profile, "state", data.get("state"))
    set_if_missing(profile, "pincode", data.get("pincode"))
    set_dob(profile, data.get("date_of_birth"))

    house = data.get("house_number")
    sector = data.get("sector")
    city = data.get("city")
    if (house or sector) and not profile.get("full_address"):
        profile["full_address"] = f"{house}, {sector}, {city}".strip(", ")


def process_pan(data, profile):
    set_if_missing(profile, "pan_number", data.get("pan_number"))
    set_if_missing(profile, "name", data.get("name"))
    set_dob(profile, data.get("date_of_birth"))


def process_form16(data, profile):
    profile["employment_type"] = "salaried"
    set_if_missing(profile, "pan_number", data.get("pan_number"))
    set_if_missing(profile, "aadhaar_number", data.get("aadhaar_number"))
    set_if_missing(profile, "name", data.get("employee_name"))
    set_if_missing(profile, "employer_name", data.get("employer_name"))
    set_if_missing(profile, "assessment_year", data.get("assessment_year"))

    gross = data.get("gross_salary")
    if isinstance(gross, (int, float)) and gross:
        profile["annual_income"] = float(gross)
        profile["monthly_income"] = round(float(gross) / 12, 2)

    net = data.get("net_taxable_income")
    if isinstance(net, (int, float)) and net:
        profile["net_taxable_income"] = float(net)

    tds = data.get("tds_deducted")
    if isinstance(tds, (int, float)) and tds:
        profile["tds_deducted"] = float(tds)


def process_itr(data, profile):
    profile["employment_type"] = "self_employed"
    set_if_missing(profile, "pan_number", data.get("pan_number"))
    set_if_missing(profile, "name", data.get("name"))
    set_if_missing(profile, "business_name", data.get("business_name"))
    set_if_missing(profile, "assessment_year", data.get("assessment_year"))

    gross = data.get("gross_receipts")
    if isinstance(gross, (int, float)) and gross:
        profile["gross_receipts"] = float(gross)

    net = data.get("net_profit")
    if isinstance(net, (int, float)) and net:
        profile["annual_net_profit"] = float(net)
        profile["annual_income"] = float(net)
        profile["monthly_income"] = round(float(net) / 12, 2)

    total = data.get("total_income")
    if isinstance(total, (int, float)) and total:
        profile["total_income"] = float(total)

    tax = data.get("tax_paid")
    if isinstance(tax, (int, float)) and tax:
        profile["tax_paid"] = float(tax)


def process_bank(data, profile):
    set_if_missing(profile, "bank_name", data.get("bank_name"))
    set_if_missing(profile, "account_holder_name", data.get("account_holder_name"))
    if data.get("account_number") and not profile.get("account_number"):
        profile["account_number"] = str(data.get("account_number"))

    # Use explicit average balance if present, otherwise calculate from opening + closing
    avg = data.get("average_balance")
    opening = data.get("opening_balance")
    closing = data.get("closing_balance")

    if isinstance(avg, (int, float)) and avg:
        profile["average_balance"] = float(avg)
    elif isinstance(opening, (int, float)) and isinstance(closing, (int, float)):
        profile["average_balance"] = round((float(opening) + float(closing)) / 2, 2)
        print(f"  📊 Average balance calculated: ({opening} + {closing}) / 2 = {profile['average_balance']}")


# ──────────────────────────────────────────────────────────────────────────────
# STEP 7: VALIDATE — check what's missing
# ──────────────────────────────────────────────────────────────────────────────

REQUIRED_FIELDS = {
    "name":           "Full name (from Aadhaar/PAN/Form16/ITR)",
    "date_of_birth":  "Date of birth (from Aadhaar/PAN)",
    "aadhaar_number": "Aadhaar number (from Aadhaar card)",
    "pan_number":     "PAN number (from PAN card/Form16/ITR)",
    "employment_type":"Employment type (needs Form16 or ITR)",
    "monthly_income": "Monthly income (from Form16 or ITR)",
    "annual_income":  "Annual income (from Form16 or ITR)",
    "account_number": "Bank account number (from bank statement)",
    "average_balance":"Account balance (from bank statement)",
}

def validate_profile(profile):
    missing = []
    for field, description in REQUIRED_FIELDS.items():
        if not profile.get(field):
            missing.append(f"  ❌ {field}: {description}")
    return missing


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def extract_profile(pdf_paths):
    profile = {}
    for pdf in pdf_paths:
        text = extract_text(pdf)
        if not text:
            continue
        doc_type = classify_document(text)
        if doc_type == "unknown":
            continue
        data = extract_structured(text, doc_type)
        if doc_type == "aadhaar":    process_aadhaar(data, profile)
        elif doc_type == "pan":      process_pan(data, profile)
        elif doc_type == "form16":   process_form16(data, profile)
        elif doc_type == "itr":      process_itr(data, profile)
        elif doc_type == "bank":     process_bank(data, profile)

    final_output = {
        "personal_info": {
            "name":           profile.get("name"),
            "date_of_birth":  profile.get("date_of_birth"),
            "age":            profile.get("age"),
            "gender":         profile.get("gender"),
            "aadhaar_number": profile.get("aadhaar_number"),
            "pan_number":     profile.get("pan_number"),
        },
        "contact_info": {
            "full_address":   profile.get("full_address"),
            "city":           profile.get("city"),
            "state":          profile.get("state"),
            "pincode":        profile.get("pincode"),
        },
        "employment_info": {
            "employment_type":    profile.get("employment_type"),
            "employer_name":      profile.get("employer_name"),
            "assessment_year":    profile.get("assessment_year"),
            "monthly_income":     profile.get("monthly_income"),
            "annual_income":      profile.get("annual_income"),
            "net_taxable_income": profile.get("net_taxable_income"),
            "tds_deducted":       profile.get("tds_deducted"),
            "business_name":      profile.get("business_name"),
            "gross_receipts":     profile.get("gross_receipts"),
            "annual_net_profit":  profile.get("annual_net_profit"),
            "total_income":       profile.get("total_income"),
            "tax_paid":           profile.get("tax_paid"),
        },
        "bank_info": {
            "bank_name":           profile.get("bank_name"),
            "account_holder_name": profile.get("account_holder_name"),
            "account_number":      profile.get("account_number"),
            "average_balance":     profile.get("average_balance"),
        }
    }
    missing = validate_profile(profile)
    return final_output, missing
