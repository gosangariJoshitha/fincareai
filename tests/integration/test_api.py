"""
Tests for Flask REST APIs
Validates analytics, monitoring, events, and notification endpoints.
"""

import pytest
import database
import app


@pytest.fixture
def client():
    app.app.config["TESTING"] = True
    token = database.generate_token(1, "test@fincare.ai", "User")
    with app.app.test_client() as c:
        c.set_cookie("jwt_token", token)
        yield c


def test_api_analytics_overview(client):
    res = client.get("/api/analytics/overview?range=all")
    assert res.status_code == 200
    data = res.json
    assert data["success"] is True
    assert "overview" in data
    assert "trends" in data
    assert "distribution" in data
    assert "ai_effectiveness" in data


def test_api_analytics_monitoring(client):
    res = client.get("/api/analytics/monitoring")
    assert res.status_code == 200
    data = res.json
    assert data["success"] is True
    assert "monitoring" in data
    for k in ["api", "database", "ai_pipeline", "knowledge_base", "jira", "smtp"]:
        assert k in data["monitoring"]


def test_api_analytics_events(client):
    res = client.get("/api/analytics/events?limit=5")
    assert res.status_code == 200
    data = res.json
    assert data["success"] is True
    assert "events" in data
    assert len(data["events"]) > 0


def test_api_notifications(client):
    res = client.get("/api/notifications")
    assert res.status_code == 200
    data = res.json
    assert data["success"] is True
    assert "notifications" in data
    assert "unread_count" in data
