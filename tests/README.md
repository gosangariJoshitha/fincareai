# Test Suite

- `unit/`: isolated component tests (classifier, RAG retriever, multi-agent workflow).
- `integration/`: Flask API, analytics calculations, escalation, UI consistency, and cross-milestone checks.
- `security/`: customer/user data scoping and authorization boundaries.
- `conftest.py`: shared test setup.

Run all automated tests from the repository root with `pytest tests/`. Do not place ad-hoc scripts or live integration checks in the automatically collected test paths. Tests must not depend on production database contents or real SMTP/Jira credentials.
