"""
Tests for M4 Analytics Service (analytics.py)
Validates that calculations are 100% database driven and comparisons conform to M4 specs.
"""

import pytest
import sqlite3
import datetime
from analytics import (
    get_date_range_bounds,
    calc_comparison,
    get_complete_analytics_data,
    get_system_monitoring_status
)


def test_date_range_bounds():
    # Test 'today'
    c_start, c_end, p_start, p_end = get_date_range_bounds('today')
    assert c_start is not None
    assert c_end is not None
    assert p_start is not None
    assert p_end is not None

    # Test 'all'
    c_start, c_end, p_start, p_end = get_date_range_bounds('all')
    assert c_start is None
    assert p_start is None

    # Test '7d'
    c_start, c_end, p_start, p_end = get_date_range_bounds('7d')
    assert c_start < c_end
    assert p_start < p_end


def test_comparison_logic():
    # Test increase
    res_up = calc_comparison(120, 100)
    assert res_up['direction'] == 'up'
    assert res_up['value'] == 20.0
    assert '↑ 20.0%' in res_up['formatted']

    # Test decrease
    res_down = calc_comparison(80, 100)
    assert res_down['direction'] == 'down'
    assert res_down['value'] == 20.0
    assert '↓ 20.0%' in res_down['formatted']

    # Test insufficient previous data returns '—' (never 0%)
    res_none = calc_comparison(100, None)
    assert res_none['direction'] == 'neutral'
    assert res_none['formatted'] == '—'

    res_zero = calc_comparison(100, 0)
    assert res_zero['direction'] == 'neutral'
    assert res_zero['formatted'] == '—'


def test_complete_analytics_data():
    data = get_complete_analytics_data('all')
    assert data is not None
    assert 'overview' in data
    assert 'trends' in data
    assert 'distribution' in data
    assert 'ai_effectiveness' in data
    assert 'escalation' in data
    assert 'monitoring' in data
    assert 'performance' in data
    assert 'events' in data
    assert 'recent_tickets' in data

    # Verify overview counts and data consistency
    overview = data['overview']
    assert overview['total_tickets'] >= 0
    assert 0.0 <= overview['ai_resolution_rate'] <= 100.0
    assert overview['escalated'] >= 0

    # Strict outcome consistency (No 96 vs 74 discrepancies)
    outcomes = data['trends']['outcomes']
    outcome_sum = (
        outcomes['ai_resolved'] +
        outcomes['escalated'] +
        outcomes['pending'] +
        outcomes['resolution_failed']
    )
    assert outcome_sum == overview['total_tickets']
    assert outcomes['total'] == overview['total_tickets']

    # Features 3, 5, 7 assertions
    assert 'branching' in data['escalation']
    assert 'sla_risk' in data
    assert 'confidence_validation' in data['ai_effectiveness']
    assert 0.0 <= data['sla_risk']['within_sla_pct'] <= 100.0


def test_system_monitoring_health():
    mon = get_system_monitoring_status()
    for sys_key in ['api', 'database', 'ai_pipeline', 'knowledge_base', 'jira', 'smtp']:
        assert sys_key in mon
        assert 'status' in mon[sys_key]
        assert 'badge' in mon[sys_key]
        assert mon[sys_key]['is_operational'] is True
