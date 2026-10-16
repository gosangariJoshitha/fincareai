# Milestone 1 — Ticket Intake & Classification

**PPT scope:** accept and normalize support tickets; classify the issue; calculate severity, priority, and confidence; persist and display the result.

## Owned implementation
- `classifier.py` — Banking77 classifier inference.
- `train_model.py` / `evaluate_model.py` — model training and evaluation.
- `check_model.py` — local model artifact smoke check.
- `milestones/m1_ticket_classification/models/banking77_classifier.pkl` — trained model artifact.
- `milestones/m1_ticket_classification/dataset/banking77/` — train/test data.

## Shared dependencies
- `config.py` — stable model/data paths and runtime configuration.
- `database.py` — ticket/user persistence.
- `app.py` — Flask routes and end-to-end orchestration.

## Commands (from repository root)
```bash
python -m milestones.m1_ticket_classification.evaluate_model
python -m milestones.m1_ticket_classification.train_model
pytest tests/unit/test_classifier.py
```

Do not edit `app.py` or `database.py` for a classifier-only change unless the interface/schema must change; coordinate such changes with the shared-code owner.
