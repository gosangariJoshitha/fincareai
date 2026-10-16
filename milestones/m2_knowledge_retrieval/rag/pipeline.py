"""
RAG Pipeline – orchestrates all 4 steps of the resolution workflow.

Step 1 : Ticket Analysis & Query Generation   (analyzer.py)
Step 2 : Knowledge Base Retrieval             (retriever.py)
Step 3 : Context Augmentation                 (generator.py)
Step 4 : Resolution Generation                (generator.py)
"""

import time
from config import TOP_K, MIN_RELEVANCE
from rag.analyzer  import analyze_ticket
from rag.retriever import KnowledgeRetriever
from rag.generator import build_context, generate_resolution


def run_pipeline(ticket: dict, retriever: KnowledgeRetriever, settings: dict = None) -> dict:
    """
    Run the full RAG pipeline for a single ticket using active system settings.

    Parameters
    ----------
    ticket    : dict with id, title, description, category, priority
    retriever : initialised KnowledgeRetriever instance
    settings  : optional dict of system_settings from database

    Returns
    -------
    dict with workflow_status, analysis, retrieved_documents,
         context, resolution, response_time_seconds
    """
    start_time = time.time()

    if not settings:
        try:
            from database import get_system_settings
            settings = get_system_settings()
        except Exception:
            settings = {}

    top_k     = int(settings.get("retrieval_top_k", TOP_K))
    min_score = float(settings.get("minimum_similarity", MIN_RELEVANCE))
    model     = settings.get("llm_model")

    workflow_status = {
        "ticket_analysis":       "pending",
        "knowledge_retrieval":   "pending",
        "context_augmentation":  "pending",
        "response_generation":   "pending",
    }

    # --------------------------------------------------
    # Step 1 – Ticket Analysis
    # --------------------------------------------------
    analysis = analyze_ticket(ticket)
    workflow_status["ticket_analysis"] = "completed"

    # Check for extremely vague issues (e.g. "help", "problem")
    query_text = (ticket.get("title", "") + " " + ticket.get("description", "")).strip().lower()
    is_vague = len(query_text) < 8 or query_text in ["help", "support", "issue", "problem", "test", "urgent"]

    if is_vague:
        # Avoid generic hallucinated steps for empty or vague complaints
        resolution = {
            "status": "AWAITING_CLARIFICATION",
            "steps": [
                {
                    "step": 1,
                    "text": "Your support request requires additional details to identify the specific banking service or transaction.",
                    "source_id": "SYS-CLARIFY",
                    "source_title": "Customer Clarification Request"
                },
                {
                    "step": 2,
                    "text": "Please provide your registered account type (Savings/Current), affected channel (ATM, UPI, Mobile App, NetBanking), and error message.",
                    "source_id": "SYS-CLARIFY",
                    "source_title": "Customer Clarification Request"
                },
                {
                    "step": 3,
                    "text": "If this relates to a financial debit, include the transaction date, approximate time, and last 4 digits of your card/account.",
                    "source_id": "SYS-CLARIFY",
                    "source_title": "Customer Clarification Request"
                },
                {
                    "step": 4,
                    "text": "A support agent has placed this ticket on hold awaiting your response.",
                    "source_id": "SYS-POLICY",
                    "source_title": "Support Desk Policy"
                }
            ],
            "sources_used": [],
            "message": "Ticket requires clarification from customer before automated resolution can proceed.",
            "llm_used": False,
            "model": None,
            "prompt": "",
        }
        retrieved_docs = []
        context = ""
        workflow_status["knowledge_retrieval"]  = "skipped"
        workflow_status["context_augmentation"] = "skipped"
        workflow_status["response_generation"]  = "completed"
    else:
        # --------------------------------------------------
        # Step 2 – Knowledge Base Retrieval
        # --------------------------------------------------
        retrieved_docs = retriever.search(
            analysis["query"],
            top_k=top_k,
            min_score=min_score,
        )
        workflow_status["knowledge_retrieval"] = "completed"

        # --------------------------------------------------
        # Step 3 – Context Augmentation
        # --------------------------------------------------
        context = build_context(retrieved_docs)
        workflow_status["context_augmentation"] = "completed"

        # --------------------------------------------------
        # Step 4 – Resolution Generation
        # --------------------------------------------------
        resolution = generate_resolution(ticket, retrieved_docs, model=model)
        workflow_status["response_generation"] = "completed"

    response_time = round(time.time() - start_time, 2)

    return {
        "workflow_status":     workflow_status,
        "analysis":            analysis,
        "retrieved_documents": retrieved_docs,
        "context":             context,
        "resolution":          resolution,
        "response_time":       response_time,
    }
