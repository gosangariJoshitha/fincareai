# FinCare AI — AI-Powered Financial Support Desk

FinCare AI is a Flask-based financial support application that automates support-ticket processing using machine learning, Retrieval-Augmented Generation (RAG), and a multi-agent AI workflow.

The application ingests support tickets, classifies financial and banking issues, retrieves relevant knowledge, generates AI-assisted resolutions, validates outcomes, escalates unresolved or high-risk tickets, and provides operational analytics.

This repository contains the implementation through **Milestones 1–4**.

## Table of Contents

- [Project Overview](#project-overview)
- [Milestone Scope](#milestone-scope)
- [Repository Structure](#repository-structure)
- [Technology Stack](#technology-stack)
- [Requirements](#requirements)
- [Installation and Setup](#installation-and-setup)
- [Running the Application](#running-the-application)
- [Running Tests](#running-tests)
- [Model Training and Evaluation](#model-training-and-evaluation)
- [Milestone-Based Development](#milestone-based-development)
- [Data and Security Guidelines](#data-and-security-guidelines)
- [Troubleshooting](#troubleshooting)

## Project Overview

FinCare AI follows a structured support workflow:

**Ticket Intake → Classification → Knowledge Retrieval → Resolution Generation → Validation → Escalation → Analytics**

The system is organized into four milestones, with shared application components maintained separately to reduce duplication and integration conflicts.

## Milestone Scope

### M1 — Ticket Intake and Classification

Responsible for receiving and processing tickets and identifying the nature and urgency of reported issues.

Key functionality:
- Ticket ingestion and structured data handling.
- Banking77-based ticket classification.
- Severity and priority handling.
- Classification confidence scores.
- Model training and evaluation.

Folder: `milestones/m1_ticket_classification/`

### M2 — Knowledge Retrieval and RAG

Responsible for retrieving relevant information and providing knowledge-grounded resolution suggestions.

Key functionality:
- Banking knowledge-base integration.
- TF-IDF-based document retrieval.
- Cosine-similarity ranking.
- Context assembly using retrieved documents.
- AI-assisted resolution generation.

Folder: `milestones/m2_knowledge_retrieval/`

### M3 — Multi-Agent Workflow and Integrations

Responsible for coordinating specialized agents and connecting the resolution workflow with external support services.

Key functionality:
- Diagnosis and retrieval coordination.
- Resolution generation and validation.
- Escalation decisions.
- Jira ticket integration.
- SMTP email automation.

Folder: `milestones/m3_multi_agent_integrations/`

### M4 — Analytics and Monitoring

Responsible for evaluating support operations and monitoring system performance.

Key functionality:
- Database-backed analytics and KPIs.
- Ticket trends and distributions.
- Resolution and escalation metrics.
- Response-time measurements.
- Monitoring, testing, and optimization.

Folder: `milestones/m4_analytics_monitoring/`

Analytics must use actual stored data. User-facing analytics must respect the authenticated user's ticket ownership and authorization; global metrics should be available only through an appropriately authorized administrative view.

For detailed ownership and contribution guidelines, see [`milestones/README.md`](milestones/README.md) and the README inside each milestone folder.

## Repository Structure

```text
FinCareAI/
├── app.py
├── config.py
├── database.py
├── auth.py
├── classifier.py
├── agents.py
├── analytics.py
├── email_service.py
├── jira_service.py
├── requirements.txt
├── .env.example
├── .gitignore
├── README.md
│
├── milestones/
│   ├── README.md
│   ├── m1_ticket_classification/
│   │   ├── README.md
│   │   ├── classifier.py
│   │   ├── train_model.py
│   │   ├── evaluate_model.py
│   │   ├── check_model.py
│   │   ├── models/
│   │   └── dataset/
│   │
│   ├── m2_knowledge_retrieval/
│   │   ├── README.md
│   │   └── rag/
│   │       ├── analyzer.py
│   │       ├── retriever.py
│   │       ├── generator.py
│   │       └── pipeline.py
│   │
│   ├── m3_multi_agent_integrations/
│   │   ├── README.md
│   │   ├── agents.py
│   │   ├── jira_service.py
│   │   └── email_service.py
│   │
│   └── m4_analytics_monitoring/
│       ├── README.md
│       └── analytics.py
│
├── knowledge_base/
│   └── banking_support_fraud.json
│
├── data/
│   └── transactions.json
│
├── templates/
├── static/
│   ├── css/
│   ├── js/
│   └── images/
│
└── tests/
    ├── conftest.py
    ├── unit/
    ├── integration/
    └── security/
```

*Note: This is the intended logical structure. Refer to the actual repository contents and milestone README files for the definitive list of files.*

### Shared Application Components

The root-level application files provide shared functionality:

- `app.py` — Flask application, routes, and workflow orchestration.
- `config.py` — Environment configuration and shared paths.
- `database.py` — SQLite schema initialization and data-access functions.
- `auth.py` — Authentication and authorization helpers.
- `templates/` — Shared Flask/Jinja templates.
- `static/` — Shared stylesheets, JavaScript, and branding assets.

Root-level compatibility modules preserve existing import paths where required. Avoid duplicating shared functionality inside individual milestone folders.

## Technology Stack

| Component | Technology |
|---|---|
| Programming language | Python |
| Web framework | Flask |
| Machine learning | Scikit-learn |
| Text retrieval | TF-IDF and cosine similarity |
| AI resolution generation | Configured Groq LLM service |
| Database | SQLite |
| Frontend | HTML, CSS, JavaScript, Bootstrap/Jinja templates |
| Ticket integration | Jira REST API |
| Email integration | SMTP |
| Testing | Pytest |

## Requirements

- Python 3.11 recommended.
- Dependencies listed in `requirements.txt`.
- Scikit-learn version `1.5.2` is pinned to match the serialized classifier artifact.
- Internet connectivity is required for configured external services, such as Groq and Jira.
- Local application startup and automated tests should not depend on live integrations unless explicitly configured.

## Installation and Setup

### 1. Clone the repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd <YOUR_REPOSITORY_FOLDER>
```

Replace the placeholders with your actual repository URL and folder name.

### 2. Create a virtual environment

**Windows PowerShell**

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

**macOS/Linux**

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

**Windows PowerShell**

```powershell
Copy-Item .env.example .env
```

**macOS/Linux**

```bash
cp .env.example .env
```

Edit `.env` and provide the required configuration.

At a minimum, configure fresh, unique values for:

- `SECRET_KEY`
- `JWT_SECRET`

For live AI resolution, configure `GROQ_API_KEY` and any related provider settings required by the application.

Jira and SMTP credentials are optional for local development unless you intend to test those integrations live. Keep Jira simulation enabled during development when supported by the current configuration.

**Security:** Never commit `.env` or share real credentials in source code, screenshots, logs, or team messages. Use `.env.example` only for safe placeholder values.

### 5. Initialize local data

The application initializes its SQLite database according to its existing startup logic.

The source package intentionally excludes local database files. Each developer should use a local database, and tests should use an isolated test database.

Do not copy production or personal ticket data into the repository.

## Running the Application

From the repository root, activate the virtual environment and run:

```bash
python app.py
```

Open the application in your browser:

[http://127.0.0.1:5000](http://127.0.0.1:5000)

If the configured port differs, use the address printed by Flask at startup.

## Running Tests

All automated tests belong under `tests/`.

Run the complete test suite from the repository root:

```bash
pytest tests/
```

Run individual test groups when debugging:

```bash
pytest tests/unit/
pytest tests/integration/
pytest tests/security/
```

Examples of focused tests, if these files exist in the current checkout:

```bash
pytest tests/unit/test_classifier.py
pytest tests/unit/test_rag.py
pytest tests/integration/test_analytics.py
pytest tests/integration/test_metrics.py
pytest tests/integration/test_escalation.py
pytest tests/security/test_customer_scoping.py
```

### Testing Guidelines

- Use isolated test data and temporary databases.
- Mock Groq, Jira, and SMTP integrations by default.
- Never send real emails or create external Jira issues during the standard test run.
- Keep unit tests, integration tests, and security tests inside `tests/`.
- Remove duplicate tests only after verifying that their behavior is covered elsewhere.
- Run the complete suite after changing shared database schemas, routes, or cross-milestone interfaces.

A successful test run should be verified from actual command output. Do not treat previous test reports as proof that the current checkout passes.

## Model Training and Evaluation

Run model training and evaluation from the repository root using the actual package/module paths available in the checkout.

If the milestone modules are configured as Python packages, the commands may be:

```bash
python -m milestones.m1_ticket_classification.train_model
python -m milestones.m1_ticket_classification.evaluate_model
```

If those commands are unsupported by the current folder structure, use the corresponding script paths documented in the M1 README.

Training can overwrite the model artifact used by the application. Coordinate model changes with the team, review evaluation results, and run classifier tests before committing an updated model.

Report measured accuracy, precision, and recall from actual evaluation data rather than illustrative values.

## Milestone-Based Development

Each milestone should own its feature-specific implementation while shared application components remain centralized.

| Area | Ownership |
|---|---|
| M1 | Classification, model training, severity/priority logic |
| M2 | Retrieval, context construction, RAG pipeline |
| M3 | Multi-agent orchestration, Jira, email integrations |
| M4 | Analytics calculations, monitoring and performance metrics |
| Shared | Flask routes, authentication, database schema, templates and common configuration |
| Tests | All unit, integration, end-to-end and security tests under `tests/` |

### Team Collaboration Guidelines

1. Create a separate Git branch for each feature or assigned task.
2. Review the relevant milestone README before modifying files.
3. Avoid editing shared files unnecessarily.
4. Coordinate changes to database schemas, configuration keys, API contracts, and common templates.
5. Do not create duplicate implementations of shared modules in different milestone folders.
6. Commit only the files required for your change.
7. Run relevant tests before pushing.
8. Merge milestone branches into the integration branch in a controlled order.
9. Run the full test suite after merging.
10. Resolve conflicts by reviewing functionality and tests rather than blindly accepting one side.

**Important:** Folder separation reduces unnecessary overlap, but it cannot guarantee conflict-free merges. Changes to shared files and interfaces still require coordination.

## Data and Security Guidelines

- **Secrets:** Keep `.env` untracked and use fresh credentials.
- **Databases:** Do not commit local `*.db` files containing user or ticket information.
- **Backups:** Keep required backups in a secure location outside the shared source package.
- **Datasets:** Preserve datasets needed for training and evaluation.
- **Models:** Retain the trained classifier artifact required by the application.
- **Knowledge base:** Preserve the knowledge corpus used by retrieval.
- **Generated files:** Do not commit `__pycache__/`, `.pytest_cache/`, temporary logs, or editor-specific files.
- **Tests:** Do not leave experimental scripts at the repository root when they belong in `tests/` or are no longer needed.
- **Authorization:** Ensure ticket and analytics APIs enforce authenticated-user ownership and administrative permissions.

## Troubleshooting

### Dependency or model-loading errors

Verify the active Python environment and installed dependency versions:

```bash
python --version
python -m pip show scikit-learn
pip check
```

Use the pinned Scikit-learn version when loading the supplied serialized model.

### Missing environment variables

Check `.env.example`, create a local `.env`, and provide the required configuration. Never resolve missing configuration by hardcoding credentials.

### Tests fail after a merge

1. Activate the intended virtual environment.
2. Install the current requirements.
3. Review the failing test and changed shared interfaces.
4. Confirm that tests use isolated databases and mocked integrations.
5. Fix the root cause and rerun the affected tests.
6. Run `pytest tests/` before merging or submitting the change.

### RAG retrieval or knowledge-base errors

Verify the configured knowledge-base path and JSON format. Keep the full corpus available to the retrieval pipeline; frontend pagination should not restrict the documents available to RAG.

---

## Project Status

This repository represents the implementation scope through **Milestones 1–4**. Feature completeness, integration health, and test status must be confirmed against the current code and actual test results.

For additional implementation details, consult the README files in the individual milestone folders.