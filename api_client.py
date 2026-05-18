"""
api_client.py  —  KPR Lab CRM
══════════════════════════════════════════════════════════════════
db_manager.py కి EXACT drop-in replacement.
Client PCs లో db_manager కి బదులు ఈ file import చేయాలి.

Each module లో ONLY import line మారాలి:
  Before:  from db_manager import get_app_settings, ...
  After:   from api_client import get_app_settings, ...

SERVER IP సెట్ చేయడం:
  1. Server PC లో: cmd → ipconfig → IPv4 Address copy చేయండి
  2. SERVER_IP ని ఆ IP తో replace చేయండి (line 26)
══════════════════════════════════════════════════════════════════
"""

import json
import urllib.request
import urllib.error
import urllib.parse
import datetime
from typing import Optional, Any

# ─────────────────────────────────────────────────────────────────
# CONFIG  ← ఇక్కడ మాత్రమే Server IP మార్చాలి
# ─────────────────────────────────────────────────────────────────
SERVER_IP   = "192.168.0.25"    # ← Server PC IP (cmd → ipconfig → IPv4)
SERVER_PORT = 8000
BASE_URL    = f"http://{SERVER_IP}:{SERVER_PORT}"
TIMEOUT     = 15
# ─────────────────────────────────────────────────────────────────

_token:        Optional[str]  = None
_current_user: Optional[dict] = None


class APIError(Exception):
    def __init__(self, msg, code=0):
        super().__init__(msg)
        self.code = code


# ── Core HTTP ────────────────────────────────────────────────────

def _req(method: str, path: str, data: dict = None,
         params: dict = None, auth: bool = True) -> Any:
    url = f"{BASE_URL}{path}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    body = json.dumps(data).encode() if data is not None else None
    hdrs = {"Content-Type": "application/json", "Accept": "application/json"}
    if auth and _token:
        hdrs["Authorization"] = f"Bearer {_token}"
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read().decode()).get("detail", str(e))
        except Exception:
            detail = str(e)
        raise APIError(detail, e.code)
    except urllib.error.URLError as e:
        raise APIError(
            f"Server ({SERVER_IP}:{SERVER_PORT}) connect అవ్వట్లేదు.\n"
            f"Server PC on గా ఉందో, IP correct గా ఉందో check చేయండి.\n{e.reason}"
        )


def _get(path, params=None, auth=True):  return _req("GET",    path, params=params, auth=auth)
def _post(path, data=None, auth=True):   return _req("POST",   path, data=data,     auth=auth)
def _patch(path, data=None):             return _req("PATCH",  path, data=data)
def _put(path, data=None):               return _req("PUT",    path, data=data)
def _delete(path):                       return _req("DELETE", path)


# ── Health ───────────────────────────────────────────────────────

def test_connection() -> bool:
    try:
        _get("/health", auth=False)
        return True
    except APIError:
        return False


# ═══════════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════════

def authenticate_user(username: str, password: str):
    """Login — success అయితే user dict, fail అయితే None."""
    global _token, _current_user
    try:
        r = _post("/auth/login",
                  {"username": username, "password": password},
                  auth=False)
        _token = r["access_token"]
        _current_user = {
            "id":        r["user_id"],
            "user_id":   r["user_id"],
            "username":  r["username"],
            "role":      r["role"],
            "full_name": r.get("full_name", r["username"]),
        }
        return _current_user
    except APIError:
        return None


def logout_user_api():
    global _token, _current_user
    try:
        if _token:
            _post("/auth/logout")
    except Exception:
        pass
    _token = None
    _current_user = None


def get_all_users() -> list:
    try:
        return _get("/admin/users")
    except APIError:
        return []


def get_staff_users() -> list:
    try:
        return _get("/auth/staff")
    except APIError:
        return []


def get_user_by_id(user_id: int) -> Optional[dict]:
    try:
        return next((u for u in get_all_users() if u["id"] == user_id), None)
    except Exception:
        return None


def change_user_password(user_id: int, old_password: str, new_password: str):
    """
    BUG FIX: user_id body లో పంపట్లేదు — server token నుండి తీసుకుంటుంది.
    """
    try:
        r = _post("/auth/change_password", {
            "old_password": old_password,
            "new_password": new_password
        })
        return r.get("success", False), r.get("message", "")
    except APIError as e:
        return False, str(e)


def admin_reset_password(admin_id: int, target_user_id: int, new_password: str):
    """
    BUG FIX: admin_id server లో అవసరం లేదు — token నుండి admin verify అవుతుంది.
    """
    try:
        r = _post("/auth/admin_reset_password", {
            "target_user_id": target_user_id,
            "new_password":   new_password
        })
        return r.get("success", False), r.get("message", "")
    except APIError as e:
        return False, str(e)


def create_user(username: str, password: str, role: str = "staff",
                full_name: str = None, email: str = None) -> tuple:
    try:
        r = _post("/admin/users", {
            "username": username, "password": password,
            "role": role, "full_name": full_name, "email": email
        })
        return True, r.get("message", "User created.")
    except APIError as e:
        return False, str(e)


def update_user(user_id: int, **kwargs) -> tuple:
    try:
        r = _put(f"/admin/users/{user_id}", kwargs)
        return True, r.get("message", "Updated.")
    except APIError as e:
        return False, str(e)


def delete_user(user_id: int) -> bool:
    try:
        _delete(f"/admin/users/{user_id}")
        return True
    except APIError:
        return False


# ═══════════════════════════════════════════════════════════════
# SETTINGS
# ═══════════════════════════════════════════════════════════════

def get_app_settings() -> dict:
    try:
        return _get("/settings")
    except APIError:
        return {
            "currency_symbol": "₹",
            "lab_name":        "KPR Colour Lab",
            "shop_name":       "KPR Lab",
            "logo_path":       "",
            "invoice_footer":  "",
        }


def update_app_settings(**kwargs):
    try:
        _post("/settings/update", {"settings": kwargs})
    except APIError:
        pass


# ═══════════════════════════════════════════════════════════════
# ACTIVITY LOG
# ═══════════════════════════════════════════════════════════════

def log_activity(user_id: int, username: str,
                 activity_type: str, description: str):
    try:
        _post("/activity/log", {
            "user_id": user_id, "username": username,
            "activity_type": activity_type, "description": description
        })
    except APIError:
        pass   # Non-critical — server side లో log అవుతుంది


# ═══════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════

def get_notifications_for_user(user_id: int, unread_only: bool = False) -> list:
    try:
        return _get(f"/notifications/{user_id}",
                    params={"unread_only": "true" if unread_only else "false"})
    except APIError:
        return []


def get_unread_notification_count(user_id: int) -> int:
    try:
        return _get(f"/notifications/unread_count/{user_id}").get("count", 0)
    except APIError:
        return 0


def mark_notification_read(notification_id: int):
    try:
        _post(f"/notifications/mark_read/{notification_id}")
    except APIError:
        pass


def mark_all_notifications_read(user_id: int):
    try:
        _post(f"/notifications/mark_all_read/{user_id}")
    except APIError:
        pass


def log_notification_sent(job_id: int, channel: str, mobile: str,
                           message: str, sent_by_user_id: int):
    try:
        _post("/notifications/log_sent", {
            "job_id": job_id, "channel": channel, "mobile": mobile,
            "message": message, "sent_by_user_id": sent_by_user_id
        })
    except APIError:
        pass


# ═══════════════════════════════════════════════════════════════
# DASHBOARD
# ═══════════════════════════════════════════════════════════════

def get_dashboard_material_stats() -> dict:
    try:
        return _get("/dashboard/material_stats")
    except APIError:
        return {"low_stock_count": 0, "today_usage": 0,
                "today_wastage": 0, "month_wastage_pct": 0, "top_wasted": []}


def get_low_stock_items() -> list:
    try:
        return _get("/inventory/low-stock")
    except APIError:
        return []


def get_pending_jobs_count() -> int:
    try:
        return _get("/dashboard/summary").get("jobs", {}).get("pending", 0)
    except APIError:
        return 0


def get_total_unpaid_amount() -> float:
    try:
        return _get("/dashboard/summary").get("payments", {}).get("pending_collection", 0.0)
    except APIError:
        return 0.0


def get_unpaid_customer_details() -> list:
    try:
        return _get("/customers", params={"limit": 200})
    except APIError:
        return []


# ═══════════════════════════════════════════════════════════════
# JOBS
# ═══════════════════════════════════════════════════════════════

def get_assigned_jobs_for_user(user_id: int) -> list:
    try:
        return _get(f"/jobs/assigned/{user_id}")
    except APIError:
        return []


def get_job_notes(job_id: int) -> list:
    try:
        return _get(f"/jobs/notes/{job_id}")
    except APIError:
        return []


def add_job_note(job_id: int, note_text: str, user_id: int):
    try:
        _post("/jobs/notes",
              {"job_id": job_id, "note_text": note_text, "user_id": user_id})
    except APIError:
        pass


def update_job_payment_status(job_id: int, amount_paid: float):
    try:
        _patch(f"/jobs/{job_id}/payment", {"amount_paid": amount_paid})
    except APIError:
        pass


def get_payments_for_job(job_id: int) -> list:
    try:
        return _get("/payments", params={"job_id": job_id})
    except APIError:
        return []


def get_payments_for_customer(customer_id: int) -> list:
    try:
        return _get("/payments", params={"customer_id": customer_id})
    except APIError:
        return []


def get_all_job_types_structured() -> list:
    try:
        return _get("/job-types")
    except APIError:
        return []


def get_job_for_notification(job_id: int) -> Optional[dict]:
    """Job data + shop settings — notification SMS/WhatsApp కోసం."""
    try:
        r = _get(f"/jobs/order_slip/{job_id}")   # reuses order_slip data
        s = get_app_settings()
        r["shop_name"] = s.get("shop_name", "KPR Lab")
        r["currency"]  = s.get("currency_symbol", "₹")
        return r
    except APIError:
        return None


def get_order_slip_data(job_id: int) -> Optional[dict]:
    try:
        r = _get(f"/jobs/order_slip/{job_id}")
        s = get_app_settings()
        r["shop_name"]    = s.get("shop_name",       "KPR Lab")
        r["shop_phone"]   = s.get("shop_phone",       "")
        r["shop_address"] = s.get("shop_address",     "")
        r["currency"]     = s.get("currency_symbol",  "₹")
        r["slip_footer"]  = s.get("slip_footer", "Thank you for your business!")
        r["payments"]     = get_payments_for_job(job_id)
        return r
    except APIError:
        return None


# ═══════════════════════════════════════════════════════════════
# CUSTOMERS
# ═══════════════════════════════════════════════════════════════

def get_all_customers_for_filter() -> list:
    try:
        return _get("/customers", params={"limit": 500})
    except APIError:
        return []


def get_customer_report_data(start: str, end: str, search: str = "") -> list:
    try:
        return _get("/reports/customers",
                    params={"start": start, "end": end, "search": search})
    except APIError:
        return []


def get_customer_unbilled_jobs(customer_id: int) -> list:
    try:
        return _get(f"/customers/unbilled/{customer_id}")
    except APIError:
        return []


# ═══════════════════════════════════════════════════════════════
# INVENTORY / MATERIAL
# ═══════════════════════════════════════════════════════════════

def process_inventory_transaction(item_id: int, user_id: int, trans_type: str,
                                   qty: float, remarks: str = "",
                                   job_id: Optional[int] = None) -> bool:
    try:
        r = _post("/inventory/transaction", {
            "item_id": item_id, "user_id": user_id,
            "trans_type": trans_type, "qty": qty,
            "remarks": remarks, "job_id": job_id
        })
        return r.get("success", False)
    except APIError:
        return False


def get_active_jobs_for_selection(user_id: Optional[int] = None,
                                   role: Optional[str] = None) -> list:
    try:
        return _get("/inventory/active_jobs",
                    params={"user_id": user_id, "role": role})
    except APIError:
        return []


def get_my_material_entries(user_id: int, days: int = 30) -> list:
    try:
        return _get(f"/inventory/my_entries/{user_id}", params={"days": days})
    except APIError:
        return []


def get_material_usage_report(start: str, end: str) -> list:
    try:
        return _get("/reports/material_usage", params={"start": start, "end": end})
    except APIError:
        return []


def get_material_transaction_details(start: str, end: str,
                                      user_id_filter=None,
                                      trans_type_filter=None) -> list:
    try:
        return _get("/reports/material_transactions", params={
            "start": start, "end": end,
            "user_id": user_id_filter, "trans_type": trans_type_filter
        })
    except APIError:
        return []


def get_material_usage_by_job(start: str, end: str) -> list:
    try:
        return _get("/reports/material_by_job",
                    params={"start": start, "end": end})
    except APIError:
        return []


def get_staff_usage_summary(start: str, end: str) -> list:
    try:
        return _get("/reports/staff_summary",
                    params={"start": start, "end": end})
    except APIError:
        return []


# ═══════════════════════════════════════════════════════════════
# DB CONNECTION STUB
# (db_manager.py లో direct get_db_connection() వాడే చోట్ల)
# ═══════════════════════════════════════════════════════════════

class _FakeConn:
    """Direct SQL వాడే చోట్ల graceful fallback."""
    class _FakeCursor:
        def execute(self, *a, **kw): return self
        def fetchall(self): return []
        def fetchone(self): return None
    def cursor(self): return self._FakeCursor()
    def close(self): pass
    def commit(self): pass
    def rollback(self): pass
    row_factory = None

def get_db_connection():
    return _FakeConn()


def hash_password(password: str) -> str:
    """Stub — server side hash చేస్తుంది."""
    import hashlib
    return hashlib.sha256(password.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════
# QUICK TEST
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print(f"\nTesting connection to {BASE_URL} ...")
    if test_connection():
        print("✅ Server is reachable!")
        r = authenticate_user("admin", "admin123")
        if r:
            print(f"✅ Login OK: {r['username']} ({r['role']})")
            stats = get_dashboard_material_stats()
            print(f"   Low stock  : {stats.get('low_stock_count')}")
            print(f"   Today usage: {stats.get('today_usage')}")
        else:
            print("❌ Login failed — check credentials")
    else:
        print(f"❌ Cannot reach {BASE_URL}")
        print(f"   → api_client.py లో SERVER_IP మార్చండి")
