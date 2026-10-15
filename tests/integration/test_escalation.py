"""
Tests for M4 Escalation Analytics
Validates escalation counting, rates, root causes, and routing breakdowns.
"""

import pytest
from database import get_connection
from analytics import get_escalation_analytics


def test_escalation_analytics_calculation():
    conn = get_connection()
    esc = get_escalation_analytics(conn, None, None)
    conn.close()

    assert esc is not None
    assert 'total_escalations' in esc
    assert 'escalation_rate' in esc
    assert 'reasons' in esc
    assert 'routing' in esc

    assert esc['total_escalations'] >= 0
    assert 0.0 <= esc['escalation_rate'] <= 100.0

    # Reasons list should contain real categories
    reasons = esc['reasons']
    assert isinstance(reasons, list)
    reason_names = [r['reason'] for r in reasons]
    assert any('Low AI Confidence' in name for name in reason_names)
    assert any('Critical Priority' in name for name in reason_names)

    # Routing should partition escalations
    routing = esc['routing']
    assert 'jira' in routing
    assert 'human_specialist' in routing
    assert (routing['jira'] + routing['human_specialist']) == esc['total_escalations']
