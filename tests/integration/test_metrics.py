"""
Tests for Core KPI Metrics & Formulas
Validates that Total Tickets, Resolution Rates, P95, and CSAT follow exact M4 mathematical rules.
"""

import pytest
from database import get_connection
from analytics import (
    get_performance_overview,
    get_performance_monitoring,
    get_ai_effectiveness
)


def test_core_kpi_formulas():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM tickets")
    db_total = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM tickets WHERE status = 'Resolved'")
    db_resolved = c.fetchone()[0]

    overview = get_performance_overview(conn, None, None, None, None)
    conn.close()

    assert overview['total_tickets'] == db_total
    expected_rate = round((db_resolved / db_total) * 100, 1) if db_total > 0 else 0.0
    assert overview['ai_resolution_rate'] == expected_rate


def test_p95_response_time():
    conn = get_connection()
    perf = get_performance_monitoring(conn, None, None)
    conn.close()

    assert perf['avg_response_time'] > 0
    assert perf['p95_response_time'] >= perf['avg_response_time']
    assert perf['rag_retrieval_time'] > 0
    assert perf['rag_resolution_time'] > 0


def test_customer_satisfaction_not_fake():
    conn = get_connection()
    eff = get_ai_effectiveness(conn, None, None)
    conn.close()

    # Rule: If no customer feedback in DB, CSAT must be 'N/A' (NEVER a fake 4.5/5)
    assert eff['customer_satisfaction'] in ['N/A', '5.0 / 5.0', '4.0 / 5.0']
    if eff['customer_satisfaction'] == 'N/A':
        assert 'No customer feedback' in eff['csat_subtext']
