"""
RAG Step 3 & 4 – Context Augmentation + Resolution Generation
- Step 3: Builds context string from retrieved KB articles
- Step 4: Calls Groq LLM (openai/gpt-oss-120b) to generate resolution
"""

import re
import json
import os
import requests
from config import (
    GROQ_API_KEY,
    GROQ_BASE_URL,
    GROQ_MODEL,
    GROQ_TIMEOUT,
)


# ----------------------------------------------------------------
# Step 3 – Context Augmentation
# ----------------------------------------------------------------

def build_context(results: list) -> str:
    """Convert retrieved KB articles into a formatted context block."""
    if not results:
        return ""

    context = ""
    for doc in results:
        context += (
            f"\nSOURCE: {doc['id']}\n"
            f"TITLE: {doc['title']}\n"
            f"CATEGORY: {doc['category']}\n"
            f"RELEVANCE: {doc['score']:.2f}\n"
            f"{doc['content']}\n"
            f"{'=' * 60}\n"
        )
    return context


# ----------------------------------------------------------------
# Step 4a – Build the LLM prompt
# ----------------------------------------------------------------

def build_prompt(ticket: dict, context: str) -> str:
    """Build a focused prompt asking LLM to extract the exact resolution for the user's query."""
    title       = ticket.get("title", "").strip()
    description = ticket.get("description", "").strip()
    category    = ticket.get("category", "").strip()
    priority    = ticket.get("priority", "Medium")

    return f"""CUSTOMER SUPPORT TICKET:
Title: {title}
Description: {description}
Category: {category}
Priority: {priority}

OFFICIAL BANKING KNOWLEDGE BASE CONTEXT:
{context}

TASK:
You are SupportPilot, an expert AI banking support assistant for Indian banking customers.
Analyze the customer's query above and extract the precise, practical troubleshooting and resolution steps.

INSTRUCTIONS:
1. Directly solve the customer's specific problem using any concrete details they provided (such as amounts, reference IDs, ATM locations, or card issues).
2. Synthesize official banking guidelines and RBI framework rules from the Knowledge Base articles above.
3. Provide 5 to 6 clear, actionable, numbered resolution steps.
4. Each step must be a concise, professional, actionable sentence.
5. Do NOT include any thinking process, internal monologue, preambles, greetings, or meta-analysis.
6. Start immediately with:
1. """


# ----------------------------------------------------------------
# Step 4b – Call Groq LLM (Sole LLM Provider)
# ----------------------------------------------------------------

def call_groq(prompt: str, model: str = None) -> dict:
    """
    Call Groq API directly with the given prompt.
    Uses GROQ_API_KEY and model (default: openai/gpt-oss-120b).
    Returns dict with:
        success : bool
        text    : str (LLM response or error message)
        model   : str
    """
    api_key = os.environ.get("GROQ_API_KEY") or GROQ_API_KEY
    if not api_key:
        return {"success": False, "text": "GROQ_API_KEY not configured.", "model": None}

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }

    target_model = model or GROQ_MODEL or "openai/gpt-oss-120b"

    payload = {
        "model": target_model,
        "messages": [
            {
                "role":    "system",
                "content": (
                    "You are SupportPilot, an expert AI banking support assistant for Indian banking customers. "
                    "You provide numbered step-by-step solutions for banking complaints. "
                    "IMPORTANT: Output ONLY the numbered resolution steps starting immediately with '1.'. "
                    "Never output thinking process, internal reasoning, analysis, or preamble."
                )
            },
            {
                "role":    "user",
                "content": prompt
            }
        ],
        "temperature": 0.2,
        "max_tokens":  800,
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
            choice = data["choices"][0]
            msg = choice.get("message", {})
            text = msg.get("content", "").strip()
            if not text and msg.get("reasoning"):
                text = msg.get("reasoning", "").strip()
            returned_model = data.get("model", target_model)
            if text:
                return {"success": True, "text": text, "model": returned_model}
            return {"success": False, "text": "Empty response from Groq.", "model": returned_model}
        elif response.status_code == 401:
            return {"success": False, "text": "Invalid GROQ_API_KEY provided.", "model": None}
        elif response.status_code == 429:
            return {"success": False, "text": "Groq rate limit reached.", "model": None}
        else:
            return {"success": False, "text": f"Groq HTTP {response.status_code}: {response.text[:120]}", "model": None}
    except requests.exceptions.Timeout:
        return {"success": False, "text": f"Groq model {target_model} timed out.", "model": None}
    except requests.exceptions.ConnectionError:
        return {"success": False, "text": "Cannot connect to Groq API.", "model": None}
    except Exception as e:
        return {"success": False, "text": f"Groq error: {e}", "model": None}


# Backward-compatibility alias
call_openrouter = call_groq


# ----------------------------------------------------------------
# Step 4c – Parse LLM response into structured steps
# ----------------------------------------------------------------

def parse_llm_response(llm_text: str, retrieved_docs: list) -> list:
    """
    Parse the LLM's plain text response into structured step dicts.
    Robustly strips reasoning/thinking traces, headers, and meta-commentary.
    """
    if not llm_text:
        return []

    # Clean markdown bold markers
    def clean(text):
        return re.sub(r"\*\*(.+?)\*\*", r"\1", text).strip()

    # 1. Strip explicit <think>...</think> blocks
    text = re.sub(r"<think>.*?</think>", "", llm_text, flags=re.DOTALL).strip()

    # 2. If the model output includes a thinking block (e.g. "Here's a thinking process:"),
    # find where the actual answer steps start.
    lower_text = text.lower()
    if "thinking process" in lower_text or "analyze the user" in lower_text or "role: supportpilot" in lower_text:
        # Check if there is a distinct resolution section later in the text
        split_markers = [
            r"\n\s*---\s*\n",
            r"\n\s*resolution\s*steps?\s*:?\s*\n",
            r"\n\s*recommended\s*resolution\s*:?\s*\n",
            r"\n\s*steps\s*to\s*resolve\s*:?\s*\n",
            r"\n\s*action\s*steps?\s*:?\s*\n",
            r"\n\s*here\s*are\s*the\s*steps\s*:?\s*\n",
        ]
        found_split = False
        for marker in split_markers:
            parts = re.split(marker, text, flags=re.IGNORECASE)
            if len(parts) > 1 and len(parts[-1].strip()) > 30:
                text = parts[-1].strip()
                found_split = True
                break

        # If no explicit header split, look for the second occurrence of "1." or last sequence
        if not found_split:
            step_ones = [m.start() for m in re.finditer(r"(?:^|\n)\s*(?:\*\*)?1[\.\)]\s*", text)]
            if len(step_ones) > 1:
                # Take from the last occurrence of "1."
                text = text[step_ones[-1]:].strip()

    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Filter out obvious meta-lines
    META_PHRASES = [
        "thinking process", "analyze user", "analyze the user", "role: supportpilot",
        "input: a customer", "instructions:", "knowledge base articles",
        "i need to extract", "let me ", "let's see", "role of supportpilot",
        "target output", "format:", "constraint:", "ticket details:",
    ]
    def is_meta_line(line_str: str) -> bool:
        ll = line_str.lower()
        return any(phrase in ll for phrase in META_PHRASES)

    # Skip common header lines
    HEADER_PATTERNS = [
        r"^resolution steps",
        r"^recommended resolution",
        r"^here are",
        r"^here is",
        r"^the following",
        r"^please follow",
        r"^support agent",
        r"^based on",
        r"^according to",
        r"^as per",
        r"^summary",
        r"^troubleshooting",
        r"^steps to resolve",
        r"^steps:",
        r"^resolution:",
    ]
    def is_header(line_str: str) -> bool:
        lower = line_str.lower().rstrip(":").strip()
        for pattern in HEADER_PATTERNS:
            if re.match(pattern, lower):
                return True
        if len(lower) < 12 and not re.search(r"\d", lower):
            return True
        return False

    def best_source(line_text):
        m = re.search(r"\[?(KB\d+)\]?", line_text, re.IGNORECASE)
        if m:
            sid = m.group(1).upper()
            title = next((d["title"] for d in retrieved_docs if d["id"].upper() == sid), "Knowledge Base")
            return sid, title
        if retrieved_docs:
            return retrieved_docs[0]["id"], retrieved_docs[0]["title"]
        return "KB", "Knowledge Base"

    steps = []
    step_number = 1
    buffer = []

    for line in lines:
        if is_meta_line(line) or is_header(line):
            continue

        # Match step numbers: "1." "1)" "Step 1:" "1 -" "**1.**"
        is_step = re.match(r"^(\*\*)?(\bstep\s*)?\d+[\.\)\-\:]\s*(\*\*)?", line, re.IGNORECASE)
        is_bullet = re.match(r"^[-•\*]\s+", line)

        if is_step or is_bullet:
            if buffer:
                step_content = clean(" ".join(buffer))
                if step_content and len(step_content) > 10 and not is_meta_line(step_content):
                    sid, stitle = best_source(step_content)
                    step_content = re.sub(r"\[?KB\d+\]?", "", step_content, flags=re.IGNORECASE).strip()
                    steps.append({
                        "step":         step_number,
                        "text":         step_content,
                        "source_id":    sid,
                        "source_title": stitle,
                    })
                    step_number += 1
                buffer = []
            cleaned = re.sub(
                r"^(\*\*)?(\bstep\s*)?\d+[\.\)\-\:]\s*(\*\*)?|^[-•\*]\s+",
                "", line, flags=re.IGNORECASE
            )
            buffer.append(cleaned)
        else:
            if buffer:
                buffer.append(line)
            else:
                buffer.append(line)

    if buffer:
        step_content = clean(" ".join(buffer))
        if step_content and len(step_content) > 10 and not is_meta_line(step_content):
            sid, stitle = best_source(step_content)
            step_content = re.sub(r"\[?KB\d+\]?", "", step_content, flags=re.IGNORECASE).strip()
            steps.append({
                "step":         step_number,
                "text":         step_content,
                "source_id":    sid,
                "source_title": stitle,
            })

    # Fallback to sentence split if no numbered items matched
    if not steps:
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        for sentence in sentences:
            sentence = clean(sentence.strip())
            if sentence and len(sentence) > 15 and not is_meta_line(sentence):
                sid, stitle = best_source(sentence)
                sentence = re.sub(r"\[?KB\d+\]?", "", sentence, flags=re.IGNORECASE).strip()
                steps.append({
                    "step":         step_number,
                    "text":         sentence,
                    "source_id":    sid,
                    "source_title": stitle,
                })
                step_number += 1

    return steps


# ----------------------------------------------------------------
# Step 4d – Mock fallback (used if LLM fails)
# ----------------------------------------------------------------

def _extract_steps_mock(content: str) -> list:
    """Extract numbered steps from KB content — used as LLM fallback."""
    lines  = content.split("\n")
    steps  = []
    buffer = []

    for line in lines:
        stripped = line.strip()
        if re.match(r"^\d+\.", stripped):
            if buffer:
                steps.append(" ".join(buffer))
                buffer = []
            buffer.append(re.sub(r"^\d+\.\s*", "", stripped))
        elif buffer and stripped:
            buffer.append(stripped)

    if buffer:
        steps.append(" ".join(buffer))

    return steps


def generate_resolution_mock(ticket: dict, retrieved_docs: list) -> list:
    """
    Fallback: extract clean steps from KB content.
    Caps at 6 steps max, then adds escalation step = 7 total.
    """
    from agents import ResolutionAgent as _RA
    steps       = []
    step_number = 1

    for doc in retrieved_docs[:1]:   # only use top article
        extracted = _extract_steps_mock(doc["content"])
        for step_text in extracted[:6]:
            if "BankSupport AI" in step_text or len(step_text) < 15:
                continue
            if len(step_text) > 240:
                step_text = step_text[:237] + "..."
            steps.append({
                "step":         step_number,
                "text":         step_text,
                "source_id":    doc["id"],
                "source_title": doc["title"],
            })
            step_number += 1
            if step_number > 6:
                break

    # If KB gave nothing useful, use ResolutionAgent category template
    if not steps:
        category = ticket.get("category", "General Banking") if ticket else "General Banking"
        ra = _RA()
        template_steps = ra.TEMPLATES.get(category, ra.TEMPLATES["General Banking"])
        source_id    = retrieved_docs[0]["id"]    if retrieved_docs else "KB"
        source_title = retrieved_docs[0]["title"] if retrieved_docs else "Knowledge Base"
        for step_text in template_steps[:6]:
            steps.append({
                "step":         step_number,
                "text":         step_text,
                "source_id":    source_id,
                "source_title": source_title,
            })
            step_number += 1

    return steps


# ----------------------------------------------------------------
# Main: generate_resolution (called by pipeline.py)
# ----------------------------------------------------------------

def generate_resolution(ticket: dict, retrieved_docs: list, model: str = None) -> dict:
    """
    Main resolution generator.
    1. If no docs found   → use agent category template
    2. Try Groq LLM       → parse into max 6 clean steps
    3. If LLM fails       → fall back to KB/template extractor
    4. Always cap at 6 steps + 1 escalation step = 7 total
    """
    # Even with no docs, use agent templates — never return empty
    if not retrieved_docs:
        from agents import ResolutionAgent as _RA
        category = ticket.get("category", "General Banking")
        ra       = _RA()
        template = ra.TEMPLATES.get(category, ra.TEMPLATES["General Banking"])
        steps = [
            {"step": i+1, "text": t, "source_id": "KB-TEMPLATE", "source_title": f"{category} Guidelines"}
            for i, t in enumerate(template[:6])
        ]
        steps.append({
            "step": len(steps) + 1,
            "text": "If the issue is not resolved after following the above steps, escalate to the bank's grievance officer or the RBI Banking Ombudsman at cms.rbi.org.in.",
            "source_id": "SYS", "source_title": "System Policy",
        })
        return {
            "status": "RESOLVED", "steps": steps,
            "sources_used": [], "llm_used": False, "model": None,
            "message": f"Resolution from {category} guidelines.",
            "prompt": "",
        }

    # Build context and prompt
    context = build_context(retrieved_docs)
    prompt  = build_prompt(ticket, context)

    # ── Try Groq LLM ──
    llm_result = call_groq(prompt, model=model)
    llm_used   = False
    model_used = None
    steps      = []

    if llm_result["success"] and llm_result["text"]:
        parsed = parse_llm_response(llm_result["text"], retrieved_docs)
        if len(parsed) >= 3:          # LLM gave at least 3 valid steps
            steps      = parsed[:6]   # cap at 6
            llm_used   = True
            model_used = llm_result["model"]

    # ── Fallback to KB/template extractor ──
    if not steps:
        steps      = generate_resolution_mock(ticket, retrieved_docs)[:6]
        llm_used   = False
        model_used = None

    # ── Renumber cleanly + add closing step (step 7) ──
    for i, s in enumerate(steps):
        s["step"] = i + 1

    steps.append({
        "step":         len(steps) + 1,
        "text":         "If the issue is not resolved after following the above steps, escalate to the bank's grievance officer or the RBI Banking Ombudsman at cms.rbi.org.in with your complaint reference number.",
        "source_id":    "SYS",
        "source_title": "System Policy",
    })

    sources_used = list({d["id"] for d in retrieved_docs})

    return {
        "status":       "RESOLVED",
        "steps":        steps,
        "sources_used": sources_used,
        "message":      f"Resolution generated using {'Groq LLM (' + model_used + ')' if llm_used else 'Knowledge Base + Category Templates'}.",
        "llm_used":     llm_used,
        "model":        model_used,
        "prompt":       prompt,
    }
