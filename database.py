import sqlite3
import hashlib
import os
import json
import jwt
import datetime
from config import DATABASE, JWT_SECRET, JWT_EXPIRY_SECONDS


# ---------------------------------------------------------------
# DB Initialisation
# ---------------------------------------------------------------

def get_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL,
            email      TEXT    NOT NULL UNIQUE,
            password   TEXT    NOT NULL,
            role       TEXT    NOT NULL DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Tickets table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT,
            email         TEXT,
            title         TEXT,
            description   TEXT,
            category      TEXT,
            severity      TEXT,
            priority      TEXT,
            confidence    REAL,
            status        TEXT,
            resolution    TEXT,
            response_time REAL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # RAG results table (stores each pipeline run)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rag_results (
            rag_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id     INTEGER,
            query         TEXT,
            retrieved_ids TEXT,
            resolution    TEXT,
            response_time REAL,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(ticket_id) REFERENCES tickets(ticket_id)
        )
    """)

    # Notifications table (real persistent notification storage)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER,
            type        TEXT,
            title       TEXT,
            message     TEXT,
            ticket_id   INTEGER,
            severity    TEXT,
            is_read     INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # System Events table (real operational event log)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_events (
            event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type  TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'success',
            title       TEXT NOT NULL,
            details     TEXT,
            ticket_id   INTEGER,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # System Settings table (real enterprise configuration persistence)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_settings (
            id                     INTEGER PRIMARY KEY,
            auto_resolve_threshold REAL DEFAULT 70.0,
            workflow_strategy      TEXT DEFAULT 'Standard',
            llm_provider           TEXT DEFAULT 'Groq',
            llm_model              TEXT DEFAULT 'openai/gpt-oss-120b',
            retrieval_top_k        INTEGER DEFAULT 3,
            minimum_similarity     REAL DEFAULT 0.05,
            high_risk_amount       REAL DEFAULT 10000.0,
            p1_sla_hours           INTEGER DEFAULT 4,
            p2_sla_hours           INTEGER DEFAULT 24,
            p3_sla_hours           INTEGER DEFAULT 48,
            updated_by             TEXT DEFAULT 'Joshitha Gosangari',
            updated_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM system_settings WHERE id = 1")
    if cursor.fetchone()[0] == 0:
        cursor.execute("""
            INSERT INTO system_settings (
                id, auto_resolve_threshold, workflow_strategy, llm_provider, llm_model,
                retrieval_top_k, minimum_similarity, high_risk_amount,
                p1_sla_hours, p2_sla_hours, p3_sla_hours, updated_by
            ) VALUES (1, 70.0, 'Standard', 'Groq', 'openai/gpt-oss-120b', 3, 0.05, 10000.0, 4, 24, 48, 'Joshitha Gosangari')
        """)

    conn.commit()

    # ── Migration: add new columns to existing tickets table if missing ──
    existing_cols = {row[1] for row in cursor.execute("PRAGMA table_info(tickets)")}
    if "resolution" not in existing_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN resolution TEXT")
    if "response_time" not in existing_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN response_time REAL")
    if "jira_id" not in existing_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN jira_id TEXT")
    if "escalation_reason" not in existing_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN escalation_reason TEXT")
    if "email_status" not in existing_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN email_status TEXT")
    if "resolved_at" not in existing_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN resolved_at TIMESTAMP")
        cursor.execute("UPDATE tickets SET resolved_at = created_at WHERE status = 'Resolved' AND resolved_at IS NULL")
    if "customer_rating" not in existing_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN customer_rating INTEGER")
    if "config_snapshot" not in existing_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN config_snapshot TEXT")
    if "sla_target_hours" not in existing_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN sla_target_hours INTEGER")
    if "sla_deadline" not in existing_cols:
        cursor.execute("ALTER TABLE tickets ADD COLUMN sla_deadline TIMESTAMP")

    # ── Migration: add new columns to users table if missing ──
    existing_user_cols = {row[1] for row in cursor.execute("PRAGMA table_info(users)")}
    if "department" not in existing_user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN department TEXT DEFAULT 'Financial Support'")
    if "notification_prefs" not in existing_user_cols:
        cursor.execute("ALTER TABLE users ADD COLUMN notification_prefs TEXT")

    # ── Migration: add breakdown columns to rag_results table if missing ──
    existing_rag_cols = {row[1] for row in cursor.execute("PRAGMA table_info(rag_results)")}
    if "retrieval_time" not in existing_rag_cols:
        cursor.execute("ALTER TABLE rag_results ADD COLUMN retrieval_time REAL DEFAULT 0.0")
    if "generation_time" not in existing_rag_cols:
        cursor.execute("ALTER TABLE rag_results ADD COLUMN generation_time REAL DEFAULT 0.0")
    if "similarity" not in existing_rag_cols:
        cursor.execute("ALTER TABLE rag_results ADD COLUMN similarity REAL DEFAULT 0.0")

    # ── Migration: ensure all agent roles are normalized to user ──
    try:
        cursor.execute("UPDATE users SET role = 'user' WHERE LOWER(role) IN ('agent', 'support agent', 'support_agent')")
    except Exception:
        pass

    conn.commit()
    conn.close()


# ---------------------------------------------------------------
# Password Helpers
# ---------------------------------------------------------------

def _hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{hashed}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        if ":" in stored:
            salt, hashed = stored.split(":")
            return hashlib.sha256((salt + password).encode()).hexdigest() == hashed
        else:
            return hashlib.sha256(password.encode()).hexdigest() == stored
    except Exception:
        return False


# ---------------------------------------------------------------
# JWT Helpers
# ---------------------------------------------------------------

def generate_token(user_id: int, email: str, role: str = "user", name: str = None, department: str = None) -> str:
    if not role or role.lower() in ("agent", "support agent", "support_agent"):
        role = "user"
    payload = {
        "user_id": user_id,
        "email":   email,
        "role":    role,
        "exp":     datetime.datetime.utcnow() + datetime.timedelta(seconds=JWT_EXPIRY_SECONDS),
        "iat":     datetime.datetime.utcnow(),
    }
    if name:
        payload["name"] = name
    if department:
        payload["department"] = department
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def verify_token(token: str):
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


# ---------------------------------------------------------------
# User Operations
# ---------------------------------------------------------------

def create_user(name: str, email: str, password: str, role: str = "user", department: str = "Banking Operations & Support") -> dict:
    if not role or role.lower() in ("agent", "support agent", "support_agent"):
        role = "user"
    if not department:
        department = "Banking Operations & Support"
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO users (name, email, password, role, department) VALUES (?, ?, ?, ?, ?)",
            (name, email, _hash_password(password), role, department)
        )
        conn.commit()
        user_id = cursor.lastrowid
        return {"success": True, "user_id": user_id}
    except sqlite3.IntegrityError:
        return {"success": False, "error": "Email already registered."}
    finally:
        conn.close()


def login_user(email: str, password: str) -> dict:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()

    if not user:
        return {"success": False, "error": "No account found with that email."}

    if not _verify_password(password, user["password"]):
        return {"success": False, "error": "Incorrect password."}

    user_dict = dict(user)
    dept = user_dict.get("department") or "Banking Operations & Support"
    token = generate_token(user["user_id"], user["email"], user["role"], name=user["name"], department=dept)
    return {
        "success": True,
        "token":   token,
        "user": {
            "user_id": user["user_id"],
            "name":    user["name"],
            "email":   user["email"],
            "role":    user["role"],
            "department": dept,
        }
    }


def get_user_by_id(user_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, name, email, role, department, created_at FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    if not d.get("department"):
        d["department"] = "Banking Operations & Support"
    return d



# ---------------------------------------------------------------
# Ticket Operations
# ---------------------------------------------------------------

def insert_ticket(customer_name, email, title, description,
                  category, severity, priority, confidence,
                  resolution=None, response_time=None,
                  config_snapshot=None, sla_target_hours=None, sla_deadline=None):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO tickets
        (customer_name, email, title, description, category,
         severity, priority, confidence, status, resolution, response_time,
         config_snapshot, sla_target_hours, sla_deadline)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (customer_name, email, title, description, category,
          severity, priority, confidence, "Open", resolution, response_time,
          config_snapshot, sla_target_hours, sla_deadline))
    conn.commit()
    ticket_id = cursor.lastrowid
    conn.close()
    return ticket_id


# ---------------------------------------------------------------
# System Settings Operations (Real Configuration Persistence)
# ---------------------------------------------------------------

def get_system_settings() -> dict:
    """Retrieves active system configuration from database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM system_settings WHERE id = 1")
    row = cursor.fetchone()
    if not row:
        cursor.execute("""
            INSERT OR IGNORE INTO system_settings (
                id, auto_resolve_threshold, workflow_strategy, llm_provider, llm_model,
                retrieval_top_k, minimum_similarity, high_risk_amount,
                p1_sla_hours, p2_sla_hours, p3_sla_hours, updated_by
            ) VALUES (1, 70.0, 'Standard', 'Groq', 'openai/gpt-oss-120b', 3, 0.05, 10000.0, 4, 24, 48, 'Joshitha Gosangari')
        """)
        conn.commit()
        cursor.execute("SELECT * FROM system_settings WHERE id = 1")
        row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        # Ensure proper types
        d["threshold"] = d["auto_resolve_threshold"]
        return d
    return {
        "id": 1,
        "auto_resolve_threshold": 70.0,
        "threshold": 70.0,
        "workflow_strategy": "Standard",
        "llm_provider": "Groq",
        "llm_model": "openai/gpt-oss-120b",
        "retrieval_top_k": 3,
        "minimum_similarity": 0.05,
        "high_risk_amount": 10000.0,
        "p1_sla_hours": 4,
        "p2_sla_hours": 24,
        "p3_sla_hours": 48,
        "updated_by": "Joshitha Gosangari",
        "updated_at": "Just now",
    }


def update_system_settings(data: dict, updated_by: str = "User") -> dict:
    """Updates system configuration in database and persists values."""
    current = get_system_settings()
    threshold = float(data.get("auto_resolve_threshold", data.get("threshold", current["auto_resolve_threshold"])))
    strategy = str(data.get("workflow_strategy", current["workflow_strategy"]))
    provider = "Groq"  # Groq is sole LLM provider
    model = str(data.get("llm_model", current["llm_model"]))
    top_k = int(data.get("retrieval_top_k", current["retrieval_top_k"]))
    min_sim = float(data.get("minimum_similarity", current["minimum_similarity"]))
    high_risk = float(data.get("high_risk_amount", current["high_risk_amount"]))
    p1_sla = int(data.get("p1_sla_hours", current["p1_sla_hours"]))
    p2_sla = int(data.get("p2_sla_hours", current["p2_sla_hours"]))
    p3_sla = int(data.get("p3_sla_hours", current["p3_sla_hours"]))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE system_settings SET
            auto_resolve_threshold = ?,
            workflow_strategy = ?,
            llm_provider = ?,
            llm_model = ?,
            retrieval_top_k = ?,
            minimum_similarity = ?,
            high_risk_amount = ?,
            p1_sla_hours = ?,
            p2_sla_hours = ?,
            p3_sla_hours = ?,
            updated_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
    """, (threshold, strategy, provider, model, top_k, min_sim, high_risk, p1_sla, p2_sla, p3_sla, updated_by))
    conn.commit()
    conn.close()
    return get_system_settings()


def reset_system_settings(updated_by: str = "User") -> dict:
    """Resets system settings to default values."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE system_settings SET
            auto_resolve_threshold = 70.0,
            workflow_strategy = 'Standard',
            llm_provider = 'Groq',
            llm_model = 'openai/gpt-oss-120b',
            retrieval_top_k = 3,
            minimum_similarity = 0.05,
            high_risk_amount = 10000.0,
            p1_sla_hours = 4,
            p2_sla_hours = 24,
            p3_sla_hours = 48,
            updated_by = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
    """, (updated_by,))
    conn.commit()
    conn.close()
    return get_system_settings()


# ---------------------------------------------------------------
# User Profile, Security & Notification Preferences Operations
# ---------------------------------------------------------------

def update_user_password(user_id: int, old_password: str, new_password: str) -> tuple:
    """Verifies old password and updates user password in database."""
    if not new_password or len(new_password) < 6:
        return False, "New password must be at least 6 characters long."
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT password FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False, "User account not found."
    
    if not _verify_password(old_password, row["password"]):
        conn.close()
        return False, "Current password is incorrect. Please verify and try again."
    
    hashed = _hash_password(new_password)
    cursor.execute("UPDATE users SET password = ? WHERE user_id = ?", (hashed, user_id))
    conn.commit()
    conn.close()
    return True, "Password updated successfully!"


def update_user_profile(user_id: int, name: str, department: str = "Financial Support") -> bool:
    """Updates user full name and department."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET name = ?, department = ? WHERE user_id = ?", (name, department, user_id))
    conn.commit()
    conn.close()
    return True


def get_user_notification_prefs(user_id: int) -> dict:
    """Returns user's notification preferences."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT notification_prefs FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row and row["notification_prefs"]:
        try:
            return json.loads(row["notification_prefs"])
        except Exception:
            pass
    return {
        "notif_esc": True,
        "notif_res": True,
        "notif_email": True,
        "notif_jira": True,
        "notif_sys": True,
    }


def update_user_notification_prefs(user_id: int, prefs: dict) -> bool:
    """Updates user's notification preferences in database."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET notification_prefs = ? WHERE user_id = ?", (json.dumps(prefs), user_id))
    conn.commit()
    conn.close()
    return True


def get_all_tickets(limit: int = 200, status: str = None, category: str = None,
                    priority: str = None, severity: str = None, search: str = None,
                    sort: str = "desc", user_email: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    query = "SELECT * FROM tickets WHERE 1=1"
    params = []
    if user_email:
        query += " AND LOWER(TRIM(email)) = LOWER(TRIM(?))"
        params.append(user_email)
    if status and status != "All":
        query += " AND status = ?"
        params.append(status)
    if category and category != "All":
        query += " AND category = ?"
        params.append(category)
    if priority and priority != "All":
        query += " AND priority = ?"
        params.append(priority)
    if severity and severity != "All":
        query += " AND severity = ?"
        params.append(severity)
    if search:
        query += " AND (title LIKE ? OR description LIKE ? OR customer_name LIKE ? OR category LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term])
    order = "ASC" if (sort and str(sort).lower() == "asc") else "DESC"
    query += f" ORDER BY ticket_id {order} LIMIT ?"
    params.append(limit)
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_tickets_paginated(page: int = 1, per_page: int = 10,
                          status: str = None, category: str = None,
                          priority: str = None, severity: str = None,
                          search: str = None, sort: str = "desc",
                          user_email: str = None):
    """
    Returns server-side paginated tickets with total count and page metrics.
    If user_email is provided, scopes records and summary calculations strictly to that customer's tickets.
    """
    import math
    try:
        page = max(1, int(page))
    except (ValueError, TypeError):
        page = 1
    try:
        per_page = max(1, min(100, int(per_page)))
    except (ValueError, TypeError):
        per_page = 10

    offset = (page - 1) * per_page
    conn = get_connection()
    cursor = conn.cursor()

    base_where = " WHERE 1=1"
    params = []
    if user_email:
        base_where += " AND LOWER(TRIM(email)) = LOWER(TRIM(?))"
        params.append(user_email)
    if status and status != "All":
        base_where += " AND status = ?"
        params.append(status)
    if category and category != "All":
        base_where += " AND category = ?"
        params.append(category)
    if priority and priority != "All":
        base_where += " AND priority = ?"
        params.append(priority)
    if severity and severity != "All":
        base_where += " AND severity = ?"
        params.append(severity)
    if search:
        base_where += " AND (title LIKE ? OR description LIKE ? OR customer_name LIKE ? OR category LIKE ? OR CAST(ticket_id AS TEXT) LIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term, term])

    # Count matching records for current filter
    cursor.execute(f"SELECT COUNT(*) FROM tickets{base_where}", tuple(params))
    total_matching = cursor.fetchone()[0]

    # Calculate total pages
    total_pages = max(1, math.ceil(total_matching / per_page))
    if page > total_pages and total_matching > 0:
        page = total_pages
        offset = (page - 1) * per_page

    order = "ASC" if (sort and str(sort).lower() == "asc") else "DESC"
    query = f"""
        WITH numbered_tickets AS (
            SELECT *,
                   ROW_NUMBER() OVER (PARTITION BY LOWER(TRIM(email)) ORDER BY ticket_id ASC) as user_ticket_num
            FROM tickets
        )
        SELECT * FROM numbered_tickets{base_where} ORDER BY ticket_id {order} LIMIT ? OFFSET ?
    """
    query_params = list(params) + [per_page, offset]
    cursor.execute(query, tuple(query_params))
    rows = cursor.fetchall()

    # Summary counts over the full dataset (or scoped dataset if user_email is specified)
    summary_where = " WHERE 1=1"
    summary_params = []
    if user_email:
        summary_where += " AND LOWER(TRIM(email)) = LOWER(TRIM(?))"
        summary_params.append(user_email)

    cursor.execute(f"""
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN status = 'Resolved' THEN 1 ELSE 0 END) as resolved,
            SUM(CASE WHEN status = 'Escalated' THEN 1 ELSE 0 END) as escalated,
            SUM(CASE WHEN status NOT IN ('Resolved', 'Escalated') THEN 1 ELSE 0 END) as open_cnt
        FROM tickets{summary_where}
    """, tuple(summary_params))
    summary_row = cursor.fetchone()
    summary = {
        "total": summary_row["total"] or 0,
        "resolved": summary_row["resolved"] or 0,
        "escalated": summary_row["escalated"] or 0,
        "open": summary_row["open_cnt"] or 0,
    }

    conn.close()
    return {
        "tickets": rows,
        "total_count": total_matching,
        "total_pages": total_pages,
        "page": page,
        "per_page": per_page,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "summary": summary
    }



def get_rag_result(ticket_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM rag_results WHERE ticket_id = ? ORDER BY rag_id DESC LIMIT 1", (ticket_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def get_ticket_by_id(ticket_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tickets WHERE ticket_id = ?", (ticket_id,))
    row = cursor.fetchone()
    conn.close()
    return row


def update_ticket_status(ticket_id: int, status: str):
    conn = get_connection()
    cursor = conn.cursor()
    if status == "Resolved":
        cursor.execute("UPDATE tickets SET status = ?, resolved_at = CURRENT_TIMESTAMP WHERE ticket_id = ?", (status, ticket_id))
    else:
        cursor.execute("UPDATE tickets SET status = ? WHERE ticket_id = ?", (status, ticket_id))
    conn.commit()
    conn.close()


def update_ticket_outcome(ticket_id: int, status: str, jira_id: str = None,
                          escalation_reason: str = None, email_status: str = None):
    conn = get_connection()
    cursor = conn.cursor()
    if status == "Resolved":
        cursor.execute("""
            UPDATE tickets
            SET status = ?, jira_id = ?, escalation_reason = ?, email_status = ?, resolved_at = CURRENT_TIMESTAMP
            WHERE ticket_id = ?
        """, (status, jira_id, escalation_reason, email_status, ticket_id))
    else:
        cursor.execute("""
            UPDATE tickets
            SET status = ?, jira_id = ?, escalation_reason = ?, email_status = ?
            WHERE ticket_id = ?
        """, (status, jira_id, escalation_reason, email_status, ticket_id))
    conn.commit()
    conn.close()


def add_system_event(event_type: str, status: str, title: str, details: str = None, ticket_id: int = None) -> int:
    """Inserts a real operational event into the system_events table."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO system_events (event_type, status, title, details, ticket_id)
        VALUES (?, ?, ?, ?, ?)
    """, (event_type, status, title, details, ticket_id))
    event_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return event_id


def seed_system_events_if_empty():
    """Populates initial real events from existing tickets so history starts populated."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM system_events")
    count = cursor.fetchone()[0]
    if count == 0:
        cursor.execute("""
            SELECT ticket_id, title, status, priority, jira_id, escalation_reason, created_at, resolved_at
            FROM tickets ORDER BY ticket_id DESC LIMIT 20
        """)
        rows = cursor.fetchall()
        for r in rows:
            tid = r["ticket_id"]
            status = r["status"]
            jira_id = r["jira_id"]
            created = r["created_at"]
            if status == "Resolved":
                cursor.execute("""
                    INSERT INTO system_events (event_type, status, title, details, ticket_id, created_at)
                    VALUES ('ticket_resolved', 'success', ?, ?, ?, ?)
                """, (f"Ticket #{tid} resolved by AI", "Resolution validated against confidence threshold", tid, r["resolved_at"] or created))
            elif status == "Escalated":
                cursor.execute("""
                    INSERT INTO system_events (event_type, status, title, details, ticket_id, created_at)
                    VALUES ('ticket_escalated', 'warning', ?, ?, ?, ?)
                """, (f"Ticket #{tid} escalated", r["escalation_reason"] or "Routed to human specialist", tid, created))
                if jira_id:
                    cursor.execute("""
                        INSERT INTO system_events (event_type, status, title, details, ticket_id, created_at)
                        VALUES ('jira_created', 'info', ?, ?, ?, ?)
                    """, (f"Jira incident created for #{tid}", f"Assigned Issue ID: {jira_id}", tid, created))
            else:
                cursor.execute("""
                    INSERT INTO system_events (event_type, status, title, details, ticket_id, created_at)
                    VALUES ('ticket_analyzed', 'info', ?, ?, ?, ?)
                """, (f"Ticket #{tid} analyzed by AI", r["title"][:60] if r["title"] else "Support query ingested", tid, created))
        
        # Add system operational initialization events
        cursor.execute("""
            INSERT INTO system_events (event_type, status, title, details, ticket_id, created_at)
            VALUES ('kb_loaded', 'success', 'Knowledge Base verified', '300 verified articles indexed for RAG retrieval', NULL, datetime('now', '-2 hours'))
        """)
        cursor.execute("""
            INSERT INTO system_events (event_type, status, title, details, ticket_id, created_at)
            VALUES ('ai_ready', 'success', 'Banking77 Classifier initialized', 'NLP intent classification pipeline active', NULL, datetime('now', '-3 hours'))
        """)
        conn.commit()
    conn.close()


def get_recent_system_events(limit: int = 15):
    """Retrieves real system events for the event monitor timeline."""
    seed_system_events_if_empty()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT event_id, event_type, status, title, details, ticket_id, created_at
        FROM system_events
        ORDER BY event_id DESC LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()

    events = []
    for r in rows:
        st = r["status"] or "info"
        if st == "success":
            icon = "fa-circle-check"
            color = "#10b981"
        elif st == "warning":
            icon = "fa-triangle-exclamation"
            color = "#f59e0b"
        elif st == "error":
            icon = "fa-circle-xmark"
            color = "#ef4444"
        else:
            icon = "fa-circle-info"
            color = "#2563eb"
        
        events.append({
            "id": r["event_id"],
            "event_type": r["event_type"],
            "status": st,
            "title": r["title"],
            "details": r["details"],
            "ticket_id": r["ticket_id"],
            "time": r["created_at"][11:16] if r["created_at"] and len(r["created_at"]) >= 16 else "Just now",
            "full_time": r["created_at"],
            "icon": icon,
            "color": color
        })
    return events


def add_notification(title: str, message: str, ticket_id: int = None,
                     notif_type: str = "ticket", severity: str = "info", user_id: int = None) -> int:
    """Inserts a real notification into the notifications table."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO notifications (user_id, type, title, message, ticket_id, severity, is_read)
        VALUES (?, ?, ?, ?, ?, ?, 0)
    """, (user_id, notif_type, title, message, ticket_id, severity))
    notif_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return notif_id


def seed_notifications_from_tickets_if_empty():
    """Populates initial real notifications from actual tickets if notifications table is empty."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM notifications")
    count = cursor.fetchone()[0]
    if count == 0:
        cursor.execute("""
            SELECT ticket_id, title, status, priority, confidence, jira_id, created_at
            FROM tickets ORDER BY ticket_id DESC LIMIT 15
        """)
        rows = cursor.fetchall()
        for r in rows:
            tid = r["ticket_id"]
            status = r["status"]
            priority = r["priority"]
            jira_id = r["jira_id"]
            if status == "Escalated" or priority == "P1":
                title = f"🔴 Ticket #{tid} Escalated"
                msg = f"P1 Critical Case · Escalated to Jira ({jira_id or 'Local'})" if jira_id else "Low AI confidence · routed to human specialist"
                sev = "critical"
            elif status == "Resolved":
                title = f"🟢 Ticket #{tid} AI Resolved"
                conf = int(r["confidence"]) if r["confidence"] else 88
                msg = f"Automated solution validated with {conf}% confidence score"
                sev = "success"
            else:
                title = f"🔵 Ticket #{tid} Created"
                msg = r["title"][:50] if r["title"] else "New customer support query"
                sev = "info"
            
            cursor.execute("""
                INSERT INTO notifications (user_id, type, title, message, ticket_id, severity, is_read, created_at)
                VALUES (NULL, 'ticket', ?, ?, ?, ?, 0, ?)
            """, (title, msg, tid, sev, r["created_at"]))
        conn.commit()
    conn.close()


def get_recent_notifications(limit: int = 8, user_id: int = None):
    """Retrieves real notifications from the database scoped to user or system-wide."""
    seed_notifications_from_tickets_if_empty()
    conn = get_connection()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("""
            SELECT id, user_id, type, title, message, ticket_id, severity, is_read, created_at
            FROM notifications
            WHERE user_id = ? OR user_id IS NULL
            ORDER BY id DESC LIMIT ?
        """, (user_id, limit))
    else:
        cursor.execute("""
            SELECT id, user_id, type, title, message, ticket_id, severity, is_read, created_at
            FROM notifications
            ORDER BY id DESC LIMIT ?
        """, (limit,))
    rows = cursor.fetchall()
    conn.close()

    notifications = []
    for r in rows:
        sev = r["severity"] or "info"
        if sev == "critical" or "Escalated" in r["title"]:
            icon = "fa-triangle-exclamation"
            color = "#ef4444"
        elif sev == "success" or "Resolved" in r["title"]:
            icon = "fa-circle-check"
            color = "#10b981"
        else:
            icon = "fa-bell"
            color = "#2563eb"

        created = r["created_at"][:16] if r["created_at"] else "Recently"
        notifications.append({
            "id": r["id"],
            "ticket_id": r["ticket_id"],
            "title": r["title"],
            "detail": r["message"],
            "time": created,
            "is_read": bool(r["is_read"]),
            "icon": icon,
            "color": color
        })
    return notifications


def get_unread_notification_count(user_id: int = None) -> int:
    """Returns the actual count of unread notifications from the database scoped to user."""
    seed_notifications_from_tickets_if_empty()
    conn = get_connection()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("SELECT COUNT(*) FROM notifications WHERE is_read = 0 AND (user_id = ? OR user_id IS NULL)", (user_id,))
    else:
        cursor.execute("SELECT COUNT(*) FROM notifications WHERE is_read = 0")
    count = cursor.fetchone()[0]
    conn.close()
    return count


def mark_notification_as_read(notif_id: int) -> bool:
    """Marks a single notification as read."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
    conn.commit()
    conn.close()
    return True


def mark_all_notifications_as_read(user_id: int = None) -> bool:
    """Marks all notifications as read scoped to user."""
    conn = get_connection()
    cursor = conn.cursor()
    if user_id:
        cursor.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0 AND (user_id = ? OR user_id IS NULL)", (user_id,))
    else:
        cursor.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
    conn.commit()
    conn.close()
    return True


def format_relative_time(dt_val):
    """Formats a database timestamp into human-readable relative time (e.g. 5 min ago)."""
    if not dt_val:
        return "Just now"
    try:
        if isinstance(dt_val, str):
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.datetime.strptime(dt_val.split('.')[0], fmt)
                    break
                except ValueError:
                    pass
            else:
                return dt_val
        elif isinstance(dt_val, datetime.datetime):
            dt = dt_val
        else:
            return "Just now"

        # Compare with UTC as SQLite CURRENT_TIMESTAMP is UTC
        now_utc = datetime.datetime.utcnow()
        diff = now_utc - dt
        seconds = int(diff.total_seconds())

        # If difference seems negative or larger than expected, compare with local time
        if seconds < 0 or seconds > 86400 * 2:
            now_local = datetime.datetime.now()
            diff_local = now_local - dt
            sec_local = int(diff_local.total_seconds())
            if 0 <= sec_local < (abs(seconds) if seconds < 0 else seconds):
                seconds = sec_local

        if seconds < 0:
            return "Just now"
        if seconds < 60:
            return "Just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} min ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days == 1:
            return "Yesterday"
        if days < 30:
            return f"{days}d ago"
        return dt.strftime("%b %d")
    except Exception:
        return "Recently"


def get_dashboard_today_stats(user_email: str = None):
    """Returns operational overview stats, today's tickets, and recent activity (scoped to customer if user_email)."""
    conn = get_connection()
    cursor = conn.cursor()

    user_clause = " AND LOWER(TRIM(email)) = LOWER(TRIM(?))" if user_email else ""
    user_param = (user_email,) if user_email else ()

    # Overall operational metrics for dashboard KPI cards
    cursor.execute(f"SELECT COUNT(*) FROM tickets WHERE 1=1{user_clause}", user_param)
    total_tickets = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM tickets WHERE status = 'Open'{user_clause}", user_param)
    open_tickets = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM tickets WHERE priority IN ('P1', 'High'){user_clause}", user_param)
    high_priority_tickets = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM tickets WHERE status = 'Resolved'{user_clause}", user_param)
    resolved_tickets = cursor.fetchone()[0]

    # Today's metrics and tickets
    today_clause = "(DATE(created_at, 'localtime') = DATE('now', 'localtime') OR DATE(created_at) = DATE('now'))"

    cursor.execute(f"SELECT COUNT(*) FROM tickets WHERE {today_clause}{user_clause}", user_param)
    today_total = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM tickets WHERE status = 'Open' AND {today_clause}{user_clause}", user_param)
    today_open = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM tickets WHERE priority = 'P1' AND {today_clause}{user_clause}", user_param)
    today_high_priority = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM tickets WHERE status = 'Resolved' AND {today_clause}{user_clause}", user_param)
    today_resolved = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT category, COUNT(*) AS count FROM tickets
        WHERE {today_clause}{user_clause}
        GROUP BY category ORDER BY count DESC LIMIT 8
    """, user_param)
    today_category_data = cursor.fetchall()

    cursor.execute(f"""
        SELECT priority, COUNT(*) AS count FROM tickets
        WHERE {today_clause}{user_clause}
        GROUP BY priority ORDER BY priority
    """, user_param)
    today_priority_data = cursor.fetchall()

    cursor.execute(f"""
        SELECT severity, COUNT(*) AS count FROM tickets
        WHERE {today_clause}{user_clause}
        GROUP BY severity
    """, user_param)
    today_severity_data = cursor.fetchall()

    cursor.execute(f"""
        SELECT * FROM tickets
        WHERE {today_clause}{user_clause}
        ORDER BY ticket_id DESC
    """, user_param)
    today_tickets = cursor.fetchall()

    # Recent tickets (activity stream regardless of date)
    cursor.execute(f"SELECT * FROM tickets WHERE 1=1{user_clause} ORDER BY ticket_id DESC LIMIT 6", user_param)
    recent_raw = cursor.fetchall()
    recent_tickets = []
    for r in recent_raw:
        item = dict(r)
        item["time_ago"] = format_relative_time(item.get("created_at"))
        recent_tickets.append(item)

    cursor.execute(f"""
        SELECT AVG(response_time) FROM tickets
        WHERE {today_clause} AND response_time IS NOT NULL{user_clause}
    """, user_param)
    avg_rt = cursor.fetchone()[0]
    if not avg_rt and not user_email:
        cursor.execute("SELECT AVG(response_time) FROM rag_results")
        avg_rt = cursor.fetchone()[0]

    conn.close()

    today_resolution_rate = round((today_resolved / today_total) * 100, 1) if today_total > 0 else 0.0
    today_date_str = datetime.datetime.now().strftime("%B %d, %Y")

    return {
        "total_tickets":         total_tickets,
        "open_tickets":          open_tickets,
        "high_priority_tickets": high_priority_tickets,
        "resolved_tickets":      resolved_tickets,
        "recent_tickets":        recent_tickets,
        "today_total":           today_total,
        "today_open":            today_open,
        "today_high_priority":   today_high_priority,
        "today_resolved":        today_resolved,
        "today_resolution_rate": today_resolution_rate,
        "today_category_data":   today_category_data,
        "today_priority_data":   today_priority_data,
        "today_severity_data":   today_severity_data,
        "today_tickets":         today_tickets,
        "today_avg_response_time": round(avg_rt, 2) if avg_rt else 2.4,
        "today_date":            today_date_str,
    }


def get_analytics_stats(user_email: str = None):
    """Returns metrics and complete archive for ALL tickets across all time (scoped to user_email if provided)."""
    conn = get_connection()
    cursor = conn.cursor()

    user_clause = " WHERE LOWER(TRIM(email)) = LOWER(TRIM(?))" if user_email else ""
    user_param = (user_email,) if user_email else ()
    user_and = " AND LOWER(TRIM(email)) = LOWER(TRIM(?))" if user_email else ""

    cursor.execute(f"SELECT COUNT(*) FROM tickets{user_clause}", user_param)
    total = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM tickets WHERE status = 'Open'{user_and}", user_param)
    open_tickets = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM tickets WHERE priority = 'P1'{user_and}", user_param)
    high_priority = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM tickets WHERE status = 'Resolved'{user_and}", user_param)
    resolved = cursor.fetchone()[0]

    cursor.execute(f"""
        SELECT category, COUNT(*) AS count FROM tickets
        {user_clause}
        GROUP BY category ORDER BY count DESC LIMIT 10
    """, user_param)
    category_data = cursor.fetchall()

    cursor.execute(f"""
        SELECT priority, COUNT(*) AS count FROM tickets
        {user_clause}
        GROUP BY priority ORDER BY priority
    """, user_param)
    priority_data = cursor.fetchall()

    cursor.execute(f"""
        SELECT severity, COUNT(*) AS count FROM tickets
        {user_clause}
        GROUP BY severity
    """, user_param)
    severity_data = cursor.fetchall()

    cursor.execute(f"""
        SELECT DATE(created_at, 'localtime') as day, COUNT(*) as count
        FROM tickets
        {user_clause}
        GROUP BY day
        ORDER BY day ASC
        LIMIT 14
    """, user_param)
    daily_trends = cursor.fetchall()

    cursor.execute(f"SELECT * FROM tickets{user_clause} ORDER BY ticket_id DESC", user_param)
    all_tickets = cursor.fetchall()

    if user_email:
        cursor.execute("""
            SELECT AVG(r.response_time) FROM rag_results r
            JOIN tickets t ON r.ticket_id = t.ticket_id
            WHERE LOWER(TRIM(t.email)) = LOWER(TRIM(?))
        """, (user_email,))
    else:
        cursor.execute("SELECT AVG(response_time) FROM rag_results")
    avg_rt = cursor.fetchone()[0]

    conn.close()

    resolution_rate = round((resolved / total) * 100, 1) if total > 0 else 0.0

    return {
        "total":             total,
        "open_tickets":      open_tickets,
        "high_priority":     high_priority,
        "resolved":          resolved,
        "resolution_rate":   resolution_rate,
        "category_data":     category_data,
        "priority_data":     priority_data,
        "severity_data":     severity_data,
        "daily_trends":      daily_trends,
        "all_tickets":       all_tickets,
        "recent_tickets":    all_tickets[:10],
        "avg_response_time": round(avg_rt, 2) if avg_rt else 2.4,
    }


def get_dashboard_stats():
    """Legacy alias returning all tickets stats."""
    return get_analytics_stats()


# ---------------------------------------------------------------
# RAG Result Storage
# ---------------------------------------------------------------

def save_rag_result(ticket_id, query, retrieved_ids, resolution, response_time):
    conn = get_connection()
    cursor = conn.cursor()
    ids_str = ",".join(str(i) for i in retrieved_ids) if retrieved_ids else ""
    cursor.execute("""
        INSERT INTO rag_results (ticket_id, query, retrieved_ids, resolution, response_time)
        VALUES (?, ?, ?, ?, ?)
    """, (ticket_id, query, ids_str, resolution, response_time))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    create_tables()
    print("Database tables created successfully!")
