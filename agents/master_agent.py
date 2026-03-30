import os
import re
import numpy as np
import torch
from sentence_transformers import SentenceTransformer, util
from typing import Dict, List, Tuple, Optional, Set, Any
import logging
from enum import Enum
import time
from datetime import datetime
from utils.config import REQUIRED_FIELDS as CFG_REQUIRED_FIELDS, KYC_FIELDS as CFG_KYC_FIELDS, WORKFLOW_STAGES

from utils.preprocess import (
    clean_text, extract_amount, extract_tenure, extract_age,
    extract_income, extract_name, extract_pan, extract_aadhaar,
    extract_pincode, extract_employment_type, extract_purpose,
    validate_amount, validate_age, validate_tenure
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ConversationStage(Enum):
    GREETING = "greeting"
    COLLECTING_DETAILS = "collecting_details"
    KYC_COLLECTION = "kyc_collection"
    FRAUD_CHECK = "fraud_check"
    UNDERWRITING = "underwriting"
    OFFER_PRESENTATION = "offer_presentation"
    REJECTION_COUNSELING = "rejection_counseling"
    DOCUMENTATION = "documentation"
    CLOSED = "closed"

class IntentType(Enum):
    GREETING = "greeting"
    LOAN_APPLICATION = "loan_application"
    RATE_INQUIRY = "rate_inquiry"
    NEGOTIATE_TERMS = "negotiate_terms"
    ACCEPT_OFFER = "accept_offer"
    REJECT_OFFER = "reject_offer"
    HELP_GENERAL = "help_general"
    EXIT = "exit"
    UNCLEAR = "unclear"
    PROVIDE_INFO = "provide_info"
    CHECK_ELIGIBILITY = "check_eligibility"
    EMI_QUERY = "emi_query"
    STATUS_CHECK = "status_check"

REQUIRED_FIELDS = CFG_REQUIRED_FIELDS
KYC_FIELDS = CFG_KYC_FIELDS

# ---------------------------------------------------------------------------
# Indian English conversation patterns (checked BEFORE calling the LLM)
# ---------------------------------------------------------------------------
CONVERSATION_PATTERNS = {
    IntentType.GREETING: [
        'hi', 'hello', 'hlo', 'hii', 'hey', 'namaste', 'namaskar',
        'good morning', 'good afternoon', 'good evening', 'sup',
    ],
    IntentType.LOAN_APPLICATION: [
        'loan chahiye', 'loan lena hai', 'mujhe loan', 'apply karna',
        'loan apply', 'i need a loan', 'i want a loan', 'loan do',
        'give me a loan', 'need financing', 'apply for loan',
        'loan application', 'need money', 'paisa chahiye',
    ],
    IntentType.CHECK_ELIGIBILITY: [
        'kitna milega', 'eligible', 'qualification', 'am i eligible',
        'how much can i get', 'eligibility', 'qualify',
    ],
    IntentType.EMI_QUERY: [
        'emi kya hogi', 'monthly payment', 'installment', 'emi kitni',
        'emi calculate', 'what will be my emi',
    ],
    IntentType.STATUS_CHECK: [
        'status', 'kahan tak', 'kitna hua', 'application status',
        'my application', 'where is my loan', 'track',
    ],
    IntentType.EXIT: [
        'band karo', 'cancel', 'nahi chahiye', 'exit', 'quit',
        'bye', 'goodbye', 'stop', 'end chat', 'close',
    ],
    IntentType.ACCEPT_OFFER: [
        'accept', 'i accept', 'yes', 'haan', 'proceed', 'agreed',
        'manzoor', "i'll take it", 'lets go', 'done', 'theek hai',
        'i accept the offer',
    ],
    IntentType.REJECT_OFFER: [
        'reject', 'no thanks', 'nahi', 'decline', 'not interested',
        'nahi chahiye ab', 'maybe later',
    ],
    IntentType.NEGOTIATE_TERMS: [
        'negotiate', 'reduce rate', 'lower interest', 'better offer',
        'kam karo', 'rate kam', 'discount',
        "i'd like", 'can you do better', 'too high',
    ],
    IntentType.RATE_INQUIRY: [
        'interest rate', 'what rate', 'roi', 'kitna percent',
        'rate of interest', 'what is the rate',
    ],
    IntentType.HELP_GENERAL: [
        'help', 'how does this work', 'explain', 'kaise',
        'what can you do', 'tell me more', 'process kya hai',
    ],
}


class MasterAgent:

    INTENT_TEMPLATES = {
        IntentType.GREETING: ["Hello", "Hi there", "Good morning", "Hey", "Greetings"],
        IntentType.LOAN_APPLICATION: ["I need a loan", "I want to apply for a loan",
                                      "Can I borrow money", "Give me a loan", "Loan application",
                                      "Apply for loan", "Need financing", "Looking for loan"],
        IntentType.RATE_INQUIRY: ["What is the interest rate", "How much interest will I pay",
                                  "Tell me about the rates", "Rate of interest", "What's the rate"],
        IntentType.NEGOTIATE_TERMS: ["Can you reduce the rate", "I want a better offer",
                                     "Lower the interest", "Can we negotiate", "Better terms"],
        IntentType.ACCEPT_OFFER: ["I accept the offer", "Yes I agree", "Proceed with the loan",
                                  "Approved", "I'll take it", "Let's proceed", "Yes please"],
        IntentType.REJECT_OFFER: ["I reject this offer", "No thanks", "Not interested",
                                  "I decline", "Not now", "Maybe later", "I refuse"],
        IntentType.HELP_GENERAL: ["I need help", "How does this work", "Explain the process",
                                  "Help me", "What can you do", "Tell me more"],
        IntentType.EXIT: ["Goodbye", "Exit", "Stop", "End chat", "Bye", "Close", "Quit"],
        IntentType.PROVIDE_INFO: ["My name is", "I am", "My income is", "I want",
                                  "I need", "My age is", "Here is my", "I work as"]
    }

    # Context-aware responses for different stages
    STAGE_RESPONSES = {
        ConversationStage.GREETING: [
            "Hello! I'm CredGen, your AI-powered loan assistant. I'll guide you through the loan application process step by step.",
            "Welcome to CredGen! I'm here to help you get a loan. Let's start with some basic details.",
            "Hi there! Ready to find the perfect loan for you. How can I assist?"
        ],
        ConversationStage.COLLECTING_DETAILS: [
            "Let's start with your basic loan requirements. I'll need a few details:",
            "Great! First, I need to collect some basic information about your loan needs:",
            "I'll help you apply. First, let me gather some basic details:"
        ],
        ConversationStage.KYC_COLLECTION: [
            "Now I need your KYC details for verification:",
            "Great! Now for the verification process, I need your KYC information:",
            "Next step is KYC verification. I need:"
        ],
        ConversationStage.OFFER_PRESENTATION: [
            "Based on your profile, here's our offer:",
            "Great news! I have a loan offer for you:",
            "Here's what we can offer based on your application:"
        ]
    }

    # Priority order for collecting missing fields
    FIELD_PRIORITY = ['loan_amount', 'purpose', 'name', 'age',
                      'employment_type', 'income', 'tenure']

    KYC_PRIORITY = ['pan', 'aadhaar', 'address', 'pincode']

    _shared_model = None
    _shared_embeddings = None
    _shared_intent_list = None

    def __init__(self, model_name='paraphrase-MiniLM-L6-v2'):
        """Initialize master agent with potentially shared AI model and fresh state"""
        self.state = self._initialize_state()
        self.conversation_history = []
        self.model_name = model_name
        self.intent_cache = {}

        # Use class-level singleton for models to save memory and time
        if MasterAgent._shared_model is None:
            try:
                logger.info(f"Loading shared SentenceTransformer model: {model_name}")
                MasterAgent._shared_model = SentenceTransformer(model_name)
                # Compute embeddings once
                self._compute_shared_embeddings()
            except Exception as e:
                logger.error(f"Failed to load shared SentenceTransformer: {e}")
                MasterAgent._shared_model = None

        self.intent_model = MasterAgent._shared_model

    def _initialize_state(self) -> Dict:
        """Create fresh state for new user session"""
        return {
            "stage": ConversationStage.GREETING,
            "workflow_stage": "collecting_details",
            "last_intent": None,
            "entities": {field: None for field in REQUIRED_FIELDS + KYC_FIELDS},
            "risk_score": None,
            "approval_status": None,
            "interest_rate": None,
            "offer_accepted": False,
            "missing_fields": list(REQUIRED_FIELDS),
            "missing_kyc_fields": list(KYC_FIELDS),
            "current_offer": None,
            "conversation_start_time": time.time(),
            "attempts": 0,
            "fraud_check_passed": False,
            "workflow_progress": 0,
            "completed_stages": [],
            "workflow_stage_index": 0,
            "stage_history": [],
            "offer_version": 0,
            "risk_band": None,
            "max_eligible_amount": None,
            "rejection_reasons": [],
            "credit_score": 700,
            "num_active_loans": 0,
            "last_asked_field": None,
            "last_asked_at": None,
        }

    def _compute_shared_embeddings(self):
        """Pre-compute and store shared embeddings for all intent templates."""
        logger.info("Computing shared intent embeddings...")
        intent_list = []
        embeddings_list = []

        for intent, templates in self.INTENT_TEMPLATES.items():
            embeddings = self.intent_model.encode(templates, convert_to_numpy=True)
            mean_embedding = np.mean(embeddings, axis=0)
            norm_embedding = mean_embedding / np.linalg.norm(mean_embedding)
            
            for _ in range(len(templates)): # Optional: or just one per intent
                pass # We only need one per intent for current logic
            
            intent_list.append(intent)
            embeddings_list.append(norm_embedding)

        import torch
        MasterAgent._shared_intent_list = intent_list
        MasterAgent._shared_embeddings = torch.tensor(np.array(embeddings_list))

    # -------------------------------------------------------------------
    # DETERMINISTIC REGEX ENTITY EXTRACTION (supplements LLM extraction)
    # -------------------------------------------------------------------

    def update_entities(self, new_entities: dict):
        """Update state entities dictionary."""
        for k, v in new_entities.items():
            if v is not None:
                self.state['entities'][k] = v

    def calculate_missing_fields(self) -> Tuple[Set[str], Set[str]]:
        """Calculate basic and KYC missing fields based on current state."""
        REQUIRED_BASIC = ['loan_amount', 'tenure', 'age', 'income',
                          'name', 'employment_type', 'purpose']
        REQUIRED_KYC   = ['pan', 'aadhaar', 'address', 'pincode']

        # Ensure purpose is present if loan_type is set
        entities = self.state['entities']
        if entities.get('loan_type') and not entities.get('purpose'):
            entities['purpose'] = entities['loan_type']

        def is_present(field):
            val = self.state['entities'].get(field)
            if val is None: return False
            if isinstance(val, str) and val.strip() == '': return False
            if isinstance(val, (int, float)) and val == 0: return False
            return True

        missing_basic = set(f for f in REQUIRED_BASIC if not is_present(f))
        missing_kyc = set(f for f in REQUIRED_KYC if not is_present(f))

        # Email is optional — remove from missing if skipped
        if self.state['entities'].get('email_skipped'):
            missing_basic.discard('email')

        return missing_basic, missing_kyc

    def recalculate_missing_fields(self):
        """Update state with current missing fields."""
        missing_basic, missing_kyc = self.calculate_missing_fields()
        self.state["missing_fields"] = missing_basic
        self.state["missing_kyc_fields"] = missing_kyc

        # Auto-advance if all required fields now present
        stage = self.state['stage']
        if (stage == ConversationStage.COLLECTING_DETAILS
                and not self.state['missing_fields']):
            self.transition_stage(ConversationStage.KYC_COLLECTION)
        elif (stage == ConversationStage.KYC_COLLECTION
                and not self.state['missing_kyc_fields']):
            self.transition_stage(ConversationStage.FRAUD_CHECK)

    def extract_entities_from_text(self, text: str) -> dict:
        import re
        entities = {}
        text_lower = text.lower()
        
        # Amount
        amt_match = re.search(r'(?:rs\.?|inr|₹)\s*([\d,]+(?:k|lakh|l|cr)?)|([\d,]+)\s*(?:k|lakh|l|cr|rupees)', text_lower)
        if amt_match:
            val_str = amt_match.group(1) or amt_match.group(2)
            val_str = val_str.replace(',', '')
            multiplier = 1
            if 'k' in val_str or 'k' in text_lower: multiplier = 1000
            elif 'lakh' in val_str or 'l' in val_str or 'lakh' in text_lower: multiplier = 100000
            elif 'cr' in val_str or 'cr' in text_lower: multiplier = 10000000
            try:
                val = float(re.sub(r'[^\d.]', '', val_str)) * multiplier
                entities['loan_amount'] = int(val)
            except ValueError: pass

        # Age
        age_match = re.search(r'(\d{2})\s*(?:years? old|years? of age|yrs?|yo|age)', text_lower)
        if age_match:
            val = int(age_match.group(1))
            if 18 <= val <= 80: entities['age'] = val

        # Income
        inc_match = re.search(r'(?:earn|salary|income|make)s?\s*(?:rs\.?|inr|₹)?\s*([\d,]+(?:k|lakh|l|cr)?)|([\d,]+)\s*(?:k|lakh|l|cr|rupees)\s*(?:per month|pm|/month|a month)', text_lower)
        if inc_match:
            val_str = inc_match.group(1) or inc_match.group(2)
            val_str = val_str.replace(',', '')
            multiplier = 1
            if 'k' in val_str or 'k' in text_lower: multiplier = 1000
            elif 'lakh' in val_str or 'l' in val_str or 'lakh' in text_lower: multiplier = 100000
            try:
                val = float(re.sub(r'[^\d.]', '', val_str)) * multiplier
                entities['income'] = int(val)
            except ValueError: pass

        # Employment
        if 'salary' in text_lower or 'salaried' in text_lower or 'job' in text_lower:
            entities['employment_type'] = 'salaried'
        elif 'business' in text_lower or 'self employed' in text_lower:
            entities['employment_type'] = 'self-employed'

        # Tenure
        ten_match = re.search(r'(\d+)\s*(months?|years?|yrs?|mo)', text_lower)
        if ten_match:
            val = int(ten_match.group(1))
            is_year = 'year' in ten_match.group(2) or 'yr' in ten_match.group(2)
            entities['tenure'] = val * 12 if is_year else val

        # KYC Fields
        pan_match = re.search(r'([a-zA-Z]{5}\d{4}[a-zA-Z]{1})', text)
        if pan_match: entities['pan'] = pan_match.group(1).upper()
        aadhaar_match = re.search(r'\b(\d{4}\s?\d{4}\s?\d{4})\b', text)
        if aadhaar_match: entities['aadhaar'] = aadhaar_match.group(1).replace(' ', '')
        pin_match = re.search(r'\b(\d{6})\b', text)
        if pin_match: entities['pincode'] = pin_match.group(1)

        # Name
        name_pats = [r'(?:my name is|i am|i\'m|call me|naam hai|mera naam)\s+([A-Za-z]+(?:\s+[A-Za-z]+)+)']
        for pat in name_pats:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                words = candidate.split()
                if len(words) >= 2 and all(w.isalpha() for w in words):
                    entities['name'] = candidate.title()
                    break

        # Phone & Email
        phone_pat = r'\b([6-9]\d{9})\b'
        m = re.search(phone_pat, text)
        if m: entities['phone'] = m.group(1)

        email_pat = r'\b([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\b'
        m = re.search(email_pat, text)
        if m: entities['email'] = m.group(1).lower()

        # Purpose
        purpose_kw = {
            'home': ['home loan', 'house', 'ghar', 'property', 'flat'],
            'vehicle': ['car', 'vehicle', 'bike', 'gaadi'],
            'education': ['education', 'study'],
            'business': ['business', 'startup'],
            'personal': ['personal loan'],
        }
        for purp, kws in purpose_kw.items():
            if any(kw in text_lower for kw in kws):
                entities['purpose'] = purp
                break

        return entities

    # -------------------------------------------------------------------
    # PATTERN-BASED INTENT DETECTION (checked before LLM)
    # -------------------------------------------------------------------

    def _pattern_based_intent(self, text: str) -> Optional[Tuple[IntentType, float]]:
        """Check CONVERSATION_PATTERNS before calling the LLM for intent."""
        text_lower = text.lower().strip()
        for intent, patterns in CONVERSATION_PATTERNS.items():
            for p in patterns:
                if p in text_lower:
                    return intent, 0.85
        return None

    # -------------------------------------------------------------------
    # MISSING FIELDS
    # -------------------------------------------------------------------


    FIELD_QUESTIONS = {
        'loan_amount': (
            "How much loan are you looking for? "
            "(e.g., 5 lakhs, 10 lakh, 500000)",
            'loan_amount'
        ),
        'purpose': (
            "What do you need the loan for? "
            "(home, car, education, business, personal, medical, wedding…)",
            'purpose'
        ),
        'name': (
            "What is your full name?",
            'name'
        ),
        'age': (
            "How old are you?",
            'age'
        ),
        'employment_type': (
            "Are you salaried, self-employed, or a business owner?",
            'employment_type'
        ),
        'income': (
            "What is your monthly income? (e.g., 50000, 1.5 lakh)",
            'income'
        ),
        'phone': (
            "What is your 10-digit mobile number?",
            'phone'
        ),
        'email': (
            "What is your email address? (optional — type 'skip' to skip)",
            'email'
        ),
        'tenure': (
            "For how many months or years do you need the loan?",
            'tenure'
        ),
        # KYC fields
        'pan': (
            "Please share your PAN number. (format: ABCDE1234F)",
            'pan'
        ),
        'aadhaar': (
            "Please share your 12-digit Aadhaar number.",
            'aadhaar'
        ),
        'address': (
            "What is your current residential address?",
            'address'
        ),
        'pincode': (
            "What is your 6-digit PIN code?",
            'pincode'
        ),
    }

    def get_next_question(self) -> tuple:
        """
        Returns (question_text, field_name) for the next missing field.
        Also sets state['last_asked_field'] so the next reply is
        automatically mapped to the right field.
        """
        BASIC_ORDER = ['loan_amount', 'purpose', 'name', 'age',
                       'employment_type', 'income', 'tenure', 'phone', 'email']
        KYC_ORDER   = ['pan', 'aadhaar', 'address', 'pincode']

        stage = self.state['stage']
        entities = self.state['entities']

        if stage == ConversationStage.COLLECTING_DETAILS:
            field_order = BASIC_ORDER
        elif stage == ConversationStage.KYC_COLLECTION:
            field_order = KYC_ORDER
        else:
            return (None, None)

        for field in field_order:
            if field == 'email' and entities.get('email_skipped'):
                continue
            if not entities.get(field):
                question, asked_field = self.FIELD_QUESTIONS.get(field, (None, None))
                self.state['last_asked_field'] = asked_field
                self.state['last_asked_at'] = time.time()
                return (question, asked_field)

        self.state['last_asked_field'] = None
        return (None, None)

    # -------------------------------------------------------------------
    # STAGE TRANSITIONS
    # -------------------------------------------------------------------

    def transition_stage(self, new_stage: ConversationStage):
        """Explicit stage transition with history tracking."""
        old_stage = self.state['stage']
        if old_stage == new_stage:
            return

        self.state['stage'] = new_stage
        self.state['stage_history'].append({
            'from': old_stage.value if hasattr(old_stage, 'value') else str(old_stage),
            'to': new_stage.value,
            'at': datetime.now().isoformat(),
            'entities_at_transition': {k: v for k, v in self.state['entities'].items() if v is not None},
        })

        progress_map = {
            ConversationStage.GREETING: 0,
            ConversationStage.COLLECTING_DETAILS: 15,
            ConversationStage.KYC_COLLECTION: 35,
            ConversationStage.FRAUD_CHECK: 55,
            ConversationStage.UNDERWRITING: 70,
            ConversationStage.OFFER_PRESENTATION: 85,
            ConversationStage.REJECTION_COUNSELING: 80,
            ConversationStage.DOCUMENTATION: 95,
            ConversationStage.CLOSED: 100,
        }
        self.state['workflow_progress'] = progress_map.get(new_stage, 0)

        if old_stage.value not in self.state['completed_stages']:
            self.state['completed_stages'].append(old_stage.value)

        logger.info(f"Stage transition: {old_stage.value} → {new_stage.value}")

    # -------------------------------------------------------------------
    # INTENT DETECTION
    # -------------------------------------------------------------------

    def detect_intent(self, text: str) -> Tuple[IntentType, float]:
        """AI-powered intent detection with pattern fallback and context awareness."""
        cache_key = hash(text.lower().strip())
        if cache_key in self.intent_cache:
            return self.intent_cache[cache_key]

        if not text:
            return IntentType.UNCLEAR, 0.0

        # Check for exact pattern matches first (high priority)
        keyword_intent = self._rule_based_intent_detection(text)
        if keyword_intent != IntentType.UNCLEAR:
            self.intent_cache[cache_key] = (keyword_intent, 0.95)
            return keyword_intent, 0.95

        # Semantic similarity using shared model
        if not self.intent_model or MasterAgent._shared_embeddings is None:
            # Fallback to rule-based logic if model isn't available
            return self._rule_based_intent_detection(text), 0.5

        try:
            query_embedding = self.intent_model.encode(text, convert_to_tensor=True)
            cos_scores = util.cos_sim(query_embedding, MasterAgent._shared_embeddings)[0]
            
            top_idx = int(torch.argmax(cos_scores))
            confidence = float(cos_scores[top_idx])
            intent = MasterAgent._shared_intent_list[top_idx]
            
            result = (intent, confidence)
            self.intent_cache[cache_key] = result
            return result
        except Exception as e:
            logger.error(f"Intent detection error: {e}")
            return IntentType.UNCLEAR, 0.0

    def _apply_context_boosting(self, similarities: Dict[IntentType, float]) -> Dict[IntentType, float]:
        """Apply context-aware boosting to intent similarities."""
        stage = self.state["stage"]
        boosted = similarities.copy()

        boost_rules = {
            ConversationStage.OFFER_PRESENTATION: {
                IntentType.ACCEPT_OFFER: 1.4,
                IntentType.REJECT_OFFER: 1.4,
                IntentType.NEGOTIATE_TERMS: 1.3
            },
            ConversationStage.REJECTION_COUNSELING: {
                IntentType.LOAN_APPLICATION: 1.3,
                IntentType.NEGOTIATE_TERMS: 1.2
            },
            ConversationStage.KYC_COLLECTION: {
                IntentType.PROVIDE_INFO: 1.3
            },
            ConversationStage.COLLECTING_DETAILS: {
                IntentType.PROVIDE_INFO: 1.4
            }
        }

        for intent, factor in boost_rules.get(stage, {}).items():
            if intent in boosted:
                boosted[intent] *= factor

        if self.state["last_intent"] == IntentType.LOAN_APPLICATION:
            if IntentType.PROVIDE_INFO in boosted:
                boosted[IntentType.PROVIDE_INFO] *= 1.2

        return boosted

    def _validate_intent_with_rules(self, text: str, ai_intent: IntentType,
                                   confidence: float) -> Tuple[IntentType, float]:
        """Validate AI intent with rule-based checks."""
        info_keywords = ["my", "is", "I am", "I have", "I work", "income", "age", "name"]
        if any(keyword in text.lower() for keyword in info_keywords):
            entities = self.extract_entities(text)
            if any(entities.values()):
                return IntentType.PROVIDE_INFO, max(confidence, 0.7)

        if confidence < 0.4:
            entities = self.extract_entities(text)
            if any(entities.values()):
                return IntentType.PROVIDE_INFO, 0.7

        exit_phrases = ["goodbye", "bye", "exit", "stop", "end", "close", "quit"]
        if any(phrase in text.lower() for phrase in exit_phrases):
            return IntentType.EXIT, 0.9

        question_patterns = ["what", "how", "when", "where", "why", "can you", "could you"]
        if any(pattern in text.lower() for pattern in question_patterns):
            if "rate" in text.lower() or "interest" in text.lower():
                return IntentType.RATE_INQUIRY, max(confidence, 0.8)
            return IntentType.HELP_GENERAL, max(confidence, 0.7)

        return ai_intent, confidence

    def _rule_based_intent_detection(self, text: str) -> IntentType:
        """Fallback rule-based intent detection when AI is unavailable."""
        text_lower = text.lower()

        if any(greet in text_lower for greet in ["hello", "hi", "hey", "greetings", "namaste"]):
            return IntentType.GREETING

        if any(loan_word in text_lower for loan_word in ["loan", "borrow", "apply", "need money"]):
            return IntentType.LOAN_APPLICATION

        if any(rate_word in text_lower for rate_word in ["rate", "interest", "percent"]):
            return IntentType.RATE_INQUIRY

        if any(nego_word in text_lower for nego_word in ["negotiate", "lower", "reduce", "better"]):
            return IntentType.NEGOTIATE_TERMS

        if any(accept_word in text_lower for accept_word in ["accept", "yes", "agree", "proceed"]):
            return IntentType.ACCEPT_OFFER

        if any(reject_word in text_lower for reject_word in ["reject", "no", "decline", "not interested"]):
            return IntentType.REJECT_OFFER

        if any(help_word in text_lower for help_word in ["help", "how", "explain", "what"]):
            return IntentType.HELP_GENERAL

        if any(exit_word in text_lower for exit_word in ["exit", "bye", "goodbye", "stop"]):
            return IntentType.EXIT

        entities = self.extract_entities(text)
        if any(entities.values()):
            return IntentType.PROVIDE_INFO

        return IntentType.UNCLEAR

    # -------------------------------------------------------------------
    # ENTITY EXTRACTION (existing logic, kept intact)
    # -------------------------------------------------------------------

    def extract_entities(self, text: str) -> Dict[str, Optional[str]]:
        """Advanced entity extraction with validation and context awareness."""
        entities = {}

        extraction_functions = [
            (extract_amount, "loan_amount", validate_amount),
            (extract_tenure, "tenure", validate_tenure),
            (extract_age, "age", validate_age),
            (extract_income, "income", None),
            (extract_name, "name", None),
            (extract_employment_type, "employment_type", None),
            (extract_purpose, "purpose", None),
            (extract_pan, "pan", None),
            (extract_aadhaar, "aadhaar", None),
            (extract_pincode, "pincode", None)
        ]

        for extract_func, field, validate_func in extraction_functions:
            try:
                value = extract_func(text)
                if value:
                    if validate_func:
                        if validate_func(value):
                            entities[field] = value
                    else:
                        entities[field] = value
            except Exception as e:
                logger.warning(f"Error extracting {field}: {e}")

        # Address extraction — match with common prefixes
        address_prefixes = [
            r'(?:my address is|address is|address:|i live at|living at|reside at|'
            r'residing at|house is at|flat is|)\s*'
        ]
        address_pattern = (
            r'(?:my address is|address is|i live at|residing at|house at|flat at|'
            r'plot at|'
            r')\s*'
            r'([A-Za-z0-9\s,./\-#]+(?:delhi|mumbai|bangalore|bengaluru|chennai|'
            r'hyderabad|pune|kolkata|nagar|road|street|colony|sector|phase|'
            r'block|floor|flat|house|plot|wz|dda|'
            r'\d{6})[A-Za-z0-9\s,./\-#]*)'
        )
        addr_match = re.search(address_pattern, text, re.IGNORECASE)
        if addr_match:
            entities['address'] = addr_match.group(1).strip()

        # Also extract pincode from address string
        pincode_in_addr = re.search(r'\b(\d{6})\b', text)
        if pincode_in_addr:
            entities['pincode'] = pincode_in_addr.group(1)

        # Fallback: if message contains address keywords, treat whole message as address
        address_keywords = ['flat', 'house', 'plot', 'wz', 'sector', 'nagar',
                            'road', 'street', 'colony', 'apartment', 'building',
                            'floor', '#', 'st no', 'st.no', 'phase', 'block',
                            'sahib', 'pura', 'vihar']
        lower_text = text.lower()
        if any(kw in lower_text for kw in address_keywords):
            # Clean up the prefix if present
            clean = re.sub(r'^(?:my address is|address is|i live at)\s*',
                           '', text, flags=re.IGNORECASE).strip()
            entities['address'] = clean
            # Extract pincode from it
            pin = re.search(r'\b(\d{6})\b', clean)
            if pin:
                entities['pincode'] = pin.group(1)

        return entities

    # -------------------------------------------------------------------
    # STATE UPDATE
    # -------------------------------------------------------------------

    def update_state(self, entities: Dict, intent: IntentType):
        """Advanced state management with validation and logging."""
        for key, value in entities.items():
            if value is not None:
                old_value = self.state["entities"].get(key)
                self.state["entities"][key] = value

                if old_value != value:
                    logger.info(f"Updated {key}: {old_value} -> {value}")

        # Recalculate missing fields
        missing_basic, missing_kyc = self.calculate_missing_fields()
        self.state["missing_fields"] = missing_basic
        self.state["missing_kyc_fields"] = missing_kyc

        self.state["last_intent"] = intent
        self.state["attempts"] += 1

        # Check workflow progression
        self._check_workflow_progression()

        logger.info(f"State updated: {self.state['stage'].value}, intent: {intent.value}")

    def _check_workflow_progression(self):
        """Check and update workflow stage based on collected data."""
        current_stage = self.state["stage"]

        if current_stage == ConversationStage.GREETING:
            self.transition_stage(ConversationStage.COLLECTING_DETAILS)

        elif current_stage == ConversationStage.COLLECTING_DETAILS:
            missing_basic, _ = self.calculate_missing_fields()
            if not missing_basic:
                self.transition_stage(ConversationStage.KYC_COLLECTION)

        elif current_stage == ConversationStage.KYC_COLLECTION:
            _, missing_kyc = self.calculate_missing_fields()
            if not missing_kyc:
                self.transition_stage(ConversationStage.FRAUD_CHECK)

    def route_to_worker(self, intent: IntentType) -> str:
        """Intelligent routing to specialized worker agents."""
        stage = self.state["stage"]

        routing_map = {
            ConversationStage.FRAUD_CHECK: "fraud",
            ConversationStage.UNDERWRITING: "underwriting",
            ConversationStage.REJECTION_COUNSELING: "sales",
            ConversationStage.OFFER_PRESENTATION: {
                IntentType.RATE_INQUIRY: "sales",
                IntentType.NEGOTIATE_TERMS: "sales",
                IntentType.ACCEPT_OFFER: "documentation",
                "default": "sales"
            },
            ConversationStage.DOCUMENTATION: "documentation",
        }

        stage_routing = routing_map.get(stage, "none")

        if isinstance(stage_routing, dict):
            return stage_routing.get(intent, stage_routing.get("default", "none"))

        return stage_routing

    def generate_response(self, intent: IntentType, confidence: float) -> Dict:
        """Generate context-aware, natural responses."""
        stage = self.state["stage"]

        if stage == ConversationStage.CLOSED:
            return {
                "message": "Thank you for considering CredGen. Feel free to reach out if you need assistance in the future. Have a great day!",
                "terminate": True
            }

        if stage == ConversationStage.DOCUMENTATION:
            return {
                "message": "All checks complete! Please proceed with the final documentation step to generate your Sanction Letter.",
                "terminate": False,
                "next_action": "documentation"
            }

        if stage in (ConversationStage.OFFER_PRESENTATION, ConversationStage.REJECTION_COUNSELING):
            if self.state["current_offer"]:
                return self.state["current_offer"]

        response_templates = {
            ConversationStage.GREETING: {
                "message": self._get_random_response(ConversationStage.GREETING),
                "terminate": False
            },
            ConversationStage.COLLECTING_DETAILS: self._generate_collecting_response(),
            ConversationStage.KYC_COLLECTION: self._generate_kyc_response(),
            ConversationStage.FRAUD_CHECK: {
                "message": "Running security verification...",
                "terminate": False,
                "processing": True
            },
            ConversationStage.UNDERWRITING: {
                "message": "Processing your application... This will take just a moment.",
                "terminate": False,
                "processing": True
            }
        }

        response = response_templates.get(stage, {})
        if response:
            return response

        intent_responses = {
            IntentType.HELP_GENERAL: {
                "message": "I can help you with:\n- Loan applications\n- Interest rate inquiries\n- Document collection\n- Application status\nWhat would you like to know?"
            },
            IntentType.RATE_INQUIRY: {
                "message": "Our interest rates range from 9.5% to 24% based on your credit profile. Would you like to check what rate you qualify for?"
            },
            IntentType.UNCLEAR: {
                "message": "I didn't quite understand. Could you please rephrase or tell me if you'd like to:\n1. Apply for a loan\n2. Check interest rates\n3. Get help with an existing application"
            }
        }

        return intent_responses.get(intent, {
            "message": f"How can I assist you further with your loan application?",
            "terminate": False
        })

    def _generate_collecting_response(self) -> Dict:
        """Generate response for information collection stage."""
        missing_basic, _ = self.calculate_missing_fields()

        if not missing_basic:
            return {
                "message": "Great! I have all the basic details. Now I need your KYC information for verification.",
                "terminate": False,
                "next_action": "collect_kyc"
            }

        nq = self.get_next_question()
        if nq and nq[0]:
            return {
                "message": f"To proceed, {nq[0]}",
                "terminate": False,
                "missing_field": nq[1]
            }

        return {
            "message": "Please provide the remaining details.",
            "terminate": False
        }

    def _generate_kyc_response(self) -> Dict:
        """Generate response for KYC collection stage."""
        _, missing_kyc = self.calculate_missing_fields()

        if not missing_kyc:
            return {
                "message": "All KYC details collected. Running security verification...",
                "terminate": False,
                "processing": True
            }

        kyc_prompts = {
            "pan": "Please provide your PAN card number (format: ABCDE1234F)",
            "aadhaar": "Please provide your Aadhaar number (12 digits)",
            "address": "Please provide your complete residential address",
            "pincode": "What is your 6-digit pincode?",
        }

        # Priority order
        for field in self.KYC_PRIORITY:
            if field in missing_kyc:
                return {
                    "message": f"For KYC verification: {kyc_prompts.get(field, f'Please provide your {field}')}",
                    "terminate": False,
                    "missing_field": field
                }

        next_kyc = missing_kyc[0]
        return {
            "message": f"For KYC verification: {kyc_prompts.get(next_kyc, f'Please provide your {next_kyc}')}",
            "terminate": False,
            "missing_field": next_kyc
        }

    def _get_random_response(self, stage: ConversationStage) -> str:
        """Get a random response from stage templates."""
        import random
        responses = self.STAGE_RESPONSES.get(stage, ["How can I help you?"])
        return random.choice(responses)

    # --- Integration Methods for Worker Agents ---

    def set_underwriting_result(self, risk_score: float, approval_status: bool,
                               interest_rate: float = None, offer_details: Dict = None,
                               risk_band: str = None, max_eligible_amount: float = None,
                               rejection_reasons: list = None):
        """Called by Underwriting Agent with results."""
        self.state["risk_score"] = risk_score
        self.state["approval_status"] = approval_status
        self.state["interest_rate"] = interest_rate
        self.state["risk_band"] = risk_band
        self.state["max_eligible_amount"] = max_eligible_amount
        self.state["rejection_reasons"] = rejection_reasons or []

        if approval_status:
            self.transition_stage(ConversationStage.OFFER_PRESENTATION)
            if offer_details:
                self.state["current_offer"] = offer_details
        else:
            self.transition_stage(ConversationStage.REJECTION_COUNSELING)

        logger.info(f"Underwriting result: approval={approval_status}, risk={risk_score}")

    def set_fraud_check_result(self, passed: bool, details: Dict = None):
        """Called by Fraud Check Agent."""
        self.state["fraud_check_passed"] = passed
        if passed:
            self.transition_stage(ConversationStage.UNDERWRITING)
        else:
            self.state["current_offer"] = {
                "message": "We couldn't proceed with your application due to verification issues. Please contact support for more details.",
                "terminate": True
            }
            self.transition_stage(ConversationStage.CLOSED)

        logger.info(f"Fraud check result: passed={passed}")

    def set_fraud_result(self, fraud_score: float = None, fraud_flag: str = None):
        """Compatibility alias used by app.py; routes to set_fraud_check_result."""
        passed = (fraud_flag or 'Low') != 'High'
        details = {"fraud_score": fraud_score, "fraud_flag": fraud_flag}
        self.set_fraud_check_result(passed=passed, details=details)

    def set_offer(self, offer_details: Dict):
        """Compatibility method used by app.py and SalesAgent to set current offer."""
        self.state["current_offer"] = offer_details
        ir = offer_details.get("interest_rate") if isinstance(offer_details, dict) else None
        if ir is not None:
            self.state["interest_rate"] = ir
        ov = offer_details.get("offer_version") if isinstance(offer_details, dict) else None
        if ov is not None:
            self.state["offer_version"] = ov
        self.state["stage"] = ConversationStage.OFFER_PRESENTATION

    def set_offer_accepted(self, accepted: bool = True):
        """Mark offer as accepted and move to documentation."""
        self.state["offer_accepted"] = accepted
        if accepted:
            self.transition_stage(ConversationStage.DOCUMENTATION)

    def reset_conversation(self):
        """Reset the conversation for a new user."""
        self.state = self._initialize_state()
        self.conversation_history = []
        self.intent_cache.clear()
        logger.info("Conversation reset")

    def _build_response(self, message: str, worker: str = 'none', action: str = 'none', suggestions: list = None) -> dict:
        result = {
            "message": message,
            "worker": worker,
            "action": action,
            "intent": "provide_info",
            "stage": self.state["stage"].value if hasattr(self.state["stage"], "value") else str(self.state["stage"]),
            "confidence": 1.0,
            "entities_collected": {k: v for k, v in self.state["entities"].items() if v},
            "missing_fields": list(self.state.get("missing_fields", [])),
            "missing_kyc_fields": list(self.state.get("missing_kyc_fields", [])),
            "workflow_progress": self.state.get("workflow_progress", 0),
            "terminate": False
        }
        if suggestions is not None:
            result['suggestions'] = suggestions
        return result

    def _build_acknowledgement(self, just_extracted: dict) -> str:
        """
        Returns a short acknowledgement of what was just collected.
        e.g. "Got it! " or "Thanks, Ashmeet. " or "₹7,00,000 — noted. "
        """
    def _get_acknowledgment(self, just_extracted: Dict) -> str:
        """Helper to create a response prefix based on extracted entities."""
        if not just_extracted:
            return ''

        acks = {
            'name':            lambda v: f"Nice to meet you, {v.split()[0]}! ",
            'age':             lambda v: f"Got it. ",
            'loan_amount':     lambda v: f"₹{self._fmt(v)} — noted. ",
            'income':          lambda v: f"Monthly income ₹{self._fmt(v)} — got it. ",
            'employment_type': lambda v: f"Understood. ",
            'purpose':         lambda v: f"Got it. ",
            'phone':           lambda v: f"Phone number saved. ",
            'email':           lambda v: f"Email noted. ",
            'pan':             lambda v: f"PAN verified ✓. ",
            'aadhaar':         lambda v: f"Aadhaar noted ✓. ",
            'address':         lambda v: f"Address saved. ",
            'pincode':         lambda v: f"PIN code noted. ",
            'tenure':          lambda v: f"{v} months — got it. ",
        }
        parts = []
        for field, value in just_extracted.items():
            if field in acks and value:
                parts.append(acks[field](value))
        return ''.join(parts[:1])  # Only acknowledge the primary field

    def _fmt(self, n) -> str:
        """Format number in Indian style."""
        try:
            n = int(n)
            s = str(n)
            if len(s) <= 3: return s
            last3 = s[-3:]
            rest = s[:-3]
            import re
            rest = re.sub(r'\B(?=(\d{2})+(?!\d))', ',', rest)
            return rest + ',' + last3
        except:
            return str(n)
            
    def _parse_amount(self, text: str) -> dict:
        """Parse any monetary amount from free text → returns {'loan_amount': int}"""
        t = text.lower().strip()
        # Remove currency symbols
        t = re.sub(r'[₹rs.]', '', t).strip()

        crore = re.search(r'(\d+(?:\.\d+)?)\s*cr(?:ore)?', t)
        lakh  = re.search(r'(\d+(?:\.\d+)?)\s*(?:l(?:akh)?|lac)', t)
        k     = re.search(r'(\d+(?:\.\d+)?)\s*k\b', t)
        plain = re.search(r'(\d[\d,]*)', t)

        if crore:
            return {'loan_amount': int(float(crore.group(1)) * 10_000_000)}
        elif lakh:
            return {'loan_amount': int(float(lakh.group(1)) * 100_000)}
        elif k:
            return {'loan_amount': int(float(k.group(1)) * 1_000)}
        elif plain:
            val = int(plain.group(1).replace(',', ''))
            if val < 1000:
                val = val * 100_000
            return {'loan_amount': val}
        return {}

    def _get_field_suggestions(self, field: str) -> list:
        suggestions_map = {
            'loan_amount':     ['₹1 lakh', '₹3 lakh', '₹5 lakh',
                                '₹10 lakh'],
            'purpose':         ['Personal use', 'Home purchase',
                                'Vehicle', 'Education', 'Business'],
            'employment_type': ['Salaried', 'Self-employed',
                                'Business owner', 'Retired'],
            'income':          ['₹25,000/month', '₹50,000/month',
                                '₹1 lakh/month'],
            'tenure':          ['1 year', '2 years', '3 years', '5 years'],
            'age':             [],      # no chips for age
            'name':            [],      # no chips for name
            'phone':           [],      # no chips for phone
            'email':           ['Skip email'],
            'pan':             [],      # sensitive — no chips
            'aadhaar':         [],      # sensitive — no chips
            'address':         [],      # free text
            'pincode':         [],      # free text
        }
        return suggestions_map.get(field, [])

    def extract_from_context(self, user_input: str) -> dict:
        """
        If the bot just asked for a specific field, treat the user's
        entire reply as the answer to that field.
        This runs BEFORE regex extraction and takes highest priority.
        """
        last_field = self.state.get('last_asked_field')
        if not last_field:
            return {}

        text = user_input.strip()
        if not text:
            return {}

        extracted = {}

        if last_field == 'name':
            clean = re.sub(r'[^A-Za-z\s\.]', '', text).strip()
            words = [w for w in clean.split() if len(w) >= 2]
            if len(words) >= 1:
                extracted['name'] = ' '.join(words).title()

        elif last_field == 'age':
            nums = re.findall(r'\b(\d{1,3})\b', text)
            for n in nums:
                val = int(n)
                if 18 <= val <= 75:
                    extracted['age'] = val
                    break

        elif last_field == 'loan_amount':
            extracted.update(self._parse_amount(text))

        elif last_field == 'income':
            result = self._parse_amount(text)
            if 'loan_amount' in result:
                extracted['income'] = result['loan_amount']

        elif last_field == 'tenure':
            yr = re.search(r'(\d+)\s*(?:year|yr|y\b|साल)', text, re.I)
            mo = re.search(r'(\d+)\s*(?:month|mo\b|emi|महीने)', text, re.I)
            plain = re.search(r'^\s*(\d+)\s*$', text)
            if yr:
                extracted['tenure'] = int(yr.group(1)) * 12
            elif mo:
                extracted['tenure'] = int(mo.group(1))
            elif plain:
                val = int(plain.group(1))
                extracted['tenure'] = val * 12 if val <= 30 else val

        elif last_field == 'employment_type':
            t = text.lower()
            if any(w in t for w in ['salar', 'job', 'employee', 'employed',
                                     'service', 'govt', 'government',
                                     'private', 'mnc']):
                extracted['employment_type'] = 'salaried'
            elif any(w in t for w in ['self', 'freelance', 'consultant',
                                       'independent', 'contractor']):
                extracted['employment_type'] = 'self_employed'
            elif any(w in t for w in ['business', 'owner', 'entrepreneur',
                                       'shop', 'firm', 'company']):
                extracted['employment_type'] = 'business_owner'
            elif any(w in t for w in ['retire', 'pension']):
                extracted['employment_type'] = 'retired'
            elif any(w in t for w in ['student', 'study', 'college',
                                       'university']):
                extracted['employment_type'] = 'student'
            else:
                extracted['employment_type'] = text.strip().lower()

        elif last_field == 'purpose':
            t = text.lower()
            type_map = {
                'home': ['home', 'house', 'property', 'flat', 'plot',
                         'apartment', 'ghar'],
                'vehicle': ['car', 'vehicle', 'bike', 'scooter', 'gaadi'],
                'education': ['education', 'study', 'college', 'course',
                              'fees', 'school'],
                'business': ['business', 'shop', 'startup', 'office',
                             'expansion', 'capital'],
                'personal': ['personal', 'medical', 'wedding', 'travel',
                             'emergency', 'repair', 'renovation'],
            }
            found_type = 'personal'
            for ltype, keywords in type_map.items():
                if any(kw in t for kw in keywords):
                    found_type = ltype
                    break
            extracted['purpose'] = text.strip()
            extracted['loan_type'] = found_type

        elif last_field == 'phone':
            digits = re.sub(r'[^\d]', '', text)
            if digits.startswith('91') and len(digits) == 12:
                digits = digits[2:]
            if len(digits) == 10 and digits[0] in '6789':
                extracted['phone'] = digits

        elif last_field == 'email':
            email = re.search(
                r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
                text)
            if email:
                extracted['email'] = email.group(0).lower()

        elif last_field == 'pan':
            clean = text.upper().replace(' ', '')
            pan = re.search(r'[A-Z]{5}[0-9]{4}[A-Z]', clean)
            if pan:
                extracted['pan'] = pan.group(0)

        elif last_field == 'aadhaar':
            digits = re.sub(r'[\s\-]', '', text)
            aadhaar = re.search(r'\d{12}', digits)
            if aadhaar:
                extracted['aadhaar'] = aadhaar.group(0)

        elif last_field == 'address':
            clean = text.strip()
            if len(clean) >= 10:
                extracted['address'] = clean
                pin = re.search(r'\b(\d{6})\b', clean)
                if pin:
                    extracted['pincode'] = pin.group(1)

        elif last_field == 'pincode':
            pin = re.search(r'\b(\d{6})\b', text)
            if pin:
                extracted['pincode'] = pin.group(1)

        elif last_field == 'credit_score':
            nums = re.findall(r'\b(\d{3})\b', text)
            for n in nums:
                val = int(n)
                if 300 <= val <= 900:
                    extracted['credit_score'] = val
                    break

        elif last_field in ('num_active_loans', 'num_closed_loans'):
            plain = re.search(r'\b(\d{1,2})\b', text)
            none_words = ['no', 'none', 'zero', '0', 'nil', 'nahi', 'nahin']
            if any(w in text.lower() for w in none_words):
                extracted[last_field] = 0
            elif plain:
                extracted[last_field] = int(plain.group(1))

        else:
            if len(text) >= 2:
                extracted[last_field] = text.strip()

        return extracted

    def handle(self, user_input: str) -> dict:
        text = user_input.strip()
        lower = text.lower()
        if not text:
            return self._build_response("Please type your response.")

        self.conversation_history.append({"user": user_input, "timestamp": time.time()})

        # 1. Intent Detection
        intent, conf = self.detect_intent(text)

        # 2. Extract Entities Immediately (Catch details even in the first message)
        # Context-first extraction (if we just asked a question)
        context_entities = self.extract_from_context(text)
        if context_entities:
            self.update_entities(context_entities)

        # Regex/NLP extraction
        extracted_entities = self.extract_entities_from_text(text)
        for k, v in extracted_entities.items():
            # Apply if not already found by context or if context didn't find anything
            if v and (k not in context_entities or not context_entities[k]):
                self.update_entities({k: v})

        # Special handling for loan type in free text (for greeting bypass)
        type_map = {
            'personal': ['personal', 'cash', 'emergency', 'medical', 'wedding', 'travel'],
            'home':     ['home', 'house', 'property', 'flat', 'plot', 'ghar', 'makaan'],
            'vehicle':  ['car', 'vehicle', 'bike', 'scooter', 'gaadi'],
            'education':['education', 'study', 'college', 'fees', 'course', 'school'],
            'business': ['business', 'shop', 'startup', 'capital', 'expand'],
        }
        detected_type = None
        for ltype, keywords in type_map.items():
            if any(kw in lower for kw in keywords):
                detected_type = ltype
                break
        
        if detected_type and not self.state['entities'].get('purpose'):
            self.state['entities']['purpose'] = detected_type

        # 3. Recalculate State
        self.recalculate_missing_fields()
        current_stage = self.state['stage']
        entities = self.state['entities']
        has_essential_entities = any(v for k, v in entities.items() if v and k in REQUIRED_FIELDS)

        # ── INITIAL GREETING BYPASS ──────────────────────────────────────
        # If we are in GREETING but the user provides info, move to COLLECTING_DETAILS
        if current_stage == ConversationStage.GREETING:
            if has_essential_entities or detected_type:
                self.transition_stage(ConversationStage.COLLECTING_DETAILS)
                current_stage = ConversationStage.COLLECTING_DETAILS
            elif (intent == IntentType.GREETING and conf > 0.6) or not entities.get('purpose'):
                # Regular greeting flow
                self.state['last_asked_field'] = 'purpose'
                self.transition_stage(ConversationStage.COLLECTING_DETAILS)
                return self._build_response(
                    "Hi there! 👋 I'm CredGen AI, your loan assistant.\n\n"
                    "I can help you get a loan tailored to your needs — quickly and digitally.\n\n"
                    "What kind of loan are you looking for today?",
                    suggestions=['Personal loan', 'Home loan', 'Business loan', 'Vehicle loan']
                )

        # 4. Handle Specialized Intents (Help, Rates, etc.)
        intent_prefix = ""
        if intent in (IntentType.HELP_GENERAL, IntentType.RATE_INQUIRY) and conf > 0.6:
            resp = self.generate_response(intent, conf)
            intent_prefix = resp['message'] + "\n\n"
        elif intent == IntentType.EXIT and conf > 0.7:
            return self._build_response("Goodbye! Feel free to return when you're ready.")

        # 5. Handle Stage Workflow
        if current_stage == ConversationStage.COLLECTING_DETAILS:
            if not self.state.get('missing_fields'):
                self.transition_stage(ConversationStage.KYC_COLLECTION)
                question, _ = self.get_next_question()
                return self._build_response(
                    f"{intent_prefix}Great! I have all your basic details. "
                    "Next, I need to collect some KYC documents for verification.\n\n"
                    f"{question}",
                    suggestions=self._get_field_suggestions(self.state.get('last_asked_field'))
                )
            else:
                question, field = self.get_next_question()
                ack = self._get_acknowledgment(extracted_entities or context_entities)
                return self._build_response(
                    f"{intent_prefix}{ack}{question}",
                    suggestions=self._get_field_suggestions(field)
                )

        elif current_stage == ConversationStage.KYC_COLLECTION:
            if not self.state.get('missing_kyc_fields'):
                self.transition_stage(ConversationStage.FRAUD_CHECK)
                return self._build_response(
                    "Perfect! I have all your KYC details. "
                    "Running security verification now...",
                    worker='fraud',
                    action='call_fraud_api',
                    suggestions=[]
                )
            else:
                question, field = self.get_next_question()
                if question:
                    ack = self._get_acknowledgment(context_entities)
                    return self._build_response(
                        f"{ack}{question}",
                        suggestions=self._get_field_suggestions(field)
                    )

        elif current_stage == ConversationStage.FRAUD_CHECK:
            return self._build_response(
                "Security verification is in progress...",
                worker='fraud',
                action='call_fraud_api'
            )

        elif current_stage == ConversationStage.UNDERWRITING:
            return self._build_response(
                "Assessing your application...",
                worker='underwriting',
                action='call_underwriting_api'
            )

        elif current_stage == ConversationStage.OFFER_PRESENTATION:
            accept_words = ['yes', 'accept', 'ok', 'okay', 'agree',
                            'proceed', 'confirm', 'haan', 'theek']
            negotiate_words = ['negotiate', 'lower', 'reduce', 'better',
                               'less', 'discount', 'kam']
            if any(w in lower for w in accept_words):
                self.set_offer_accepted(True)
                self.transition_stage(ConversationStage.DOCUMENTATION)
                return self._build_response(
                    "Excellent! Generating your sanction letter...",
                    worker='documentation',
                    action='call_documentation_api'
                )
            elif any(w in lower for w in negotiate_words):
                return self._build_response(
                    "Let me see what I can do for you...",
                    worker='sales',
                    action='call_sales_api'
                )
            else:
                return self._build_response(
                    "Would you like to accept this offer?",
                    suggestions=['Accept offer', 'Negotiate rate',
                                 'Explain the terms']
                )

        elif current_stage == ConversationStage.DOCUMENTATION:
            return self._build_response(
                "Generating your sanction letter...",
                worker='documentation',
                action='call_documentation_api'
            )

        elif current_stage == ConversationStage.CLOSED:
            return self._build_response(
                "Your loan has been sanctioned! "
                "Download your letter using the button on the right.",
                suggestions=['Start a new application']
            )

        question, field = self.get_next_question()
        if question:
            return self._build_response(question, suggestions=self._get_field_suggestions(field))
            
        return self._build_response(
            "I'm here to help with your application. To proceed, I need to know a bit more about your loan needs. Shall we continue?")

    def get_workflow_status(self) -> Dict:
        """Get current workflow status."""
        return {
            "current_stage": self.state["stage"].value,
            "progress": self.state["workflow_progress"],
            "completed_stages": self.state["completed_stages"],
            "missing_fields": list(self.state["missing_fields"]),
            "missing_kyc_fields": list(self.state["missing_kyc_fields"])
        }

    # -------------------------------------------------------------------
    # WORKFLOW HELPERS  (called by workflow_routes.py)
    # -------------------------------------------------------------------

    def set_fraud_result(self, fraud_score: float, fraud_flag: str):
        """Update state with fraud check result and transition stage."""
        self.state["fraud_score"] = fraud_score
        self.state["fraud_flag"] = fraud_flag
        if fraud_flag == "High":
            self.transition_stage(ConversationStage.REJECTION_COUNSELING)
        else:
            self.transition_stage(ConversationStage.UNDERWRITING)

    def set_underwriting_result(self, risk_score: float, approval_status: bool,
                                 interest_rate: float = 12.5,
                                 risk_band: str = None,
                                 max_eligible_amount: float = None,
                                 rejection_reasons: list = None):
        """Update state with underwriting result and transition stage."""
        self.state["risk_score"] = risk_score
        self.state["approval_status"] = approval_status
        self.state["interest_rate"] = interest_rate
        if risk_band:
            self.state["risk_band"] = risk_band
        if max_eligible_amount is not None:
            self.state["max_eligible_amount"] = max_eligible_amount
        if rejection_reasons:
            self.state["rejection_reasons"] = rejection_reasons

        if approval_status:
            self.transition_stage(ConversationStage.OFFER_PRESENTATION)
        else:
            self.transition_stage(ConversationStage.REJECTION_COUNSELING)

    def set_offer(self, offer: Dict):
        """Store the current offer in state."""
        self.state["current_offer"] = offer
        self.state["offer_version"] = offer.get("offer_version", 1)
        if self.state["stage"] != ConversationStage.OFFER_PRESENTATION:
            self.transition_stage(ConversationStage.OFFER_PRESENTATION)

    def set_offer_accepted(self, accepted: bool):
        """Mark offer as accepted and transition to documentation."""
        self.state["offer_accepted"] = accepted
        if accepted:
            self.transition_stage(ConversationStage.DOCUMENTATION)