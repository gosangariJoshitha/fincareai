"""
Tests for NLP Intent Classification Model
Validates Banking77 predictions, probabilities, and confidence score outputs.
"""

import pytest
from classifier import classify_ticket


def test_classifier_prediction():
    text = "Someone stole my wallet and used my debit card to withdraw cash without authorization"
    category, confidence = classify_ticket(text)

    assert category is not None
    assert isinstance(category, str)
    assert len(category) > 0

    # Confidence must be a valid percentage
    assert 0.0 <= confidence <= 100.0


def test_classifier_fraud_detection():
    text = "Unauthorized transaction on my card. My account is compromised!"
    category, confidence = classify_ticket(text)

    assert category is not None
    assert any(term in category for term in ["card", "transaction", "unauthorised", "compromised", "fraud", "cash", "payment"])
    assert 0.0 <= confidence <= 100.0
