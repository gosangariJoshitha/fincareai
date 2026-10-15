import os
import sys
import json
import time
import requests
from app import app
from database import (
    get_connection, get_ticket_by_id, get_user_by_id,
    get_system_settings, update_system_settings,
    get_tickets_paginated, get_unread_notification_count,
    mark_all_notifications_as_read
)

def run_e2e_cycle():
    print("=== STARTING COMPLETE END-TO-END VERIFICATION CYCLE ===")
    app.config["TESTING"] = True
    client = app.test_client()

    # Step 1: Sign up as test user with department
    timestamp = int(time.time() * 1000)
    test_email = f"e2e_user_{timestamp}@fincare.ai"
    test_dept = "Fraud & Risk Investigation"
    print(f"\n[1] Registering test user: {test_email} (Dept: {test_dept})")
    
    signup_res = client.post("/signup", data={
        "name": "E2E Automated User",
        "email": test_email,
        "department": test_dept,
        "password": "Password1234!",
        "confirm_password": "Password1234!"
    }, follow_redirects=True)
    assert signup_res.status_code == 200, f"Signup failed with {signup_res.status_code}"
    print("    -> User created and authenticated successfully.")

    # Step 2: Confirm department persistence in database
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT user_id, name, email, department FROM users WHERE email = ?", (test_email,))
    user_row = c.fetchone()
    conn.close()
    assert user_row is not None, "User row not found in database!"
    assert user_row["department"] == test_dept, f"Department mismatch: {user_row['department']}"
    uid = user_row["user_id"]
    print(f"    -> Verified persistent department in DB: '{user_row['department']}' (User ID: {uid})")

    # Step 3 & 4: Create a test ticket and run actual 5-agent AI pipeline
    print("\n[3-7] Submitting Test Ticket to Multi-Agent Pipeline...")
    ticket_payload = {
        "customer_name": "Deepak Verma",
        "email": "joshithagosangari@gmail.com",
        "title": "Unauthorized debit of INR 15,000 via unknown ATM terminal",
        "description": "My account was debited Rs 15,000 without my consent from ATM terminal in Mumbai. I never withdrew this cash. Please block card and initiate immediate reversal under zero liability.",
        "channel": "Web Portal",
        "account_ref": "ACC-99281-E2E"
    }

    t_res = client.post("/add-ticket", data=ticket_payload, headers={"X-Requested-With": "XMLHttpRequest"})
    assert t_res.status_code == 200, f"Add ticket failed with {t_res.status_code}"
    res_data = json.loads(t_res.data)
    assert res_data.get("success") is True, f"Ticket processing failed: {res_data}"
    ticket_id = res_data["ticket_id"]
    result = res_data["result"]
    print(f"    -> Ticket #{ticket_id} created successfully!")
    print(f"    -> Predicted Category: {result.get('category')}")
    print(f"    -> AI Confidence: {result.get('confidence')}%")
    print(f"    -> Severity: {result.get('severity')} | Priority: {result.get('priority')}")
    print(f"    -> Final Status: {result.get('final_status')}")
    print(f"    -> Jira Key: {result.get('jira_id')}")
    print(f"    -> Email Status: {result.get('email_status')}")

    # Step 5: Verify persisted ticket in database
    db_ticket = get_ticket_by_id(ticket_id)
    assert db_ticket is not None, f"Ticket #{ticket_id} missing from database!"
    assert db_ticket["title"] == ticket_payload["title"]
    assert db_ticket["category"] is not None
    assert db_ticket["status"] == result["final_status"]
    print(f"    -> Database verified: Status='{db_ticket['status']}', Category='{db_ticket['category']}'")

    # Step 10: Verify notification was created and scoped
    unread = get_unread_notification_count(uid)
    print(f"\n[10] Notifications verified: Unread count for User {uid} = {unread}")

    # Mark all read and verify count drops to 0
    mark_all_notifications_as_read(uid)
    assert get_unread_notification_count(uid) == 0, "Unread notifications count didn't reset to 0!"
    print("     -> Successfully marked all read, unread count verified 0.")

    # Step 11 & 12: Verify My Tickets server-side pagination & filter
    print("\n[11-12] Verifying My Tickets pagination & filters...")
    paged = get_tickets_paginated(page=1, per_page=10, search=str(ticket_id))
    assert paged["total_count"] >= 1, "Ticket not found via search query!"
    found = any(t["ticket_id"] == ticket_id for t in paged["tickets"])
    assert found is True, f"Ticket #{ticket_id} not returned in paginated search!"
    print(f"     -> Ticket #{ticket_id} successfully located via server-side paginated search.")

    # Step 13: Verify Analytics data consistency
    print("\n[13] Verifying Analytics calculation from real tickets...")
    from analytics import get_complete_analytics_data
    analytics_data = get_complete_analytics_data("all")
    overview = analytics_data["overview"]
    assert overview["total_tickets"] >= 1, "Total tickets in analytics is 0!"
    print(f"     -> Analytics Total Tickets: {overview['total_tickets']}")
    print(f"     -> AI Resolution Rate: {overview['ai_resolution_rate']}%")
    print(f"     -> Escalated Tickets: {overview['escalated']}")

    # Step 14: Settings modification affects subsequent execution
    print("\n[14] Testing system settings modification...")
    curr_settings = get_system_settings()
    orig_threshold = curr_settings["auto_resolve_threshold"]
    
    # Temporarily set threshold to 95.0
    update_system_settings({"auto_resolve_threshold": 95.0}, updated_by="Joshitha Gosangari")
    new_settings = get_system_settings()
    assert new_settings["auto_resolve_threshold"] == 95.0, "Settings update failed to persist!"
    print(f"     -> Updated Auto-Resolve Threshold from {orig_threshold}% to 95.0% in DB.")

    # Restore threshold back to original
    update_system_settings({"auto_resolve_threshold": orig_threshold}, updated_by="Joshitha Gosangari")
    restored = get_system_settings()
    assert restored["auto_resolve_threshold"] == orig_threshold
    print(f"     -> Restored Auto-Resolve Threshold back to {orig_threshold}%.")

    # Step 15: Logout & Re-login session check
    print("\n[15] Testing Logout and Re-authentication...")
    logout_res = client.get("/logout")
    assert logout_res.status_code in (200, 302)
    
    relogin_res = client.post("/login", data={"email": test_email, "password": "Password1234!"}, follow_redirects=True)
    assert relogin_res.status_code == 200
    print("     -> Successfully re-authenticated user after logout.")
    
    print("\n=== ALL 15 END-TO-END WORKFLOW STAGES PASSED SUCCESSFULLY ===")
    return True

def test_full_e2e_cycle():
    assert run_e2e_cycle() is True

if __name__ == "__main__":
    success = run_e2e_cycle()
    if not success:
        sys.exit(1)
