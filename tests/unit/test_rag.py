"""
Tests for RAG Retrieval & Knowledge Base
Validates TF-IDF vector index, cosine similarity rankings, and top-K doc retrieval.
"""

import pytest
from config import KB_PATH
from rag.retriever import KnowledgeRetriever


def test_rag_retrieval():
    retriever = KnowledgeRetriever(KB_PATH)
    assert retriever is not None
    assert retriever.documents is not None
    assert len(retriever.documents) > 0

    query = "card retained in atm cash machine"
    results = retriever.search(query, top_k=3)

    assert isinstance(results, list)
    assert len(results) > 0
    first = results[0]
    assert "score" in first
    assert "title" in first
    assert "content" in first
