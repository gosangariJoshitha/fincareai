import pytest
import sqlite3
import json
import time
from app import app
from database import (
    create_user, login_user, get_user_by_id, update_user_profile,
    get_tickets_paginated, get_all_tickets, mark_all_notifications_as_read,
    get_unread_notification_count, add_notification
)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def os_time():
    return int(time.time() * 1000)


# ==============================================================================
# PHASE 8: Signup, Department, and Profile Persistence Tests
# ==============================================================================

def test_signup_with_department(client):
    unique_email = f"test_user_{os_time()}@example.com"
    res = client.post("/signup", data={
        "name": "Audit Test User",
        "email": unique_email,
        "department": "Fraud & Risk Investigation",
        "password": "SecurePassword123!",
        "confirm_password": "SecurePassword123!"
    }, follow_redirects=True)
    assert res.status_code == 200

    # Verify user exists in database with the department
    login_res = login_user(unique_email, "SecurePassword123!")
    assert login_res["success"] is True
    user = login_res["user"]
    assert user["department"] == "Fraud & Risk Investigation"

    # Verify get_user_by_id returns department
    db_user = get_user_by_id(user["user_id"])
    assert db_user["department"] == "Fraud & Risk Investigation"


def test_signup_missing_department_fails(client):
    res = client.post("/signup", data={
        "name": "No Dept User",
        "email": f"nodept_{os_time()}@example.com",
        "department": "",
        "password": "SecurePassword123!",
        "confirm_password": "SecurePassword123!"
    })
    assert res.status_code == 200
    assert b"All fields are required" in res.data


def test_profile_update_department(client):
    email = f"updept_{os_time()}@example.com"
    reg = create_user("Dept Update", email, "SecurePass123!", "user", "Banking Operations & Support")
    assert reg["success"] is True
    uid = reg["user_id"]

    # Update department
    ok = update_user_profile(uid, "Dept Update", "Card Services & Disputes")
    assert ok is True

    u = get_user_by_id(uid)
    assert u["department"] == "Card Services & Disputes"


# ==============================================================================
# PHASE 6: My Tickets Server-Side Pagination Tests
# ==============================================================================

def test_tickets_pagination_database():
    # Page 1 with per_page=5
    res1 = get_tickets_paginated(page=1, per_page=5)
    assert len(res1["tickets"]) <= 5
    assert res1["total_count"] > 0
    assert res1["page"] == 1
    assert res1["total_pages"] >= 1
    assert "summary" in res1
    assert res1["summary"]["total"] >= res1["total_count"]

    if res1["total_pages"] > 1:
        # Page 2
        res2 = get_tickets_paginated(page=2, per_page=5)
        assert len(res2["tickets"]) <= 5
        assert res2["page"] == 2
        # Ensure Page 1 and Page 2 have distinct tickets
        t1_ids = {t["ticket_id"] for t in res1["tickets"]}
        t2_ids = {t["ticket_id"] for t in res2["tickets"]}
        assert len(t1_ids.intersection(t2_ids)) == 0


def test_tickets_pagination_filter():
    res_resolved = get_tickets_paginated(page=1, per_page=10, status="Resolved")
    for t in res_resolved["tickets"]:
        assert t["status"] == "Resolved"

    res_escalated = get_tickets_paginated(page=1, per_page=10, status="Escalated")
    for t in res_escalated["tickets"]:
        assert t["status"] == "Escalated"


# ==============================================================================
# PHASE 7: Knowledge Base Server-Side Pagination Tests
# ==============================================================================

def test_knowledge_base_route_pagination(client):
    # Log in first
    email = f"kb_tester_{os_time()}@example.com"
    create_user("KB Tester", email, "Password123!", "user")
    login = client.post("/login", data={"email": email, "password": "Password123!"}, follow_redirects=True)
    assert login.status_code == 200

    # Request Page 1 with per_page=10
    res = client.get("/knowledge-base?page=1&per_page=10")
    assert res.status_code == 200
    assert b"Showing" in res.data
    assert b"of <strong>300</strong> articles" in res.data

    # Request Page 2 with per_page=10
    res2 = client.get("/knowledge-base?page=2&per_page=10")
    assert res2.status_code == 200
    assert b"Showing <strong>11</strong> to <strong>20</strong>" in res2.data

    # Request search
    res_search = client.get("/knowledge-base?search=atm")
    assert res_search.status_code == 200
    assert b"Showing" in res_search.data


# ==============================================================================
# PHASE 2: Notifications Persistence Tests
# ==============================================================================

def test_notifications_mark_all_read():
    uid = 999999
    add_notification("Test Notif 1", "Detail 1", ticket_id=1, user_id=uid)
    add_notification("Test Notif 2", "Detail 2", ticket_id=2, user_id=uid)

    unread_before = get_unread_notification_count(uid)
    assert unread_before >= 2

    mark_all_notifications_as_read(uid)

    unread_after = get_unread_notification_count(uid)
    assert unread_after == 0


# ==============================================================================
# PHASE 5: Isolated Workflow Tests with Mocked External Integrations
# ==============================================================================

def test_workflow_ai_resolved_email_branch(client):
    from unittest.mock import patch
    from database import get_ticket_by_id

    # Authenticate client
    u_email = f"wf_res_{os_time()}@example.com"
    create_user("Workflow Resolved Tester", u_email, "Password123!", "user")
    client.post("/login", data={"email": u_email, "password": "Password123!"}, follow_redirects=True)

    mock_agent_result = {
        "diagnosis": {"category": "Balance Inquiry", "risk": "Low", "confidence": 95.0},
        "retrieval": {"article": {"title": "Check Balance", "id": 1}, "similarity": 0.88},
        "resolution": {"steps": [{"step": 1, "text": "Open the mobile app and check balance."}]},
        "validation": {"status": "AUTO_RESOLVE", "confidence": 95.0, "score": 95},
        "escalation": False
    }
    mock_pipeline = {
        "response_time": 0.5,
        "workflow_status": "RESOLVED",
        "analysis": {"query": "How to check my account balance online"},
        "retrieved_documents": [{"id": 1, "title": "Check Balance"}],
        "resolution": {"status": "RESOLVED", "steps": [{"step": 1, "text": "Open the mobile app and check balance."}]}
    }

    with patch("app.email_service.send_email", return_value={"success": True, "simulated": False}) as mock_email, \
         patch("app.jira_service.create_ticket") as mock_jira, \
         patch("app.bank_ai.process_ticket", return_value=mock_agent_result), \
         patch("app.run_pipeline", return_value=mock_pipeline):
        
        res = client.post("/add-ticket", data={
            "customer_name": "Suresh Raina",
            "email": "suresh@example.com",
            "title": "How to check my account balance online",
            "description": "Please guide me on how to view my savings account balance through mobile app.",
            "channel": "Mobile App"
        }, headers={"X-Requested-With": "XMLHttpRequest"})
        
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        tid = data["ticket_id"]
        t = get_ticket_by_id(tid)

        assert t["status"] == "Resolved"
        assert not mock_jira.called
        assert t["jira_id"] is None
        assert mock_email.called
        args, kwargs = mock_email.call_args
        assert "Resolution for your banking issue" in args[1]
        assert t["email_status"] == "Sent"
        assert t["resolved_at"] is not None


def test_workflow_escalated_jira_and_email_branch(client):
    from unittest.mock import patch
    from database import get_ticket_by_id

    # Authenticate client
    u_email = f"wf_esc_{os_time()}@example.com"
    create_user("Workflow Esc Tester", u_email, "Password123!", "user")
    client.post("/login", data={"email": u_email, "password": "Password123!"}, follow_redirects=True)

    mock_jira_resp = {"success": True, "ticket_id": "MOCK-101", "key": "MOCK-101", "url": "https://jira.mock/MOCK-101"}
    with patch("app.jira_service.create_ticket", return_value=mock_jira_resp) as mock_jira, \
         patch("app.email_service.send_email", return_value={"success": True, "simulated": False}) as mock_email:
        
        res = client.post("/add-ticket", data={
            "customer_name": "Rohan Mehra",
            "email": "rohan@example.com",
            "title": "URGENT: Unauthorized debit of Rs 50,000",
            "description": "My debit card was charged 50000 at 3 AM while I was sleeping. Fraudulent transaction, block card now!",
            "channel": "Web Portal"
        }, headers={"X-Requested-With": "XMLHttpRequest"})
        
        assert res.status_code == 200
        data = res.get_json()
        assert data["success"] is True
        tid = data["ticket_id"]
        t = get_ticket_by_id(tid)

        assert t["status"] == "Escalated"
        assert mock_jira.called
        assert t["jira_id"] == "MOCK-101"

        # Check escalation acknowledgement email
        assert mock_email.called
        args, kwargs = mock_email.call_args
        to_email, subject, body = args[0], args[1], args[2]
        assert to_email == "rohan@example.com"
        assert "escalated" in subject.lower()
        assert "MOCK-101" in body
        assert t["email_status"] == "Sent"


def test_workflow_jira_failure_handling(client):
    from unittest.mock import patch
    from database import get_ticket_by_id

    # Authenticate client
    u_email = f"wf_jfail_{os_time()}@example.com"
    create_user("Workflow JiraFail Tester", u_email, "Password123!", "user")
    client.post("/login", data={"email": u_email, "password": "Password123!"}, follow_redirects=True)

    mock_fail_resp = {"success": False, "error": "Connection timed out to Atlassian Cloud"}
    with patch("app.jira_service.create_ticket", return_value=mock_fail_resp) as mock_jira, \
         patch("app.email_service.send_email", return_value={"success": True, "simulated": False}) as mock_email:
        
        res = client.post("/add-ticket", data={
            "customer_name": "Pooja Hegde",
            "email": "pooja@example.com",
            "title": "Fraud complaint Rs 25000 unauthorized",
            "description": "Unauthorized online charge detected. Card compromised.",
            "channel": "Phone"
        }, headers={"X-Requested-With": "XMLHttpRequest"})
        
        assert res.status_code == 200
        data = res.get_json()
        tid = data["ticket_id"]
        t = get_ticket_by_id(tid)

        assert t["status"] == "Escalated"
        # Jira failed: jira_id must NOT be set to a fake link or mock key
        assert t["jira_id"] is None

        # Email sent must NOT falsely claim a Jira ticket was created
        if mock_email.called:
            args, _ = mock_email.call_args
            body = args[2]
            assert "Jira Incident Reference:" not in body


def test_workflow_smtp_failure_handling(client):
    from unittest.mock import patch
    from database import get_ticket_by_id

    # Authenticate client
    u_email = f"wf_sfail_{os_time()}@example.com"
    create_user("Workflow SmtpFail Tester", u_email, "Password123!", "user")
    client.post("/login", data={"email": u_email, "password": "Password123!"}, follow_redirects=True)

    mock_fail_smtp = {"success": False, "error": "SMTPAuthenticationError: Bad credentials"}
    with patch("app.email_service.send_email", return_value=mock_fail_smtp), \
         patch("app.jira_service.create_ticket", return_value={"success": True, "key": "MOCK-202"}):
        
        res = client.post("/add-ticket", data={
            "customer_name": "Test User",
            "email": "fail_test@example.com",
            "title": "Inquiry about loan statement",
            "description": "Please send my home loan amortization schedule.",
            "channel": "Web Portal"
        }, headers={"X-Requested-With": "XMLHttpRequest"})
        
        assert res.status_code == 200
        data = res.get_json()
        tid = data["ticket_id"]
        t = get_ticket_by_id(tid)

        # Email failed: status must reflect failure, NOT 'Sent'
        assert t["email_status"] == "Unavailable / Failed"

