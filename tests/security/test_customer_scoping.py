import pytest
import sqlite3
import time
from app import app
from database import (
    create_user, login_user, insert_ticket, get_connection,
    get_tickets_paginated, get_dashboard_today_stats
)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def unique_time():
    return int(time.time() * 1000)


def test_customer_ticket_scoping(client):
    ts = unique_time()
    email_a = f"cust_a_{ts}@banktest.com"
    email_b = f"cust_b_{ts}@banktest.com"
    pwd = "Password123!"

    # Create two customer accounts
    create_user("Customer Alpha", email_a, pwd, role="user", department="Personal Banking")
    create_user("Customer Beta", email_b, pwd, role="user", department="Personal Banking")

    # Insert a ticket for Customer Alpha
    ticket_id_a = insert_ticket(
        customer_name="Customer Alpha",
        email=email_a,
        title=f"Alpha Unauthorized Debit {ts}",
        description="Amount debited without notification",
        category="Card Fraud",
        severity="High",
        priority="P1",
        confidence=96.5,
        resolution="Blocking card immediately."
    )

    # Insert a ticket for Customer Beta
    ticket_id_b = insert_ticket(
        customer_name="Customer Beta",
        email=email_b,
        title=f"Beta Cheque Deposit {ts}",
        description="Cheque clearance query",
        category="Deposit Services",
        severity="Low",
        priority="P3",
        confidence=88.0,
        resolution="Cleared in 24 hours."
    )

    # 1. Verify DB query scoping directly
    res_a = get_tickets_paginated(user_email=email_a)
    assert res_a["total_count"] >= 1
    for t in res_a["tickets"]:
        assert t["email"].lower() == email_a.lower()

    res_b = get_tickets_paginated(user_email=email_b)
    assert res_b["total_count"] >= 1
    for t in res_b["tickets"]:
        assert t["email"].lower() == email_b.lower()

    # 2. Login as Customer Alpha and verify /tickets route only shows Alpha's tickets
    login_a = login_user(email_a, pwd)
    assert login_a["success"] is True
    client.set_cookie("jwt_token", login_a["token"])

    page_a = client.get("/tickets")
    assert page_a.status_code == 200
    html_a = page_a.data.decode("utf-8")
    assert f"Alpha Unauthorized Debit {ts}" in html_a
    assert f"Beta Cheque Deposit {ts}" not in html_a

    # 3. Customer Alpha accessing Customer Beta's ticket details must be denied
    detail_b = client.get(f"/ticket/{ticket_id_b}", follow_redirects=False)
    # Should redirect with unauthorized notice
    assert detail_b.status_code in (302, 403)

    # Customer Alpha accessing their own ticket must succeed
    detail_a = client.get(f"/ticket/{ticket_id_a}")
    assert detail_a.status_code == 200

    # 4. Customer Alpha accessing Customer Beta's ticket API must return 403 Forbidden
    api_b = client.get(f"/api/ticket/{ticket_id_b}")
    assert api_b.status_code == 403

    api_a = client.get(f"/api/ticket/{ticket_id_a}")
    assert api_a.status_code == 200

    # 5. Customer Beta login check
    login_b = login_user(email_b, pwd)
    client.set_cookie("jwt_token", login_b["token"])

    page_b = client.get("/tickets")
    assert page_b.status_code == 200
    html_b = page_b.data.decode("utf-8")
    assert f"Beta Cheque Deposit {ts}" in html_b
    assert f"Alpha Unauthorized Debit {ts}" not in html_b

    # 6. Admin / Support desk user can view both
    admin_email = f"admin_{ts}@banktest.com"
    create_user("Bank Admin", admin_email, pwd, role="admin", department="Operations Supervision")
    login_admin = login_user(admin_email, pwd)
    client.set_cookie("jwt_token", login_admin["token"])

    page_admin = client.get("/tickets")
    assert page_admin.status_code == 200
    html_admin = page_admin.data.decode("utf-8")
    assert f"Alpha Unauthorized Debit {ts}" in html_admin
    assert f"Beta Cheque Deposit {ts}" in html_admin

    # 7. Verify Dashboard Total Tickets reflects only tickets done by that user
    # Login back as Customer Alpha
    client.set_cookie("jwt_token", login_a["token"])
    dash_a = client.get("/dashboard")
    assert dash_a.status_code == 200
    html_dash_a = dash_a.data.decode("utf-8")
    # Customer Alpha has exactly 1 ticket created in this test, so Total Tickets must be 1, not the overall desk total
    assert '<h2 id="totalCount">1</h2>' in html_dash_a
    assert email_a in html_dash_a

    # Verify api/stats for Customer Alpha also scopes to Customer Alpha
    api_stats_a = client.get("/api/stats")
    assert api_stats_a.status_code == 200
    stats_data_a = api_stats_a.get_json()
    assert stats_data_a["total_tickets"] == 1

    # Login as Customer Beta
    client.set_cookie("jwt_token", login_b["token"])
    dash_b = client.get("/dashboard")
    assert dash_b.status_code == 200
    html_dash_b = dash_b.data.decode("utf-8")
    assert '<h2 id="totalCount">1</h2>' in html_dash_b
    assert email_b in html_dash_b

    # 8. Verify Analytics page and API reflect only tickets done by that user
    # Customer Alpha
    client.set_cookie("jwt_token", login_a["token"])
    analytics_page_a = client.get("/analytics")
    assert analytics_page_a.status_code == 200
    html_an_a = analytics_page_a.data.decode("utf-8")
    assert email_a in html_an_a
    assert '<div class="hero-kpi-value" id="kpiTotalTickets">1</div>' in html_an_a

    api_an_a = client.get("/api/analytics/overview?range=all")
    assert api_an_a.status_code == 200
    an_data_a = api_an_a.get_json()
    assert an_data_a["success"] is True
    assert an_data_a["overview"]["total_tickets"] == 1
    assert an_data_a["trends"]["outcomes"]["total"] == 1
    assert len(an_data_a["recent_tickets"]) == 1
    assert an_data_a["recent_tickets"][0]["id"] == ticket_id_a

    # Customer Beta
    client.set_cookie("jwt_token", login_b["token"])
    analytics_page_b = client.get("/analytics")
    assert analytics_page_b.status_code == 200
    html_an_b = analytics_page_b.data.decode("utf-8")
    assert email_b in html_an_b
    assert '<div class="hero-kpi-value" id="kpiTotalTickets">1</div>' in html_an_b

    api_an_b = client.get("/api/analytics/overview?range=all")
    assert api_an_b.status_code == 200
    an_data_b = api_an_b.get_json()
    assert an_data_b["overview"]["total_tickets"] == 1
    assert an_data_b["recent_tickets"][0]["id"] == ticket_id_b

    # Admin with scope=all sees both Alpha and Beta
    client.set_cookie("jwt_token", login_admin["token"])
    api_an_all = client.get("/api/analytics/overview?range=all&scope=all")
    assert api_an_all.status_code == 200
    an_data_all = api_an_all.get_json()
    assert an_data_all["overview"]["total_tickets"] >= 2
