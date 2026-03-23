import logging
import os
import numpy as np
from datetime import datetime
from utils.config import (
    MIN_LOAN_AMOUNT, MAX_LOAN_AMOUNT, MIN_AGE, MAX_AGE,
    MIN_INCOME, INTEREST_BANDS, MIN_TENURE, MAX_TENURE
)

logger = logging.getLogger(__name__)


class UnderwritingAgent:
    """
    Enhanced Underwriting Agent.
    Combines ML risk scoring with detailed rule-based eligibility checks.
    Returns enriched results with financial ratios, rate matrix,
    max eligible amount, rejection reasons, and feature importance.
    """

    # Rate matrix: risk_band × credit_bracket → interest rate %
    RATE_MATRIX = {
        # (risk_band, credit_bracket): interest_rate
        ("low", "excellent"):   9.0,   # risk 0-0.3, credit 750+
        ("low", "good"):        9.75,  # risk 0-0.3, credit 700-749
        ("low", "fair"):       10.5,   # risk 0-0.3, credit 650-699
        ("low", "poor"):       11.5,   # risk 0-0.3, credit <650
        ("medium", "excellent"):10.5,
        ("medium", "good"):    11.5,
        ("medium", "fair"):    13.0,
        ("medium", "poor"):    14.5,
        ("high", "excellent"): 13.0,
        ("high", "good"):      14.5,
        ("high", "fair"):      16.0,
        ("high", "poor"):      18.0,
    }

    # Hard rejection thresholds
    MAX_DTI_RATIO = 0.50      # Debt-to-Income
    MAX_LTI_RATIO = 5.0       # Loan-to-Income (annual)
    MIN_CREDIT_SCORE = 550

    def __init__(self):
        self.model = None
        self.model_loaded = False
        self._load_model()

    def _load_model(self):
        """Load the underwriting ML model."""
        try:
            import joblib
            model_path = os.path.join(os.path.dirname(__file__), '..', 'models', 'underwriting_model.pkl')
            if os.path.exists(model_path):
                self.model = joblib.load(model_path)
                self.model_loaded = True
                logger.info("Underwriting model loaded successfully")
            else:
                logger.warning(f"Underwriting model not found at {model_path}, using rule-based")
        except Exception as e:
            logger.error(f"Failed to load underwriting model: {e}")
            self.model_loaded = False

    # ------------------------------------------------------------------
    # HELPERS
    # ------------------------------------------------------------------

    def _get_credit_bracket(self, credit_score: int) -> str:
        if credit_score >= 750:
            return "excellent"
        elif credit_score >= 700:
            return "good"
        elif credit_score >= 650:
            return "fair"
        else:
            return "poor"

    def _get_risk_band(self, risk_score: float) -> str:
        if risk_score <= 0.3:
            return "low"
        elif risk_score <= 0.7:
            return "medium"
        else:
            return "high"

    def _compute_emi(self, principal: float, annual_rate: float, months: int) -> float:
        if principal <= 0 or months <= 0 or annual_rate <= 0:
            return 0
        r = annual_rate / 12 / 100
        emi = principal * r * ((1 + r) ** months) / (((1 + r) ** months) - 1)
        return round(emi, 2)

    def _compute_max_eligible(self, monthly_income: float, existing_obligations: float,
                              annual_rate: float, tenure: int) -> float:
        """Compute max loan amount such that EMI + obligations ≤ 50% income."""
        available = monthly_income * self.MAX_DTI_RATIO - existing_obligations
        if available <= 0:
            return 0
        r = annual_rate / 12 / 100
        if r <= 0 or tenure <= 0:
            return 0
        max_loan = available * (((1 + r) ** tenure) - 1) / (r * ((1 + r) ** tenure))
        return round(max(max_loan, 0), 0)

    # ------------------------------------------------------------------
    # RULE-BASED CHECKS
    # ------------------------------------------------------------------

    def _hard_rejection_checks(self, entities: dict) -> list:
        """Return list of hard rejection reasons (instant disqualifiers)."""
        reasons = []
        age = entities.get('age')
        if age is not None:
            if age < MIN_AGE:
                reasons.append(f"Applicant age ({age}) below minimum ({MIN_AGE})")
            if age > MAX_AGE:
                reasons.append(f"Applicant age ({age}) above maximum ({MAX_AGE})")

        income = entities.get('income', 0)
        monthly_income = income if income < 100000 else income / 12
        annual_income = monthly_income * 12
        if annual_income < MIN_INCOME:
            reasons.append(f"Annual income (₹{annual_income:,.0f}) below minimum (₹{MIN_INCOME:,.0f})")

        loan_amount = entities.get('loan_amount', 0)
        if loan_amount < MIN_LOAN_AMOUNT:
            reasons.append(f"Loan amount (₹{loan_amount:,.0f}) below minimum (₹{MIN_LOAN_AMOUNT:,.0f})")
        if loan_amount > MAX_LOAN_AMOUNT:
            reasons.append(f"Loan amount (₹{loan_amount:,.0f}) above maximum (₹{MAX_LOAN_AMOUNT:,.0f})")

        credit_score = entities.get('credit_score', 700)
        if credit_score < self.MIN_CREDIT_SCORE:
            reasons.append(f"Credit score ({credit_score}) below minimum ({self.MIN_CREDIT_SCORE})")

        return reasons

    def _compute_financial_ratios(self, entities: dict) -> dict:
        """Compute DTI, LTI, repayment capacity."""
        income = entities.get('income', 0)
        monthly_income = income if income < 100000 else income / 12
        annual_income = monthly_income * 12

        loan_amount = entities.get('loan_amount', 0)
        existing_obligations = entities.get('monthly_obligations', 0)

        # DTI (existing obligations / monthly income)
        dti = existing_obligations / max(monthly_income, 1)

        # LTI (loan amount / annual income)
        lti = loan_amount / max(annual_income, 1)

        # Repayment capacity (disposable income after obligations)
        repayment_capacity = monthly_income - existing_obligations

        return {
            "monthly_income": round(monthly_income, 2),
            "annual_income": round(annual_income, 2),
            "existing_obligations": existing_obligations,
            "dti_ratio": round(dti, 4),
            "lti_ratio": round(lti, 4),
            "repayment_capacity": round(repayment_capacity, 2),
        }

    # ------------------------------------------------------------------
    # ML RISK SCORING
    # ------------------------------------------------------------------

    def _ml_risk_score(self, entities: dict) -> float:
        """Get risk score from ML model or rule-based fallback."""
        if self.model_loaded and self.model:
            try:
                features = self._prepare_features(entities)
                if features is not None:
                    if hasattr(self.model, 'predict_proba'):
                        proba = self.model.predict_proba(features.reshape(1, -1))
                        return float(proba[0][1]) if proba.shape[1] > 1 else float(proba[0][0])
                    elif hasattr(self.model, 'predict'):
                        pred = self.model.predict(features.reshape(1, -1))
                        return float(pred[0])
            except Exception as e:
                logger.warning(f"ML prediction error: {e}")

        return self._rule_based_risk(entities)

    def _rule_based_risk(self, entities: dict) -> float:
        """Deterministic risk scoring when ML model unavailable."""
        score = 0.5  # Start at medium

        credit_score = entities.get('credit_score', 700)
        if credit_score >= 750:
            score -= 0.2
        elif credit_score >= 700:
            score -= 0.1
        elif credit_score < 600:
            score += 0.2

        age = entities.get('age', 35)
        if 28 <= age <= 50:
            score -= 0.05
        elif age < 25 or age > 58:
            score += 0.1

        emp = entities.get('employment_type', '')
        if emp == 'salaried':
            score -= 0.1
        elif emp == 'self_employed':
            score += 0.05

        income = entities.get('income', 0)
        monthly = income if income < 100000 else income / 12
        loan_amount = entities.get('loan_amount', 0)
        if monthly > 0:
            lti = loan_amount / (monthly * 12)
            if lti > 4:
                score += 0.15
            elif lti < 1.5:
                score -= 0.1

        num_active = entities.get('num_active_loans', 0)
        if num_active >= 3:
            score += 0.15
        elif num_active == 0:
            score -= 0.05

        return round(min(max(score, 0.0), 1.0), 4)

    def _prepare_features(self, entities: dict):
        """Prepare feature array for ML model."""
        try:
            age = entities.get('age', 30)
            income = entities.get('income', 500000)
            monthly_income = income if income < 100000 else income / 12
            loan_amount = entities.get('loan_amount', 300000)
            tenure = entities.get('tenure', 36)
            credit_score = entities.get('credit_score', 700)
            num_active = entities.get('num_active_loans', 0)
            num_closed = entities.get('num_closed_loans', 0)
            monthly_obligations = entities.get('monthly_obligations', 0)

            emp_map = {'salaried': 0, 'self_employed': 1, 'professional': 2, 'retired': 3}
            emp_encoded = emp_map.get(entities.get('employment_type', 'salaried'), 0)

            features = np.array([
                age,
                monthly_income,
                loan_amount,
                tenure,
                credit_score,
                num_active,
                num_closed,
                monthly_obligations,
                emp_encoded,
                loan_amount / max(monthly_income, 1),
                monthly_obligations / max(monthly_income, 1),
            ], dtype=np.float64)

            return features
        except Exception as e:
            logger.error(f"Feature prep error: {e}")
            return None

    # ------------------------------------------------------------------
    # MAIN UNDERWRITING
    # ------------------------------------------------------------------

    def perform_underwriting(self, entities: dict) -> dict:
        """
        Full underwriting pipeline.
        Returns enriched dict with:
          risk_score, risk_band, approval_status, interest_rate,
          max_eligible_amount, rejection_reasons, financial_ratios,
          emi, feature_importance, message
        """
        # 1. Hard rejection checks
        hard_rejections = self._hard_rejection_checks(entities)
        if hard_rejections:
            return self._build_rejection_result(entities, hard_rejections)

        # 2. Financial ratios
        ratios = self._compute_financial_ratios(entities)

        # 3. Soft rejection checks (DTI, LTI)
        soft_rejections = []
        if ratios["dti_ratio"] > self.MAX_DTI_RATIO:
            soft_rejections.append(f"DTI ratio ({ratios['dti_ratio']:.1%}) exceeds limit ({self.MAX_DTI_RATIO:.0%})")
        if ratios["lti_ratio"] > self.MAX_LTI_RATIO:
            soft_rejections.append(f"LTI ratio ({ratios['lti_ratio']:.1f}x) exceeds limit ({self.MAX_LTI_RATIO:.1f}x)")

        # 4. ML risk score
        risk_score = self._ml_risk_score(entities)
        risk_band = self._get_risk_band(risk_score)

        # 5. Interest rate from RATE_MATRIX
        credit_score = entities.get('credit_score', 700)
        credit_bracket = self._get_credit_bracket(credit_score)
        interest_rate = self.RATE_MATRIX.get((risk_band, credit_bracket), 14.0)

        # 6. Max eligible amount
        tenure = entities.get('tenure', 36)
        max_eligible = self._compute_max_eligible(
            ratios['monthly_income'],
            ratios['existing_obligations'],
            interest_rate,
            tenure
        )

        # 7. Approval decision
        loan_amount = entities.get('loan_amount', 0)
        all_rejections = hard_rejections + soft_rejections

        if risk_score >= 0.85:
            all_rejections.append(f"Risk score too high ({risk_score:.2f})")
        if loan_amount > max_eligible and max_eligible > 0:
            all_rejections.append(f"Requested amount (₹{loan_amount:,.0f}) exceeds max eligible (₹{max_eligible:,.0f})")

        approval_status = len(all_rejections) == 0

        # 8. Compute EMI for approved loan
        approved_amount = loan_amount if approval_status else min(loan_amount, max_eligible)
        emi = self._compute_emi(approved_amount, interest_rate, tenure)
        total_payable = round(emi * tenure, 2)
        total_interest = round(total_payable - approved_amount, 2)

        # 9. Feature importance (approximate)
        feature_importance = {
            "credit_score": 0.30,
            "dti_ratio": 0.20,
            "lti_ratio": 0.15,
            "employment_type": 0.10,
            "age": 0.10,
            "income": 0.15,
        }

        # 10. Build result
        if approval_status:
            message = f"✅ Congratulations! Your loan of ₹{loan_amount:,.0f} has been approved at {interest_rate}% p.a."
        else:
            message = f"❌ We're unable to approve the requested amount. {'; '.join(all_rejections[:2])}"

        result = {
            "risk_score": round(risk_score, 4),
            "risk_band": risk_band,
            "approval_status": approval_status,
            "interest_rate": interest_rate,
            "max_eligible_amount": max_eligible,
            "approved_amount": approved_amount if approval_status else 0,
            "emi": emi,
            "total_payable": total_payable,
            "total_interest": total_interest,
            "tenure_months": tenure,
            "credit_score": credit_score,
            "credit_bracket": credit_bracket,
            "rejection_reasons": all_rejections,
            "financial_ratios": ratios,
            "feature_importance": feature_importance,
            "message": message,
            "underwritten_at": datetime.utcnow().isoformat(),
        }

        logger.info(f"Underwriting: approval={approval_status}, risk={risk_score}, rate={interest_rate}%")
        return result

    def _build_rejection_result(self, entities: dict, reasons: list) -> dict:
        """Build rejection result with max eligible calculation."""
        ratios = self._compute_financial_ratios(entities)
        risk_score = self._ml_risk_score(entities)
        risk_band = self._get_risk_band(risk_score)
        credit_score = entities.get('credit_score', 700)
        credit_bracket = self._get_credit_bracket(credit_score)
        interest_rate = self.RATE_MATRIX.get((risk_band, credit_bracket), 14.0)
        tenure = entities.get('tenure', 36)

        max_eligible = self._compute_max_eligible(
            ratios['monthly_income'],
            ratios['existing_obligations'],
            interest_rate,
            tenure
        )

        return {
            "risk_score": round(risk_score, 4),
            "risk_band": risk_band,
            "approval_status": False,
            "interest_rate": interest_rate,
            "max_eligible_amount": max_eligible,
            "approved_amount": 0,
            "emi": 0,
            "total_payable": 0,
            "total_interest": 0,
            "tenure_months": tenure,
            "credit_score": credit_score,
            "credit_bracket": credit_bracket,
            "rejection_reasons": reasons,
            "financial_ratios": ratios,
            "feature_importance": {},
            "message": f"❌ Application rejected: {reasons[0]}",
            "underwritten_at": datetime.utcnow().isoformat(),
        }