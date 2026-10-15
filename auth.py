"""
JWT Authentication middleware for Flask routes.
"""

from functools import wraps
from flask import request, redirect, url_for, flash
from database import verify_token


class UserProxy:
    """Wraps the JWT payload dict so templates and backend code can use dot-notation and dictionary access."""
    def __init__(self, payload: dict):
        self._data = dict(payload) if payload else {}
        self.user_id = self._data.get("user_id") or self._data.get("id")
        self.id = self.user_id
        self.email = self._data.get("email", "")

        # Normalize role: always represent 'agent' / 'support agent' as 'user'
        raw_role = self._data.get("role", "user")
        if not raw_role or str(raw_role).strip().lower() in ("agent", "support agent", "support_agent"):
            self.role = "user"
        else:
            self.role = str(raw_role).strip().lower()

        self._data["role"] = self.role
        self._data["id"] = self.id
        self._data["user_id"] = self.user_id

        # Populate name & department from DB or fallback if omitted in JWT payload
        name = self._data.get("name")
        department = self._data.get("department")
        if (not name or not department) and self.user_id:
            try:
                from database import get_connection
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("SELECT name, role, department FROM users WHERE user_id = ?", (self.user_id,))
                row = cur.fetchone()
                if row:
                    if not name:
                        name = row["name"]
                    if not department:
                        department = row["department"]
                    db_role = row["role"]
                    if db_role and str(db_role).strip().lower() in ("agent", "support agent", "support_agent"):
                        self.role = "user"
                        self._data["role"] = "user"
                    elif db_role:
                        self.role = str(db_role).strip().lower()
                        self._data["role"] = self.role
                conn.close()
            except Exception:
                pass

        self.name = name or "Joshitha Gosangari"
        self._data["name"] = self.name
        self.department = department or "Banking Operations & Support"
        self._data["department"] = self.department

        self.is_authenticated = True
        self.is_anonymous = False
        self.is_active = True

    def __getattr__(self, item):
        try:
            return self._data[item]
        except KeyError:
            return None

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, item):
        return self._data.get(item)

    def __contains__(self, item):
        return item in self._data

    def __bool__(self):
        return bool(self._data)

    def to_dict(self):
        return self._data.copy()


def login_required(f):
    """Decorator: redirects to /login (or returns 401 for /api/) if JWT cookie is missing or invalid."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.cookies.get("jwt_token")
        if not token:
            if request.path.startswith("/api/"):
                from flask import jsonify
                return jsonify({"success": False, "error": "Unauthorized"}), 401
            flash("Please log in to continue.", "warning")
            return redirect(url_for("login"))
        payload = verify_token(token)
        if not payload:
            if request.path.startswith("/api/"):
                from flask import jsonify
                return jsonify({"success": False, "error": "Session expired"}), 401
            flash("Your session has expired. Please log in again.", "warning")
            return redirect(url_for("login"))
        request.current_user = UserProxy(payload)
        return f(*args, **kwargs)
    return decorated


def get_current_user():
    """Returns a UserProxy (dot-accessible) or None."""
    token = request.cookies.get("jwt_token")
    if not token:
        return None
    payload = verify_token(token)
    if not payload:
        return None
    return UserProxy(payload)
