"""
Tests for 5-Agent Multi-Agent Lifecycle
Validates Diagnosis, Retrieval, Resolution, Validation Gate, and Routing Outcomes.
"""

import pytest
from agents import BankSupportAI


def test_bank_support_ai_workflow():
    agent = BankSupportAI(threshold=70.0)

    # Test complete multi-agent pipeline
    query = "How do I check my account balance online?"
    result = agent.process_query(query)

    assert result is not None
    assert "diagnosis" in result
    assert "retrieval" in result
    assert "resolution" in result
    assert "validation" in result
    assert "escalation" in result

    # Validation contains weighted score
    val = result["validation"]
    assert "score" in val
    assert "status" in val
    assert val["status"] in ["AUTO_RESOLVE", "ESCALATE"]
