# Milestone 2 — Knowledge Retrieval & RAG

**PPT scope:** analyze ticket text, retrieve relevant enterprise knowledge, rank results with TF-IDF/cosine similarity, build context, and generate grounded troubleshooting responses.

## Owned implementation
- `rag/` — analyzer, retriever, context/resolution generator, and pipeline.
- `knowledge_base/` at repository root — shared source corpus used by both M2 retrieval and M3 agents.

## Shared dependencies
- `config.py` — canonical `KB_PATH`, retrieval settings, and provider configuration.
- `app.py` — calls the pipeline from the ticket workflow.
- `database.py` — persists RAG results and timing.

## Commands
```bash
pytest tests/unit/test_rag.py
```

Keep the full knowledge corpus independent of UI pagination. UI page limits must never truncate the RAG retrieval corpus.
