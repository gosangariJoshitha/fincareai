# Milestone Ownership & Team Collaboration

The four milestones follow the supplied PPTs: **M1 classification**, **M2 knowledge retrieval/RAG**, **M3 agents and integrations**, **M4 analytics/monitoring**.

| Milestone | Main ownership | Primary files |
|---|---|---|
| M1 | Intake classification, model training/evaluation, severity/priority inputs | `milestones/m1_ticket_classification/` |
| M2 | Retrieval, context building, RAG pipeline | `milestones/m2_knowledge_retrieval/rag/` |
| M3 | Agent orchestration, escalation, Jira, email | `milestones/m3_multi_agent_integrations/` |
| M4 | Analytics calculations and operational monitoring | `milestones/m4_analytics_monitoring/analytics.py` |

## Shared files — coordinate before editing
`app.py`, `config.py`, `database.py`, `auth.py`, `templates/`, `static/`, `requirements.txt`, and `knowledge_base/` are shared integration surfaces. They affect multiple milestones and should not be independently overwritten by parallel branches.

Root-level compatibility modules (`classifier.py`, `agents.py`, `analytics.py`, `email_service.py`, `jira_service.py`, and `rag/`) are intentionally thin re-export wrappers. Keep them until all imports/tests have migrated; do not place feature logic in these wrappers.

## Low-conflict workflow
1. Create one branch per task, not one branch per person for the whole project.
2. Prefer changes inside the owning milestone package.
3. If a database/schema or shared API change is needed, open a small separate PR and notify the other milestone owners.
4. Pull/rebase `main` before starting and before requesting review.
5. Run `pytest tests/` before merging.
6. Merge one milestone PR at a time and run the full suite after each merge.
7. Never commit `.env`, database files, caches, or generated secrets.

Separate folders reduce overlap, but cannot guarantee zero conflicts. The shared app, schema, templates, and dependency file still need coordinated changes and integration tests.
