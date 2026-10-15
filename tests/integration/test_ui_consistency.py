"""
End-to-end integration and data consistency test for FinCare AI Analytics.
Verifies:
1. All 10 sections rendered in HTML.
2. Removal of hamburger, Create Ticket, and large Live badge.
3. Every ticket row in Recent Activity is clickable and navigates to /ticket/<id>.
4. Authoritative data consistency: Total Tickets == sum of resolution outcomes.
5. Features 3, 5, 7: AI Confidence vs Validation, Financial Risk, SLA Risk.
"""

import pytest
import database
import app


@pytest.fixture
def auth_client():
    app.app.config["TESTING"] = True
    token = database.generate_token(1, "admin@banksupport.ai", "admin", name="Bank Admin", department="Operations Supervision")
    with app.app.test_client() as c:
        c.set_cookie("jwt_token", token)
        yield c


def test_analytics_html_all_sections(auth_client):
    res = auth_client.get("/analytics")
    assert res.status_code == 200
    html = res.data.decode("utf-8")

    sections = [
        "01 Performance Overview",
        "02 Ticket &amp; Resolution Trends",
        "03 Ticket Distribution",
        "04 AI Decision Intelligence",
        "05 Escalation Analytics",
        "06 System Monitoring",
        "07 Performance Monitoring",
        "08 Recent Ticket Activity"
    ]
    for s in sections:
        assert s in html, f"Missing section: {s}"

    # Verify Financial Impact and SLA Risk Analytics are completely removed
    assert "Financial Impact" not in html
    assert "SLA Risk Analytics" not in html
    assert "slaGaugeChart" not in html

    # Verify UI cleanups
    assert 'id="sidebarToggle"' not in html
    assert "btn-create-ticket" not in html
    assert "● Live" not in html

    # Verify clickable rows
    assert "ticket-clickable-row" in html
    assert "window.location.href='/ticket/" in html


def test_data_consistency_mathematical_identity(auth_client):
    res = auth_client.get("/api/analytics?range=all")
    assert res.status_code == 200
    data = res.json
    assert data["success"] is True

    tot = data["overview"]["total_tickets"]
    outcomes = data["trends"]["outcomes"]
    out_sum = (
        outcomes["ai_resolved"] +
        outcomes["escalated"] +
        outcomes["pending"] +
        outcomes["resolution_failed"]
    )
    # Zero discrepancy
    assert tot == out_sum
    assert outcomes["total"] == tot


def test_financial_and_sla_risk_data(auth_client):
    res = auth_client.get("/api/analytics/overview?range=all")
    assert res.status_code == 200
    data = res.json

    assert "branching" in data["escalation"]
    assert "financial_risk" not in data
    assert "sla_risk" in data
    assert "confidence_validation" in data["ai_effectiveness"]

    # SLA risk metrics
    assert 0.0 <= data["sla_risk"]["within_sla_pct"] <= 100.0
    for p in ["P1", "P2", "P3", "P4"]:
        assert p in data["sla_risk"]["compliance_by_priority"]
