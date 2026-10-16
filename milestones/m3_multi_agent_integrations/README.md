# Milestone 3 — Multi-Agent Workflow & Integrations

**PPT scope:** diagnosis, retrieval coordination, resolution generation, confidence/validation gate, escalation, Jira ticket creation, and automated support email.

## Owned implementation
- `agents.py` — specialized agents and orchestrator.
- `jira_service.py` — Jira REST API integration.
- `email_service.py` — SMTP delivery.

## Shared dependencies
- M2 RAG pipeline and shared banking knowledge base.
- `config.py` — provider/integration configuration.
- `database.py` — ticket, event, integration result, and notification persistence.
- `app.py` — coordinates the request lifecycle.

## Commands
```bash
pytest tests/unit/test_agents.py
pytest tests/integration/test_escalation.py
```

Default automated tests must mock Jira and SMTP. Live integrations require explicit opt-in and must never run as a side effect of ordinary `pytest`.
