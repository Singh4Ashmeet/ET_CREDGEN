import logging
from datetime import datetime
from utils.config import INTEREST_BANDS

logger = logging.getLogger(__name__)


class SalesAgent:
    """
    Enhanced Sales Agent.
    Handles offer generation with versioning, negotiation limits,
    counter-offers, and detailed rejection counseling.
    """

    # Negotiation limits
    MAX_RATE_REDUCTION = 1.5      # Max 1.5% reduction from initial rate
    MAX_AMOUNT_INCREASE_PCT = 10  # Max 10% increase over approved amount
    MAX_OFFER_VERSIONS = 3        # After 3 negotiations → final offer
    PROCESSING_FEE_PCT = 1.0      # 1% processing fee

    def __init__(self):
        logger.info("SalesAgent initialized")

    # ------------------------------------------------------------------
    # EMI / FINANCIALS
    # ------------------------------------------------------------------

    def _compute_emi(self, principal: float, annual_rate: float, months: int) -> float:
        if principal <= 0 or months <= 0 or annual_rate <= 0:
            return 0
        r = annual_rate / 12 / 100
        emi = principal * r * ((1 + r) ** months) / (((1 + r) ** months) - 1)
        return round(emi, 2)

    def _format_inr(self, amount) -> str:
        """Format number in Indian comma style."""
        try:
            amount = int(round(float(amount)))
            s = str(amount)
            if len(s) <= 3:
                return s
            last_three = s[-3:]
            rest = s[:-3]
            groups = []
            while rest:
                groups.insert(0, rest[-2:])
                rest = rest[:-2]
            return ','.join(groups) + ',' + last_three
        except Exception:
            return str(amount)

    # ------------------------------------------------------------------
    # OFFER GENERATION
    # ------------------------------------------------------------------

    def generate_offer(self, entities: dict, underwriting_result: dict,
                       current_version: int = 0, negotiation_request: dict = None) -> dict:
        """
        Generate or counter-offer based on underwriting result.

        Args:
            entities: User's collected entities
            underwriting_result: Dict from UnderwritingAgent
            current_version: Current offer version (0 = first offer)
            negotiation_request: Optional dict with rate/amount the user wants

        Returns:
            Offer dict with all financial details + version info
        """
        base_rate = underwriting_result.get('interest_rate', 12.5)
        approved_amount = underwriting_result.get('approved_amount',
                          entities.get('loan_amount', 0))
        tenure = underwriting_result.get('tenure_months',
                 entities.get('tenure', 36))
        risk_band = underwriting_result.get('risk_band', 'medium')

        new_version = current_version + 1
        is_final = new_version >= self.MAX_OFFER_VERSIONS

        # Apply negotiation if requested
        offer_rate = base_rate
        offer_amount = approved_amount

        if negotiation_request and new_version > 1:
            requested_rate = negotiation_request.get('rate')
            requested_amount = negotiation_request.get('amount')

            # Rate negotiation
            if requested_rate is not None:
                min_allowed_rate = base_rate - self.MAX_RATE_REDUCTION
                # Meet halfway between current and requested, but not below min
                if requested_rate < min_allowed_rate:
                    offer_rate = min_allowed_rate
                elif requested_rate < base_rate:
                    # Give partial concession
                    concession = (base_rate - requested_rate) * 0.5
                    offer_rate = round(base_rate - concession, 2)
                    offer_rate = max(offer_rate, min_allowed_rate)

            # Amount negotiation
            if requested_amount is not None and requested_amount > approved_amount:
                max_allowed = approved_amount * (1 + self.MAX_AMOUNT_INCREASE_PCT / 100)
                if requested_amount <= max_allowed:
                    offer_amount = requested_amount
                else:
                    offer_amount = max_allowed

        # Compute financials
        emi = self._compute_emi(offer_amount, offer_rate, tenure)
        processing_fee = round(offer_amount * self.PROCESSING_FEE_PCT / 100, 2)
        total_interest = round(emi * tenure - offer_amount, 2)
        total_payable = round(emi * tenure + processing_fee, 2)

        offer = {
            "loan_amount": offer_amount,
            "interest_rate": offer_rate,
            "tenure_months": tenure,
            "monthly_emi": emi,
            "processing_fee": processing_fee,
            "total_interest": total_interest,
            "total_payable": total_payable,
            "risk_band": risk_band,
            "offer_version": new_version,
            "is_final": is_final,
            "created_at": datetime.utcnow().isoformat(),
        }

        # Build message
        if is_final:
            offer["message"] = (
                f"This is our best and final offer:\n\n"
                f"💰 **Loan Amount:** ₹{self._format_inr(offer_amount)}\n"
                f"📊 **Interest Rate:** {offer_rate}% p.a.\n"
                f"📅 **Tenure:** {tenure} months\n"
                f"💳 **Monthly EMI:** ₹{self._format_inr(emi)}\n"
                f"🏷️ **Processing Fee:** ₹{self._format_inr(processing_fee)}\n"
                f"📈 **Total Payable:** ₹{self._format_inr(total_payable)}\n\n"
                f"Would you like to accept this offer?"
            )
        elif new_version > 1:
            offer["message"] = (
                f"Here's our revised offer (Version {new_version}):\n\n"
                f"💰 **Loan Amount:** ₹{self._format_inr(offer_amount)}\n"
                f"📊 **Interest Rate:** {offer_rate}% p.a.\n"
                f"📅 **Tenure:** {tenure} months\n"
                f"💳 **Monthly EMI:** ₹{self._format_inr(emi)}\n"
                f"🏷️ **Processing Fee:** ₹{self._format_inr(processing_fee)}\n"
                f"📈 **Total Payable:** ₹{self._format_inr(total_payable)}\n\n"
                f"You can accept, negotiate further, or decline."
            )
        else:
            offer["message"] = (
                f"Based on your profile, here's your loan offer:\n\n"
                f"💰 **Loan Amount:** ₹{self._format_inr(offer_amount)}\n"
                f"📊 **Interest Rate:** {offer_rate}% p.a.\n"
                f"📅 **Tenure:** {tenure} months\n"
                f"💳 **Monthly EMI:** ₹{self._format_inr(emi)}\n"
                f"🏷️ **Processing Fee:** ₹{self._format_inr(processing_fee)}\n"
                f"📈 **Total Payable:** ₹{self._format_inr(total_payable)}\n\n"
                f"You can **accept**, **negotiate**, or **decline** this offer."
            )

        offer["suggestions"] = ["Accept Offer", "Negotiate Rate", "Decline"]

        logger.info(f"Offer v{new_version}: ₹{offer_amount} @ {offer_rate}%, EMI ₹{emi}")
        return offer

    # ------------------------------------------------------------------
    # REJECTION COUNSELING
    # ------------------------------------------------------------------

    def provide_counseling(self, entities: dict, rejection_reasons: list,
                           max_eligible_amount: float = 0,
                           underwriting_result: dict = None) -> dict:
        """
        Provide specific, actionable counseling for rejected applications.
        Suggests alternative amounts if eligible, and concrete next steps.
        """
        advice_lines = []
        suggestions = []

        # Category-specific advice
        for reason in rejection_reasons:
            reason_lower = reason.lower()

            if 'credit score' in reason_lower:
                advice_lines.append(
                    "📋 **Improve Credit Score:** Pay off outstanding dues, maintain low "
                    "credit utilization, and avoid new credit inquiries for 3-6 months."
                )
            elif 'age' in reason_lower and 'below' in reason_lower:
                advice_lines.append(
                    "👤 **Age Requirement:** You need to be at least 21 to apply. "
                    "Consider applying with a co-borrower who meets the age criteria."
                )
            elif 'age' in reason_lower and 'above' in reason_lower:
                advice_lines.append(
                    "👤 **Age Limit:** For applicants above 65, we recommend shorter "
                    "tenure loans or adding a co-borrower."
                )
            elif 'income' in reason_lower and 'below' in reason_lower:
                advice_lines.append(
                    "💼 **Income Requirement:** Consider adding a co-applicant's income "
                    "or providing additional income proof (rent, investments, freelancing)."
                )
            elif 'dti' in reason_lower:
                advice_lines.append(
                    "💳 **High Debt Burden:** Try reducing existing EMIs/obligations "
                    "before reapplying. Closing 1-2 active loans can significantly "
                    "improve eligibility."
                )
            elif 'lti' in reason_lower:
                advice_lines.append(
                    "📊 **Loan-to-Income Ratio:** The requested amount is high relative "
                    "to your income. Consider a smaller amount or longer tenure."
                )
            elif 'risk' in reason_lower:
                advice_lines.append(
                    "⚡ **Risk Profile:** Maintain consistent employment, reduce "
                    "outstanding debts, and ensure timely payments on existing loans."
                )
            elif 'amount' in reason_lower and 'exceeds' in reason_lower:
                advice_lines.append(
                    "💰 **Amount Exceeds Eligibility:** You may qualify for a smaller "
                    "loan amount based on your income and existing obligations."
                )

        # Suggest alternative if any amount is eligible
        if max_eligible_amount and max_eligible_amount > 50000:
            rate = 14.0
            if underwriting_result:
                rate = underwriting_result.get('interest_rate', 14.0)
            tenure = entities.get('tenure', 36)
            alt_emi = self._compute_emi(max_eligible_amount, rate, tenure)

            advice_lines.append(
                f"\n🔄 **Alternative Offer:** You may qualify for ₹{self._format_inr(max_eligible_amount)} "
                f"at {rate}% p.a. with EMI of ₹{self._format_inr(alt_emi)}/month. "
                f"Would you like to explore this option?"
            )
            suggestions = ["Try Lower Amount", "Start New Application", "Exit"]
        else:
            advice_lines.append(
                "\n📞 **Next Steps:** Please visit your nearest branch or call our "
                "helpline (1800-XXX-XXXX) for personalized assistance."
            )
            suggestions = ["Start New Application", "Exit"]

        if not advice_lines:
            advice_lines.append(
                "We weren't able to approve your application at this time. "
                "Please ensure all your details are accurate and try again later."
            )

        message = (
            "We understand this isn't the outcome you were hoping for. "
            "Here's what you can do:\n\n" + "\n\n".join(advice_lines)
        )

        return {
            "message": message,
            "suggestions": suggestions,
            "max_eligible_amount": max_eligible_amount,
            "rejection_reasons": rejection_reasons,
        }

    # ------------------------------------------------------------------
    # OFFER ACCEPTANCE
    # ------------------------------------------------------------------

    def accept_offer(self, offer: dict) -> dict:
        """Process offer acceptance."""
        return {
            "message": (
                f"🎉 Congratulations! Your loan of ₹{self._format_inr(offer.get('loan_amount', 0))} "
                f"has been confirmed!\n\n"
                f"We'll now generate your **Sanction Letter**. Please wait a moment..."
            ),
            "accepted": True,
            "offer": offer,
            "next_action": "documentation",
        }
