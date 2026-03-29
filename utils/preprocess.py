import re
import string

def clean_text(text):
    """Clean and normalize text"""
    text = text.lower().strip()
    text = text.translate(str.maketrans('', '', string.punctuation))
    return text

def extract_amount(text):
    """Extract loan amount with context awareness."""
    text = text.lower()
    
    # Context-aware pattern: looks for loan/need/amount near a number
    # Also handles lakhs/lac/L suffix specifically for the number
    patterns = [
        r'(?:loan|amount|need|of|for|₹|rs\.?)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(lakh|lac|l|cr|crore)?\b',
        r'\b(\d+(?:,\d+)*(?:\.\d+)?)\s*(lakh|lac|l|cr|crore)\b'
    ]
    
    for pattern in patterns:
        matches = re.finditer(pattern, text)
        for match in matches:
            val_str = match.group(1).replace(',', '')
            try:
                amount = float(val_str)
                suffix = match.group(2)
                if suffix in ['lakh', 'lac', 'l']:
                    amount *= 100000
                elif suffix in ['cr', 'crore']:
                    amount *= 10000000
                
                if amount >= 10000: # Threshold to avoid picking up age/tenure
                    return int(amount)
            except:
                continue
    return None

def extract_tenure(text):
    """Extract tenure with context awareness."""
    text = text.lower()
    
    # Specific patterns for months and years that aren't age
    patterns = [
        r'(\d+)\s*(?:month|mon|m)\b',
        r'(?:for|tenure|period|of)\s*(\d+)\s*(?:year|yr|y)\b'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            val = int(match.group(1))
            if 'year' in pattern or 'yr' in pattern or 'y' in match.group(0):
                if val < 50: # Likely years
                    return val * 12
            return val
    return None

def extract_age(text):
    """Extract age with context awareness."""
    text = text.lower()
    patterns = [
        r'(\d{2})\s*(?:year|yr|y)?\s*(?:old|age)\b',
        r'(?:age|is|am)\s*(\d{2})\b'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            val = int(match.group(1))
            if 18 <= val <= 85:
                return val
    return None

def extract_income(text):
    """Extract income with context awareness."""
    text = text.lower()
    
    # Patterns for LPA, monthly, annual
    patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:lpa|lakh per annum|lakh a year)',
        r'(\d+(?:,\d+)*)\s*(?:per month|pm|monthly)',
        r'(?:income|earn|salary|earning)(?:\s+is)?\s*(?:rs\.?|₹)?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(lakh|lac|l)?(?:\s*(?:per year|yearly|per annum|annually|a year))?'
    ]
    
    for i, pattern in enumerate(patterns):
        match = re.search(pattern, text)
        if match:
            try:
                val = float(match.group(1).replace(',', ''))
                if i == 0: # LPA
                    return int(val * 100000)
                if i == 1: # Monthly
                    if val < 1000: # handled as 'k'
                         val *= 1000
                    return int(val * 12)
                if i == 2: # Annual
                    suffix = match.group(2) if len(match.groups()) > 1 else None
                    if suffix in ['lakh', 'lac', 'l']:
                        val *= 100000
                    return int(val)
            except:
                continue
    return None

def extract_name(text):
    """Extract name using simple patterns"""
    # Pattern: "I'm NAME" or "My name is NAME"
    pattern1 = r"(?:i'm|i am|my name is|this is)\s+([a-z]+(?:\s+[a-z]+)?)"
    match = re.search(pattern1, text.lower())
    if match:
        name = match.group(1)
        return name.title()
    
    return None

def extract_pan(text):
    """Extract PAN card number"""
    pattern = r'\b[A-Z]{5}\d{4}[A-Z]\b'
    match = re.search(pattern, text.upper())
    return match.group(0) if match else None

def extract_aadhaar(text):
    """Extract Aadhaar number"""
    pattern = r'\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b'
    match = re.search(pattern, text)
    if match:
        return match.group(0).replace('-', '').replace(' ', '')
    return None

def extract_pincode(text):
    """Extract 6-digit pincode"""
    pattern = r'\b\d{6}\b'
    match = re.search(pattern, text)
    return match.group(0) if match else None

def extract_employment_type(text):
    """Extract employment type"""
    text = text.lower()
    if any(word in text for word in ['salaried', 'salary', 'employee', 'job']):
        return 'salaried'
    elif any(word in text for word in ['self employed', 'self-employed', 'business', 'entrepreneur']):
        return 'self_employed'
    elif 'professional' in text:
        return 'professional'
    return None

def extract_purpose(text):
    """Extract loan purpose"""
    text = text.lower()
    purposes = {
        'home': ['home', 'house', 'property', 'renovation', 'repair'],
        'education': ['education', 'study', 'college', 'university', 'course'],
        'business': ['business', 'startup', 'venture', 'company'],
        'medical': ['medical', 'health', 'hospital', 'treatment'],
        'personal': ['personal', 'family', 'wedding', 'travel']
    }
    
    for purpose, keywords in purposes.items():
        if any(keyword in text for keyword in keywords):
            return purpose
    return 'personal'  # default

def validate_amount(amount):
    """Validate loan amount against constraints"""
    from utils.config import MIN_LOAN_AMOUNT, MAX_LOAN_AMOUNT
    if amount and MIN_LOAN_AMOUNT <= amount <= MAX_LOAN_AMOUNT:
        return True
    return False

def validate_age(age):
    """Validate age against constraints"""
    from utils.config import MIN_AGE, MAX_AGE
    if age and MIN_AGE <= age <= MAX_AGE:
        return True
    return False

def validate_tenure(tenure):
    """Validate tenure against constraints"""
    from utils.config import MIN_TENURE, MAX_TENURE
    if tenure and MIN_TENURE <= tenure <= MAX_TENURE:
        return True
    return False
