"""
Test Groq LLM integration end-to-end.
Run with: python tests/unit/test_llm.py
"""
import sys
import json
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
from config import GROQ_API_KEY, GROQ_MODEL, KB_PATH
from rag.retriever import KnowledgeRetriever
from rag.generator import (
    build_context,
    build_prompt,
    call_groq,
    generate_resolution,
)


def run_llm_test():
    print("=" * 65)
    print("  FinCare AI — Groq LLM Integration Test")
    print("=" * 65)

    # ── 1. Config check ──
    print("\n[1] Config check")
    print(f"    API Key  : {GROQ_API_KEY[:20]}...{GROQ_API_KEY[-6:] if len(GROQ_API_KEY) > 26 else ''}")
    print(f"    Model    : {GROQ_MODEL}")

    # ── 2. Load KB ──
    print("\n[2] Loading Knowledge Base...")
    r = KnowledgeRetriever(KB_PATH)
    print(f"    Loaded {len(r.documents)} articles")

    # ── 3. Search KB ──
    print("\n[3] Searching KB for ATM ticket...")
    ticket = {
        "id":          1,
        "title":       "ATM did not dispense cash but amount was debited",
        "description": "I tried to withdraw Rs 5000 from HDFC ATM. Machine showed Transaction Successful but no cash came out. Account debited Rs 5000. Transaction ref TXN998821.",
        "category":    "wrong_amount_of_cash_received",
        "priority":    "P1",
    }
    docs = r.search(ticket["title"] + " " + ticket["description"], top_k=3)
    print(f"    Retrieved {len(docs)} articles:")
    for d in docs:
        print(f"      • {d['id']}: {d['title']} (score={d['score']:.4f})")

    # ── 4. Build context + prompt ──
    print("\n[4] Building context and prompt...")
    context = build_context(docs)
    prompt  = build_prompt(ticket, context)
    print(f"    Prompt length: {len(prompt)} characters")

    # ── 5. Call Groq ──
    print("\n[5] Calling Groq LLM...")
    print(f"    Model: {GROQ_MODEL}")
    result = call_groq(prompt)

    if result["success"]:
        print(f"    ✓ LLM responded successfully!")
        print(f"    Model used : {result['model']}")
        print(f"    Response   : {len(result['text'])} characters")
    else:
        print(f"    ⚠ Groq call returned fallback: {result.get('error')}")
        print("    → Falling back to KB-only synthesis...")

    # ── 6. Full resolution generation ──
    print("\n[6] Running full generate_resolution()...")
    resolution = generate_resolution(ticket, docs)
    print(f"    Status   : {resolution['status']}")
    print(f"    LLM used : {resolution['llm_used']}")
    print(f"    Model    : {resolution['model']}")
    print(f"    Steps    : {len(resolution['steps'])}")
    print(f"    Message  : {resolution['message']}")
    print("\n    --- Resolution Steps ---")
    for step in resolution["steps"]:
        print(f"    {step['step']}. {step['text'][:80]}...")
        print(f"       Source: {step['source_id']} – {step['source_title']}")

    print("\n" + "=" * 65)
    if resolution["llm_used"]:
        print("  ✓ Groq LLM is ACTIVE — real AI responses enabled!")
    else:
        print("  ⚠ Groq unavailable — fallback KB extraction is working")
        print("  → Check your API key in config.py")
    print("=" * 65)


def test_groq_resolution_pipeline():
    """Pytest-friendly assertion that resolution generation completes without crashing."""
    r = KnowledgeRetriever(KB_PATH)
    ticket = {
        "id": 1,
        "title": "ATM did not dispense cash",
        "description": "Account debited Rs 5000",
        "category": "wrong_amount_of_cash_received",
        "priority": "P1"
    }
    docs = r.search("ATM cash debit", top_k=2)
    resolution = generate_resolution(ticket, docs)
    assert resolution is not None
    assert "steps" in resolution
    assert len(resolution["steps"]) > 0


if __name__ == "__main__":
    run_llm_test()
