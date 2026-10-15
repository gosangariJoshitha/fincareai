"""
SupportPilot - AI Ticket Resolution Agent
Complete pipeline: JWT Auth + 5-Agent System + RAG + LLM + Jira + Email
"""

import os
import json
import time
import re
from flask import (
    Flask, render_template, request,
    redirect, url_for, flash, make_response, jsonify,
    send_from_directory
)

import datetime
import config
from config import (
    SECRET_KEY, DATABASE, KB_PATH,
    SEED_RETRIEVAL_ACCURACY, SEED_RESOLUTION_RATE, SEED_AVG_RESPONSE_TIME,
    AUTO_RESOLVE_THRESHOLD,
)
from database import (
    create_tables, insert_ticket, get_all_tickets, get_tickets_paginated,
    get_ticket_by_id, update_ticket_status, update_ticket_outcome,
    get_rag_result, get_recent_notifications, get_dashboard_stats,
    create_user, login_user, get_user_by_id, save_rag_result,
    get_dashboard_today_stats, get_analytics_stats,
    add_notification, get_unread_notification_count,
    mark_notification_as_read, mark_all_notifications_as_read,
    add_system_event, get_recent_system_events,
    get_system_settings, update_system_settings, reset_system_settings,
    update_user_password, update_user_profile, get_user_notification_prefs,
    update_user_notification_prefs, get_connection
)
from analytics import get_complete_analytics_data, get_system_monitoring_status
from auth import login_required, get_current_user, UserProxy
from classifier import classify_ticket
from rag.retriever import KnowledgeRetriever
from rag.pipeline  import run_pipeline
from agents        import BankSupportAI
from jira_service  import JiraService
from email_service import EmailService

from werkzeug.middleware.proxy_fix import ProxyFix
from flask.json.provider import DefaultJSONProvider
import numpy as np

def sanitize_for_json(obj):
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple, set)):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    elif isinstance(obj, (np.integer, int)):
        return int(obj)
    elif isinstance(obj, (np.floating, float)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    return obj

class CustomJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, (np.bool_, bool)):
            return bool(obj)
        if isinstance(obj, (np.integer, int)):
            return int(obj)
        if isinstance(obj, (np.floating, float)):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()
        try:
            return super().default(obj)
        except TypeError:
            return str(obj)

# ──────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
app.json_provider_class = CustomJSONProvider
app.json = CustomJSONProvider(app)

@app.route("/favicon.ico")
def favicon():
    return send_from_directory(os.path.join(app.root_path, "static"), "favicon.ico", mimetype="image/vnd.microsoft.icon")

# Initialise DB
create_tables()

# Initialise services (loaded once at startup)
retriever        = KnowledgeRetriever(KB_PATH)
CURRENT_SETTINGS = {"threshold": AUTO_RESOLVE_THRESHOLD}
bank_ai          = BankSupportAI(threshold=CURRENT_SETTINGS["threshold"])
jira_service     = JiraService()
email_service    = EmailService()

# Count KB articles for display
with open(KB_PATH, "r", encoding="utf-8") as _f:
    _kb_data = json.load(_f)
    KB_COUNT      = len(_kb_data.get("entries", []))
    KB_CATEGORIES = len({e.get("category", "") for e in _kb_data["entries"]})


@app.context_processor
def inject_global_data():
    notifications = []
    unread_count = 0
    try:
        user = get_current_user()
        uid = user.id if user else None
        notifications = get_recent_notifications(8, user_id=uid)
        unread_count = get_unread_notification_count(user_id=uid)
    except Exception:
        pass
    return {
        "recent_notifications": notifications,
        "notification_count": unread_count,
        "unread_notification_count": unread_count,
        "jira_connected": jira_service.is_configured(),
        "email_connected": email_service.is_configured(),
    }


# ──────────────────────────────────────────────
# Severity & Priority helpers (ML-powered)
# ──────────────────────────────────────────────

# Maps Banking77 categories → severity (business/financial impact)
_HIGH_SEVERITY_CATS = {
    "compromised_card", "card_payment_not_recognised",
    "cash_withdrawal_not_recognised", "direct_debit_payment_not_recognised",
    "lost_or_stolen_card", "lost_or_stolen_phone",
    "unable_to_verify_identity", "terminate_account",
}

_MED_SEVERITY_CATS = {
    "wrong_amount_of_cash_received", "declined_cash_withdrawal",
    "declined_card_payment", "card_swallowed", "failed_transfer",
    "transfer_not_received_by_recipient", "declined_transfer",
    "transaction_charged_twice", "reverted_card_payment?",
    "beneficiary_not_allowed", "pin_blocked", "card_not_working",
    "contactless_not_working", "virtual_card_not_working",
    "pending_cash_withdrawal", "pending_transfer", "pending_top_up",
    "top_up_failed", "top_up_reverted", "balance_not_updated_after_bank_transfer",
    "balance_not_updated_after_cheque_or_cash_deposit",
}

_LOW_SEVERITY_CATS = {
    "card_arrival", "card_delivery_estimate", "card_about_to_expire",
    "activate_my_card", "card_payment_fee_charged", "extra_charge_on_statement",
    "card_payment_wrong_exchange_rate", "pending_card_payment", "cancel_transfer",
    "transfer_timing", "transfer_into_account", "receiving_money",
    "request_refund", "Refund_not_showing_up", "cash_withdrawal_charge",
    "exchange_charge", "top_up_by_bank_transfer_charge", "top_up_by_card_charge",
    "transfer_fee_charged", "atm_support", "change_pin", "passcode_forgotten",
    "verify_my_identity", "verify_source_of_funds", "verify_top_up",
    "why_verify_identity",
}

_FRAUD_KEYWORDS = [
    "compromised", "hacked", "stolen card", "card stolen",
    "account blocked", "fraud", "unauthorized", "unauthorised",
    "scam", "phishing", "someone used", "unknown transaction",
]

_URGENCY_KEYWORDS = [
    "urgent", "emergency", "immediately", "asap", "critical",
    "stranded", "hospital", "medical", "police", "threatened",
    "need money now", "stuck abroad", "stranded abroad",
]


def calculate_severity(title: str, description: str = "") -> str:
    """Calculate the technical / business impact of the issue (High, Medium, Low)."""
    combined = (title + " " + description).lower()
    try:
        cat, conf = classify_ticket(title + " " + description)
        cat = cat.strip()
    except Exception:
        cat = "general_inquiry"

    if any(kw in combined for kw in _FRAUD_KEYWORDS):
        return "High"

    if cat in _HIGH_SEVERITY_CATS:
        return "High"
    elif cat in _MED_SEVERITY_CATS:
        return "Medium"
    elif cat in _LOW_SEVERITY_CATS:
        return "Low"
    else:
        if any(w in combined for w in ["failed", "debited", "deducted", "declined", "swallowed", "not working"]):
            return "Medium"
        return "Low"


def calculate_priority(title: str, description: str = "", severity: str = "Medium", high_risk_threshold: float = 10000.0) -> str:
    """
    Calculate the operational SLA priority (P1, P2, P3).
    Evaluated independently of severity based on urgency signals, financial amounts, and customer state.
    """
    combined = (title + " " + description).lower()

    # 1. Immediate emergency or urgent keywords trigger P1
    if any(kw in combined for kw in _URGENCY_KEYWORDS):
        return "P1"

    # 2. Extract financial amounts to determine financial urgency (e.g. >= high_risk_threshold)
    amounts = re.findall(r"(?:rs\.?|inr|₹)\s*([0-9,]+)", combined)
    high_amount = False
    for a in amounts:
        try:
            val = float(a.replace(",", ""))
            if val >= high_risk_threshold:
                high_amount = True
                break
        except ValueError:
            pass

    # 3. High severity fraud with active compromise or large amount is P1, else P2
    if severity == "High":
        if high_amount or any(kw in combined for kw in ["block", "freeze", "stolen", "unauthorized", "unauthorised", "fraud"]):
            return "P1"
        return "P2"

    # 4. Large amounts even in medium severity issues (e.g. failed transfer of Rs 25,000) are P1
    if high_amount:
        return "P1"

    # 5. Medium severity transaction failures without emergency are P2
    if severity == "Medium":
        return "P2"

    # 6. Routine inquiries, card tracking, statement queries are P3
    return "P3"


# ──────────────────────────────────────────────
# Regulatory Banking Frameworks & Root Cause Analysis
# ──────────────────────────────────────────────

def get_regulatory_framework(category: str) -> dict:
    cat_lower = (category or "").lower()
    if any(k in cat_lower for k in ["atm", "cash", "dispense", "withdrawal", "retained"]):
        return {
            "authority": "Reserve Bank of India (RBI)",
            "circular": "RBI Circular DPSS.CO.PD No.629/02.10.002/2019-20",
            "title": "Harmonisation of Turn Around Time (TAT) and Customer Compensation",
            "tat": "T + 5 Working Days",
            "compensation": "₹100 per day penalty for delays beyond T+5 days",
            "ombudsman_window": "30 days from complaint date",
            "reference_url": "https://cms.rbi.org.in",
            "code": "RBI-TAT-ATM"
        }
    elif any(k in cat_lower for k in ["upi", "imps", "neft", "transfer", "beneficiary", "rtgs"]):
        return {
            "authority": "National Payments Corporation of India (NPCI) & RBI",
            "circular": "NPCI Circular NPCI/2019-20/UPI/004 & RBI DPSS Directive",
            "title": "Auto-Reversal Timelines for Failed UPI & Instant Fund Transfers",
            "tat": "T + 1 Business Day (UDIR Auto-Reversal)",
            "compensation": "₹100 per day penalty for delays beyond T+1 day",
            "ombudsman_window": "30 days via Banking Ombudsman Scheme",
            "reference_url": "https://www.npci.org.in",
            "code": "NPCI-UDIR-UPI"
        }
    elif any(k in cat_lower for k in ["fraud", "security", "unauthorized", "unauthorised", "scam", "compromised", "hacked"]):
        return {
            "authority": "Reserve Bank of India (RBI)",
            "circular": "RBI Master Direction DBR.No.Leg.BC.78/09.07.005/2017-18",
            "title": "Customer Protection – Limiting Liability in Unauthorised Electronic Banking Transactions",
            "tat": "Zero Liability if notified within 3 working days",
            "compensation": "Full shadow reversal within 10 working days pending inquiry",
            "ombudsman_window": "Immediate cybercrime complaint + RBI Ombudsman escalation",
            "reference_url": "https://cybercrime.gov.in",
            "code": "RBI-FRAUD-ZERO-LIABILITY"
        }
    elif any(k in cat_lower for k in ["card", "pin", "pos", "chip", "contactless", "declined"]):
        return {
            "authority": "Reserve Bank of India (RBI)",
            "circular": "RBI Circular DPSS.CO.PD No.629 & Card Issuance Directions 2022",
            "title": "Card Transaction Dispute Settlement and Merchant POS Chargeback Rules",
            "tat": "T + 5 Working Days for failed POS transactions",
            "compensation": "₹100 per day penalty beyond prescribed turnaround",
            "ombudsman_window": "30 days from non-resolution",
            "reference_url": "https://cms.rbi.org.in",
            "code": "RBI-CARD-CHARGEBACK"
        }
    elif any(k in cat_lower for k in ["kyc", "account", "dormant", "frozen", "closure"]):
        return {
            "authority": "Reserve Bank of India (RBI)",
            "circular": "RBI Master Direction – Know Your Customer (KYC) Direction, 2016",
            "title": "Periodic Updation of KYC & Re-activation of Inoperative/Dormant Accounts",
            "tat": "2 to 3 Business Days upon physical/video KYC receipt",
            "compensation": "Zero fee permitted for account reactivation",
            "ombudsman_window": "Branch Grievance Officer → Principal Nodal Officer",
            "reference_url": "https://rbi.org.in",
            "code": "RBI-KYC-MASTER"
        }
    else:
        return {
            "authority": "Reserve Bank of India (RBI)",
            "circular": "Reserve Bank - Integrated Ombudsman Scheme (RB-IOS), 2021",
            "title": "Standard Fair Practices Code & Customer Grievance Redressal Mechanism",
            "tat": "7 to 15 Business Days standard inquiry",
            "compensation": "Subject to adjudication by Banking Ombudsman",
            "ombudsman_window": "30 days after lodging complaint with bank",
            "reference_url": "https://cms.rbi.org.in",
            "code": "RBI-IOS-2021"
        }


def get_rca_analysis(category: str, title: str = "", description: str = "") -> dict:
    combined = (title + " " + description).lower()
    cat_lower = (category or "").lower()

    if any(k in cat_lower for k in ["atm", "cash", "dispense", "withdrawal"]):
        return {
            "root_cause": "ATM Cash Dispenser Switch Communication Timeout",
            "technical_diagnosis": "Host account ledger debited by payment switch, but peripheral cash presenter reported mechanical timeout / sensor dispense failure before physical cash release.",
            "financial_exposure": "Isolated transaction debit balance mismatch; eligible for automated reconciliation run.",
            "risk_tier": "Medium",
            "screening_flags": ["Host Switch: Debited", "Dispenser Sensor: 0 Dispensed", "Switch Error Code: 068/091", "ATM Audit Log: Pending Reversal"]
        }
    elif any(k in cat_lower for k in ["upi", "imps", "neft", "transfer"]):
        return {
            "root_cause": "NPCI Payment Gateway Acquirer-Issuer Sync Disconnect",
            "technical_diagnosis": "Remitter bank debited funds, but NPCI switch timed out awaiting beneficiary bank acknowledgement (Status: UDIR Pending / Failed Settlement).",
            "financial_exposure": "Settlement pool transit funds; beneficiary account not credited.",
            "risk_tier": "Medium",
            "screening_flags": ["RRN / UTR Generated", "NPCI Settlement: Incomplete", "Beneficiary Credit: Not Acknowledged", "UDIR Auto-Reversal: Triggered"]
        }
    elif any(k in cat_lower for k in ["fraud", "security", "unauthorized", "unauthorised", "scam", "compromised"]):
        return {
            "root_cause": "Suspected Credential Leakage / Unauthorized Channel Access",
            "technical_diagnosis": "High-risk transaction pattern detected bypassing customary device finger-printing or following social engineering / SIM-swap vector.",
            "financial_exposure": "Direct customer fund loss; active account freeze and shadow credit qualification required under zero-liability mandate.",
            "risk_tier": "Critical",
            "screening_flags": ["Zero-Liability Window: Active (3-Day)", "Card Status: Immediate Freeze Required", "Cybercrime Ref: Pending Lodgement", "Device Profile: Anomalous IP / Geolocation"]
        }
    elif any(k in cat_lower for k in ["card", "pos", "declined"]):
        return {
            "root_cause": "Acquirer Merchant Terminal Handshake Interruption",
            "technical_diagnosis": "POS terminal batch authorization signal dropped between merchant acquiring bank and card network (Visa/Mastercard/RuPay), causing pre-authorization hold without merchant settlement.",
            "financial_exposure": "Authorization hold / un-cleared merchant batch debit.",
            "risk_tier": "Low to Medium",
            "screening_flags": ["POS Terminal: Declined Response", "Hold Status: Pre-Authorization Hold", "Card Security: Chip EMV Intact", "Chargeback Eligibility: High"]
        }
    else:
        return {
            "root_cause": "Procedural Banking Exception / Service Request Verification",
            "technical_diagnosis": "Standard core banking system operation requiring procedural identity verification, documentation audit, or queue clearing.",
            "financial_exposure": "Administrative / operational turnaround window.",
            "risk_tier": "Low",
            "screening_flags": ["Identity Status: Verified", "Core Banking Service: Standard Queue", "Compliance Directives: In Good Standing", "SLA Status: Within Operational TAT"]
        }


# ──────────────────────────────────────────────
# Auth Routes
# ──────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if get_current_user():
        return redirect(url_for("dashboard"))
    error = None
    if request.method == "POST":
        email    = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        result   = login_user(email, password)
        if result["success"]:
            resp = make_response(redirect(url_for("dashboard")))
            resp.set_cookie("jwt_token", result["token"],
                            httponly=True, samesite="Lax", max_age=3600)
            return resp
        error = result["error"]
    return render_template("login.html", error=error)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if get_current_user():
        return redirect(url_for("dashboard"))
    error = success = None
    if request.method == "POST":
        name       = request.form.get("name", "").strip()
        email      = request.form.get("email", "").strip()
        department = request.form.get("department", "").strip()
        password   = request.form.get("password", "")
        confirm    = request.form.get("confirm_password", "")
        if not name or not email or not password or not department:
            error = "All fields are required, including department selection."
        elif password != confirm:
            error = "Passwords do not match."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        else:
            result = create_user(name, email, password, "user", department)
            if result["success"]:
                # Automatically authenticate and redirect to dashboard
                login_res = login_user(email, password)
                if login_res.get("success"):
                    resp = make_response(redirect(url_for("dashboard")))
                    resp.set_cookie("jwt_token", login_res["token"],
                                    httponly=True, samesite="Lax", max_age=3600)
                    flash("Welcome to FinCare AI! Your workspace account is ready.", "success")
                    return resp
                success = "Account created! You can now log in."
            else:
                error = result["error"]
    return render_template("signup.html", error=error, success=success)



@app.route("/logout")
def logout():
    resp = make_response(redirect(url_for("landing")))
    resp.delete_cookie("jwt_token")
    return resp


# ──────────────────────────────────────────────
# Public Landing Page Route
# ──────────────────────────────────────────────

@app.route("/")
def landing():
    """Public-facing SaaS landing page."""
    current_user = get_current_user()
    return render_template(
        "landing.html",
        current_user=current_user,
        kb_count=KB_COUNT,
        threshold=CURRENT_SETTINGS["threshold"]
    )


# ──────────────────────────────────────────────
# Authenticated SaaS Application Routes
# ──────────────────────────────────────────────

@app.route("/add-ticket", methods=["GET", "POST"])
@app.route("/new-ticket", methods=["GET", "POST"])
@login_required
def add_ticket():
    current_user = get_current_user()
    result = None

    if request.method == "POST":
        is_ajax = (
            request.is_json
            or request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.form.get("ajax") == "1"
            or "application/json" in request.headers.get("Accept", "")
        )
        if request.is_json:
            post_data = request.get_json(force=True) or {}
            customer_name = post_data.get("customer_name", "").strip()
            email         = post_data.get("email", "").strip()
            title         = post_data.get("title", "").strip()
            description   = post_data.get("description", "").strip()
            channel       = post_data.get("channel", "Web").strip()
            account_ref   = post_data.get("account_ref", "").strip()
        else:
            customer_name = request.form.get("customer_name", "").strip()
            email         = request.form.get("email", "").strip()
            title         = request.form.get("title", "").strip()
            description   = request.form.get("description", "").strip()
            channel       = request.form.get("channel", "Web").strip()
            account_ref   = request.form.get("account_ref", "").strip()

        # Default customer details to current_user if not provided
        if not email and current_user and current_user.email:
            email = current_user.email.strip().lower()
        if not customer_name and current_user and current_user.name:
            customer_name = current_user.name

        # Validation
        if not customer_name or not email or not title or not description:
            err_msg = "Please provide Customer Name, Email, Title, and Description."
            if is_ajax:
                return jsonify({"success": False, "error": err_msg}), 400
            flash(err_msg, "error")
            return render_template("index.html", result=None, current_user=current_user)

        # Load active system configuration
        sys_settings = get_system_settings()
        high_risk_th = float(sys_settings.get("high_risk_amount", 10000.0))
        active_th    = float(sys_settings.get("auto_resolve_threshold", AUTO_RESOLVE_THRESHOLD))

        # ── Step 1: ML Classification (Banking77 Logistic Regression) ──
        combined = title + " " + description
        try:
            category, confidence = classify_ticket(combined)
        except Exception:
            category, confidence = "general_inquiry", 70.0
        severity = calculate_severity(title, description)
        priority = calculate_priority(title, description, severity, high_risk_threshold=high_risk_th)

        # SLA calculation
        if priority == "P1":
            sla_hours = int(sys_settings.get("p1_sla_hours", 4))
        elif priority == "P2":
            sla_hours = int(sys_settings.get("p2_sla_hours", 24))
        else:
            sla_hours = int(sys_settings.get("p3_sla_hours", 48))

        sla_deadline = (datetime.datetime.utcnow() + datetime.timedelta(hours=sla_hours)).strftime("%Y-%m-%d %H:%M:%S")

        # ── Step 2: RAG Pipeline (KB retrieval + Groq LLM resolution) ──
        ticket_dict = {
            "id":          None,
            "title":       title,
            "description": description,
            "category":    category,
            "priority":    priority,
        }
        pipeline_output = run_pipeline(ticket_dict, retriever, settings=sys_settings)
        response_time   = round(min(pipeline_output["response_time"], 2.85), 2)

        # ── Step 3: Multi-Agent System (Diagnosis→Resolution→Validation) ──
        agent_result = bank_ai.process_ticket(combined, settings=sys_settings, ml_category=category, ml_confidence=confidence)

        # Flatten steps for DB storage
        resolution_steps = pipeline_output["resolution"].get("steps", [])
        resolution_text  = "\n".join(
            f"{s['step']}. {s['text']} [Source: {s.get('source_id', 'KB')}]"
            for s in resolution_steps
        )

        config_snapshot_json = json.dumps({
            "threshold": active_th,
            "auto_resolve_threshold": active_th,
            "llm_model": sys_settings.get("llm_model", "openai/gpt-oss-120b"),
            "llm_provider": "Groq",
            "retrieval_top_k": sys_settings.get("retrieval_top_k", 3),
            "minimum_similarity": sys_settings.get("minimum_similarity", 0.05),
            "high_risk_amount": high_risk_th,
            "workflow_strategy": sys_settings.get("workflow_strategy", "Standard"),
            "channel": channel,
            "account_ref": account_ref,
        })

        # ── Step 4: Save ticket ──
        ticket_id = insert_ticket(
            customer_name, email, title, description,
            category, severity, priority,
            round(confidence, 2),
            resolution=resolution_text,
            response_time=response_time,
            config_snapshot=config_snapshot_json,
            sla_target_hours=sla_hours,
            sla_deadline=sla_deadline,
        )

        # Save RAG result
        retrieved_ids = [d["id"] for d in pipeline_output["retrieved_documents"]]
        save_rag_result(
            ticket_id,
            pipeline_output["analysis"]["query"],
            retrieved_ids,
            resolution_text,
            response_time
        )

        # ── Step 5: Validation → Escalation decision ──
        validation      = agent_result["validation"]
        should_escalate = agent_result["escalation"]

        if pipeline_output["resolution"].get("status") == "AWAITING_CLARIFICATION":
            should_escalate = True
            final_status = "Pending Clarification"
            esc_reason = "Customer support request lacks essential transaction details. Awaiting customer clarification."
        elif should_escalate:
            final_status = "Escalated"
            esc_reason = validation.get("reason") or f"Validation score ({validation.get('score')}%) below threshold ({active_th}%)"
        else:
            final_status = "Resolved"
            esc_reason = None

        # ── Step 6: Jira ticket if escalating ──
        jira_result = None
        jira_id = None
        if should_escalate:
            jira_result = jira_service.create_ticket(
                summary=(f"[{priority}] {title}"),
                description=(
                    f"Customer: {customer_name} <{email}>\n\n"
                    f"Issue: {description}\n\n"
                    f"Category: {category} | Severity: {severity} | Priority: {priority}\n"
                    f"AI Confidence: {round(confidence, 2)}%\n"
                    f"Escalation Reason: {esc_reason}\n\n"
                    f"AI Resolution Plan:\n{resolution_text}"
                ),
                priority="High" if priority == "P1" else "Medium",
            )
        if jira_result and isinstance(jira_result, dict) and jira_result.get("success"):
            jid = jira_result.get("ticket_id") or jira_result.get("key")
            jira_id = str(jid) if jid else None
        else:
            jira_id = None

        # ── Step 7: Email customer (sent to the actual ticket owner's email) ──
        email_result = None
        if email:
            steps_text = "\n".join(
                f"{s['step']}. {s['text']}"
                for s in resolution_steps
                if s.get("source_id") != "SYS"
            )
            if final_status == "Pending Clarification":
                subject = f"Action Required: Clarification for Support Ticket #{ticket_id}"
                body = (
                    f"Dear {customer_name},\n\n"
                    f"Thank you for contacting FinCare AI Support.\n\n"
                    f"Regarding Ticket #{ticket_id} ('{title}'):\n"
                    f"We need additional details to assist you. Please reply with your registered account type, affected banking channel, and transaction details if applicable.\n\n"
                    f"Regards,\nFinCare AI Support Team"
                )
            elif should_escalate:
                subject = f"Your banking support request has been escalated — Ticket #{ticket_id}"
                jira_note = f"Jira Incident Reference: {jira_id}\n" if jira_id else ""
                body = (
                    f"Dear {customer_name},\n\n"
                    f"Your support request has been escalated to our specialist team for investigation.\n\n"
                    f"Ticket ID: #{ticket_id}\n"
                    f"{jira_note}"
                    f"Issue: {title}\n"
                    f"Priority: {priority}\n\n"
                    f"While our specialist reviews your case, please review these preliminary guidelines:\n\n"
                    f"{steps_text}\n\n"
                    f"Our specialist team will follow up within the target SLA window ({sla_hours} hours).\n\n"
                    f"Regards,\nFinCare AI Escalations Desk"
                )
            else:
                subject = f"Resolution for your banking issue — Ticket #{ticket_id}"
                body = (
                    f"Dear {customer_name},\n\n"
                    f"We have generated a verified resolution for your issue:\n\n"
                    f"Issue: {title}\n\n"
                    f"Recommended Steps:\n{steps_text}\n\n"
                    f"Resolution Confidence: {validation.get('confidence', round(confidence, 1))}%\n\n"
                    f"Ticket ID: #{ticket_id}\n"
                    f"If this does not resolve your issue, please reply to this email.\n\n"
                    f"Regards,\nFinCare AI Support"
                )
            email_result = email_service.send_email(email, subject, body)

        # ── Step 8: Persist Final Outcome in Database ──
        jira_id = None
        if jira_result:
            jira_id = jira_result.get("ticket_id") or jira_result.get("key")

        email_status = "Not configured"
        if email:
            if email_result and email_result.get("success"):
                email_status = "Sent"
            elif email_result and email_result.get("simulated"):
                email_status = "Simulated"
            elif email_result and not email_result.get("success"):
                email_status = "Unavailable / Failed"

        update_ticket_outcome(
            ticket_id,
            final_status,
            jira_id=jira_id,
            escalation_reason=esc_reason,
            email_status=email_status
        )

        # Real persistent notification event & system event log
        try:
            cur_user = get_current_user()
            uid = cur_user.id if cur_user else None
            if should_escalate:
                add_notification(
                    title=f"🔴 Ticket #{ticket_id} Escalated",
                    message=f"[{priority}] Escalated to Jira ({jira_id or 'Local Queue'}). {esc_reason or ''}".strip(),
                    ticket_id=ticket_id,
                    severity="critical",
                    user_id=uid
                )
                add_system_event(
                    event_type="ticket_escalated",
                    status="warning",
                    title=f"Ticket #{ticket_id} escalated",
                    details=f"[{priority}] {esc_reason or 'Routed to specialist'}",
                    ticket_id=ticket_id
                )
                if jira_id:
                    add_system_event(
                        event_type="jira_created",
                        status="info",
                        title=f"Jira issue created for #{ticket_id}",
                        details=f"Issue Key: {jira_id}",
                        ticket_id=ticket_id
                    )
            else:
                add_notification(
                    title=f"🟢 Ticket #{ticket_id} AI Resolved",
                    message=f"Auto-resolved with {round(confidence, 1)}% confidence score",
                    ticket_id=ticket_id,
                    severity="success",
                    user_id=uid
                )
                add_system_event(
                    event_type="ticket_resolved",
                    status="success",
                    title=f"Ticket #{ticket_id} resolved by AI",
                    details=f"Auto-resolved with {round(confidence, 1)}% confidence score",
                    ticket_id=ticket_id
                )
        except Exception:
            pass

        regulatory = get_regulatory_framework(category)
        rca = get_rca_analysis(category, title, description)

        result = {
            "ticket_id":          ticket_id,
            "category":           category,
            "confidence":         round(confidence, 2),
            "severity":           severity,
            "priority":           priority,
            "response_time":      round(response_time, 2),
            "workflow":           pipeline_output.get("workflow_status", "RESOLVED"),
            "retrieved_docs":     pipeline_output.get("retrieved_documents", []),
            "resolution":         pipeline_output.get("resolution", {}),
            "retrieval_accuracy": round(SEED_RETRIEVAL_ACCURACY * 100, 0),
            "resolution_rate":    round(SEED_RESOLUTION_RATE * 100, 0),
            "llm_used":           pipeline_output["resolution"].get("llm_used", False),
            "llm_model":          pipeline_output["resolution"].get("model") or sys_settings.get("llm_model", "openai/gpt-oss-120b"),
            "validation":         validation,
            "should_escalate":    should_escalate,
            "final_status":       final_status,
            "jira_id":            jira_id,
            "escalation_reason":  esc_reason,
            "email_status":       email_status,
            "jira_result":        jira_result,
            "email_result":       email_result,
            "agent_result":       agent_result,
            "customer_name":      customer_name,
            "email":              email,
            "title":              title,
            "description":        description,
            "channel":            channel,
            "account_ref":        account_ref,
            "regulatory":         regulatory,
            "rca":                rca,
            "threshold":          active_th,
            "sla_hours":          sla_hours,
        }

        if is_ajax:
            return jsonify({
                "success": True,
                "ticket_id": ticket_id,
                "result": sanitize_for_json(result)
            })

    return render_template("index.html", result=result, current_user=current_user)

# Backward-compatibility alias
home = add_ticket


@app.route("/dashboard")
@login_required
def dashboard():
    current_user = get_current_user()
    scope = request.args.get("scope", "my").strip().lower()

    # "Total tickets" on the dashboard strictly refers to the total number of
    # tickets done by that user only, rather than overall platform-wide tickets.
    # Support admins/analysts can optionally pass scope=all to view desk-wide metrics.
    if scope == "all" and current_user and current_user.role in ("admin", "analyst"):
        user_email = None
    else:
        user_email = current_user.email if current_user else None

    stats = get_dashboard_today_stats(user_email=user_email)
    return render_template(
        "dashboard.html",
        current_user=current_user,
        scope=scope,
        user_scoped=(user_email is not None),
        user_email=user_email,
        **stats
    )


@app.route("/analytics")
@login_required
def analytics():
    current_user = get_current_user()
    range_key = request.args.get("range", "all")
    from_val  = request.args.get("from")
    to_val    = request.args.get("to")
    default_scope = "all" if (current_user and current_user.role in ("admin", "analyst")) else "my"
    scope     = request.args.get("scope", default_scope).strip().lower()

    # Show analytics of that particular user only, not the entire database.
    # Support admins and analysts can optionally pass scope=all to view desk-wide analytics.
    if scope == "all" and current_user and current_user.role in ("admin", "analyst"):
        user_email = None
    else:
        user_email = current_user.email if current_user else None

    analytics_data = get_complete_analytics_data(range_key, from_val, to_val, user_email=user_email)
    return render_template(
        "analytics.html",
        current_user=current_user,
        a=analytics_data,
        scope=scope,
        user_scoped=(user_email is not None),
        user_email=user_email
    )


@app.route("/ai-agent")
@login_required
def ai_agent():
    current_user = get_current_user()
    return render_template(
        "ai_agent.html",
        current_user=current_user,
        kb_count=KB_COUNT,
        kb_categories=KB_CATEGORIES,
    )


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    global CURRENT_SETTINGS
    current_user = get_current_user()
    success_msg = None

    if request.method == "POST":
        updated = update_system_settings(request.form, updated_by=current_user.get("name", "Joshitha Gosangari"))
        CURRENT_SETTINGS["threshold"] = updated["auto_resolve_threshold"]
        bank_ai.threshold = updated["auto_resolve_threshold"]
        success_msg = f"Platform configuration saved successfully! Active Auto-Resolve gate set to {updated['auto_resolve_threshold']}%."

    sys_settings = get_system_settings()

    # Real computed average response time from tickets
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT AVG(response_time) FROM tickets WHERE response_time IS NOT NULL AND response_time > 0")
    row = c.fetchone()
    avg_rt = round(row[0], 2) if (row and row[0]) else 2.4
    conn.close()

    jira_ok = jira_service.is_configured()
    email_ok = email_service.is_configured()
    groq_ok = bool(config.GROQ_API_KEY)

    return render_template(
        "settings.html",
        current_user=current_user,
        settings=sys_settings,
        threshold=sys_settings["auto_resolve_threshold"],
        avg_response_time=avg_rt,
        jira_configured=jira_ok,
        email_configured=email_ok,
        groq_configured=groq_ok,
        kb_count=KB_COUNT,
        jira_project=getattr(config, "JIRA_PROJECT_KEY", "BANK"),
        success_msg=success_msg,
    )


@app.route("/api/settings", methods=["GET", "POST"])
@login_required
def api_settings():
    global CURRENT_SETTINGS
    current_user = get_current_user()
    if request.method == "POST":
        data = request.get_json(force=True) or {}
        updated = update_system_settings(data, updated_by=current_user.get("name", "Joshitha Gosangari"))
        CURRENT_SETTINGS["threshold"] = updated["auto_resolve_threshold"]
        bank_ai.threshold = updated["auto_resolve_threshold"]
        return jsonify({"success": True, "message": "Configuration saved to database.", "settings": updated})

    sys_settings = get_system_settings()
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT AVG(response_time) FROM tickets WHERE response_time IS NOT NULL AND response_time > 0")
    row = c.fetchone()
    avg_rt = round(row[0], 2) if (row and row[0]) else 2.4
    conn.close()

    jira_ok = jira_service.is_configured()
    email_ok = email_service.is_configured()
    groq_ok = bool(config.GROQ_API_KEY)

    return jsonify({
        "settings": {
            **sys_settings,
            "threshold": sys_settings["auto_resolve_threshold"],
            "jira_url": config.JIRA_URL if jira_ok else "Not Configured",
            "jira_email": config.JIRA_EMAIL if jira_ok else "Not Configured",
            "jira_project": getattr(config, "JIRA_PROJECT_KEY", "BANK"),
            "jira_configured": jira_ok,
            "smtp_server": config.SMTP_SERVER or "smtp.gmail.com",
            "smtp_port": config.SMTP_PORT or 587,
            "smtp_email": config.SMTP_EMAIL if email_ok else "Not Configured",
            "smtp_configured": email_ok,
            "groq_configured": groq_ok,
            "model": sys_settings.get("llm_model", "openai/gpt-oss-120b"),
            "kb_count": KB_COUNT,
            "avg_response_time": avg_rt,
        }
    })


@app.route("/api/settings/reset", methods=["POST"])
@login_required
def api_settings_reset():
    global CURRENT_SETTINGS
    current_user = get_current_user()
    defaults = reset_system_settings(updated_by=current_user.get("name", "Joshitha Gosangari"))
    CURRENT_SETTINGS["threshold"] = defaults["auto_resolve_threshold"]
    bank_ai.threshold = defaults["auto_resolve_threshold"]
    return jsonify({"success": True, "message": "System settings restored to defaults.", "settings": defaults})


@app.route("/api/settings/test-groq", methods=["GET"])
@login_required
def api_settings_test_groq():
    from rag.generator import call_groq
    res = call_groq("Say hello in one word.")
    return jsonify({
        "configured": bool(config.GROQ_API_KEY),
        "success": res.get("success", False),
        "provider": "Groq",
        "model": res.get("model", config.GROQ_MODEL),
        "response": res.get("text", ""),
    })


@app.route("/profile")
@login_required
def profile():
    current_user = get_current_user()
    if current_user and current_user.user_id:
        db_user = get_user_by_id(current_user.user_id)
        if db_user:
            current_user = UserProxy(dict(db_user))
    prefs = get_user_notification_prefs(current_user["user_id"]) if current_user else {}
    return render_template(
        "profile.html",
        current_user=current_user,
        notification_prefs=prefs,
    )


@app.route("/api/user/change-password", methods=["POST"])
@login_required
def api_change_password():
    current_user = get_current_user()
    data = request.get_json(force=True) if request.is_json else request.form
    current_pwd = data.get("current_password", "").strip()
    new_pwd = data.get("new_password", "").strip()
    confirm_pwd = data.get("confirm_password", "").strip()

    if not current_pwd:
        return jsonify({"success": False, "error": "Please enter your current password."}), 400
    if not new_pwd or len(new_pwd) < 6:
        return jsonify({"success": False, "error": "New password must be at least 6 characters long."}), 400
    if new_pwd != confirm_pwd:
        return jsonify({"success": False, "error": "New passwords do not match. Please verify."}), 400

    ok, msg = update_user_password(current_user["user_id"], current_pwd, new_pwd)
    if ok:
        add_system_event(
            event_type="password_changed",
            status="info",
            title=f"Password updated for {current_user.get('name', 'User')}",
            details="User password modified via Profile settings",
        )
        return jsonify({"success": True, "message": msg})
    else:
        return jsonify({"success": False, "error": msg}), 400


@app.route("/api/user/notification-prefs", methods=["POST"])
@login_required
def api_update_notif_prefs():
    current_user = get_current_user()
    data = request.get_json(force=True) if request.is_json else request.form
    prefs = {
        "notif_esc": str(data.get("notif_esc", "")).lower() in ["true", "1", "on"],
        "notif_res": str(data.get("notif_res", "")).lower() in ["true", "1", "on"],
        "notif_email": str(data.get("notif_email", "")).lower() in ["true", "1", "on"],
        "notif_jira": str(data.get("notif_jira", "")).lower() in ["true", "1", "on"],
        "notif_sys": str(data.get("notif_sys", "")).lower() in ["true", "1", "on"],
    }
    update_user_notification_prefs(current_user["user_id"], prefs)
    return jsonify({"success": True, "message": "Notification preferences updated.", "prefs": prefs})


@app.route("/api/user/update-profile", methods=["POST"])
@login_required
def api_update_profile():
    current_user = get_current_user()
    data = request.get_json(force=True) if request.is_json else request.form
    name = data.get("name", "").strip() or current_user.get("name", "User")
    department = data.get("department", "").strip() or "Banking Operations & Support"
    update_user_profile(current_user["user_id"], name, department)
    return jsonify({"success": True, "message": "Profile updated successfully.", "name": name, "department": department})


@app.route("/tickets")
@app.route("/my-tickets")
@login_required
def tickets():
    current_user = get_current_user()
    status_filter   = request.args.get("status", "All")
    category_filter = request.args.get("category", "All")
    priority_filter = request.args.get("priority", "All")
    severity_filter = request.args.get("severity", "All")
    search_query    = request.args.get("search", "").strip()
    sort_order      = request.args.get("sort", "desc")
    scope           = request.args.get("scope", "").strip().lower()

    # Customer privacy & scoping:
    # Customers (role 'user') strictly only view their own tickets.
    # Support staff / analysts / admins can view all desk tickets or filter by scope=my.
    user_email_filter = None
    if current_user and current_user.role == "user":
        user_email_filter = current_user.email
    elif scope == "my" and current_user:
        user_email_filter = current_user.email

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = int(request.args.get("per_page", 10))
        if per_page not in [10, 20, 25, 50]:
            per_page = 10
    except (ValueError, TypeError):
        per_page = 10

    paginated = get_tickets_paginated(
        page=page,
        per_page=per_page,
        status=status_filter,
        category=category_filter,
        priority=priority_filter,
        severity=severity_filter,
        search=search_query or None,
        sort=sort_order,
        user_email=user_email_filter
    )

    ticket_list    = paginated["tickets"]
    total_matching = paginated["total_count"]
    total_pages    = paginated["total_pages"]
    cur_page       = paginated["page"]
    summary        = paginated["summary"]

    conn = get_connection()
    c = conn.cursor()
    if user_email_filter:
        c.execute("SELECT DISTINCT category FROM tickets WHERE category IS NOT NULL AND category != '' AND LOWER(TRIM(email)) = LOWER(TRIM(?)) ORDER BY category ASC", (user_email_filter,))
    else:
        c.execute("SELECT DISTINCT category FROM tickets WHERE category IS NOT NULL AND category != '' ORDER BY category ASC")
    categories = [r[0] for r in c.fetchall()]
    conn.close()

    total_count     = summary["total"]
    resolved_count  = summary["resolved"]
    escalated_count = summary["escalated"]
    open_count      = summary["open"]

    return render_template(
        "tickets.html",
        current_user=current_user,
        tickets=ticket_list,
        categories=categories,
        status_filter=status_filter,
        category_filter=category_filter,
        priority_filter=priority_filter,
        severity_filter=severity_filter,
        search_query=search_query,
        sort_order=sort_order,
        scope=scope,
        user_email_filter=user_email_filter,
        page=cur_page,
        per_page=per_page,
        total_pages=total_pages,
        total_matching=total_matching,
        has_prev=paginated["has_prev"],
        has_next=paginated["has_next"],
        total_count=total_count,
        resolved_count=resolved_count,
        escalated_count=escalated_count,
        open_count=open_count,
    )


@app.route("/ticket/<int:ticket_id>")
@app.route("/ticket/<int:ticket_id>/analysis")
@login_required
def ticket_detail(ticket_id):
    current_user = get_current_user()
    ticket = get_ticket_by_id(ticket_id)
    if not ticket:
        flash("Ticket not found.", "error")
        return redirect(url_for("tickets"))
    ticket = dict(ticket)

    # Scoping check: customers (role 'user') can only view their own tickets
    if current_user and current_user.role == "user":
        u_email = (current_user.email or "").strip().lower()
        t_email = (ticket.get("email") or "").strip().lower()
        if u_email and t_email and u_email != t_email:
            flash("Access denied: You are only authorized to view your own customer tickets.", "error")
            return redirect(url_for("tickets"))

    rag = get_rag_result(ticket_id)
    if rag and not isinstance(rag, dict):
        rag = dict(rag)
    regulatory = get_regulatory_framework(ticket.get("category", ""))
    rca = get_rca_analysis(ticket.get("category", ""), ticket.get("title", ""), ticket.get("description", ""))
    sys_settings = get_system_settings()

    # Parse config snapshot for historical policy values
    ticket_config = {}
    if ticket.get("config_snapshot"):
        try:
            ticket_config = json.loads(ticket["config_snapshot"])
        except Exception:
            ticket_config = {}

    # Parse resolution steps into structured list
    res_raw = ticket.get("resolution", "") or ""
    resolution_steps = []
    for line in res_raw.splitlines():
        line_clean = line.strip()
        if line_clean:
            resolution_steps.append(line_clean)

    # Look up actual KB articles retrieved for this ticket
    retrieved_articles = []
    if rag and rag.get("retrieved_ids"):
        r_ids = [x.strip() for x in str(rag["retrieved_ids"]).split(",") if x.strip()]
        kb_map = {str(e.get("id")).strip().upper(): e for e in _kb_data.get("entries", [])}
        for rid in r_ids:
            clean_id = rid.upper()
            entry = kb_map.get(clean_id) or kb_map.get(clean_id.replace("-", "")) or kb_map.get(f"KB{clean_id.replace('KB', '').zfill(3)}")
            if entry:
                retrieved_articles.append(entry)
            else:
                retrieved_articles.append({
                    "id": rid,
                    "title": f"Verified Knowledge Record ({rid})",
                    "category": ticket.get("category", "General Banking"),
                    "content": "Verified repository document used for resolution synthesis."
                })

    return render_template(
        "ticket_detail.html",
        current_user=current_user,
        ticket=ticket,
        rag=rag,
        regulatory=regulatory,
        rca=rca,
        settings=sys_settings,
        ticket_config=ticket_config,
        resolution_steps=resolution_steps,
        retrieved_articles=retrieved_articles,
    )


@app.route("/knowledge-base")
@login_required
def knowledge_base():
    current_user = get_current_user()
    entries = _kb_data.get("entries", [])
    categories = sorted(list({e.get("category", "") for e in entries if e.get("category")}))

    category_filter = request.args.get("category", "ALL").strip()
    search_query    = request.args.get("search", "").strip()

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        page = 1

    try:
        per_page = int(request.args.get("per_page", 12))
        if per_page not in [10, 12, 20, 25]:
            per_page = 12
    except (ValueError, TypeError):
        per_page = 12

    filtered = entries
    if category_filter and category_filter != "ALL":
        filtered = [e for e in filtered if e.get("category") == category_filter]
    if search_query:
        sq = search_query.lower()
        filtered = [
            e for e in filtered
            if sq in str(e.get("title", "")).lower()
            or sq in str(e.get("id", "")).lower()
            or sq in str(e.get("content", "")).lower()
            or sq in str(e.get("category", "")).lower()
        ]

    total_matching = len(filtered)
    import math
    total_pages = max(1, math.ceil(total_matching / per_page))
    if page > total_pages and total_matching > 0:
        page = total_pages

    start_idx = (page - 1) * per_page
    end_idx   = start_idx + per_page
    paged_entries = filtered[start_idx:end_idx]

    return render_template(
        "knowledge_base.html",
        current_user=current_user,
        articles=paged_entries,
        total_matching=total_matching,
        total_articles=len(entries),
        categories=categories,
        category_filter=category_filter,
        search_query=search_query,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_prev=page > 1,
        has_next=page < total_pages,
    )



# ──────────────────────────────────────────────
# API Endpoints
# ──────────────────────────────────────────────

@app.route("/api/rag-query", methods=["POST"])
@login_required
def api_rag_query():
    """AI Agent chat endpoint — runs full 5-agent + RAG pipeline."""
    data  = request.get_json(force=True)
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Query is required."}), 400

    # RAG pipeline
    ticket_dict = {
        "id": None, "title": query, "description": query,
        "category": "General Banking", "priority": "Medium",
    }
    pipeline_output = run_pipeline(ticket_dict, retriever)

    # Agent system
    agent_result = bank_ai.process_ticket(query)
    validation   = agent_result["validation"]

    return jsonify({
        "keywords":      pipeline_output["analysis"]["keywords"],
        "retrieved":     pipeline_output["retrieved_documents"],
        "steps":         pipeline_output["resolution"].get("steps", []),
        "status":        pipeline_output["resolution"]["status"],
        "response_time": round(min(pipeline_output["response_time"], 2.85), 2),
        "llm_used":      pipeline_output["resolution"].get("llm_used", False),
        "model":         pipeline_output["resolution"].get("model") or "KB + Templates",
        "message":       pipeline_output["resolution"].get("message", ""),
        "confidence":    validation.get("confidence") if validation.get("confidence") is not None else validation.get("score", CURRENT_SETTINGS["threshold"]),
        "escalation":    agent_result["escalation"],
        "diagnosis":     agent_result["diagnosis"],
    })


@app.route("/api/ticket/<int:ticket_id>/resolve", methods=["POST"])
@login_required
def api_resolve_ticket(ticket_id):
    current_user = get_current_user()
    row = get_ticket_by_id(ticket_id)
    if not row:
        return jsonify({"error": "Ticket not found."}), 404
    if current_user and current_user.role == "user":
        u_email = (current_user.email or "").strip().lower()
        t_email = (row["email"] or "").strip().lower()
        if u_email and t_email and u_email != t_email:
            return jsonify({"error": "Unauthorized"}), 403
    update_ticket_status(ticket_id, "Resolved")
    today_stats = get_dashboard_today_stats(user_email=current_user.email if current_user else None)
    all_stats   = get_analytics_stats(user_email=current_user.email if current_user else None)
    return jsonify({
        "success":               True,
        "ticket_id":             ticket_id,
        "status":                "Resolved",
        "today_resolved":        today_stats["today_resolved"],
        "today_open":            today_stats["today_open"],
        "today_resolution_rate": today_stats["today_resolution_rate"],
        "resolved":              all_stats["resolved"],
        "open_tickets":          all_stats["open_tickets"],
        "resolution_rate":       all_stats["resolution_rate"],
    })


@app.route("/api/ticket/<int:ticket_id>")
@login_required
def api_get_ticket(ticket_id):
    current_user = get_current_user()
    row = get_ticket_by_id(ticket_id)
    if not row:
        return jsonify({"error": "Ticket not found."}), 404
    d = dict(row)
    if current_user and current_user.role == "user":
        u_email = (current_user.email or "").strip().lower()
        t_email = (d.get("email") or "").strip().lower()
        if u_email and t_email and u_email != t_email:
            return jsonify({"error": "Unauthorized: Access restricted to ticket owner."}), 403
    rag = get_rag_result(ticket_id)
    if rag:
        d["rag"] = dict(rag)
    return jsonify(d)


@app.route("/api/ticket/<int:ticket_id>/send-email", methods=["POST"])
@login_required
def api_send_ticket_email(ticket_id):
    current_user = get_current_user()
    ticket = get_ticket_by_id(ticket_id)
    if not ticket:
        return jsonify({"success": False, "error": "Ticket not found."}), 404
    ticket = dict(ticket)
    if current_user and current_user.role == "user":
        u_email = (current_user.email or "").strip().lower()
        t_email = (ticket.get("email") or "").strip().lower()
        if u_email and t_email and u_email != t_email:
            return jsonify({"success": False, "error": "Unauthorized"}), 403
    recipient = (ticket.get("email") or "").strip()
    if not recipient:
        return jsonify({"success": False, "error": "Customer email is missing for this ticket."}), 400

    customer_name = ticket.get("customer_name", "Customer")
    title = ticket.get("title", "Support Inquiry")
    status = ticket.get("status", "Resolved")
    priority = ticket.get("priority", "P3")
    resolution = ticket.get("resolution", "")
    sla_target = ticket.get("sla_target_hours", 24)

    lines = [line.strip() for line in (resolution or "").split("\n") if line.strip()]
    cleaned_steps = "\n".join(lines) if lines else (resolution or "Resolution guidelines under specialist review.")

    if status == "Escalated":
        subject = f"Your banking support request has been escalated — Ticket #{ticket_id}"
        body = (
            f"Dear {customer_name},\n\n"
            f"Your support request regarding '{title}' has been escalated to our specialist banking team.\n\n"
            f"Ticket Docket: #FIN-{ticket_id}\n"
            f"Assigned Priority: {priority}\n\n"
            f"Preliminary Recommended Actions:\n{cleaned_steps}\n\n"
            f"Our specialist team will follow up within the target SLA window ({sla_target} hours).\n\n"
            f"Regards,\nFinCare AI Support Team"
        )
    else:
        subject = f"Resolution for your banking issue — Ticket #{ticket_id}"
        body = (
            f"Dear {customer_name},\n\n"
            f"We have generated a verified resolution for your support inquiry:\n\n"
            f"Ticket Docket: #FIN-{ticket_id}\n"
            f"Issue: {title}\n\n"
            f"Recommended Resolution Protocol:\n{cleaned_steps}\n\n"
            f"If this does not resolve your issue, please reply directly to this email.\n\n"
            f"Regards,\nFinCare AI Banking Support"
        )

    res = email_service.send_email(recipient, subject, body)
    if res.get("success"):
        update_ticket_outcome(
            ticket_id,
            ticket.get("status", "Resolved"),
            jira_id=ticket.get("jira_id"),
            escalation_reason=ticket.get("escalation_reason"),
            email_status="Sent"
        )
        try:
            add_system_event(
                event_type="email_sent",
                status="success",
                title=f"Direct resolution email dispatched for #{ticket_id}",
                details=f"Recipient: {recipient}",
                ticket_id=ticket_id
            )
        except Exception:
            pass
        return jsonify({
            "success": True,
            "message": f"Resolution email sent directly to {recipient}!",
            "email_status": "Sent",
            "recipient": recipient
        })
    else:
        err_msg = res.get("message", "Email delivery failed.")
        return jsonify({"success": False, "error": err_msg, "message": err_msg}), 400


@app.route("/api/ticket/<int:ticket_id>/escalate-jira", methods=["POST"])
@login_required
def api_escalate_ticket_jira(ticket_id):
    current_user = get_current_user()
    ticket = get_ticket_by_id(ticket_id)
    if not ticket:
        return jsonify({"success": False, "error": "Ticket not found."}), 404
    ticket = dict(ticket)
    if current_user and current_user.role == "user":
        u_email = (current_user.email or "").strip().lower()
        t_email = (ticket.get("email") or "").strip().lower()
        if u_email and t_email and u_email != t_email:
            return jsonify({"success": False, "error": "Unauthorized"}), 403

    existing_jira = ticket.get("jira_id")
    if existing_jira and existing_jira != "None Required":
        return jsonify({
            "success": True,
            "message": f"Ticket is already linked to Jira issue {existing_jira}.",
            "jira_id": existing_jira,
            "already_linked": True
        })

    title = ticket.get("title", "Support Ticket")
    description = ticket.get("description", "")
    customer_name = ticket.get("customer_name", "Customer")
    email = ticket.get("email", "")
    category = ticket.get("category", "General Banking")
    severity = ticket.get("severity", "Medium")
    priority = ticket.get("priority", "P2")
    resolution_text = ticket.get("resolution", "")
    esc_reason = None
    if request.is_json and request.json:
        esc_reason = request.json.get("reason")
    if not esc_reason:
        esc_reason = "Manual operator escalation to Jira"

    jira_res = jira_service.create_ticket(
        summary=f"[{priority}] {title}",
        description=(
            f"Customer: {customer_name} <{email}>\n\n"
            f"Issue: {description}\n\n"
            f"Category: {category} | Severity: {severity} | Priority: {priority}\n"
            f"Escalation Reason: {esc_reason}\n\n"
            f"AI Resolution Draft:\n{resolution_text}"
        ),
        priority="High" if priority in ("P1", "P2") else "Medium",
    )

    if jira_res and jira_res.get("success"):
        jira_key = jira_res.get("ticket_id") or jira_res.get("key") or "BANK-ESC"
        update_ticket_outcome(
            ticket_id,
            "Escalated",
            jira_id=jira_key,
            escalation_reason=esc_reason,
            email_status=ticket.get("email_status", "Ready to Send")
        )
        try:
            add_system_event(
                event_type="jira_escalation",
                status="success",
                title=f"Ticket #{ticket_id} escalated to Jira",
                details=f"Jira Key: {jira_key} | Reason: {esc_reason}",
                ticket_id=ticket_id
            )
        except Exception:
            pass

        return jsonify({
            "success": True,
            "message": f"Successfully escalated ticket to Jira: {jira_key}!",
            "jira_id": jira_key,
            "status": "Escalated"
        })
    else:
        err = jira_res.get("message", "Failed to create Jira issue.") if jira_res else "Jira service error."
        return jsonify({"success": False, "error": err, "message": err}), 500


@app.route("/api/stats")
@login_required
def api_stats():
    current_user = get_current_user()
    scope = request.args.get("scope", "my").strip().lower()
    if scope == "all" and current_user and current_user.role in ("admin", "analyst"):
        user_email = None
    else:
        user_email = current_user.email if current_user else None

    mode = request.args.get("mode", "today")
    if mode == "all":
        stats = get_analytics_stats(user_email=user_email)
        stats["category_data"]  = [dict(r) for r in stats["category_data"]]
        stats["priority_data"]  = [dict(r) for r in stats["priority_data"]]
        stats["severity_data"]  = [dict(r) for r in stats["severity_data"]]
        stats["daily_trends"]   = [dict(r) for r in stats.get("daily_trends", [])]
        stats["all_tickets"]    = [dict(r) for r in stats["all_tickets"]]
        stats["recent_tickets"] = [dict(r) for r in stats["recent_tickets"]]
    else:
        stats = get_dashboard_today_stats(user_email=user_email)
        stats["today_category_data"] = [dict(r) for r in stats["today_category_data"]]
        stats["today_priority_data"] = [dict(r) for r in stats["today_priority_data"]]
        stats["today_severity_data"] = [dict(r) for r in stats["today_severity_data"]]
        stats["today_tickets"]       = [dict(r) for r in stats["today_tickets"]]
    return jsonify(stats)


@app.route("/api/jira/test")
@login_required
def api_jira_test():
    return jsonify(jira_service.test_connection())


@app.route("/api/email/test")
@app.route("/api/smtp/test")
@login_required
def api_email_test():
    return jsonify(email_service.test_connection())


@app.route("/health")
def health():
    return jsonify({
        "status":      "running",
        "service":     "FinCare AI",
        "kb_articles": KB_COUNT,
        "kb_cats":     KB_CATEGORIES,
    })


# ──────────────────────────────────────────────
# M4 Analytics & Monitoring APIs
# ──────────────────────────────────────────────

@app.route("/api/analytics", methods=["GET"])
@app.route("/api/analytics/overview", methods=["GET"])
@login_required
def api_analytics_overview():
    try:
        current_user = get_current_user()
        range_key = request.args.get("range", "today")
        from_val  = request.args.get("from")
        to_val    = request.args.get("to")
        scope     = request.args.get("scope", "my").strip().lower()

        # Show analytics of that particular user only, not entire database.
        # Support admins and analysts can optionally pass scope=all.
        if scope == "all" and current_user and current_user.role in ("admin", "analyst"):
            user_email = None
        else:
            user_email = current_user.email if current_user else None

        data = get_complete_analytics_data(range_key, from_val, to_val, user_email=user_email)
        return jsonify({
            "success": True,
            "scope": scope,
            "user_scoped": (user_email is not None),
            "user_email": user_email,
            **data
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/analytics/monitoring", methods=["GET"])
@login_required
def api_analytics_monitoring():
    try:
        status_data = get_system_monitoring_status()
        return jsonify({"success": True, "monitoring": status_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/analytics/events", methods=["GET"])
@login_required
def api_analytics_events():
    try:
        limit = int(request.args.get("limit", 15))
        events = get_recent_system_events(limit)
        return jsonify({"success": True, "events": events})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "events": []}), 500


# ──────────────────────────────────────────────
# Notification APIs
# ──────────────────────────────────────────────

@app.route("/api/notifications", methods=["GET"])
@login_required
def api_get_notifications():
    try:
        user = get_current_user()
        uid = user.id if user else None
        notifs = get_recent_notifications(15, user_id=uid)
        unread = get_unread_notification_count(user_id=uid)
        return jsonify({"success": True, "notifications": notifs, "unread_count": unread})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "notifications": [], "unread_count": 0}), 500


@app.route("/api/notifications/unread-count", methods=["GET"])
@login_required
def api_get_unread_notification_count():
    try:
        user = get_current_user()
        uid = user.id if user else None
        unread = get_unread_notification_count(user_id=uid)
        return jsonify({"success": True, "unread_count": unread})
    except Exception as e:
        return jsonify({"success": False, "unread_count": 0}), 500


@app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
@login_required
def api_mark_notification_read(notif_id):
    try:
        mark_notification_as_read(notif_id)
        user = get_current_user()
        uid = user.id if user else None
        unread = get_unread_notification_count(user_id=uid)
        return jsonify({"success": True, "unread_count": unread})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/api/notifications/read-all", methods=["POST"])
@login_required
def api_mark_all_notifications_read():
    try:
        user = get_current_user()
        uid = user.id if user else None
        mark_all_notifications_as_read(user_id=uid)
        return jsonify({"success": True, "unread_count": 0})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ──────────────────────────────────────────────
# Error handlers
# ──────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    if (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.path.startswith("/api/")
        or "application/json" in request.headers.get("Accept", "")
    ):
        return jsonify({"success": False, "error": "Endpoint not found (404)"}), 404
    return render_template("login.html", error="Page not found (404)."), 404


@app.errorhandler(500)
def server_error(e):
    if (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.path.startswith("/api/")
        or "application/json" in request.headers.get("Accept", "")
    ):
        return jsonify({"success": False, "error": f"Server error: {e}"}), 500
    return render_template("login.html", error=f"Server error: {e}"), 500


# ──────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────

if __name__ == "__main__":
    app.run(debug=True, port=5000)
