"""
KPR Lab CRM — FastAPI Server  (kpr_api_server.py)
══════════════════════════════════════════════════════════════════════
PC1 లో run చేయాలి. PC2/PC3 లు API మాత్రమే వాడతాయి.

  python kpr_api_server.py

Requirements:
  pip install fastapi uvicorn python-multipart

Endpoints — http://PC1_IP:8000/docs లో చూడవచ్చు
══════════════════════════════════════════════════════════════════════
"""

import sqlite3
import datetime
import hashlib
import os
import secrets
from typing import Optional, List, Dict
from contextlib import contextmanager

# ── FastAPI ──────────────────────────────────────────────────────────
try:
    from fastapi import FastAPI, HTTPException, Depends, status, Request
    from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("ERROR: pip install fastapi uvicorn python-multipart")
    raise


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                        CONFIGURATION                             ║
# ╚═══════════════════════════════════════════════════════════════════╝

DATABASE_NAME              = r"C:\Users\KPRFOTOGRAPHY\AppData\Roaming\KPRLabCRM\kprlab.db"
ACCESS_TOKEN_EXPIRE_MINUTES = 480          # 8 hours
_active_tokens: Dict[str, dict] = {}       # in-memory session store


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       DATABASE HELPERS                           ║
# ╚═══════════════════════════════════════════════════════════════════╝

@contextmanager
def get_db():
    if not os.path.exists(DATABASE_NAME):
        raise HTTPException(
            status_code=503,
            detail=f"Database '{DATABASE_NAME}' not found. PC1 లో kprlab.db ఉందో చెక్ చేయండి."
        )
    conn = sqlite3.connect(DATABASE_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rows_to_list(rows) -> List[dict]:
    return [dict(r) for r in rows]


def ts():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log_activity(conn, user: dict, action: str, desc: str):
    try:
        conn.execute(
            "INSERT INTO activity_log (user_id, username, activity_type, description, timestamp) VALUES (?,?,?,?,?)",
            (user["user_id"], user["username"], action, desc, ts())
        )
    except Exception:
        pass


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       AUTH / TOKEN                               ║
# ╚═══════════════════════════════════════════════════════════════════╝

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def create_token(user_id: int, username: str, role: str) -> str:
    token = secrets.token_urlsafe(32)
    _active_tokens[token] = {
        "user_id":  user_id,
        "username": username,
        "role":     role,
        "expires":  datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }
    return token


def verify_token(token: str) -> dict:
    info = _active_tokens.get(token)
    if not info:
        raise HTTPException(status_code=401, detail="Invalid or expired token. Please login again.")
    if datetime.datetime.utcnow() > info["expires"]:
        _active_tokens.pop(token, None)
        raise HTTPException(status_code=401, detail="Token expired. Please login again.")
    return info


security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    return verify_token(credentials.credentials)

def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required.")
    return current_user

def require_staff_or_above(current_user: dict = Depends(get_current_user)) -> dict:
    if current_user["role"] not in ("admin", "staff"):
        raise HTTPException(status_code=403, detail="Staff or Admin access required.")
    return current_user


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       PYDANTIC MODELS                            ║
# ╚═══════════════════════════════════════════════════════════════════╝

class LoginRequest(BaseModel):
    username: str
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

class AdminResetPasswordRequest(BaseModel):
    target_user_id: int
    new_password: str

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "staff"
    full_name: Optional[str] = None
    email: Optional[str] = None
    is_active: bool = True

class UserUpdate(BaseModel):
    role: Optional[str] = None
    full_name: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    new_password: Optional[str] = None

class CustomerCreate(BaseModel):
    name: str
    mobile: str
    email: Optional[str] = None
    address: Optional[str] = None
    tags: Optional[str] = None
    alternate_mobile: Optional[str] = None
    gst_no: Optional[str] = None
    pan_no: Optional[str] = None

class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    tags: Optional[str] = None
    alternate_mobile: Optional[str] = None
    gst_no: Optional[str] = None
    pan_no: Optional[str] = None

class JobCreate(BaseModel):
    customer_id: int
    job_type: str
    description: Optional[str] = None
    size: Optional[str] = None
    initial_price: float
    discount_amount: float = 0.0
    advance1: float = 0.0
    due_date: Optional[str] = None
    notes: Optional[str] = None
    assigned_staff_id: Optional[int] = None
    start_date: Optional[str] = None

class JobStatusUpdate(BaseModel):
    status: str
    notes: Optional[str] = None
    completion_date: Optional[str] = None

class JobAssignRequest(BaseModel):
    staff_id: int
    notes: Optional[str] = None

class JobNoteCreate(BaseModel):
    job_id: int
    note_text: str
    user_id: int

class PaymentCreate(BaseModel):
    customer_id: int
    job_id: Optional[int] = None
    invoice_id: Optional[int] = None
    amount: float
    payment_date: str
    payment_mode: Optional[str] = "Cash"
    notes: Optional[str] = None

class InventoryStockUpdate(BaseModel):
    quantity_change: float
    notes: Optional[str] = None

class InventoryTransactionCreate(BaseModel):
    item_id: int
    user_id: int
    trans_type: str          # "Usage" | "Wastage" | "Stock In"
    qty: float
    remarks: Optional[str] = ""
    job_id: Optional[int] = None

class InvoiceCreate(BaseModel):
    customer_id: int
    job_id: Optional[int] = None
    total_amount: float
    discount: float = 0.0
    tax_percent: float = 0.0
    notes: Optional[str] = None
    due_date: Optional[str] = None


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                        FASTAPI APP                               ║
# ╚═══════════════════════════════════════════════════════════════════╝

app = FastAPI(
    title="KPR Lab CRM API",
    description="KPR Colour Lab CRM — Secure LAN API. PC2/PC3 లు ఈ endpoints వాడాలి.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = datetime.datetime.now()
    response = await call_next(request)
    dur = (datetime.datetime.now() - start).total_seconds()
    print(f"[{start.strftime('%H:%M:%S')}] {request.client.host} "
          f"{request.method} {request.url.path} → {response.status_code} ({dur:.3f}s)")
    return response


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                     HEALTH                                       ║
# ╚═══════════════════════════════════════════════════════════════════╝

@app.get("/", tags=["Health"])
def root():
    return {"status": "✅ KPR Lab CRM API running", "time": ts(), "docs": "/docs"}

@app.get("/health", tags=["Health"])
def health_check():
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "healthy", "database": "connected", "time": ts()}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "unhealthy", "error": str(e)})


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                     AUTHENTICATION                               ║
# ╚═══════════════════════════════════════════════════════════════════╝

@app.post("/auth/login", tags=["Authentication"])
def login(req: LoginRequest):
    with get_db() as conn:
        user = conn.execute(
            "SELECT id, username, password_hash, role, is_active FROM users WHERE username=?",
            (req.username,)
        ).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="Username లేదా password తప్పు.")
    if user["is_active"] != 1:
        raise HTTPException(status_code=401, detail="Account inactive. Admin ని contact చేయండి.")
    if user["password_hash"] != hash_password(req.password):
        raise HTTPException(status_code=401, detail="Username లేదా password తప్పు.")

    token = create_token(user["id"], user["username"], user["role"])
    try:
        with get_db() as conn:
            conn.execute(
                "INSERT INTO activity_log (user_id, username, activity_type, description, timestamp) VALUES (?,?,?,?,?)",
                (user["id"], user["username"], "API Login", "Logged in via API", ts())
            )
    except Exception:
        pass
    return {
        "access_token": token, "token_type": "bearer",
        "user_id": user["id"], "username": user["username"],
        "role": user["role"],
        "expires_in_hours": ACCESS_TOKEN_EXPIRE_MINUTES // 60
    }


@app.post("/auth/logout", tags=["Authentication"])
def logout(current_user: dict = Depends(get_current_user),
           credentials: HTTPAuthorizationCredentials = Depends(security)):
    _active_tokens.pop(credentials.credentials, None)
    return {"message": f"'{current_user['username']}' logged out."}


@app.post("/auth/change_password", tags=["Authentication"])
def change_password(data: ChangePasswordRequest,
                    current_user: dict = Depends(get_current_user)):
    """Token నుండి user_id తీసుకుంటుంది — body లో user_id అవసరం లేదు."""
    uid = current_user["user_id"]
    with get_db() as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE id=? AND is_active=1", (uid,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        if row["password_hash"] != hash_password(data.old_password):
            raise HTTPException(status_code=400, detail="Current password తప్పు.")
        if len(data.new_password) < 6:
            raise HTTPException(status_code=400, detail="Password minimum 6 characters.")
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(data.new_password), uid)
        )
        log_activity(conn, current_user, "Change Password", "Password changed via API")
    return {"success": True, "message": "Password changed successfully."}


@app.post("/auth/admin_reset_password", tags=["Authentication"])
def admin_reset_password(data: AdminResetPasswordRequest,
                          current_user: dict = Depends(require_admin)):
    if len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password minimum 6 characters.")
    with get_db() as conn:
        row = conn.execute("SELECT username FROM users WHERE id=?", (data.target_user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        conn.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(data.new_password), data.target_user_id)
        )
        log_activity(conn, current_user, "Admin Reset Password",
                     f"Password reset for user '{row['username']}'")
    return {"success": True, "message": f"Password reset for '{row['username']}'."}


@app.get("/auth/staff", tags=["Authentication"])
def get_staff(current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, username, full_name, role, is_active FROM users WHERE is_active=1 ORDER BY username"
        ).fetchall()
    return rows_to_list(rows)


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                     CUSTOMERS                                    ║
# ╚═══════════════════════════════════════════════════════════════════╝

@app.get("/customers", tags=["Customers"])
def get_customers(search: Optional[str] = None, limit: int = 100, offset: int = 0,
                  current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        if search:
            rows = conn.execute(
                """SELECT id, name, mobile, email, address, tags,
                          alternate_mobile, gst_no, pan_no, created_at
                   FROM customers
                   WHERE name LIKE ? OR mobile LIKE ? OR email LIKE ?
                   ORDER BY name LIMIT ? OFFSET ?""",
                (f"%{search}%", f"%{search}%", f"%{search}%", limit, offset)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, name, mobile, email, address, tags,
                          alternate_mobile, gst_no, pan_no, created_at
                   FROM customers ORDER BY name LIMIT ? OFFSET ?""",
                (limit, offset)
            ).fetchall()
    return rows_to_list(rows)


@app.get("/customers/{customer_id}", tags=["Customers"])
def get_customer(customer_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM customers WHERE id=?", (customer_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Customer కనుగొనబడలేదు.")
    return dict(row)


@app.post("/customers", tags=["Customers"], status_code=201)
def create_customer(data: CustomerCreate, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        if conn.execute("SELECT id FROM customers WHERE mobile=?", (data.mobile,)).fetchone():
            raise HTTPException(status_code=409, detail=f"Mobile '{data.mobile}' already registered.")
        cursor = conn.execute(
            """INSERT INTO customers (name, mobile, email, address, tags, alternate_mobile, gst_no, pan_no)
               VALUES (?,?,?,?,?,?,?,?)""",
            (data.name, data.mobile, data.email, data.address, data.tags,
             data.alternate_mobile, data.gst_no, data.pan_no)
        )
        new_id = cursor.lastrowid
        log_activity(conn, current_user, "Customer Add", f"Customer '{data.name}' added")
    return {"id": new_id, "message": f"Customer '{data.name}' added."}


@app.put("/customers/{customer_id}", tags=["Customers"])
def update_customer(customer_id: int, data: CustomerUpdate,
                    current_user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in data.dict().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")
    set_clause = ", ".join(f"{k}=?" for k in updates)
    with get_db() as conn:
        if not conn.execute("SELECT id FROM customers WHERE id=?", (customer_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Customer not found.")
        conn.execute(f"UPDATE customers SET {set_clause} WHERE id=?",
                     list(updates.values()) + [customer_id])
        log_activity(conn, current_user, "Customer Update", f"Customer {customer_id} updated")
    return {"message": "Customer updated."}


@app.get("/customers/{customer_id}/jobs", tags=["Customers"])
def customer_jobs(customer_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, job_type, size, final_price, balance,
                      payment_status, status, due_date, start_date
               FROM jobs WHERE customer_id=? ORDER BY id DESC""",
            (customer_id,)
        ).fetchall()
    return rows_to_list(rows)


@app.get("/customers/{customer_id}/payments", tags=["Customers"])
def customer_payments(customer_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT p.*, j.job_type FROM payments p
               LEFT JOIN jobs j ON p.job_id=j.id
               WHERE p.customer_id=? ORDER BY p.id DESC""",
            (customer_id,)
        ).fetchall()
    return rows_to_list(rows)


@app.get("/customers/{customer_id}/balance", tags=["Customers"])
def customer_balance(customer_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        cust = conn.execute(
            "SELECT name, mobile FROM customers WHERE id=?", (customer_id,)
        ).fetchone()
        if not cust:
            raise HTTPException(status_code=404, detail="Customer not found.")
        bal = conn.execute(
            "SELECT COALESCE(SUM(balance),0) FROM jobs WHERE customer_id=? AND payment_status!='Paid'",
            (customer_id,)
        ).fetchone()[0]
        paid = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments WHERE customer_id=?", (customer_id,)
        ).fetchone()[0]
        active = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE customer_id=? AND status NOT IN ('Delivered','Cancelled')",
            (customer_id,)
        ).fetchone()[0]
    return {
        "customer_id": customer_id, "customer_name": cust["name"],
        "mobile": cust["mobile"], "outstanding_balance": round(bal, 2),
        "total_paid": round(paid, 2), "active_jobs": active
    }


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                        JOBS                                      ║
# ╚═══════════════════════════════════════════════════════════════════╝

@app.get("/jobs", tags=["Jobs"])
def get_jobs(status: Optional[str] = None, customer_id: Optional[int] = None,
             assigned_to: Optional[int] = None,
             limit: int = 100, offset: int = 0,
             current_user: dict = Depends(get_current_user)):
    query = """
        SELECT j.id, j.customer_id, j.job_type, j.description, j.size,
               j.initial_price, j.discount_amount, j.advance1,
               j.final_price, j.balance, j.payment_status, j.status,
               j.start_date, j.due_date, j.completion_date, j.delivery_date,
               j.notes, j.assigned_staff_id,
               c.name AS customer_name, c.mobile AS customer_mobile,
               u.username AS assigned_staff_name
        FROM jobs j
        LEFT JOIN customers c ON j.customer_id=c.id
        LEFT JOIN users u ON j.assigned_staff_id=u.id
        WHERE 1=1
    """
    params = []
    if status:
        query += " AND j.status=?"; params.append(status)
    if customer_id:
        query += " AND j.customer_id=?"; params.append(customer_id)
    if assigned_to:
        query += " AND j.assigned_staff_id=?"; params.append(assigned_to)
    query += " ORDER BY j.id DESC LIMIT ? OFFSET ?"
    params += [limit, offset]
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return rows_to_list(rows)


@app.get("/jobs/{job_id}", tags=["Jobs"])
def get_job(job_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        row = conn.execute(
            """SELECT j.*, c.name AS customer_name, c.mobile AS customer_mobile,
                      c.email AS customer_email, c.address AS customer_address,
                      u.username AS assigned_staff_name
               FROM jobs j LEFT JOIN customers c ON j.customer_id=c.id
               LEFT JOIN users u ON j.assigned_staff_id=u.id
               WHERE j.id=?""", (job_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found.")
    return dict(row)


@app.post("/jobs", tags=["Jobs"], status_code=201)
def create_job(data: JobCreate, current_user: dict = Depends(get_current_user)):
    final_price = data.initial_price - data.discount_amount
    balance = final_price - data.advance1
    start_date = data.start_date or datetime.date.today().isoformat()
    with get_db() as conn:
        cust = conn.execute("SELECT name FROM customers WHERE id=?", (data.customer_id,)).fetchone()
        if not cust:
            raise HTTPException(status_code=404, detail="Customer not found.")
        cursor = conn.execute(
            """INSERT INTO jobs (customer_id, job_type, description, size,
               initial_price, discount_amount, advance1, final_price, balance,
               payment_status, status, start_date, due_date, notes, assigned_staff_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (data.customer_id, data.job_type, data.description, data.size,
             data.initial_price, data.discount_amount, data.advance1,
             final_price, balance,
             "Advance Paid" if data.advance1 > 0 else "Unpaid",
             "Pending", start_date, data.due_date, data.notes, data.assigned_staff_id)
        )
        new_id = cursor.lastrowid
        # Notify assigned staff
        if data.assigned_staff_id:
            try:
                conn.execute(
                    "INSERT INTO notifications (user_id, title, message) VALUES (?,?,?)",
                    (data.assigned_staff_id, "📋 New Job Assigned",
                     f"Job #{new_id} ({data.job_type}) assigned to you.")
                )
            except Exception:
                pass
        log_activity(conn, current_user, "Job Add",
                     f"Job #{new_id} '{data.job_type}' for '{cust['name']}' created")
    return {"id": new_id, "final_price": final_price, "balance": balance,
            "message": "Job created."}


@app.patch("/jobs/{job_id}/status", tags=["Jobs"])
def update_job_status(job_id: int, data: JobStatusUpdate,
                      current_user: dict = Depends(get_current_user)):
    valid = ["Pending", "In Progress", "Completed", "Delivered", "Cancelled", "On Hold"]
    if data.status not in valid:
        raise HTTPException(status_code=400, detail=f"Valid statuses: {valid}")
    with get_db() as conn:
        job = conn.execute(
            """SELECT j.id, j.assigned_staff_id, c.name AS customer_name
               FROM jobs j LEFT JOIN customers c ON j.customer_id=c.id
               WHERE j.id=?""", (job_id,)
        ).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        conn.execute(
            "UPDATE jobs SET status=?, notes=COALESCE(?,notes), completion_date=COALESCE(?,completion_date) WHERE id=?",
            (data.status, data.notes, data.completion_date, job_id)
        )
        if data.status == "Delivered":
            conn.execute("UPDATE jobs SET delivery_date=? WHERE id=?",
                         (datetime.date.today().isoformat(), job_id))
        log_activity(conn, current_user, "Job Status Update",
                     f"Job #{job_id} → '{data.status}'")
    return {"message": f"Job #{job_id} → '{data.status}'."}


@app.patch("/jobs/{job_id}/assign", tags=["Jobs"])
def assign_job(job_id: int, data: JobAssignRequest,
               current_user: dict = Depends(require_staff_or_above)):
    with get_db() as conn:
        if not conn.execute("SELECT id FROM jobs WHERE id=?", (job_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Job not found.")
        staff = conn.execute(
            "SELECT id, username FROM users WHERE id=? AND is_active=1", (data.staff_id,)
        ).fetchone()
        if not staff:
            raise HTTPException(status_code=404, detail="Staff not found.")
        conn.execute("UPDATE jobs SET assigned_staff_id=? WHERE id=?", (data.staff_id, job_id))
        try:
            conn.execute(
                "INSERT INTO notifications (user_id, title, message) VALUES (?,?,?)",
                (data.staff_id, "📋 Job Assigned",
                 f"Job #{job_id} assigned to you. {data.notes or ''}")
            )
        except Exception:
            pass
        log_activity(conn, current_user, "Job Assign",
                     f"Job #{job_id} assigned to '{staff['username']}'")
    return {"message": f"Job #{job_id} assigned to '{staff['username']}'."}


@app.get("/jobs/assigned/{user_id}", tags=["Jobs"])
def assigned_jobs(user_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT j.id, j.customer_id, j.job_type, j.description, j.size, j.status,
                      j.payment_status, j.start_date, j.due_date, j.balance,
                      c.name AS customer_name, c.mobile AS customer_mobile
               FROM jobs j JOIN customers c ON j.customer_id=c.id
               WHERE j.assigned_staff_id=? AND j.status NOT IN ('Delivered','Cancelled')
               ORDER BY j.due_date ASC""",
            (user_id,)
        ).fetchall()
    return rows_to_list(rows)


@app.get("/jobs/order_slip/{job_id}", tags=["Jobs"])
def order_slip(job_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        row = conn.execute(
            """SELECT j.*, c.name AS customer_name, c.mobile AS customer_mobile,
                      c.email AS customer_email, c.address AS customer_address,
                      c.gst_no, u.username AS assigned_staff
               FROM jobs j JOIN customers c ON j.customer_id=c.id
               LEFT JOIN users u ON j.assigned_staff_id=u.id
               WHERE j.id=?""", (job_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found.")
    return dict(row)


@app.get("/jobs/notes/{job_id}", tags=["Jobs"])
def job_notes(job_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        try:
            rows = conn.execute(
                "SELECT * FROM job_notes WHERE job_id=? ORDER BY created_at DESC", (job_id,)
            ).fetchall()
        except Exception:
            rows = []
    return rows_to_list(rows)


@app.post("/jobs/notes", tags=["Jobs"])
def add_job_note(data: JobNoteCreate, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO job_notes (job_id, user_id, note) VALUES (?,?,?)",
            (data.job_id, data.user_id, data.note_text)
        )
    return {"success": True}


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       PAYMENTS                                   ║
# ╚═══════════════════════════════════════════════════════════════════╝

@app.get("/payments", tags=["Payments"])
def get_payments(customer_id: Optional[int] = None, job_id: Optional[int] = None,
                 limit: int = 100, current_user: dict = Depends(get_current_user)):
    query = """SELECT p.*, c.name AS customer_name FROM payments p
               LEFT JOIN customers c ON p.customer_id=c.id WHERE 1=1"""
    params = []
    if customer_id:
        query += " AND p.customer_id=?"; params.append(customer_id)
    if job_id:
        query += " AND p.job_id=?"; params.append(job_id)
    query += " ORDER BY p.id DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return rows_to_list(rows)


@app.post("/payments", tags=["Payments"], status_code=201)
def create_payment(data: PaymentCreate, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO payments (customer_id, job_id, invoice_id, amount,
               payment_date, payment_mode, notes)
               VALUES (?,?,?,?,?,?,?)""",
            (data.customer_id, data.job_id, data.invoice_id, data.amount,
             data.payment_date, data.payment_mode, data.notes)
        )
        new_id = cursor.lastrowid
        if data.job_id:
            job = conn.execute(
                "SELECT balance FROM jobs WHERE id=?", (data.job_id,)
            ).fetchone()
            if job:
                new_bal = max(0, (job["balance"] or 0) - data.amount)
                new_status = "Paid" if new_bal <= 0 else "Partially Paid"
                conn.execute(
                    "UPDATE jobs SET balance=?, payment_status=? WHERE id=?",
                    (new_bal, new_status, data.job_id)
                )
        if data.invoice_id:
            inv = conn.execute(
                "SELECT balance FROM invoices WHERE id=?", (data.invoice_id,)
            ).fetchone()
            if inv:
                new_inv_bal = max(0, (inv["balance"] or 0) - data.amount)
                inv_status = "Paid" if new_inv_bal <= 0 else "Partially Paid"
                conn.execute(
                    "UPDATE invoices SET balance=?, amount_paid=amount_paid+?, status=? WHERE id=?",
                    (new_inv_bal, data.amount, inv_status, data.invoice_id)
                )
        log_activity(conn, current_user, "Payment Add",
                     f"Payment ₹{data.amount} recorded for customer {data.customer_id}")
    return {"id": new_id, "message": f"Payment ₹{data.amount} recorded."}


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       JOB TYPES                                  ║
# ╚═══════════════════════════════════════════════════════════════════╝

@app.get("/job-types", tags=["Job Types"])
def get_job_types(current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM job_types ORDER BY category, name").fetchall()
    return rows_to_list(rows)

@app.get("/job-types/categories", tags=["Job Types"])
def get_categories(current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute("SELECT DISTINCT category FROM job_types ORDER BY category").fetchall()
    return [r["category"] for r in rows]


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       INVENTORY                                  ║
# ╚═══════════════════════════════════════════════════════════════════╝

@app.get("/inventory", tags=["Inventory"])
def get_inventory(current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT i.*, c.name AS category_name, v.name AS vendor_name
               FROM inventory_items i
               LEFT JOIN inventory_categories c ON i.category_id=c.id
               LEFT JOIN vendors v ON i.vendor_id=v.id
               ORDER BY i.name"""
        ).fetchall()
    return rows_to_list(rows)


@app.get("/inventory/low-stock", tags=["Inventory"])
def get_low_stock(current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT i.*, c.name AS category_name
               FROM inventory_items i
               LEFT JOIN inventory_categories c ON i.category_id=c.id
               WHERE i.current_stock <= i.reorder_level
               ORDER BY i.current_stock ASC"""
        ).fetchall()
    return rows_to_list(rows)


@app.patch("/inventory/{item_id}/stock", tags=["Inventory"])
def update_stock(item_id: int, data: InventoryStockUpdate,
                 current_user: dict = Depends(require_staff_or_above)):
    with get_db() as conn:
        item = conn.execute("SELECT * FROM inventory_items WHERE id=?", (item_id,)).fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found.")
        new_stock = item["current_stock"] + data.quantity_change
        if new_stock < 0:
            raise HTTPException(status_code=400,
                                detail=f"Insufficient stock. Current: {item['current_stock']}")
        conn.execute(
            "UPDATE inventory_items SET current_stock=?, last_updated=? WHERE id=?",
            (new_stock, ts(), item_id)
        )
        log_activity(conn, current_user, "Inventory Update",
                     f"'{item['name']}' stock {data.quantity_change:+.2f} → {new_stock:.2f}")
        # Low-stock notification
        if item["reorder_level"] > 0 and new_stock <= item["reorder_level"]:
            admins = conn.execute(
                "SELECT id FROM users WHERE role='admin' AND is_active=1"
            ).fetchall()
            for a in admins:
                try:
                    conn.execute(
                        "INSERT INTO notifications (user_id, title, message) VALUES (?,?,?)",
                        (a["id"], "⚠️ Low Stock Alert",
                         f"'{item['name']}' stock is now {new_stock}. Please reorder.")
                    )
                except Exception:
                    pass
    return {"item_id": item_id, "new_stock": new_stock, "message": "Stock updated."}


@app.post("/inventory/transaction", tags=["Inventory"])
def inventory_transaction(data: InventoryTransactionCreate,
                           current_user: dict = Depends(get_current_user)):
    if current_user["role"] in ("staff", "sub_staff") and data.trans_type == "Stock In":
        raise HTTPException(status_code=403, detail="Staff cannot perform Stock In.")
    with get_db() as conn:
        cols = [c[1] for c in conn.execute("PRAGMA table_info(inventory_transactions)").fetchall()]
        if "job_id" not in cols:
            conn.execute("ALTER TABLE inventory_transactions ADD COLUMN job_id INTEGER")
        conn.execute(
            """INSERT INTO inventory_transactions
               (item_id, user_id, job_id, transaction_type, quantity, remarks)
               VALUES (?,?,?,?,?,?)""",
            (data.item_id, data.user_id, data.job_id,
             data.trans_type, float(data.qty), data.remarks)
        )
        if data.trans_type == "Stock In":
            conn.execute(
                "UPDATE inventory_items SET current_stock=current_stock+?, last_updated=CURRENT_TIMESTAMP WHERE id=?",
                (float(data.qty), data.item_id)
            )
        else:
            conn.execute(
                "UPDATE inventory_items SET current_stock=current_stock-?, last_updated=CURRENT_TIMESTAMP WHERE id=?",
                (float(data.qty), data.item_id)
            )
    return {"success": True}


@app.get("/inventory/my_entries/{user_id}", tags=["Inventory"])
def my_material_entries(user_id: int, days: int = 30,
                         current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        cols = [c[1] for c in conn.execute("PRAGMA table_info(inventory_transactions)").fetchall()]
        has_job = "job_id" in cols
        job_sel = ("t.job_id, COALESCE(j.job_type,'-') AS job_type, COALESCE(c.name,'-') AS customer_name"
                   if has_job else "NULL AS job_id, '-' AS job_type, '-' AS customer_name")
        job_join = ("LEFT JOIN jobs j ON t.job_id=j.id LEFT JOIN customers c ON j.customer_id=c.id"
                    if has_job else "")
        rows = conn.execute(f"""
            SELECT t.id AS txn_id, t.timestamp,
                   i.name AS material_name, COALESCE(i.uom,'Pcs') AS uom,
                   t.transaction_type, t.quantity,
                   COALESCE(t.remarks,'') AS remarks, {job_sel}
            FROM inventory_transactions t
            JOIN inventory_items i ON t.item_id=i.id
            {job_join}
            WHERE t.user_id=?
              AND t.timestamp >= datetime('now', '-{int(days)} days')
            ORDER BY t.timestamp DESC
        """, (user_id,)).fetchall()
    return rows_to_list(rows)


@app.get("/inventory/active_jobs", tags=["Inventory"])
def active_jobs_for_material(user_id: Optional[int] = None, role: Optional[str] = None,
                               current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        if role in ("staff", "sub_staff") and user_id:
            rows = conn.execute(
                """SELECT j.id, j.job_type, j.description, c.name AS customer_name, j.status
                   FROM jobs j JOIN customers c ON j.customer_id=c.id
                   WHERE j.assigned_staff_id=? AND j.status NOT IN ('Delivered')
                   ORDER BY j.id DESC LIMIT 200""", (user_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT j.id, j.job_type, j.description, c.name AS customer_name, j.status
                   FROM jobs j JOIN customers c ON j.customer_id=c.id
                   WHERE j.status NOT IN ('Delivered')
                   ORDER BY j.id DESC LIMIT 200"""
            ).fetchall()
    return rows_to_list(rows)


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       INVOICES                                   ║
# ╚═══════════════════════════════════════════════════════════════════╝

def _ensure_invoices_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no   TEXT UNIQUE,
            customer_id  INTEGER,
            job_id       INTEGER,
            total_amount REAL,
            discount     REAL DEFAULT 0,
            tax_percent  REAL DEFAULT 0,
            tax_amount   REAL DEFAULT 0,
            grand_total  REAL,
            amount_paid  REAL DEFAULT 0,
            balance      REAL,
            status       TEXT DEFAULT 'Unpaid',
            notes        TEXT,
            due_date     TEXT,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(customer_id) REFERENCES customers(id),
            FOREIGN KEY(job_id) REFERENCES jobs(id)
        )
    """)


@app.get("/invoices", tags=["Invoices"])
def get_invoices(customer_id: Optional[int] = None,
                 limit: int = 100, offset: int = 0,
                 current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        _ensure_invoices_table(conn)
        query = """
            SELECT i.*, c.name AS customer_name, c.mobile AS customer_mobile, j.job_type
            FROM invoices i
            LEFT JOIN customers c ON i.customer_id=c.id
            LEFT JOIN jobs j ON i.job_id=j.id WHERE 1=1
        """
        params = []
        if customer_id:
            query += " AND i.customer_id=?"; params.append(customer_id)
        query += " ORDER BY i.id DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        rows = conn.execute(query, params).fetchall()
    return rows_to_list(rows)


@app.get("/invoices/customer/{customer_id}", tags=["Invoices"])
def customer_invoices(customer_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        _ensure_invoices_table(conn)
        rows = conn.execute(
            "SELECT * FROM invoices WHERE customer_id=? ORDER BY id DESC", (customer_id,)
        ).fetchall()
    return rows_to_list(rows)


@app.get("/invoices/{invoice_id}", tags=["Invoices"])
def get_invoice(invoice_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        _ensure_invoices_table(conn)
        row = conn.execute(
            """SELECT i.*, c.name AS customer_name, c.mobile AS customer_mobile,
                      c.address AS customer_address, c.gst_no,
                      j.job_type, j.description AS job_description, j.size
               FROM invoices i
               LEFT JOIN customers c ON i.customer_id=c.id
               LEFT JOIN jobs j ON i.job_id=j.id
               WHERE i.id=?""", (invoice_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    return dict(row)


@app.post("/invoices", tags=["Invoices"], status_code=201)
def create_invoice(data: InvoiceCreate, current_user: dict = Depends(get_current_user)):
    net = round(data.total_amount - data.discount, 2)
    tax_amount = round(net * data.tax_percent / 100, 2)
    grand_total = round(net + tax_amount, 2)
    invoice_no = f"KPR{datetime.date.today().strftime('%Y%m%d')}{secrets.token_hex(2).upper()}"
    with get_db() as conn:
        _ensure_invoices_table(conn)
        cursor = conn.execute(
            """INSERT INTO invoices
               (invoice_no, customer_id, job_id, total_amount, discount,
                tax_percent, tax_amount, grand_total, balance, notes, due_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (invoice_no, data.customer_id, data.job_id, data.total_amount,
             data.discount, data.tax_percent, tax_amount,
             grand_total, grand_total, data.notes, data.due_date)
        )
        new_id = cursor.lastrowid
        log_activity(conn, current_user, "Invoice Create",
                     f"Invoice #{invoice_no} created for customer {data.customer_id}")
    return {"id": new_id, "invoice_no": invoice_no,
            "grand_total": grand_total, "message": "Invoice created."}


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       DASHBOARD                                  ║
# ╚═══════════════════════════════════════════════════════════════════╝

@app.get("/dashboard/summary", tags=["Dashboard"])
def dashboard_summary(current_user: dict = Depends(get_current_user)):
    today      = datetime.date.today().isoformat()
    month_start = datetime.date.today().replace(day=1).isoformat()
    week_start = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    with get_db() as conn:
        total_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        jobs_row = conn.execute("""
            SELECT
              SUM(CASE WHEN status='Pending'     THEN 1 ELSE 0 END) AS pending,
              SUM(CASE WHEN status='In Progress' THEN 1 ELSE 0 END) AS in_progress,
              SUM(CASE WHEN status='Completed'   THEN 1 ELSE 0 END) AS completed,
              SUM(CASE WHEN status='Delivered'   THEN 1 ELSE 0 END) AS delivered,
              SUM(CASE WHEN status NOT IN ('Delivered','Cancelled')
                       AND due_date < ? THEN 1 ELSE 0 END) AS overdue
            FROM jobs
        """, (today,)).fetchone()
        today_pay  = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments WHERE payment_date=?", (today,)
        ).fetchone()[0]
        month_pay  = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments WHERE payment_date>=?", (month_start,)
        ).fetchone()[0]
        week_pay   = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments WHERE payment_date>=?", (week_start,)
        ).fetchone()[0]
        pend_coll  = conn.execute(
            "SELECT COALESCE(SUM(balance),0) FROM jobs WHERE payment_status!='Paid'"
        ).fetchone()[0]
        low_stock  = conn.execute(
            "SELECT COUNT(*) FROM inventory_items WHERE current_stock<=reorder_level"
        ).fetchone()[0]
        unread = 0
        try:
            unread = conn.execute(
                "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
                (current_user["user_id"],)
            ).fetchone()[0]
        except Exception:
            pass
    return {
        "total_customers": total_customers,
        "jobs": {
            "pending":     jobs_row["pending"]     or 0,
            "in_progress": jobs_row["in_progress"] or 0,
            "completed":   jobs_row["completed"]   or 0,
            "delivered":   jobs_row["delivered"]   or 0,
            "overdue":     jobs_row["overdue"]      or 0,
        },
        "payments": {
            "today":              round(today_pay, 2),
            "this_week":          round(week_pay,  2),
            "this_month":         round(month_pay, 2),
            "pending_collection": round(pend_coll, 2),
        },
        "low_stock_alerts":      low_stock,
        "unread_notifications":  unread,
        "as_of": ts()
    }


@app.get("/dashboard/material_stats", tags=["Dashboard"])
def material_stats(current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        ls = conn.execute(
            "SELECT COUNT(*) FROM inventory_items WHERE reorder_level>0 AND current_stock<=reorder_level"
        ).fetchone()[0]
        r = conn.execute("""
            SELECT SUM(CASE WHEN transaction_type='Usage'   THEN quantity ELSE 0 END) AS u,
                   SUM(CASE WHEN transaction_type='Wastage' THEN quantity ELSE 0 END) AS w
            FROM inventory_transactions WHERE DATE(timestamp)=DATE('now')
        """).fetchone()
        r30 = conn.execute("""
            SELECT SUM(CASE WHEN transaction_type='Usage'   THEN quantity ELSE 0 END) AS u,
                   SUM(CASE WHEN transaction_type='Wastage' THEN quantity ELSE 0 END) AS w
            FROM inventory_transactions WHERE timestamp>=datetime('now','-30 days')
        """).fetchone()
        top = conn.execute("""
            SELECT i.name AS material, SUM(t.quantity) AS wasted
            FROM inventory_transactions t JOIN inventory_items i ON t.item_id=i.id
            WHERE t.transaction_type='Wastage' AND t.timestamp>=datetime('now','-30 days')
            GROUP BY t.item_id ORDER BY wasted DESC LIMIT 5
        """).fetchall()
        u30, w30 = (r30["u"] or 0), (r30["w"] or 0)
    return {
        "low_stock_count":   ls,
        "today_usage":       round(r["u"] or 0, 2),
        "today_wastage":     round(r["w"] or 0, 2),
        "month_wastage_pct": round((w30/(u30+w30)*100) if (u30+w30) > 0 else 0, 1),
        "top_wasted":        rows_to_list(top)
    }


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       NOTIFICATIONS                              ║
# ╚═══════════════════════════════════════════════════════════════════╝

@app.get("/notifications/{user_id}", tags=["Notifications"])
def get_notifications(user_id: int, unread_only: bool = False,
                       current_user: dict = Depends(get_current_user)):
    query = "SELECT * FROM notifications WHERE user_id=?"
    params = [user_id]
    if unread_only:
        query += " AND is_read=0"
    query += " ORDER BY created_at DESC LIMIT 100"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return rows_to_list(rows)

@app.get("/notifications/unread_count/{user_id}", tags=["Notifications"])
def unread_count(user_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        r = conn.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0", (user_id,)
        ).fetchone()
    return {"count": r[0] if r else 0}

@app.post("/notifications/mark_read/{notification_id}", tags=["Notifications"])
def mark_read(notification_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute("UPDATE notifications SET is_read=1 WHERE id=?", (notification_id,))
    return {"success": True}

@app.post("/notifications/mark_all_read/{user_id}", tags=["Notifications"])
def mark_all_read(user_id: int, current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user_id,))
    return {"success": True}


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       ADMIN                                      ║
# ╚═══════════════════════════════════════════════════════════════════╝

@app.get("/admin/users", tags=["Admin"])
def get_all_users(current_user: dict = Depends(require_admin)):
    with get_db() as conn:
        rows = conn.execute(
            """SELECT id, username, role, is_active,
                      COALESCE(full_name,'') AS full_name,
                      COALESCE(email,'') AS email
               FROM users ORDER BY role, username"""
        ).fetchall()
    return rows_to_list(rows)


@app.post("/admin/users", tags=["Admin"], status_code=201)
def create_user(data: UserCreate, current_user: dict = Depends(require_admin)):
    valid_roles = ["admin", "staff", "sub_staff"]
    if data.role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Valid roles: {valid_roles}")
    if len(data.password) < 6:
        raise HTTPException(status_code=400, detail="Password minimum 6 characters.")
    with get_db() as conn:
        if conn.execute("SELECT id FROM users WHERE username=?", (data.username,)).fetchone():
            raise HTTPException(status_code=409, detail=f"Username '{data.username}' already exists.")
        cursor = conn.execute(
            """INSERT INTO users (username, password_hash, role, is_active, full_name, email)
               VALUES (?,?,?,?,?,?)""",
            (data.username, hash_password(data.password), data.role,
             int(data.is_active), data.full_name, data.email)
        )
        new_id = cursor.lastrowid
        log_activity(conn, current_user, "User Create",
                     f"User '{data.username}' ({data.role}) created")
    return {"id": new_id, "message": f"User '{data.username}' created."}


@app.put("/admin/users/{user_id}", tags=["Admin"])
def update_user(user_id: int, data: UserUpdate,
                current_user: dict = Depends(require_admin)):
    if data.is_active is False and user_id == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="మీరు మీ account deactivate చేయలేరు.")
    with get_db() as conn:
        row = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        updates = {}
        if data.role is not None:
            if data.role not in ["admin", "staff", "sub_staff"]:
                raise HTTPException(status_code=400, detail="Invalid role.")
            updates["role"] = data.role
        if data.full_name is not None:
            updates["full_name"] = data.full_name
        if data.email is not None:
            updates["email"] = data.email
        if data.is_active is not None:
            updates["is_active"] = int(data.is_active)
        if data.new_password:
            if len(data.new_password) < 6:
                raise HTTPException(status_code=400, detail="Password minimum 6 characters.")
            updates["password_hash"] = hash_password(data.new_password)
        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update.")
        set_clause = ", ".join(f"{k}=?" for k in updates)
        conn.execute(f"UPDATE users SET {set_clause} WHERE id=?",
                     list(updates.values()) + [user_id])
        # Force-logout if deactivated or role changed
        if "is_active" in updates or "role" in updates:
            for tok in list(_active_tokens.keys()):
                if _active_tokens[tok]["user_id"] == user_id:
                    del _active_tokens[tok]
        log_activity(conn, current_user, "User Update",
                     f"User '{row['username']}' updated")
    return {"message": f"User '{row['username']}' updated."}


@app.delete("/admin/users/{user_id}", tags=["Admin"])
def deactivate_user(user_id: int, current_user: dict = Depends(require_admin)):
    if user_id == current_user["user_id"]:
        raise HTTPException(status_code=400, detail="మీరు మీ account delete చేయలేరు.")
    with get_db() as conn:
        row = conn.execute("SELECT username FROM users WHERE id=?", (user_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="User not found.")
        conn.execute("UPDATE users SET is_active=0 WHERE id=?", (user_id,))
        for tok in list(_active_tokens.keys()):
            if _active_tokens[tok]["user_id"] == user_id:
                del _active_tokens[tok]
        log_activity(conn, current_user, "User Deactivate",
                     f"User '{row['username']}' deactivated")
    return {"message": f"User '{row['username']}' deactivated."}


@app.get("/admin/active-sessions", tags=["Admin"])
def active_sessions(current_user: dict = Depends(require_admin)):
    now = datetime.datetime.utcnow()
    return [
        {
            "user_id":    info["user_id"],
            "username":   info["username"],
            "role":       info["role"],
            "expires_at": info["expires"].strftime("%Y-%m-%d %H:%M:%S"),
            "token_hint": tok[:8] + "…"
        }
        for tok, info in _active_tokens.items()
        if info["expires"] > now
    ]


@app.post("/admin/force-logout/{user_id}", tags=["Admin"])
def force_logout(user_id: int, current_user: dict = Depends(require_admin)):
    removed = sum(
        1 for tok in list(_active_tokens)
        if _active_tokens.pop(tok, {}).get("user_id") == user_id
    )
    with get_db() as conn:
        log_activity(conn, current_user, "Force Logout",
                     f"User ID {user_id} force-logged-out")
    return {"message": f"User {user_id} logged out.", "sessions_removed": removed}


@app.get("/admin/activity-log", tags=["Admin"])
def activity_log(limit: int = 200, current_user: dict = Depends(require_admin)):
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM activity_log ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
    return rows_to_list(rows)


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       REPORTS                                    ║
# ╚═══════════════════════════════════════════════════════════════════╝

@app.get("/admin/reports/daily", tags=["Reports"])
def daily_report(date: Optional[str] = None,
                 current_user: dict = Depends(require_admin)):
    report_date = date or datetime.date.today().isoformat()
    with get_db() as conn:
        new_customers = conn.execute(
            "SELECT COUNT(*) FROM customers WHERE DATE(created_at)=?", (report_date,)
        ).fetchone()[0]
        new_jobs = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE DATE(created_at)=?", (report_date,)
        ).fetchone()[0]
        payments = conn.execute(
            "SELECT COALESCE(SUM(amount),0), COUNT(*) FROM payments WHERE payment_date=?",
            (report_date,)
        ).fetchone()
        completed = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE DATE(completion_date)=?", (report_date,)
        ).fetchone()[0]
        delivered = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE DATE(delivery_date)=?", (report_date,)
        ).fetchone()[0]
    return {
        "date":             report_date,
        "new_customers":    new_customers,
        "new_jobs":         new_jobs,
        "jobs_completed":   completed,
        "jobs_delivered":   delivered,
        "payments_total":   round(payments[0], 2),
        "payments_count":   payments[1],
    }


@app.get("/reports/revenue", tags=["Reports"])
def revenue_report(start: str, end: str,
                   current_user: dict = Depends(require_admin)):
    with get_db() as conn:
        daily = conn.execute("""
            SELECT payment_date AS date, SUM(amount) AS revenue, COUNT(*) AS transactions
            FROM payments WHERE payment_date BETWEEN ? AND ?
            GROUP BY payment_date ORDER BY payment_date
        """, (start, end)).fetchall()
        by_mode = conn.execute("""
            SELECT COALESCE(payment_mode,'Cash') AS mode,
                   SUM(amount) AS total, COUNT(*) AS count
            FROM payments WHERE payment_date BETWEEN ? AND ?
            GROUP BY payment_mode
        """, (start, end)).fetchall()
        totals = conn.execute("""
            SELECT COALESCE(SUM(amount),0) AS total_revenue,
                   COUNT(*) AS total_transactions,
                   COUNT(DISTINCT customer_id) AS unique_customers
            FROM payments WHERE payment_date BETWEEN ? AND ?
        """, (start, end)).fetchone()
        new_jobs = conn.execute("""
            SELECT COUNT(*) AS new_jobs, COALESCE(SUM(final_price),0) AS total_job_value
            FROM jobs WHERE DATE(start_date) BETWEEN ? AND ?
        """, (start, end)).fetchone()
        overdue = conn.execute("""
            SELECT COUNT(*) AS overdue_jobs, COALESCE(SUM(balance),0) AS overdue_amount
            FROM jobs WHERE due_date BETWEEN ? AND ?
              AND payment_status!='Paid' AND status NOT IN ('Delivered','Cancelled')
        """, (start, end)).fetchone()
    return {
        "period":  {"start": start, "end": end},
        "totals":  {
            "revenue":         round(totals["total_revenue"], 2),
            "transactions":    totals["total_transactions"],
            "customers":       totals["unique_customers"],
            "new_jobs":        new_jobs["new_jobs"],
            "new_jobs_value":  round(new_jobs["total_job_value"], 2),
            "overdue_jobs":    overdue["overdue_jobs"],
            "overdue_amount":  round(overdue["overdue_amount"], 2),
        },
        "daily":   rows_to_list(daily),
        "by_mode": rows_to_list(by_mode),
    }


@app.get("/reports/monthly", tags=["Reports"])
def monthly_report(year: int = datetime.date.today().year,
                   current_user: dict = Depends(require_admin)):
    month_names = ["Jan","Feb","Mar","Apr","May","Jun",
                   "Jul","Aug","Sep","Oct","Nov","Dec"]
    with get_db() as conn:
        rows = conn.execute("""
            SELECT strftime('%m', payment_date) AS month_num,
                   SUM(amount) AS revenue, COUNT(*) AS transactions
            FROM payments WHERE strftime('%Y', payment_date)=?
            GROUP BY month_num ORDER BY month_num
        """, (str(year),)).fetchall()
        yearly_total = conn.execute(
            "SELECT COALESCE(SUM(amount),0) FROM payments WHERE strftime('%Y',payment_date)=?",
            (str(year),)
        ).fetchone()[0]
    rev_map = {r["month_num"]: r for r in rows}
    monthly = []
    for i in range(1, 13):
        m = f"{i:02d}"
        r = rev_map.get(m)
        monthly.append({
            "month": month_names[i-1], "month_num": m,
            "revenue": round(r["revenue"], 2) if r else 0,
            "transactions": r["transactions"] if r else 0
        })
    return {"year": year, "total_revenue": round(yearly_total, 2), "monthly": monthly}


@app.get("/reports/material_transactions", tags=["Reports"])
def material_transactions(start: str, end: str,
                           user_id: Optional[int] = None,
                           trans_type: Optional[str] = None,
                           current_user: dict = Depends(require_admin)):
    query = """
        SELECT t.id AS txn_id, t.timestamp,
               COALESCE(u.full_name, u.username, 'Unknown') AS entered_by,
               u.username, u.role AS user_role, t.job_id,
               COALESCE(j.job_type,'-') AS job_type,
               COALESCE(c.name,'-') AS customer_name,
               i.name AS material_name,
               COALESCE(i.uom,'Pcs') AS uom,
               t.transaction_type, t.quantity,
               COALESCE(t.remarks,'') AS remarks
        FROM inventory_transactions t
        JOIN inventory_items i ON t.item_id=i.id
        LEFT JOIN users u ON t.user_id=u.id
        LEFT JOIN jobs j ON t.job_id=j.id
        LEFT JOIN customers c ON j.customer_id=c.id
        WHERE t.timestamp BETWEEN ? AND ?
    """
    params = [start + " 00:00:00", end + " 23:59:59"]
    if user_id:
        query += " AND t.user_id=?"; params.append(user_id)
    if trans_type and trans_type != "All":
        query += " AND t.transaction_type=?"; params.append(trans_type)
    query += " ORDER BY t.timestamp DESC"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
    return rows_to_list(rows)


@app.get("/reports/staff_summary", tags=["Reports"])
def staff_summary(start: str, end: str, current_user: dict = Depends(require_admin)):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT COALESCE(u.full_name, u.username, 'Unknown') AS staff_name, u.role,
                   COUNT(DISTINCT t.job_id) AS jobs_worked,
                   SUM(CASE WHEN t.transaction_type='Usage'   THEN t.quantity ELSE 0 END) AS usage_qty,
                   SUM(CASE WHEN t.transaction_type='Wastage' THEN t.quantity ELSE 0 END) AS wastage_qty
            FROM inventory_transactions t
            LEFT JOIN users u ON t.user_id=u.id
            WHERE t.timestamp BETWEEN ? AND ?
              AND t.transaction_type IN ('Usage','Wastage')
            GROUP BY t.user_id ORDER BY usage_qty DESC
        """, (start + " 00:00:00", end + " 23:59:59")).fetchall()
    return rows_to_list(rows)


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       GLOBAL SEARCH                              ║
# ╚═══════════════════════════════════════════════════════════════════╝

@app.get("/search", tags=["Search"])
def global_search(q: str, current_user: dict = Depends(get_current_user)):
    if len(q) < 2:
        return {"customers": [], "jobs": [], "payments": []}
    like = f"%{q}%"
    with get_db() as conn:
        custs = conn.execute(
            "SELECT id, name, mobile, email FROM customers WHERE name LIKE ? OR mobile LIKE ? OR email LIKE ? LIMIT 5",
            (like, like, like)
        ).fetchall()
        jobs = conn.execute(
            """SELECT j.id, j.job_type, j.status, j.balance, c.name AS customer_name
               FROM jobs j LEFT JOIN customers c ON j.customer_id=c.id
               WHERE c.name LIKE ? OR j.job_type LIKE ? OR CAST(j.id AS TEXT) LIKE ?
               ORDER BY j.id DESC LIMIT 5""",
            (like, like, like)
        ).fetchall()
        pays = conn.execute(
            """SELECT p.id, p.amount, p.payment_date, p.payment_mode, c.name AS customer_name
               FROM payments p LEFT JOIN customers c ON p.customer_id=c.id
               WHERE c.name LIKE ? OR CAST(p.id AS TEXT) LIKE ?
               ORDER BY p.id DESC LIMIT 5""",
            (like, like)
        ).fetchall()
    return {
        "query":     q,
        "customers": rows_to_list(custs),
        "jobs":      rows_to_list(jobs),
        "payments":  rows_to_list(pays),
    }


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       SERVER STARTUP                             ║
# ╚═══════════════════════════════════════════════════════════════════╝

# ╔═══════════════════════════════════════════════════════════════════╗
# ║              MISSING ENDPOINTS (api_client.py compatibility)     ║
# ╚═══════════════════════════════════════════════════════════════════╝

class SettingsUpdate(BaseModel):
    settings: dict

class ActivityLogEntry(BaseModel):
    user_id: int
    username: str
    activity_type: str
    description: str

class JobPaymentUpdate(BaseModel):
    amount_paid: float

class NotificationLogSent(BaseModel):
    job_id: int
    channel: str
    mobile: str
    message: str
    sent_by_user_id: int


@app.get("/settings", tags=["Settings"])
def get_settings(current_user: dict = Depends(get_current_user)):
    """App settings — lab name, logo, currency, etc."""
    with get_db() as conn:
        try:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            return {r["key"]: r["value"] for r in rows}
        except Exception:
            return {
                "lab_name": "KPR Colour Lab",
                "shop_name": "KPR Lab",
                "currency_symbol": "₹",
                "logo_path": "",
                "invoice_footer": "Thank you for your business!",
                "shop_phone": "",
                "shop_address": "",
                "slip_footer": "Thank you for your business!",
            }


@app.post("/settings/update", tags=["Settings"])
def update_settings(data: SettingsUpdate,
                    current_user: dict = Depends(require_admin)):
    """Update app settings — Admin only."""
    with get_db() as conn:
        try:
            for key, value in data.settings.items():
                conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?,?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, str(value))
                )
            log_activity(conn, current_user, "Settings Update",
                         f"Updated: {list(data.settings.keys())}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    return {"success": True, "message": "Settings updated."}


@app.post("/activity/log", tags=["Activity"])
def client_log_activity(data: ActivityLogEntry,
                         current_user: dict = Depends(get_current_user)):
    """PC2/PC3 modules నుండి activity log చేయడానికి."""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO activity_log (user_id, username, activity_type, description, timestamp) VALUES (?,?,?,?,?)",
            (data.user_id, data.username, data.activity_type, data.description, ts())
        )
    return {"success": True}


@app.patch("/jobs/{job_id}/payment", tags=["Jobs"])
def update_job_payment(job_id: int, data: JobPaymentUpdate,
                        current_user: dict = Depends(get_current_user)):
    """Job balance update చేయడానికి (payment received)."""
    with get_db() as conn:
        job = conn.execute(
            "SELECT final_price, advance1 FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        total_paid = (job["advance1"] or 0) + data.amount_paid
        new_balance = max(0, (job["final_price"] or 0) - total_paid)
        new_status = "Paid" if new_balance <= 0 else "Partially Paid"
        conn.execute(
            "UPDATE jobs SET balance=?, payment_status=? WHERE id=?",
            (new_balance, new_status, job_id)
        )
        log_activity(conn, current_user, "Job Payment Update",
                     f"Job #{job_id} payment updated. Balance: {new_balance}")
    return {"job_id": job_id, "new_balance": new_balance, "status": new_status}


@app.post("/notifications/log_sent", tags=["Notifications"])
def log_notification_sent(data: NotificationLogSent,
                           current_user: dict = Depends(get_current_user)):
    """SMS/WhatsApp notification sent log চেয়াল্সি."""
    with get_db() as conn:
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS notification_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER, channel TEXT, mobile TEXT,
                    message TEXT, sent_by INTEGER,
                    sent_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute(
                "INSERT INTO notification_log (job_id,channel,mobile,message,sent_by) VALUES (?,?,?,?,?)",
                (data.job_id, data.channel, data.mobile,
                 data.message, data.sent_by_user_id)
            )
        except Exception:
            pass
    return {"success": True}


@app.get("/customers/unbilled/{customer_id}", tags=["Customers"])
def customer_unbilled_jobs(customer_id: int,
                            current_user: dict = Depends(get_current_user)):
    """Customer's unpaid / active jobs — invoice create కోసం."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, job_type, size, final_price, balance,
                   payment_status, status, due_date
            FROM jobs
            WHERE customer_id=?
              AND payment_status != 'Paid'
              AND status NOT IN ('Cancelled')
            ORDER BY id DESC
        """, (customer_id,)).fetchall()
    return rows_to_list(rows)


@app.get("/reports/customers", tags=["Reports"])
def customer_report(start: str, end: str, search: str = "",
                    current_user: dict = Depends(require_admin)):
    """Customer-wise job/payment summary for a date range."""
    like = f"%{search}%" if search else "%"
    with get_db() as conn:
        rows = conn.execute("""
            SELECT c.id, c.name, c.mobile,
                   COUNT(DISTINCT j.id)          AS total_jobs,
                   COALESCE(SUM(j.final_price),0) AS total_billed,
                   COALESCE(SUM(j.balance),0)     AS outstanding,
                   COALESCE(SUM(p.amount),0)      AS total_paid,
                   MAX(j.start_date)              AS last_job_date
            FROM customers c
            LEFT JOIN jobs j
                   ON j.customer_id=c.id
                  AND DATE(j.start_date) BETWEEN ? AND ?
            LEFT JOIN payments p
                   ON p.customer_id=c.id
                  AND p.payment_date BETWEEN ? AND ?
            WHERE c.name LIKE ? OR c.mobile LIKE ?
            GROUP BY c.id
            HAVING total_jobs > 0 OR total_paid > 0
            ORDER BY total_billed DESC
        """, (start, end, start, end, like, like)).fetchall()
    return rows_to_list(rows)


@app.get("/reports/material_usage", tags=["Reports"])
def material_usage_report(start: str, end: str,
                           current_user: dict = Depends(require_admin)):
    """Material usage summary — item-wise totals."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT i.name AS material_name,
                   COALESCE(i.uom, 'Pcs') AS uom,
                   COALESCE(i.category_id, 0) AS category_id,
                   SUM(CASE WHEN t.transaction_type='Usage'    THEN t.quantity ELSE 0 END) AS total_used,
                   SUM(CASE WHEN t.transaction_type='Wastage'  THEN t.quantity ELSE 0 END) AS total_wasted,
                   SUM(CASE WHEN t.transaction_type='Stock In' THEN t.quantity ELSE 0 END) AS total_stocked,
                   COUNT(DISTINCT t.user_id)  AS staff_count,
                   COUNT(DISTINCT t.job_id)   AS job_count
            FROM inventory_transactions t
            JOIN inventory_items i ON t.item_id=i.id
            WHERE t.timestamp BETWEEN ? AND ?
            GROUP BY t.item_id
            ORDER BY total_used DESC
        """, (start + " 00:00:00", end + " 23:59:59")).fetchall()
    return rows_to_list(rows)


@app.get("/reports/material_by_job", tags=["Reports"])
def material_by_job(start: str, end: str,
                    current_user: dict = Depends(require_admin)):
    """Material usage grouped by job — job-wise consumption."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT j.id AS job_id, j.job_type,
                   COALESCE(c.name, 'Unknown') AS customer_name,
                   i.name AS material_name,
                   COALESCE(i.uom,'Pcs') AS uom,
                   SUM(CASE WHEN t.transaction_type='Usage'   THEN t.quantity ELSE 0 END) AS used,
                   SUM(CASE WHEN t.transaction_type='Wastage' THEN t.quantity ELSE 0 END) AS wasted,
                   COUNT(DISTINCT t.user_id) AS staff_count
            FROM inventory_transactions t
            JOIN inventory_items i ON t.item_id=i.id
            LEFT JOIN jobs j ON t.job_id=j.id
            LEFT JOIN customers c ON j.customer_id=c.id
            WHERE t.job_id IS NOT NULL
              AND t.timestamp BETWEEN ? AND ?
            GROUP BY t.job_id, t.item_id
            ORDER BY j.id DESC, used DESC
        """, (start + " 00:00:00", end + " 23:59:59")).fetchall()
    return rows_to_list(rows)


if __name__ == "__main__":
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        lan_ip = "localhost"

    print("=" * 60)
    print("  KPR Colour Lab CRM — API Server v2.0")
    print("=" * 60)
    print(f"  Local  :  http://localhost:8000")
    print(f"  Network:  http://{lan_ip}:8000")
    print(f"  Swagger:  http://{lan_ip}:8000/docs")
    print("=" * 60)
    print(f"  Database: {os.path.abspath(DATABASE_NAME)}")
    print(f"  Token expiry: {ACCESS_TOKEN_EXPIRE_MINUTES // 60} hours")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
