# FinCare AI — Milestone Architecture & Team Collaboration Guide

This document maps all repository files to their respective milestones (M1–M4) based on the official presentation slides (`ref ppt/`), outlines the modular architecture in `milestones/`, details the Git branch and merge strategy to prevent team merge conflicts, and explains how to export self-contained ZIP archives for each milestone.

---

## 🗺️ Milestone Component Mapping (Based on PPTs)

### 📌 Milestone 1: Ticket Ingestion & Smart Classification

- **Core Scope**: Web ticket intake, Scikit-Learn TF-IDF classifier on Banking77, severity prediction (Low, Medium, High), SLA priority calculation (P1–P4), confidence scoring, SQLite database persistence (`users` & `tickets`).
- **Milestone 1 Files**:
  - `milestones/m1_ticket_classification/classifier.py` — Ticket classification logic, severity keywords, SLA priority rules
  - `milestones/m1_ticket_classification/train_model.py` — ML model training pipeline using TF-IDF + Logistic Regression
  - `milestones/m1_ticket_classification/evaluate_model.py` — Model evaluation script (accuracy & classification metrics)
  - `milestones/m1_ticket_classification/check_model.py` — Inspection tool for classes in `banking77_classifier.pkl`
  - `milestones/m1_ticket_classification/models/banking77_classifier.pkl` — Trained Scikit-Learn model binary
  - `milestones/m1_ticket_classification/dataset/banking77/train.csv` & `test.csv` — Training and benchmark datasets
  - `classifier.py` — Root compatibility re-export wrapper
  - `data/transactions.json` — Reference bank transactions
  - `database.py` — SQLite tables initialization (`users`, `tickets`) and query methods
  - `templates/index.html` — Ticket submission portal
  - `templates/tickets.html` — Ticket list table
  - `templates/login.html` & `templates/signup.html` — Authentication interfaces
  - `tests/unit/test_classifier.py` — Classifier & severity unit test suite

---

### 📌 Milestone 2: Enterprise Knowledge Base & RAG Retrieval

- **Core Scope**: Domain banking knowledge base, TF-IDF + Cosine similarity retrieval, context augmentation, Groq LLM resolution generation (`openai/gpt-oss-120b`), RAG retrieval accuracy and similarity metrics (`rag_results` table).
- **Milestone 2 Files**:
  - `milestones/m2_knowledge_retrieval/rag/analyzer.py` — Ticket keyword analysis & query tokenization
  - `milestones/m2_knowledge_retrieval/rag/retriever.py` — Knowledge base TF-IDF cosine similarity search engine
  - `milestones/m2_knowledge_retrieval/rag/generator.py` — Resolution step synthesis using Groq LLM
  - `milestones/m2_knowledge_retrieval/rag/pipeline.py` — End-to-end RAG orchestrator
  - `rag/` — Root compatibility re-export package
  - `knowledge_base/banking_knowledge.json` — Baseline 8-article reference KB
  - `knowledge_base/banking_support_fraud.json` — Comprehensive 300-article domain KB
  - `templates/knowledge_base.html` — Knowledge base search and exploration UI
  - `templates/ticket_detail.html` — Ticket view with RAG retrieval citations
  - `tests/unit/test_rag.py` — RAG retriever & similarity test suite

---

### 📌 Milestone 3: Multi-Agent Resolution Framework & Integrations

- **Core Scope**: 5-Agent collaborative workflow (DiagnosisAgent → RetrievalAgent → ResolutionAgent → ValidationAgent → EscalationAgent), automated Atlassian Jira issue creation on escalation, SMTP email notifications to customers.
- **Milestone 3 Files**:
  - `milestones/m3_multi_agent_integrations/agents.py` — Sequential multi-agent architecture and orchestrator
  - `milestones/m3_multi_agent_integrations/jira_service.py` — Atlassian Jira REST API client
  - `milestones/m3_multi_agent_integrations/email_service.py` — SMTP email notification client
  - `agents.py`, `jira_service.py`, `email_service.py` — Root compatibility re-export wrappers
  - `templates/ai_agent.html` — Multi-agent interactive execution visualizer
  - `tests/unit/test_agents.py` — Multi-agent execution and coordination tests
  - `tests/integration/test_escalation.py` — Jira issue creation & SMTP trigger tests

---

### 📌 Milestone 4: Support Analytics Dashboard & Live Monitoring

- **Core Scope**: 100% database-driven operational KPIs, time-series ingestion trends, resolution outcomes (AI Resolved, Escalated, Pending, Failed), category distributions, Risk Heatmap, AI Decision Intelligence, Escalation branching funnel, microservice health monitoring, and dynamic system settings.
- **Milestone 4 Files**:
  - `milestones/m4_analytics_monitoring/analytics.py` — SQLite aggregation engine for all 8 analytics sections
  - `analytics.py` — Root compatibility re-export wrapper
  - `templates/analytics.html` — Comprehensive 8-section analytics dashboard
  - `templates/dashboard.html` — Operational overview command center
  - `templates/settings.html` — Dynamic runtime configuration manager
  - `templates/profile.html` — User profile & notification preferences
  - `tests/integration/test_analytics.py` — Database KPI aggregation tests
  - `tests/integration/test_metrics.py` — Formula verification & mathematical identity tests
  - `tests/integration/test_ui_consistency.py` — Analytics section consistency tests
  - `tests/security/test_customer_scoping.py` — Multi-tenant ticket privacy tests
  - `tests/integration/test_audit_phases.py` — M1–M4 cross-milestone audit suite
  - `tests/integration/test_e2e_full_cycle.py` — Complete 15-stage end-to-end integration test

---
