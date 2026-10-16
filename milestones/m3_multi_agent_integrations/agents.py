"""
SupportPilot Multi-Agent System (Milestone 3)
5 Specialized AI Agents coordinated by BankSupportAI Orchestrator:
  Agent 1 - Diagnosis Agent      : Classify ticket, set confidence + risk
  Agent 2 - Retrieval Agent      : TF-IDF search on banking KB
  Agent 3 - Resolution Agent     : Generate 6-7 step resolution
  Agent 4 - Validation Agent     : Weighted confidence score & decision
  Agent 5 - Escalation Agent     : Decide AUTO_RESOLVE or ESCALATE
"""

import re
import json
from pathlib import Path
from config import KB_PATH
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# ── Load Banking Knowledge Base ─────────────────────────────────────
_KB_PATH = Path(KB_PATH)

try:
    with open(_KB_PATH, "r", encoding="utf-8") as _f:
        _kb_data = json.load(_f)
    KNOWLEDGE_BASE = _kb_data.get("entries", [])
except Exception:
    KNOWLEDGE_BASE = []


# ═══════════════════════════════════════════════════════════════════
# AGENT 1 — DIAGNOSIS AGENT
# ═══════════════════════════════════════════════════════════════════
class DiagnosisAgent:
    """
    Reads the ticket text, identifies the banking category,
    assigns risk level and initial confidence.
    """

    CATEGORY_KEYWORDS = {
        "ATM / Cash":         ["atm", "cash", "withdrawal", "dispensed", "swallowed", "retained"],
        "Fraud / Security":   ["fraud", "unauthorized", "scam", "hacked", "compromised",
                               "suspicious", "otp", "someone used", "unknown transaction"],
        "Card Issue":         ["card", "debit card", "credit card", "declined", "blocked",
                               "pin", "contactless", "chip"],
        "UPI / Transfer":     ["upi", "neft", "rtgs", "imps", "gpay", "phonepe", "transfer",
                               "beneficiary", "failed transfer", "payment failed"],
        "Account / KYC":      ["account", "kyc", "balance", "statement", "dormant",
                               "frozen", "blocked account", "closure"],
        "Loan / EMI":         ["loan", "emi", "interest", "repayment", "foreclosure",
                               "bounce", "overdue"],
        "Net Banking":        ["netbanking", "internet banking", "online banking",
                               "mobile banking", "app", "login"],
        "Forex / NRI":        ["forex", "foreign", "nri", "international", "currency",
                               "exchange rate", "remittance"],
        "General Banking":    [],
    }

    HIGH_RISK_CATEGORIES = {"Fraud / Security", "ATM / Cash"}

    def analyze(self, text: str, high_risk_threshold: float = 10000.0) -> dict:
        trimmed = (text or "").strip()
        lower   = trimmed.lower()

        # Check for vague input
        if len(trimmed) < 8 or lower in ["help", "test", "urgent", "problem", "issue", "support", "help me"]:
            return {
                "category":   "General Banking",
                "diagnosis":  "Support request requires additional details to diagnose specific banking issue",
                "confidence": 0.20,
                "risk":       "LOW",
                "is_vague":   True,
            }

        scores = {}
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            scores[category] = sum(1 for kw in keywords if kw in lower)

        category = max(scores, key=scores.get) if max(scores.values(), default=0) > 0 else "General Banking"
        matched  = scores.get(category, 0)

        # confidence: base 0.65, boosted by keyword matches
        confidence = min(0.65 + matched * 0.08, 0.96)

        # Check for financial amounts exceeding high-risk threshold
        amounts = re.findall(r"(?:rs\.?|inr|₹)\s*([0-9,]+)", lower)
        is_high_amount = False
        for a in amounts:
            try:
                val = float(a.replace(",", ""))
                if val >= high_risk_threshold:
                    is_high_amount = True
                    break
            except ValueError:
                pass

        # risk level
        if is_high_amount or category in self.HIGH_RISK_CATEGORIES:
            risk = "HIGH"
        elif any(kw in lower for kw in ["failed", "not working", "blocked", "deducted", "debited"]):
            risk = "MEDIUM"
        else:
            risk = "LOW"

        return {
            "category":   category,
            "diagnosis":  f"Banking issue classified as {category}",
            "confidence": round(confidence, 2),
            "risk":       risk,
            "is_vague":   False,
            "high_amount": is_high_amount,
        }


# ═══════════════════════════════════════════════════════════════════
# AGENT 2 — RETRIEVAL AGENT
# ═══════════════════════════════════════════════════════════════════
class RetrievalAgent:
    """
    Uses TF-IDF + Cosine Similarity to find the most relevant
    KB articles for the submitted ticket.
    """

    def __init__(self):
        if not KNOWLEDGE_BASE:
            self._documents = []
            self._vectorizer = None
            self._matrix     = None
            return

        self._documents = [
            item["title"] + " " + item.get("category", "") + " " + item["content"]
            for item in KNOWLEDGE_BASE
        ]
        self._vectorizer = TfidfVectorizer(stop_words="english", max_features=5000)
        self._matrix     = self._vectorizer.fit_transform(self._documents)

    def search(self, query: str, top_k: int = 1, min_similarity: float = 0.05) -> dict:
        if not self._vectorizer or not KNOWLEDGE_BASE:
            return {"article": None, "similarity": 0.0, "top_articles": []}

        query_vector = self._vectorizer.transform([query])
        scores       = cosine_similarity(query_vector, self._matrix)[0]
        ranked       = scores.argsort()[::-1]

        top_articles = []
        for idx in ranked[:top_k]:
            sim = float(scores[idx])
            if sim >= min_similarity:
                top_articles.append({
                    "id":         KNOWLEDGE_BASE[idx]["id"],
                    "title":      KNOWLEDGE_BASE[idx]["title"],
                    "category":   KNOWLEDGE_BASE[idx].get("category", ""),
                    "content":    KNOWLEDGE_BASE[idx]["content"],
                    "similarity": round(sim, 4),
                })

        best_art = top_articles[0] if top_articles else None
        best_sim = top_articles[0]["similarity"] if top_articles else 0.0

        return {
            "article":      best_art,
            "similarity":   round(best_sim, 4),
            "top_articles": top_articles,
        }


# ═══════════════════════════════════════════════════════════════════
# AGENT 3 — RESOLUTION AGENT
# ═══════════════════════════════════════════════════════════════════
class ResolutionAgent:
    """
    Generates clean, human-readable 6-7 step resolution
    from the retrieved KB article. Never returns raw KB text.
    """

    # Category-specific step templates (used when KB content is thin)
    TEMPLATES = {
        "ATM / Cash": [
            "Note the exact date, time, ATM ID and transaction reference number from your SMS alert.",
            "Check your account balance via mobile banking to confirm the debit amount.",
            "As per RBI guidelines, cash-not-dispensed ATM transactions should auto-reverse within T+5 working days — monitor your account.",
            "If no reversal occurs within 5 working days, raise a formal dispute with your bank providing the transaction reference.",
            "The bank will investigate using the ATM operator's transaction logs and CCTV records.",
            "If reversal is delayed beyond T+5 days, the bank must pay a penalty of Rs 100/day — keep your complaint reference.",
            "If the issue is not resolved after following the above steps, escalate to the Banking Ombudsman with your complaint reference number.",
        ],
        "Fraud / Security": [
            "Immediately call your bank's 24x7 helpline to block all cards and freeze your account.",
            "Do NOT share any OTP, PIN, CVV, or account credentials with anyone — including callers claiming to be bank officials.",
            "Note all unauthorized transaction details: date, time, amount, merchant/reference from your SMS alerts.",
            "File a formal fraud complaint at your bank branch or via net banking within 3 days for maximum liability protection under RBI rules.",
            "File a cybercrime complaint at cybercrime.gov.in or your nearest police station.",
            "Request a new card and change all banking passwords and PINs immediately after securing your account.",
            "Follow up with the bank's fraud investigation team using your complaint reference number until the amount is reversed.",
        ],
        "Card Issue": [
            "Check whether your card is physically intact and the chip/magnetic strip is undamaged.",
            "Verify your daily card transaction limit has not been reached via your banking app.",
            "Attempt the transaction at a different terminal or ATM to rule out merchant-side issues.",
            "If the card is blocked, call the bank helpline or unblock it via mobile banking app.",
            "For PIN-related issues, regenerate your PIN through the bank's ATM, app, or branch.",
            "If the card is lost or stolen, immediately report it to the bank to block and request a replacement.",
            "A new replacement card typically arrives within 5-7 working days — request one if needed.",
        ],
        "UPI / Transfer": [
            "Check the transaction status in your UPI app — note the UPI reference number (UTR/RRN) from the payment history.",
            "If the status shows 'Failed' or 'Pending', wait up to 30 minutes as NPCI has automatic reversal within T+1 working day.",
            "Confirm the beneficiary's account details (UPI ID, account number, IFSC) are correct before retrying.",
            "If money was debited but not credited to the beneficiary, raise a dispute through your bank's app within 30 days.",
            "For NEFT/RTGS failures, the bank must reverse the amount within 2 hours of settlement failure.",
            "Contact both your bank and the beneficiary's bank with the UTR number to trace the transaction.",
            "If unresolved after 5 working days, escalate to the NPCI dispute portal or RBI Banking Ombudsman.",
        ],
        "Account / KYC": [
            "Log in to your bank's app or netbanking to check your account status and any pending KYC notifications.",
            "Ensure your mobile number and email ID linked to the account are active and updated.",
            "Upload pending KYC documents (Aadhaar, PAN, address proof) through the bank's app, website, or by visiting a branch.",
            "For frozen accounts, visit the nearest branch with original KYC documents for in-person verification.",
            "Re-activate dormant accounts by visiting a branch with KYC documents and submitting a reactivation request.",
            "After KYC submission, allow 2-3 working days for the bank to process and activate your account.",
            "If the account remains frozen after KYC completion, escalate to the branch manager with your submission reference.",
        ],
        "Loan / EMI": [
            "Log in to your bank's app and check your loan account status and EMI schedule.",
            "Ensure sufficient balance in your linked account 2 days before EMI due date for auto-debit.",
            "If an EMI bounced, pay it immediately via net banking to avoid penal charges and credit score impact.",
            "Contact your bank's loan department to understand any overdue charges or restructuring options.",
            "Request an updated loan statement showing all payments, outstanding balance, and interest calculation.",
            "For foreclosure or prepayment, obtain a foreclosure letter from the bank and verify applicable charges.",
            "If EMI amounts seem incorrect, request a detailed amortization schedule from your branch.",
        ],
        "Net Banking": [
            "Clear your browser cache and cookies, then try logging in on a different browser or device.",
            "Ensure you are using the official bank website URL (check for HTTPS padlock) — avoid phishing sites.",
            "If locked out, use the 'Forgot Password' option to reset credentials via your registered mobile number.",
            "Generate a new password following the bank's security requirements (8+ chars, special characters).",
            "Enable two-factor authentication (2FA) with your registered mobile number for added security.",
            "If the mobile banking app is not working, uninstall and reinstall the latest version from the official app store.",
            "Contact the bank's helpline if login issues persist after following the above steps.",
        ],
        "Password & Access Recovery": [
            "Verify your registered mobile number and email ID to initiate secure credential reset.",
            "Open your official mobile banking app or net banking portal and select 'Forgot Password / Reset Login Access'.",
            "Enter your Customer ID or registered mobile number to receive the mandatory one-time password (OTP).",
            "Enter the OTP along with your active debit card details (card number, PIN, expiry) to authenticate.",
            "Create a new alphanumeric password following standard banking security guidelines (minimum 8 characters with symbol).",
            "Clear your mobile browser/app cache, re-open the application, and test sign-in with your new credentials.",
            "If account lockout persists or device binding fails, contact our 24x7 helpline or visit the nearest branch.",
        ],
        "General Banking": [
            "Gather all relevant details: account number, transaction ID, date, time, and amount involved.",
            "Check your SMS alerts and banking app for the latest transaction status and account information.",
            "Log in to your mobile banking app to verify account balance and recent transaction history.",
            "Contact your bank's 24x7 customer care helpline with your account details and issue description.",
            "Visit the nearest branch with valid photo ID (Aadhaar/PAN) if the issue cannot be resolved remotely.",
            "Raise a formal written complaint at the branch and obtain a complaint reference number.",
            "If unresolved within the bank's stated timeline, escalate to the RBI Banking Ombudsman at cms.rbi.org.in.",
        ],
    }

    def _get_template_for_category(self, category: str) -> list:
        cat_lower = (category or "").lower()
        if any(k in cat_lower for k in ["passcode", "password", "login", "pin", "credential", "locked", "access"]):
            return self.TEMPLATES["Password & Access Recovery"]
        elif any(k in cat_lower for k in ["atm", "cash", "dispense", "withdrawal"]):
            return self.TEMPLATES["ATM / Cash"]
        elif any(k in cat_lower for k in ["card", "declined", "pos", "chip", "contactless"]):
            return self.TEMPLATES["Card Issue"]
        elif any(k in cat_lower for k in ["upi", "transfer", "neft", "imps", "beneficiary", "rtgs"]):
            return self.TEMPLATES["UPI / Transfer"]
        elif any(k in cat_lower for k in ["fraud", "stolen", "unauthorized", "unauthorised", "compromised", "scam"]):
            return self.TEMPLATES["Fraud / Security"]
        elif any(k in cat_lower for k in ["kyc", "account", "freeze", "dormant", "document"]):
            return self.TEMPLATES["Account / KYC"]
        elif any(k in cat_lower for k in ["loan", "emi", "interest"]):
            return self.TEMPLATES["Loan / EMI"]
        elif any(k in cat_lower for k in ["netbanking", "online", "portal", "browser"]):
            return self.TEMPLATES["Net Banking"]
        return self.TEMPLATES.get(category, self.TEMPLATES["General Banking"])

    def generate(self, diagnosis: dict, article: dict, query: str = "") -> dict:
        category = diagnosis.get("category", "General Banking")
        template = self._get_template_for_category(category)

        # Try LLM resolution if query is provided
        if query:
            try:
                from rag.generator import generate_resolution
                ticket = {"title": query, "description": query, "category": category, "priority": "Medium"}
                docs = [article] if article else []
                res = generate_resolution(ticket, docs)
                if res and res.get("steps"):
                    step_texts = [s["text"] if isinstance(s, dict) else str(s) for s in res["steps"]]
                    return {
                        "response": f"We have identified your issue as a {category} concern. Please follow these troubleshooting steps:",
                        "steps":    step_texts,
                        "category": category,
                        "llm_used": res.get("llm_used", False),
                    }
            except Exception:
                pass

        # Try to extract steps from KB article
        steps = []
        if article and article.get("content"):
            steps = self._extract_kb_steps(article["content"], category)

        # If KB gave us usable steps, blend with template
        if steps:
            # Use KB steps but cap at 6, add escalation as step 7
            final_steps = steps[:6]
            final_steps.append(
                "If the issue is not resolved after following the above steps, "
                "escalate to the bank's grievance officer or the RBI Banking Ombudsman "
                "at cms.rbi.org.in with your complaint reference number."
            )
        else:
            final_steps = template

        response = (
            f"We have identified your issue as a {category} concern. "
            "Please follow these troubleshooting steps carefully:"
        )

        return {
            "response": response,
            "steps":    final_steps,
            "category": category,
        }

    def _extract_kb_steps(self, content: str, category: str) -> list:
        """Extract numbered steps from KB article content, clean and return max 6."""
        lines   = content.split("\n")
        steps   = []
        buffer  = []

        for line in lines:
            stripped = line.strip()
            if re.match(r"^\d+\.", stripped):
                if buffer:
                    steps.append(" ".join(buffer).strip())
                    buffer = []
                cleaned = re.sub(r"^\d+\.\s*", "", stripped).strip()
                if cleaned:
                    buffer.append(cleaned)
            elif buffer and stripped and not stripped.startswith("BankSupport AI"):
                buffer.append(stripped)

        if buffer:
            text = " ".join(buffer).strip()
            if len(text) > 10:
                steps.append(text)

        # Clean: remove KB disclaimer noise, keep meaningful steps
        clean = []
        for s in steps:
            if len(s) > 15 and "BankSupport AI" not in s and "verification_note" not in s.lower():
                # Trim very long steps
                if len(s) > 250:
                    s = s[:247] + "..."
                clean.append(s)

        return clean[:6]  # max 6 from KB


# ═══════════════════════════════════════════════════════════════════
# AGENT 4 — VALIDATION AGENT
# ═══════════════════════════════════════════════════════════════════
class ValidationAgent:
    """
    Enforces a strict multi-condition gate for Autonomous Resolution:
      1. Classification Confidence >= threshold (e.g. 70%)
      2. KB Retrieval Similarity >= min_similarity (e.g. 0.05 or configured)
      3. Composite Validation Score >= threshold (weighted: 0.40 diag + 0.40 retrieval + 0.20 completeness)
      4. Risk Level != HIGH (high risk transactions, critical fraud or amounts >= high_risk_threshold)
      5. Issue Clarity: Customer problem must have sufficient detail (not vague)
    If ANY condition fails, the ticket MUST be escalated to specialist review.
    """

    def validate(self, diagnosis_confidence: float, retrieval_similarity: float,
                 number_of_steps: int, risk: str = "LOW",
                 threshold: float = 70.0, min_similarity: float = 0.05,
                 is_vague: bool = False) -> dict:

        diag_conf_pct     = float(diagnosis_confidence * 100.0 if diagnosis_confidence <= 1.0 else diagnosis_confidence)
        retrieval_sim_pct = float(retrieval_similarity * 100.0 if retrieval_similarity <= 1.0 else retrieval_similarity)
        min_sim_pct       = float(min_similarity * 100.0 if min_similarity <= 1.0 else min_similarity)
        completeness      = float(min(number_of_steps / 6.0, 1.0))

        # Composite score
        score = float(round((diag_conf_pct * 0.40) + (retrieval_sim_pct * 0.40) + (completeness * 100.0 * 0.20), 2))

        # Strict Multi-Condition Gate evaluation
        gate_clarity   = bool(not is_vague)
        gate_risk      = bool(risk != "HIGH")
        gate_diag      = bool(diag_conf_pct >= threshold)
        gate_retrieval = bool(retrieval_sim_pct >= min_sim_pct and retrieval_similarity > 0)
        gate_score     = bool(score >= threshold)

        if not gate_clarity:
            status = "ESCALATE"
            reason = "Ticket lacks essential transaction details — customer clarification required"
        elif not gate_risk:
            status = "ESCALATE"
            reason = "High financial risk / security exposure — mandatory specialist verification required"
        elif not gate_diag:
            status = "ESCALATE"
            reason = f"Classification confidence ({round(diag_conf_pct, 1)}%) is below the autonomous gate ({threshold}%)"
        elif not gate_retrieval:
            status = "ESCALATE"
            reason = f"Knowledge base similarity ({round(retrieval_sim_pct, 1)}%) below minimum relevance threshold ({round(min_sim_pct, 1)}%)"
        elif not gate_score:
            status = "ESCALATE"
            reason = f"Composite validation score ({score}%) is below required threshold ({threshold}%)"
        else:
            status = "AUTO_RESOLVE"
            reason = f"All validation gates passed ({score}% composite, {round(diag_conf_pct, 1)}% ML confidence ≥ {threshold}%)"

        return {
            "confidence":              float(score),
            "score":                   float(score),
            "status":                  str(status),
            "reason":                  str(reason),
            "threshold":               float(threshold),
            "diagnosis_confidence":    float(round(diag_conf_pct, 1)),
            "retrieval_similarity":    float(round(retrieval_sim_pct, 1)),
            "resolution_completeness": float(round(completeness * 100, 1)),
            "gates": {
                "classification_confidence": {"passed": bool(gate_diag), "value": float(round(diag_conf_pct, 1)), "threshold": float(threshold)},
                "knowledge_relevance":       {"passed": bool(gate_retrieval), "value": float(round(retrieval_sim_pct, 1)), "threshold": float(round(min_sim_pct, 1))},
                "validation_score":          {"passed": bool(gate_score), "value": float(score), "threshold": float(threshold)},
                "risk_acceptable":           {"passed": bool(gate_risk), "risk": str(risk)},
                "clarity_sufficient":        {"passed": bool(gate_clarity), "is_vague": bool(is_vague)},
            }
        }


# ═══════════════════════════════════════════════════════════════════
# AGENT 5 — ESCALATION AGENT
# ═══════════════════════════════════════════════════════════════════
class EscalationAgent:
    """Determines whether a ticket needs human intervention."""

    def should_escalate(self, validation: dict) -> bool:
        return validation.get("status") == "ESCALATE"

    def escalation_reason(self, validation: dict) -> str:
        return validation.get("reason", "Low confidence — escalated to human specialist")


# ═══════════════════════════════════════════════════════════════════
# MULTI-AGENT ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════
class BankSupportAI:
    """
    Orchestrates all 5 agents in sequence:
    Diagnosis → Retrieval → Resolution → Validation → Escalation
    """

    def __init__(self, threshold: float = 70.0):
        self.diagnosis_agent  = DiagnosisAgent()
        self.retrieval_agent  = RetrievalAgent()
        self.resolution_agent = ResolutionAgent()
        self.validation_agent = ValidationAgent()
        self.escalation_agent = EscalationAgent()
        self.threshold        = threshold

    def process_query(self, query: str, settings: dict = None, ml_category: str = None, ml_confidence: float = None) -> dict:
        """Run the full 5-agent pipeline on a ticket query string using active settings."""
        if not settings:
            try:
                from database import get_system_settings
                settings = get_system_settings()
            except Exception:
                settings = {}

        active_th        = float(settings.get("auto_resolve_threshold", self.threshold))
        active_high_risk = float(settings.get("high_risk_amount", 10000.0))
        active_top_k     = int(settings.get("retrieval_top_k", 1))
        active_min_sim   = float(settings.get("minimum_similarity", 0.05))

        # Step 1 — Diagnosis (unified with ML model classification when provided)
        diagnosis = self.diagnosis_agent.analyze(query, high_risk_threshold=active_high_risk)
        if ml_category:
            diagnosis["category"] = ml_category
            diagnosis["diagnosis"] = f"Banking issue classified as {ml_category}"
        if ml_confidence is not None:
            # Normalize to 0-100 scale if needed
            conf_val = ml_confidence * 100.0 if ml_confidence <= 1.0 else ml_confidence
            diagnosis["confidence"] = round(conf_val, 2)

        # Step 2 — Knowledge Retrieval
        retrieval = self.retrieval_agent.search(
            query,
            top_k=active_top_k,
            min_similarity=active_min_sim
        )

        # Step 3 — Resolution Generation
        resolution = self.resolution_agent.generate(
            diagnosis,
            retrieval.get("article") or {},
            query=query,
        )

        # Step 4 — Validation (Strict multi-condition gate using exact ML confidence)
        validation = self.validation_agent.validate(
            diagnosis_confidence = diagnosis["confidence"],
            retrieval_similarity  = retrieval["similarity"],
            number_of_steps       = len(resolution["steps"]),
            risk                  = diagnosis["risk"],
            threshold             = active_th,
            min_similarity        = active_min_sim,
            is_vague              = diagnosis.get("is_vague", False),
        )

        # Step 5 — Escalation decision
        escalation = self.escalation_agent.should_escalate(validation)

        return {
            "diagnosis":  diagnosis,
            "retrieval":  retrieval,
            "resolution": resolution,
            "validation": validation,
            "escalation": escalation,
        }

    def process_ticket(self, ticket_text: str, settings: dict = None, ml_category: str = None, ml_confidence: float = None) -> dict:
        """Alias for process_query — used by Flask app."""
        return self.process_query(ticket_text, settings=settings, ml_category=ml_category, ml_confidence=ml_confidence)
