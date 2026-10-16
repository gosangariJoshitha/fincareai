"""
RAG Step 1 – Ticket Analysis & Query Generation
Extracts keywords from the ticket and builds a search query.
"""

BANKING_KEYWORDS = [
    "atm", "cash", "card", "debit", "credit", "upi", "neft", "imps", "rtgs",
    "fraud", "unauthorized", "transaction", "transfer", "account", "balance",
    "kyc", "loan", "emi", "interest", "statement", "pin", "otp", "block",
    "unblock", "refund", "dispute", "chargeback", "merchant", "online",
    "mobile", "netbanking", "branch", "cheque", "deposit", "withdrawal",
    "failed", "declined", "pending", "timeout", "error", "stolen", "lost",
    "password", "authentication", "fasttag", "nri", "international", "forex",
    "locker", "nominee", "insurance", "investment", "fd", "rd", "savings",
    "current", "zero balance", "minimum balance", "charges", "fee",
    "notification", "alert", "sms", "email", "update", "pan", "aadhaar",
    "signature", "dormant", "inactive", "close", "closure"
]


def analyze_ticket(ticket: dict) -> dict:
    """
    Analyse a support ticket and return analysis dict.

    Parameters
    ----------
    ticket : dict
        Must have keys: id, title, description, category, priority

    Returns
    -------
    dict with ticket_id, category, priority, keywords, query
    """
    text = (
        ticket.get("title", "") + " " + ticket.get("description", "")
    ).lower()

    keywords = [kw for kw in BANKING_KEYWORDS if kw in text]

    return {
        "ticket_id": ticket.get("id"),
        "category":  ticket.get("category"),
        "priority":  ticket.get("priority"),
        "keywords":  keywords,
        "query":     text.strip(),
    }
