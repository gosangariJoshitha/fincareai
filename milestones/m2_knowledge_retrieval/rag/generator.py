
"""
RAG Step 3 & 4 – Context Augmentation + Resolution Generation
Uses Groq LLM when available and category-based fallback otherwise.
"""

import re
import os
import requests

from config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MODEL,
    GROQ_TIMEOUT,
)


def build_context(results: list) -> str:
    """Format retrieved knowledge-base articles as context."""
    if not results:
        return ""

    context_parts = []

    for doc in results:
        context_parts.append(
            f"\nSOURCE: {doc.get('id', 'KB')}\n"
            f"TITLE: {doc.get('title', 'Banking Help Article')}\n"
            f"CATEGORY: {doc.get('category', '')}\n"
            f"RELEVANCE: {doc.get('score', doc.get('similarity', 0)):.2f}\n"
            f"{doc.get('content', '')}\n"
            f"{'=' * 60}\n"
        )

    return "".join(context_parts)


def build_prompt(ticket: dict, context: str) -> str:
    """Build the prompt for Groq."""
    title = ticket.get("title", "").strip()
    description = ticket.get("description", "").strip()
    category = ticket.get("category", "").strip()
    priority = ticket.get("priority", "Medium")

    return f"""CUSTOMER SUPPORT TICKET:
Title: {title}
Description: {description}
Category: {category}
Priority: {priority}

OFFICIAL BANKING KNOWLEDGE BASE CONTEXT:
{context}

TASK:
You are SupportPilot, an AI banking support assistant for Indian customers.
Provide practical steps based on the retrieved knowledge base.

Instructions:
1. Give 5 to 6 concise, numbered and actionable steps.
2. Never ask the customer to share their PIN, password, CVV or OTP.
3. For suspected fraud, advise contacting the bank immediately.
4. Do not invent transaction details or claim an action was completed.
5. Output only the numbered resolution steps.
Start with 1.
"""


def call_groq(prompt: str, model: str = None) -> dict:
    """Call the Groq chat-completions API."""
    api_key = os.environ.get("GROQ_API_KEY") or GROQ_API_KEY

    if not api_key:
        return {
            "success": False,
            "text": "GROQ_API_KEY not configured.",
            "model": None,
        }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    target_model = model or GROQ_MODEL or "openai/gpt-oss-120b"

    payload = {
        "model": target_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a banking support assistant. "
                    "Output only numbered, practical resolution steps. "
                    "Never expose internal reasoning."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 800,
    }

    url = f"{GROQ_BASE_URL.rstrip('/')}/chat/completions"

    try:
        response = requests.post(
            url,
            headers=headers,
            json=payload,
            timeout=GROQ_TIMEOUT,
        )

        if response.status_code == 200:
            data = response.json()
            message = data["choices"][0].get("message", {})
            text = (message.get("content") or "").strip()

            if text:
                return {
                    "success": True,
                    "text": text,
                    "model": data.get("model", target_model),
                }

            return {
                "success": False,
                "text": "Empty response from Groq.",
                "model": target_model,
            }

        if response.status_code == 401:
            error = "Invalid GROQ_API_KEY."
        elif response.status_code == 429:
            error = "Groq rate limit reached."
        else:
            error = f"Groq HTTP {response.status_code}: {response.text[:200]}"

        return {"success": False, "text": error, "model": None}

    except requests.exceptions.Timeout:
        return {
            "success": False,
            "text": "Groq request timed out.",
            "model": None,
        }
    except requests.exceptions.ConnectionError:
        return {
            "success": False,
            "text": "Cannot connect to Groq API.",
            "model": None,
        }
    except Exception as exc:
        return {
            "success": False,
            "text": f"Groq error: {exc}",
            "model": None,
        }


# Backward compatibility
call_openrouter = call_groq


def parse_llm_response(llm_text: str, retrieved_docs: list) -> list:
    """Convert numbered LLM output into structured resolution steps."""
    if not llm_text:
        return []

    text = re.sub(r"<think>.*?</think>", "", llm_text, flags=re.DOTALL)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text).strip()

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    steps = []
    current_step = None

    for line in lines:
        if re.match(
            r"^(?:step\s*)?\d+[\.\):\-]\s*",
            line,
            flags=re.IGNORECASE,
        ):
            if current_step:
                steps.append(current_step)

            current_step = re.sub(
                r"^(?:step\s*)?\d+[\.\):\-]\s*",
                "",
                line,
                flags=re.IGNORECASE,
            ).strip()

        elif current_step:
            current_step += " " + line

    if current_step:
        steps.append(current_step)

    source = retrieved_docs[0] if retrieved_docs else {}
    source_id = source.get("id", "KB")
    source_title = source.get("title", "Knowledge Base")

    structured = []

    for step in steps:
        step = re.sub(r"\[?KB\d+\]?", "", step).strip()

        if len(step) > 10:
            structured.append({
                "step": len(structured) + 1,
                "text": step,
                "source_id": source_id,
                "source_title": source_title,
            })

        if len(structured) >= 6:
            break

    return structured


def _extract_steps_mock(content: str) -> list:
    """Extract numbered instructions from a KB article."""
    steps = []
    current = []

    for line in (content or "").splitlines():
        line = line.strip()

        if re.match(r"^\d+[\.\)]\s*", line):
            if current:
                steps.append(" ".join(current))

            current = [
                re.sub(r"^\d+[\.\)]\s*", "", line).strip()
            ]

        elif current and line:
            current.append(line)

    if current:
        steps.append(" ".join(current))

    return [
        step for step in steps
        if len(step) > 15 and "BankSupport AI" not in step
    ]


def _category_fallback(ticket: dict, retrieved_docs: list) -> list:
    """
    Use ResolutionAgent.generate() instead of the nonexistent TEMPLATES
    class attribute.
    """
    from agents import ResolutionAgent

    ticket = ticket or {}
    category = ticket.get("category", "General Banking")

    article = retrieved_docs[0] if retrieved_docs else {}
    diagnosis = {"category": category}

    agent = ResolutionAgent()
    result = agent.generate(
        diagnosis=diagnosis,
        article=article,
        query="",  # Avoid recursively calling generate_resolution().
    )

    raw_steps = result.get("steps", [])

    source = retrieved_docs[0] if retrieved_docs else {}
    source_id = source.get("id", "KB-TEMPLATE")
    source_title = source.get(
        "title", f"{category} Guidelines"
    )

    structured = []

    for item in raw_steps[:6]:
        step_text = (
            item.get("text", "")
            if isinstance(item, dict)
            else str(item)
        ).strip()

        if len(step_text) > 10:
            structured.append({
                "step": len(structured) + 1,
                "text": step_text,
                "source_id": source_id,
                "source_title": source_title,
            })

    return structured


def generate_resolution_mock(ticket: dict, retrieved_docs: list) -> list:
    """Use KB instructions first, then category-based fallback."""
    steps = []

    for doc in (retrieved_docs or [])[:1]:
        for step_text in _extract_steps_mock(doc.get("content", ""))[:6]:
            if len(step_text) > 240:
                step_text = step_text[:237] + "..."

            steps.append({
                "step": len(steps) + 1,
                "text": step_text,
                "source_id": doc.get("id", "KB"),
                "source_title": doc.get("title", "Knowledge Base"),
            })

    if not steps:
        steps = _category_fallback(ticket, retrieved_docs or [])

    return steps[:6]


def generate_resolution(
    ticket: dict,
    retrieved_docs: list,
    model: str = None,
) -> dict:
    """Generate up to six resolution steps plus an escalation note."""
    ticket = ticket or {}
    retrieved_docs = retrieved_docs or []
    category = ticket.get("category", "General Banking")

    context = build_context(retrieved_docs)
    prompt = build_prompt(ticket, context) if retrieved_docs else ""

    steps = []
    llm_used = False
    model_used = None

    # Try Groq only when relevant KB documents exist.
    if retrieved_docs:
        llm_result = call_groq(prompt, model=model)

        if llm_result.get("success") and llm_result.get("text"):
            parsed = parse_llm_response(
                llm_result["text"], retrieved_docs
            )

            if len(parsed) >= 3:
                steps = parsed[:6]
                llm_used = True
                model_used = llm_result.get("model")

    # Fallback: KB steps, then ResolutionAgent's own category logic.
    if not steps:
        steps = generate_resolution_mock(ticket, retrieved_docs)[:6]

    # Final safety fallback if the KB and agent both return no steps.
    if not steps:
        steps = [{
            "step": 1,
            "text": (
                "Contact your bank through its official support channel "
                "and explain the issue. Never share your PIN, CVV, "
                "password or OTP."
            ),
            "source_id": "SYS",
            "source_title": "General Banking Safety",
        }]

    for index, step in enumerate(steps):
        step["step"] = index + 1

    steps.append({
        "step": len(steps) + 1,
        "text": (
            "If the issue remains unresolved, contact the bank through "
            "its official grievance channel and retain your complaint "
            "reference number."
        ),
        "source_id": "SYS",
        "source_title": "Escalation Guidance",
    })

    return {
        "status": "GENERATED",
        "steps": steps,
        "sources_used": list({
            doc.get("id", "KB") for doc in retrieved_docs
        }),
        "message": (
            f"Resolution generated using "
            f"{'Groq LLM (' + str(model_used) + ')' if llm_used else 'KB/category fallback'}."
        ),
        "llm_used": llm_used,
        "model": model_used,
        "prompt": prompt,
    }
