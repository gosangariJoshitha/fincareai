# Milestone 4 — Analytics, Monitoring & Optimization

**PPT scope:** analytics dashboard, resolution/escalation metrics, trends and distributions, system monitoring, response-time measurements, escalation monitoring, testing, and optimization.

## Owned implementation
- `analytics.py` — database-driven metric calculations and monitoring queries.
- UI templates remain in shared `templates/` because the navigation/layout and ticket views are shared across milestones.

## Shared dependencies
- `database.py` — source of truth for tickets, RAG runs, events, and feedback.
- `config.py` — database and system settings.
- `app.py` — authenticated analytics routes and API responses.

## Commands
```bash
pytest tests/integration/test_analytics.py tests/integration/test_metrics.py
```

Regular users must see their own authorized ticket analytics; global desk-wide metrics belong only in an explicitly authorized admin/analyst scope. Never add demo arrays or fabricated metrics.
