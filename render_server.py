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

import psycopg2
from psycopg2.extras import RealDictCursor
NEON_SYNC = False  # Render: directly on Neon, no secondary sync needed
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
    from fastapi.responses import JSONResponse, FileResponse
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("ERROR: pip install fastapi uvicorn python-multipart")
    raise


# ╔═══════════════════════════════════════════════════════════════════╗
# ║                        CONFIGURATION                             ║
# ╚═══════════════════════════════════════════════════════════════════╝

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable set cheyandi!")
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


def _lastrowid(conn):
    """Get last inserted id via RETURNING clause already fetched."""
    try:
        row = conn._cur.fetchone()
        return row[0] if row else None
    except Exception:
        return None

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


import base64 as _b64
_EMBEDDED_HTML = _b64.b64decode("PCFET0NUWVBFIGh0bWw+CjxodG1sIGxhbmc9ImVuIj4KPGhlYWQ+CjxtZXRhIGNoYXJzZXQ9InV0Zi04Ii8+CjxtZXRhIG5hbWU9InZpZXdwb3J0IiBjb250ZW50PSJ3aWR0aD1kZXZpY2Utd2lkdGgsaW5pdGlhbC1zY2FsZT0xIi8+Cjx0aXRsZT5LUFIgQ29sb3VyIExhYiDigJQgQ1JNPC90aXRsZT4KPHNjcmlwdCBzcmM9Imh0dHBzOi8vdW5wa2cuY29tL3JlYWN0QDE4L3VtZC9yZWFjdC5wcm9kdWN0aW9uLm1pbi5qcyI+PC9zY3JpcHQ+CjxzY3JpcHQgc3JjPSJodHRwczovL3VucGtnLmNvbS9yZWFjdC1kb21AMTgvdW1kL3JlYWN0LWRvbS5wcm9kdWN0aW9uLm1pbi5qcyI+PC9zY3JpcHQ+CjxzY3JpcHQgc3JjPSJodHRwczovL3VucGtnLmNvbS9AYmFiZWwvc3RhbmRhbG9uZS9iYWJlbC5taW4uanMiPjwvc2NyaXB0Pgo8c3R5bGU+Cip7Ym94LXNpemluZzpib3JkZXItYm94O21hcmdpbjowO3BhZGRpbmc6MH0KOnJvb3R7CiAgLS1iZy1wYWdlOiNmYWZhZjk7LS1iZy1jYXJkOiNmZmZmZmY7LS1iZy1jYXJkMjojZmFmYWY5Oy0tYmctaW5wdXQ6I2ZmZmZmZjsKICAtLXRleHQtcHJpOiMxYzE5MTc7LS10ZXh0LXNlYzojNTc1MzRlOy0tdGV4dC1tdXRlZDojNzg3MTZjOy0tdGV4dC1mYWludDojYThhMjllOwogIC0tYm9yZGVyOiNlN2U1ZTQ7LS1ib3JkZXIyOiNmNWY1ZjQ7LS1zaGFkb3c6cmdiYSgwLDAsMCwuMDgpOwogIC0tc2lkZWJhci1iZzojMWMxOTE3Oy0tc2lkZWJhci1hY3Q6IzI5MjUyNDstLXNpZGViYXItdHh0OiNlN2U1ZTQ7LS1zaWRlYmFyLW11dDojNzg3MTZjOwp9CmJvZHkuZGFya3sKICAtLWJnLXBhZ2U6IzE3MTQxMjstLWJnLWNhcmQ6IzIyMWYxZDstLWJnLWNhcmQyOiMxYTE4MTY7LS1iZy1pbnB1dDojMmEyNjIzOwogIC0tdGV4dC1wcmk6I2Y1ZjVmNDstLXRleHQtc2VjOiNkNmQzZDE7LS10ZXh0LW11dGVkOiNhOGEyOWU7LS10ZXh0LWZhaW50OiM3ODcxNmM7CiAgLS1ib3JkZXI6IzNkMzkzNjstLWJvcmRlcjI6IzJkMmIyOTstLXNoYWRvdzpyZ2JhKDAsMCwwLC40KTsKICAtLXNpZGViYXItYmc6IzBmMGQwYzstLXNpZGViYXItYWN0OiMxYzE5MTc7LS1zaWRlYmFyLXR4dDojZTdlNWU0Oy0tc2lkZWJhci1tdXQ6IzU3NTM0ZTsKfQpib2R5e2ZvbnQtZmFtaWx5OidTZWdvZSBVSScsc3lzdGVtLXVpLHNhbnMtc2VyaWY7YmFja2dyb3VuZDp2YXIoLS1iZy1wYWdlKTtvdmVyZmxvdzpoaWRkZW47Y29sb3I6dmFyKC0tdGV4dC1wcmkpO3RyYW5zaXRpb246YmFja2dyb3VuZCAuMnMsY29sb3IgLjJzfQpib2R5LmRhcmsgaW5wdXQsYm9keS5kYXJrIHNlbGVjdCxib2R5LmRhcmsgdGV4dGFyZWF7YmFja2dyb3VuZDp2YXIoLS1iZy1pbnB1dCkhaW1wb3J0YW50O2NvbG9yOnZhcigtLXRleHQtcHJpKSFpbXBvcnRhbnQ7Ym9yZGVyLWNvbG9yOnZhcigtLWJvcmRlcikhaW1wb3J0YW50fQpib2R5LmRhcmsgLmtwci1jYXJke2JhY2tncm91bmQ6dmFyKC0tYmctY2FyZCkhaW1wb3J0YW50O2JvcmRlci1jb2xvcjp2YXIoLS1ib3JkZXIpIWltcG9ydGFudDtjb2xvcjp2YXIoLS10ZXh0LXByaSkhaW1wb3J0YW50fQpib2R5LmRhcmsgLmtwci1tb2RhbHtiYWNrZ3JvdW5kOnZhcigtLWJnLWNhcmQpIWltcG9ydGFudDtjb2xvcjp2YXIoLS10ZXh0LXByaSkhaW1wb3J0YW50fQpib2R5LmRhcmsgLmtwci1zaWRlYmFye2JhY2tncm91bmQ6dmFyKC0tc2lkZWJhci1iZykhaW1wb3J0YW50fQpib2R5LmRhcmsgLmtwci1oZWFkZXJ7YmFja2dyb3VuZDp2YXIoLS1iZy1jYXJkKSFpbXBvcnRhbnQ7Ym9yZGVyLWNvbG9yOnZhcigtLWJvcmRlcikhaW1wb3J0YW50fQpib2R5LmRhcmsgLmtwci10YWJsZSB0cntib3JkZXItY29sb3I6dmFyKC0tYm9yZGVyMikhaW1wb3J0YW50fQpib2R5LmRhcmsgLmtwci10YWJsZSB0aHtjb2xvcjp2YXIoLS10ZXh0LW11dGVkKSFpbXBvcnRhbnR9CmJvZHkuZGFyayAua3ByLXRhYmxlIHRke2NvbG9yOnZhcigtLXRleHQtc2VjKSFpbXBvcnRhbnR9CmJvZHkuZGFyayAua3ByLWJ0bi1naG9zdHtiYWNrZ3JvdW5kOnZhcigtLWJnLWlucHV0KSFpbXBvcnRhbnQ7Ym9yZGVyLWNvbG9yOnZhcigtLWJvcmRlcikhaW1wb3J0YW50O2NvbG9yOnZhcigtLXRleHQtc2VjKSFpbXBvcnRhbnR9CmJvZHkuZGFyayAua3ByLXBne2JhY2tncm91bmQ6dmFyKC0tYmctcGFnZSkhaW1wb3J0YW50O2NvbG9yOiNlN2U1ZTQhaW1wb3J0YW50fQpib2R5LmRhcmsgLmtwci1wZyBoMSxib2R5LmRhcmsgLmtwci1wZyBoMixib2R5LmRhcmsgLmtwci1wZyBoMyxib2R5LmRhcmsgLmtwci1wZyBoNHtjb2xvcjojZjVmNWY0IWltcG9ydGFudH0KYm9keS5kYXJrIC5rcHItcGcgcCxib2R5LmRhcmsgLmtwci1wZyBzcGFuOm5vdChbc3R5bGUqPSJjb2xvcjojIl0pOm5vdChbc3R5bGUqPSJjb2xvcjpCIl0pLGJvZHkuZGFyayAua3ByLXBnIGxhYmVse2NvbG9yOiNkNmQzZDEhaW1wb3J0YW50fQpib2R5LmRhcmsgLmtwci10YWJsZSB0aHtjb2xvcjojYThhMjllIWltcG9ydGFudDtib3JkZXItYm90dG9tOjJweCBzb2xpZCAjM2QzOTM2IWltcG9ydGFudH0KYm9keS5kYXJrIC5rcHItdGFibGUgdHJ7Ym9yZGVyLWJvdHRvbToxcHggc29saWQgIzJkMmIyOSFpbXBvcnRhbnR9CmJvZHkuZGFyayAua3ByLXRhYmxlIHRke2NvbG9yOiNkNmQzZDEhaW1wb3J0YW50fQpib2R5LmRhcmsgLmtwci1wZyBbc3R5bGUqPSJiYWNrZ3JvdW5kOiNmZmYiXXtiYWNrZ3JvdW5kOnZhcigtLWJnLWNhcmQpIWltcG9ydGFudH0KYm9keS5kYXJrIC5rcHItcGcgW3N0eWxlKj0nYmFja2dyb3VuZDoiI2ZmZiInXXtiYWNrZ3JvdW5kOnZhcigtLWJnLWNhcmQpIWltcG9ydGFudH0KYm9keS5kYXJrIC5rcHItcGcgW3N0eWxlKj0iYmFja2dyb3VuZDojZmFmYWY5Il17YmFja2dyb3VuZDp2YXIoLS1iZy1jYXJkMikhaW1wb3J0YW50fQpib2R5LmRhcmsgLmtwci1wZyBbc3R5bGUqPSJiYWNrZ3JvdW5kOiNmNWY1ZjQiXXtiYWNrZ3JvdW5kOiMyYTI2MjMhaW1wb3J0YW50fQpib2R5LmRhcmsgLmtwci1wZyBbc3R5bGUqPSJib3JkZXI6MXB4IHNvbGlkICNlN2U1ZTQiXXtib3JkZXItY29sb3I6dmFyKC0tYm9yZGVyKSFpbXBvcnRhbnR9CmJvZHkuZGFyayAua3ByLXBnIFtzdHlsZSo9ImJvcmRlckJvdHRvbToxcHggc29saWQgI2YiXXtib3JkZXItYm90dG9tLWNvbG9yOnZhcigtLWJvcmRlcikhaW1wb3J0YW50fQo6Oi13ZWJraXQtc2Nyb2xsYmFye3dpZHRoOjVweDtoZWlnaHQ6NXB4fQo6Oi13ZWJraXQtc2Nyb2xsYmFyLXRodW1ie2JhY2tncm91bmQ6I2U3ZTVlNDtib3JkZXItcmFkaXVzOjEwcHh9CkBrZXlmcmFtZXMgc3Bpbntmcm9te3RyYW5zZm9ybTpyb3RhdGUoMCl9dG97dHJhbnNmb3JtOnJvdGF0ZSgzNjBkZWcpfX0KQGtleWZyYW1lcyBwdWxzZXswJSwxMDAle29wYWNpdHk6MX01MCV7b3BhY2l0eTouMzV9fQpAa2V5ZnJhbWVzIGZhZGVJbntmcm9te29wYWNpdHk6MDt0cmFuc2Zvcm06dHJhbnNsYXRlWSg2cHgpfXRve29wYWNpdHk6MTt0cmFuc2Zvcm06dHJhbnNsYXRlWSgwKX19Ci5mYWRle2FuaW1hdGlvbjpmYWRlSW4gLjI1cyBlYXNlfQppbnB1dDpmb2N1cyxzZWxlY3Q6Zm9jdXMsdGV4dGFyZWE6Zm9jdXN7b3V0bGluZToycHggc29saWQgI2VhNTgwYyFpbXBvcnRhbnQ7b3V0bGluZS1vZmZzZXQ6MH0KLyog4pSA4pSAIE1PQklMRSBSRVNQT05TSVZFIOKUgOKUgCAqLwpAbWVkaWEobWF4LXdpZHRoOjc2OHB4KXsKICBib2R5e292ZXJmbG93OmF1dG8haW1wb3J0YW50fQogIC5kZXNrLW9ubHl7ZGlzcGxheTpub25lIWltcG9ydGFudH0KICAubW9iLWdyaWQtMXtncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIWltcG9ydGFudH0KICAubW9iLWdyaWQtMntncmlkLXRlbXBsYXRlLWNvbHVtbnM6MWZyIDFmciFpbXBvcnRhbnR9CiAgLm1vYi1we3BhZGRpbmc6MTJweCAxNHB4IWltcG9ydGFudH0KICAubW9iLWZ1bGx7d2lkdGg6MTAwJSFpbXBvcnRhbnQ7bWF4LXdpZHRoOjEwMCUhaW1wb3J0YW50fQogIC5tb2Itc3RhY2t7ZmxleC1kaXJlY3Rpb246Y29sdW1uIWltcG9ydGFudDtnYXA6OHB4IWltcG9ydGFudH0KICAubW9iLXNjcm9sbHtvdmVyZmxvdy14OmF1dG8haW1wb3J0YW50Oy13ZWJraXQtb3ZlcmZsb3ctc2Nyb2xsaW5nOnRvdWNofQogIC5tb2ItdGV4dC1zbXtmb250LXNpemU6MTFweCFpbXBvcnRhbnR9CiAgLm1vYi1oaWRle2Rpc3BsYXk6bm9uZSFpbXBvcnRhbnR9Cn0KPC9zdHlsZT4KPGxpbmsgcmVsPSJtYW5pZmVzdCIgaHJlZj0iZGF0YTphcHBsaWNhdGlvbi9qc29uLCU3QiUyMm5hbWUlMjIlM0ElMjJLUFIlMjBDb2xvdXIlMjBMYWIlMjBDUk0lMjIlMkMlMjJzaG9ydF9uYW1lJTIyJTNBJTIyS1BSJTIwTGFiJTIyJTJDJTIyc3RhcnRfdXJsJTIyJTNBJTIyJTJGYXBwJTIyJTJDJTIyZGlzcGxheSUyMiUzQSUyMnN0YW5kYWxvbmUlMjIlMkMlMjJiYWNrZ3JvdW5kX2NvbG9yJTIyJTNBJTIyJTIzZmFmYWY5JTIyJTJDJTIydGhlbWVfY29sb3IlMjIlM0ElMjIlMjNlYTU4MGMlMjIlMkMlMjJpY29ucyUyMiUzQSU1QiU3QiUyMnNyYyUyMiUzQSUyMmh0dHBzJTNBJTJGJTJGaW1nLmljb25zOC5jb20lMkZjb2xvciUyRjk2JTJGY2FtZXJhLnBuZyUyMiUyQyUyMnNpemVzJTIyJTNBJTIyOTZ4OTYlMjIlMkMlMjJ0eXBlJTIyJTNBJTIyaW1hZ2UlMjUyRnBuZyUyMiU3RCU1RCU3RCIvPgo8bWV0YSBuYW1lPSJtb2JpbGUtd2ViLWFwcC1jYXBhYmxlIiBjb250ZW50PSJ5ZXMiLz4KPG1ldGEgbmFtZT0iYXBwbGUtbW9iaWxlLXdlYi1hcHAtY2FwYWJsZSIgY29udGVudD0ieWVzIi8+CjxtZXRhIG5hbWU9ImFwcGxlLW1vYmlsZS13ZWItYXBwLXN0YXR1cy1iYXItc3R5bGUiIGNvbnRlbnQ9ImRlZmF1bHQiLz4KPG1ldGEgbmFtZT0iYXBwbGUtbW9iaWxlLXdlYi1hcHAtdGl0bGUiIGNvbnRlbnQ9IktQUiBMYWIiLz4KPG1ldGEgbmFtZT0idGhlbWUtY29sb3IiIGNvbnRlbnQ9IiNlYTU4MGMiLz4KPC9oZWFkPgo8Ym9keT4KPGRpdiBpZD0icm9vdCI+PC9kaXY+CjxzY3JpcHQgdHlwZT0idGV4dC9iYWJlbCI+CmNvbnN0e3VzZVN0YXRlLHVzZUVmZmVjdCx1c2VSZWYsdXNlQ2FsbGJhY2t9PVJlYWN0OwoKLyog4pSA4pSAIEJSQU5EIOKUgOKUgCAqLwpjb25zdCBCPXtwcmk6IiNlYTU4MGMiLHByaUQ6IiNjMjQxMGMiLHByaUw6IiNmZmY3ZWQiLHByaU06IiNmZWQ3YWEiLAogIHNpZGU6InZhcigtLXNpZGViYXItYmcpIixzaWRlQToidmFyKC0tc2lkZWJhci1hY3QpIixzaWRlTXV0OiJ2YXIoLS1zaWRlYmFyLW11dCkiLHNpZGVUeHQ6InZhcigtLXNpZGViYXItdHh0KSJ9OwoKLyog4pSA4pSAIEFQSSDilIDilIAgKi8KZnVuY3Rpb24gbWFrZUFwaShiYXNlKXsKICBsZXQgdG9rPW51bGw7CiAgY29uc3QgaD0oYXV0aD10cnVlKT0+e2NvbnN0IGhkPXsiQ29udGVudC1UeXBlIjoiYXBwbGljYXRpb24vanNvbiIsIkFjY2VwdCI6ImFwcGxpY2F0aW9uL2pzb24ifTtpZihhdXRoJiZ0b2spaGRbIkF1dGhvcml6YXRpb24iXT1gQmVhcmVyICR7dG9rfWA7cmV0dXJuIGhkO307CiAgY29uc3QgcmVxPWFzeW5jKG1ldGhvZCxwYXRoLGJvZHksYXV0aD10cnVlKT0+ewogICAgY29uc3Qgcj1hd2FpdCBmZXRjaChgJHtiYXNlfSR7cGF0aH1gLHttZXRob2QsaGVhZGVyczpoKGF1dGgpLGJvZHk6Ym9keT9KU09OLnN0cmluZ2lmeShib2R5KTp1bmRlZmluZWR9KTsKICAgIGNvbnN0IGQ9YXdhaXQgci5qc29uKCk7CiAgICBpZighci5vayl7CiAgICAgIGlmKHIuc3RhdHVzPT09NDAxKXtsb2NhbFN0b3JhZ2UucmVtb3ZlSXRlbSgia3ByX3Nlc3Npb24iKTt3aW5kb3cubG9jYXRpb24ucmVsb2FkKCk7fQogICAgICB0aHJvdyBuZXcgRXJyb3IoZC5kZXRhaWx8fGBIVFRQICR7ci5zdGF0dXN9YCk7CiAgICB9cmV0dXJuIGQ7CiAgfTsKICByZXR1cm57CiAgICBzZXRUb2tlbjp0PT57dG9rPXQ7fSwKICAgIGhlYWx0aDooKT0+cmVxKCJHRVQiLCIvaGVhbHRoIixudWxsLGZhbHNlKSwKICAgIGxvZ2luOih1LHApPT5yZXEoIlBPU1QiLCIvYXV0aC9sb2dpbiIse3VzZXJuYW1lOnUscGFzc3dvcmQ6cH0sZmFsc2UpLAogICAgbG9nb3V0OigpPT5yZXEoIlBPU1QiLCIvYXV0aC9sb2dvdXQiKSwKICAgIHN1bW1hcnk6KCk9PnJlcSgiR0VUIiwiL2Rhc2hib2FyZC9zdW1tYXJ5IiksCiAgICBjdXN0b21lcnM6KHM9IiIsbGltPTIwMCk9PnJlcSgiR0VUIixgL2N1c3RvbWVycz9saW1pdD0ke2xpbX0ke3M/YCZzZWFyY2g9JHtlbmNvZGVVUklDb21wb25lbnQocyl9YDoiIn1gICksCiAgICBhZGRDdXN0b21lcjpkPT5yZXEoIlBPU1QiLCIvY3VzdG9tZXJzIixkKSwKICAgIHVwZGF0ZUN1c3RvbWVyOihpZCxkKT0+cmVxKCJQVVQiLGAvY3VzdG9tZXJzLyR7aWR9YCxkKSwKICAgIGpvYnM6KHA9IiIpPT5yZXEoIkdFVCIsYC9qb2JzPyR7cH1gKSwKICAgIGFkZEpvYjpkPT5yZXEoIlBPU1QiLCIvam9icyIsZCksCiAgICB1cGRhdGVKb2JTdGF0dXM6KGlkLHN0YXR1cyxub3Rlcz0iIik9PnJlcSgiUEFUQ0giLGAvam9icy8ke2lkfS9zdGF0dXNgLHtzdGF0dXMsbm90ZXN9KSwKICAgIHBheW1lbnRzOihwPSIiKT0+cmVxKCJHRVQiLGAvcGF5bWVudHM/JHtwfWApLAogICAgYWRkUGF5bWVudDpkPT5yZXEoIlBPU1QiLCIvcGF5bWVudHMiLGQpLAogICAgam9iVHlwZXM6KCk9PnJlcSgiR0VUIiwiL2pvYi10eXBlcyIpLAogICAgaW52ZW50b3J5OigpPT5yZXEoIkdFVCIsIi9pbnZlbnRvcnkiKSwKICAgIGxvd1N0b2NrOigpPT5yZXEoIkdFVCIsIi9pbnZlbnRvcnkvbG93LXN0b2NrIiksCiAgICB1cGRhdGVTdG9jazooaWQscWMsbm90ZXM9IiIpPT5yZXEoIlBBVENIIixgL2ludmVudG9yeS8ke2lkfS9zdG9ja2Ase3F1YW50aXR5X2NoYW5nZTpxYyxub3Rlc30pLAogICAgZGFpbHlSZXBvcnQ6ZGF0ZT0+cmVxKCJHRVQiLGAvYWRtaW4vcmVwb3J0cy9kYWlseSR7ZGF0ZT9gP2RhdGU9JHtkYXRlfWA6IiJ9YCApLAogICAgYWN0aXZpdHlMb2c6KGxpbT02MCk9PnJlcSgiR0VUIixgL2FkbWluL2FjdGl2aXR5LWxvZz9saW1pdD0ke2xpbX1gKSwKICAgIHN0YWZmTGlzdDooKT0+cmVxKCJHRVQiLCIvYXV0aC9zdGFmZiIpLAogICAgY2hhbmdlUGFzc3dvcmQ6KG8sbik9PnJlcSgiUE9TVCIsIi9hdXRoL2NoYW5nZV9wYXNzd29yZCIse29sZF9wYXNzd29yZDpvLG5ld19wYXNzd29yZDpufSksCiAgICBub3RpZmljYXRpb25zOnVpZD0+cmVxKCJHRVQiLGAvbm90aWZpY2F0aW9ucy8ke3VpZH1gKSwKICAgIG1hcmtBbGxSZWFkOnVpZD0+cmVxKCJQT1NUIixgL25vdGlmaWNhdGlvbnMvbWFya19hbGxfcmVhZC8ke3VpZH1gKSwKICAgIGludmVudG9yeUl0ZW1zOigpPT5yZXEoIkdFVCIsIi9pbnZlbnRvcnkiKSwKICAgIGFjdGl2ZUpvYnM6KHVpZCxyb2xlKT0+cmVxKCJHRVQiLGAvaW52ZW50b3J5L2FjdGl2ZV9qb2JzJHt1aWQ/YD91c2VyX2lkPSR7dWlkfSZyb2xlPSR7cm9sZXx8IiJ9YDoiIn1gICksCiAgICBhZGRUcmFuc2FjdGlvbjpkPT5yZXEoIlBPU1QiLCIvaW52ZW50b3J5L3RyYW5zYWN0aW9uIixkKSwKICAgIG15RW50cmllczoodWlkLGRheXM9MzApPT5yZXEoIkdFVCIsYC9pbnZlbnRvcnkvbXlfZW50cmllcy8ke3VpZH0/ZGF5cz0ke2RheXN9YCksCiAgICBhbGxVc2VyczooKT0+cmVxKCJHRVQiLCIvYXV0aC9zdGFmZiIpLAogICAgY3VzdG9tZXJKb2JzOmlkPT5yZXEoIkdFVCIsYC9qb2JzP2N1c3RvbWVyX2lkPSR7aWR9JmxpbWl0PTIwMGApLAogICAgdXBkYXRlSm9iUHJpb3JpdHk6KGlkLHByaW9yaXR5KT0+cmVxKCJQQVRDSCIsYC9qb2JzLyR7aWR9L3ByaW9yaXR5YCx7cHJpb3JpdHl9KSwKICAgIGJ1bGtVcGRhdGVTdGF0dXM6KGlkcyxzdGF0dXMpPT5yZXEoIlBPU1QiLCIvam9icy9idWxrX3N0YXR1cyIse2pvYl9pZHM6aWRzLHN0YXR1c30pLAogIH07Cn0KCi8qIOKUgOKUgCBVVElMUyDilIDilIAgKi8KY29uc3QgZm10PW49Pm49PW51bGw/IuKAlCI6YOKCuSR7TnVtYmVyKG4pLnRvTG9jYWxlU3RyaW5nKCJlbi1JTiIse21heGltdW1GcmFjdGlvbkRpZ2l0czowfSl9YDsKY29uc3QgVE9EQVk9KCk9Pm5ldyBEYXRlKCkudG9JU09TdHJpbmcoKS5zcGxpdCgiVCIpWzBdOwpjb25zdCBJTkk9bmFtZT0+KG5hbWV8fCI/Iikuc3BsaXQoIiAiKS5tYXAodz0+d1swXSkuam9pbigiIikudG9VcHBlckNhc2UoKS5zbGljZSgwLDIpOwoKLyog4pSA4pSAIFNIQVJFRCBVSSDilIDilIAgKi8KZnVuY3Rpb24gU3Bpbih7cz0xM30pe3JldHVybjxzcGFuIHN0eWxlPXt7ZGlzcGxheToiaW5saW5lLWJsb2NrIixhbmltYXRpb246InNwaW4gLjhzIGxpbmVhciBpbmZpbml0ZSJ9fT48c3ZnIHdpZHRoPXtzfSBoZWlnaHQ9e3N9IHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJjdXJyZW50Q29sb3IiIHN0cm9rZVdpZHRoPSIyLjUiIHN0cm9rZUxpbmVjYXA9InJvdW5kIj48cGF0aCBkPSJNMjEgMTJhOSA5IDAgMSAxLTYuMjE5LTguNTYiLz48L3N2Zz48L3NwYW4+O30KZnVuY3Rpb24gSWNvKHtkLHM9MTZ9KXtyZXR1cm48c3ZnIHdpZHRoPXtzfSBoZWlnaHQ9e3N9IHZpZXdCb3g9IjAgMCAyNCAyNCIgZmlsbD0ibm9uZSIgc3Ryb2tlPSJjdXJyZW50Q29sb3IiIHN0cm9rZVdpZHRoPSIxLjgiIHN0cm9rZUxpbmVjYXA9InJvdW5kIiBzdHJva2VMaW5lam9pbj0icm91bmQiPntkfTwvc3ZnPjt9CmZ1bmN0aW9uIFNrZWwoe3c9IjEwMCUiLGg9MTQscj02fSl7cmV0dXJuPGRpdiBzdHlsZT17e3dpZHRoOncsaGVpZ2h0OmgsYm9yZGVyUmFkaXVzOnIsYmFja2dyb3VuZDoiI2YzZjRmNiIsYW5pbWF0aW9uOiJwdWxzZSAxLjRzIGVhc2UgaW5maW5pdGUifX0vPjt9CgpmdW5jdGlvbiBUb2FzdCh7bXNnLHR5cGUsb25Eb25lfSl7CiAgdXNlRWZmZWN0KCgpPT57Y29uc3QgdD1zZXRUaW1lb3V0KG9uRG9uZSwzMjAwKTtyZXR1cm4oKT0+Y2xlYXJUaW1lb3V0KHQpO30sW10pOwogIGNvbnN0IG9rPXR5cGU9PT0ic3VjY2VzcyI7CiAgcmV0dXJuPGRpdiBzdHlsZT17e3Bvc2l0aW9uOiJmaXhlZCIsYm90dG9tOjE4LHJpZ2h0OjE4LGJhY2tncm91bmQ6b2s/IiNmMGZkZjQiOiIjZmVmMmYyIixib3JkZXI6YDFweCBzb2xpZCAke29rPyIjODZlZmFjIjoiI2ZjYTVhNSJ9YCxib3JkZXJSYWRpdXM6MTAscGFkZGluZzoiMTFweCAxNnB4IixkaXNwbGF5OiJmbGV4IixnYXA6OCxhbGlnbkl0ZW1zOiJjZW50ZXIiLGJveFNoYWRvdzoiMCA0cHggMjBweCByZ2JhKDAsMCwwLC4xMikiLHpJbmRleDo5OTk5LG1heFdpZHRoOjM0MCxhbmltYXRpb246ImZhZGVJbiAuMjJzIGVhc2UifX0+CiAgICA8c3BhbiBzdHlsZT17e2NvbG9yOm9rPyIjMTU4MDNkIjoiI2RjMjYyNiIsZm9udFdlaWdodDo3MDAsZm9udFNpemU6MTV9fT57b2s/IuKckyI6IuKaoCJ9PC9zcGFuPgogICAgPHNwYW4gc3R5bGU9e3tmb250U2l6ZToxMixjb2xvcjpvaz8iIzE1ODAzZCI6IiNkYzI2MjYiLGZvbnRXZWlnaHQ6NjAwfX0+e21zZ308L3NwYW4+CiAgPC9kaXY+Owp9CgpmdW5jdGlvbiBCYWRnZSh7c3RhdHVzfSl7CiAgY29uc3QgbT17IlBlbmRpbmciOlsiI2ZlZjNjNyIsIiM5MjQwMGUiLCIjZmNkMzRkIl0sIkluIFByb2dyZXNzIjpbIiNmZmY3ZWQiLCIjOWEzNDEyIiwiI2ZkYmE3NCJdLCJDb21wbGV0ZWQiOlsiI2QxZmFlNSIsIiMwNjVmNDYiLCIjNmVlN2I3Il0sIkRlbGl2ZXJlZCI6WyIjZGJlYWZlIiwiIzFlM2E4YSIsIiM5M2M1ZmQiXSwiUGFpZCI6WyIjZDFmYWU1IiwiIzA2NWY0NiIsIiM2ZWU3YjciXSwiUGFydGlhbGx5IFBhaWQiOlsiI2ZlZjNjNyIsIiM5MjQwMGUiLCIjZmNkMzRkIl0sIlVucGFpZCI6WyIjZmVmMmYyIiwiIzk5MWIxYiIsIiNmY2E1YTUiXX07CiAgY29uc3RbYmcsdGMsYmNdPW1bc3RhdHVzXXx8WyIjZjNmNGY2IiwiIzM3NDE1MSIsIiNkMWQ1ZGIiXTsKICByZXR1cm48c3BhbiBzdHlsZT17e2ZvbnRTaXplOjksZm9udFdlaWdodDo4MDAscGFkZGluZzoiMnB4IDhweCIsYm9yZGVyUmFkaXVzOjIwLGJhY2tncm91bmQ6YmcsY29sb3I6dGMsYm9yZGVyOmAxcHggc29saWQgJHtiY31gLHdoaXRlU3BhY2U6Im5vd3JhcCJ9fT57c3RhdHVzfTwvc3Bhbj47Cn0KCmZ1bmN0aW9uIE1vZGFsKHt0aXRsZSxvbkNsb3NlLGNoaWxkcmVuLHc9NDkwfSl7CiAgY29uc3QgaXNNb2I9d2luZG93LmlubmVyV2lkdGg8PTc2ODsKICByZXR1cm48ZGl2IHN0eWxlPXt7cG9zaXRpb246ImZpeGVkIixpbnNldDowLGJhY2tncm91bmQ6InJnYmEoMjgsMjUsMjMsLjU1KSIsekluZGV4OjgwMCxkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOmlzTW9iPyJmbGV4LWVuZCI6ImNlbnRlciIsanVzdGlmeUNvbnRlbnQ6ImNlbnRlciJ9fSBvbkNsaWNrPXtlPT5lLnRhcmdldD09PWUuY3VycmVudFRhcmdldCYmb25DbG9zZSgpfT4KICAgIDxkaXYgY2xhc3NOYW1lPSJrcHItbW9kYWwiIHN0eWxlPXt7YmFja2dyb3VuZDoidmFyKC0tYmctY2FyZCkiLGJvcmRlclJhZGl1czppc01vYj8iMTZweCAxNnB4IDAgMCI6IjE0cHgiLHdpZHRoOmlzTW9iPyIxMDAlIjp3LG1heFdpZHRoOiIxMDAlIixtYXhIZWlnaHQ6aXNNb2I/IjkydmgiOiI4OHZoIixvdmVyZmxvd1k6ImF1dG8iLGJveFNoYWRvdzoiMCAyMHB4IDYwcHggcmdiYSgwLDAsMCwuMikiLGFuaW1hdGlvbjoiZmFkZUluIC4ycyBlYXNlIn19PgogICAgICA8ZGl2IHN0eWxlPXt7cGFkZGluZzoiMTZweCAxOHB4IDAiLGRpc3BsYXk6ImZsZXgiLGp1c3RpZnlDb250ZW50OiJzcGFjZS1iZXR3ZWVuIixhbGlnbkl0ZW1zOiJjZW50ZXIiLG1hcmdpbkJvdHRvbToxNCxwb3NpdGlvbjoic3RpY2t5Iix0b3A6MCxiYWNrZ3JvdW5kOiIjZmZmIix6SW5kZXg6MSxib3JkZXJCb3R0b206IjFweCBzb2xpZCAjZmFmYWY5IixwYWRkaW5nQm90dG9tOjEyfX0+CiAgICAgICAgPGgzIHN0eWxlPXt7bWFyZ2luOjAsZm9udFNpemU6MTQsZm9udFdlaWdodDo4MDAsY29sb3I6IiMxYzE5MTcifX0+e3RpdGxlfTwvaDM+CiAgICAgICAgPGJ1dHRvbiBvbkNsaWNrPXtvbkNsb3NlfSBzdHlsZT17e2JhY2tncm91bmQ6Im5vbmUiLGJvcmRlcjoibm9uZSIsY3Vyc29yOiJwb2ludGVyIixjb2xvcjoiIzc4NzE2YyIsZm9udFNpemU6MjQsbGluZUhlaWdodDoxLHBhZGRpbmc6IjAgNHB4IixtaW5XaWR0aDozNixtaW5IZWlnaHQ6MzYsZGlzcGxheToiZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixqdXN0aWZ5Q29udGVudDoiY2VudGVyIn19PsOXPC9idXR0b24+CiAgICAgIDwvZGl2PgogICAgICA8ZGl2IHN0eWxlPXt7cGFkZGluZzoiMCAxOHB4IDI0cHgifX0+e2NoaWxkcmVufTwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+Owp9Cgpjb25zdCBpc01vYmlsZT0oKT0+d2luZG93LmlubmVyV2lkdGg8PTc2ODsKY29uc3QgSU5QPXt3aWR0aDoiMTAwJSIscGFkZGluZzppc01vYmlsZSgpPyIxMXB4IDEzcHgiOiI5cHggMTFweCIsYm9yZGVyOiIxcHggc29saWQgdmFyKC0tYm9yZGVyKSIsYm9yZGVyUmFkaXVzOjgsZm9udFNpemU6aXNNb2JpbGUoKT8xNDoxMixjb2xvcjoidmFyKC0tdGV4dC1wcmkpIixib3hTaXppbmc6ImJvcmRlci1ib3giLGZvbnRGYW1pbHk6ImluaGVyaXQiLGJhY2tncm91bmQ6InZhcigtLWJnLWlucHV0KSJ9Owpjb25zdCBTRUw9ey4uLklOUCxjdXJzb3I6InBvaW50ZXIifTsKY29uc3QgQlROPSh2PSJwcmkiKT0+KHtwYWRkaW5nOiI5cHggMTZweCIsYm9yZGVyUmFkaXVzOjgsYm9yZGVyOiJub25lIixmb250U2l6ZToxMixmb250V2VpZ2h0OjcwMCxjdXJzb3I6InBvaW50ZXIiLC4uLih2PT09InByaSI/e2JhY2tncm91bmQ6Qi5wcmksY29sb3I6IiNmZmYifTp2PT09Imdob3N0Ij97YmFja2dyb3VuZDoidmFyKC0tYmctY2FyZDIpIixjb2xvcjoiIzU3NTM0ZSIsYm9yZGVyOiIxcHggc29saWQgdmFyKC0tYm9yZGVyKSJ9OntiYWNrZ3JvdW5kOiIjZmVmMmYyIixjb2xvcjoiI2RjMjYyNiIsYm9yZGVyOiIxcHggc29saWQgI2ZjYTVhNSJ9KX0pOwpjb25zdCBQUklPPXt1cmdlbnQ6e2w6IlVyZ2VudCIsYmc6IiNmZWYyZjIiLHRjOiIjZGMyNjI2IixiYzoiI2ZjYTVhNSJ9LGhpZ2g6e2w6IkhpZ2giLGJnOiIjZmZmN2VkIix0YzoiI2MyNDEwYyIsYmM6IiNmZWQ3YWEifSxub3JtYWw6e2w6Ik5vcm1hbCIsYmc6IiNmZWZjZTgiLHRjOiIjYTE2MjA3IixiYzoiI2ZkZTY4YSJ9LGxvdzp7bDoiTG93IixiZzoiI2YwZmRmNCIsdGM6IiMxNTgwM2QiLGJjOiIjODZlZmFjIn19OwpmdW5jdGlvbiBQQmFkZ2Uoe3B9KXtjb25zdCB4PVBSSU9bcHx8Im5vcm1hbCJdO2lmKCF4KXJldHVybiBudWxsO3JldHVybiA8c3BhbiBzdHlsZT17e2ZvbnRTaXplOjksZm9udFdlaWdodDo4MDAscGFkZGluZzoiMnB4IDdweCIsYm9yZGVyUmFkaXVzOjIwLGJhY2tncm91bmQ6eC5iZyxjb2xvcjp4LnRjLGJvcmRlcjoiMXB4IHNvbGlkICIreC5iYyx3aGl0ZVNwYWNlOiJub3dyYXAifX0+e3gubH08L3NwYW4+O30KCgovKiDilIDilIAgRVhQT1JUIENTViDilIDilIAgKi8KCmZ1bmN0aW9uIEZsZCh7bGFiZWwsY2hpbGRyZW4scmVxfSl7cmV0dXJuPGRpdiBzdHlsZT17e21hcmdpbkJvdHRvbToxMX19PjxsYWJlbCBzdHlsZT17e2ZvbnRTaXplOjExLGZvbnRXZWlnaHQ6NzAwLGNvbG9yOiIjNTc1MzRlIixkaXNwbGF5OiJibG9jayIsbWFyZ2luQm90dG9tOjR9fT57bGFiZWx9e3JlcSYmPHNwYW4gc3R5bGU9e3tjb2xvcjpCLnByaSxtYXJnaW5MZWZ0OjJ9fT4qPC9zcGFuPn08L2xhYmVsPntjaGlsZHJlbn08L2Rpdj47fQpmdW5jdGlvbiBTSCh7dGl0bGUsYmFkZ2UsYWN0aW9uLGFsfSl7cmV0dXJuPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGp1c3RpZnlDb250ZW50OiJzcGFjZS1iZXR3ZWVuIixhbGlnbkl0ZW1zOiJjZW50ZXIiLG1hcmdpbkJvdHRvbToxM319PjxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGdhcDo3fX0+PGgzIHN0eWxlPXt7Zm9udFNpemU6MTMsZm9udFdlaWdodDo4MDAsY29sb3I6IiMxYzE5MTciLG1hcmdpbjowfX0+e3RpdGxlfTwvaDM+e2JhZGdlIT1udWxsJiY8c3BhbiBzdHlsZT17e2ZvbnRTaXplOjksZm9udFdlaWdodDo4MDAsYmFja2dyb3VuZDpCLnByaUwsY29sb3I6Qi5wcmlELGJvcmRlcjpgMXB4IHNvbGlkICR7Qi5wcmlNfWAsYm9yZGVyUmFkaXVzOjIwLHBhZGRpbmc6IjFweCA3cHgifX0+e2JhZGdlfTwvc3Bhbj59PC9kaXY+e2FjdGlvbiYmPGJ1dHRvbiBvbkNsaWNrPXthY3Rpb259IHN0eWxlPXt7Zm9udFNpemU6MTEsY29sb3I6Qi5wcmksZm9udFdlaWdodDo2MDAsYmFja2dyb3VuZDoibm9uZSIsYm9yZGVyOmAxcHggc29saWQgJHtCLnByaU19YCxib3JkZXJSYWRpdXM6NixwYWRkaW5nOiI0cHggMTBweCIsY3Vyc29yOiJwb2ludGVyIn19PnthbHx8IlJlZnJlc2gifTwvYnV0dG9uPn08L2Rpdj47fQpmdW5jdGlvbiBQZyh7Y2hpbGRyZW59KXtjb25zdCBpc01vYj13aW5kb3cuaW5uZXJXaWR0aDw9NzY4O3JldHVybjxkaXYgY2xhc3NOYW1lPSJmYWRlIGtwci1wZyIgc3R5bGU9e3twYWRkaW5nOmlzTW9iPyIxMnB4IDE0cHgiOiIxOHB4IDIycHgiLG1heFdpZHRoOjEwODAsYmFja2dyb3VuZDoidmFyKC0tYmctcGFnZSkiLGNvbG9yOiJ2YXIoLS10ZXh0LXByaSkifX0+e2NoaWxkcmVufTwvZGl2Pjt9CmZ1bmN0aW9uIFBhZ2VIZHIoe3RpdGxlLHN1YixhY3Rpb24sYWN0aW9uTGFiZWx9KXtjb25zdCBpc01vYj13aW5kb3cuaW5uZXJXaWR0aDw9NzY4O3JldHVybjxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixqdXN0aWZ5Q29udGVudDoic3BhY2UtYmV0d2VlbiIsYWxpZ25JdGVtczppc01vYj8iZmxleC1zdGFydCI6ImNlbnRlciIsbWFyZ2luQm90dG9tOjE2LGdhcDo4LGZsZXhXcmFwOiJ3cmFwIn19PjxkaXY+PGgyIHN0eWxlPXt7Zm9udFNpemU6aXNNb2I/MTY6MTksZm9udFdlaWdodDo4MDAsY29sb3I6IiMxYzE5MTciLG1hcmdpbjowfX0+e3RpdGxlfTwvaDI+e3N1YiYmPHAgc3R5bGU9e3tmb250U2l6ZToxMCxjb2xvcjoiIzc4NzE2YyIsbWFyZ2luOiIycHggMCAwIn19PntzdWJ9PC9wPn08L2Rpdj57YWN0aW9uJiY8YnV0dG9uIG9uQ2xpY2s9e2FjdGlvbn0gc3R5bGU9e3suLi5CVE4oKSxkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGdhcDo1LGZvbnRTaXplOmlzTW9iPzExOjEyLHBhZGRpbmc6aXNNb2I/IjhweCAxMnB4IjoiOXB4IDE2cHgiLHdoaXRlU3BhY2U6Im5vd3JhcCJ9fT4rIHthY3Rpb25MYWJlbH08L2J1dHRvbj59PC9kaXY+O30KCmZ1bmN0aW9uIFBhZ2VyKHtwYWdlLHRvdGFsLHBlcixvbkNoYW5nZX0pewogIGNvbnN0IHBhZ2VzPU1hdGguY2VpbCh0b3RhbC9wZXIpO2lmKHBhZ2VzPD0xKXJldHVybiBudWxsOwogIHJldHVybjxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixnYXA6NCxqdXN0aWZ5Q29udGVudDoiY2VudGVyIixtYXJnaW5Ub3A6MTQsYWxpZ25JdGVtczoiY2VudGVyIn19PgogICAgPGJ1dHRvbiBkaXNhYmxlZD17cGFnZT09PTB9IG9uQ2xpY2s9eygpPT5vbkNoYW5nZShwYWdlLTEpfSBzdHlsZT17ey4uLkJUTigiZ2hvc3QiKSxwYWRkaW5nOiI1cHggMTBweCIsZm9udFNpemU6MTEsb3BhY2l0eTpwYWdlPT09MD8uNDoxfX0+4oaQIFByZXY8L2J1dHRvbj4KICAgIDxzcGFuIHN0eWxlPXt7Zm9udFNpemU6MTEsY29sb3I6IiM3ODcxNmMiLHBhZGRpbmc6IjAgOHB4In19PlBhZ2Uge3BhZ2UrMX0gLyB7cGFnZXN9PC9zcGFuPgogICAgPGJ1dHRvbiBkaXNhYmxlZD17cGFnZT49cGFnZXMtMX0gb25DbGljaz17KCk9Pm9uQ2hhbmdlKHBhZ2UrMSl9IHN0eWxlPXt7Li4uQlROKCJnaG9zdCIpLHBhZGRpbmc6IjVweCAxMHB4Iixmb250U2l6ZToxMSxvcGFjaXR5OnBhZ2U+PXBhZ2VzLTE/LjQ6MX19Pk5leHQg4oaSPC9idXR0b24+CiAgPC9kaXY+Owp9CgpmdW5jdGlvbiBTcGFyayh7ZGF0YSxjb2xvcj0iI2VhNTgwYyIsdz02OCxoPTI2fSl7CiAgaWYoIWRhdGF8fGRhdGEubGVuZ3RoPDIpcmV0dXJuIG51bGw7CiAgY29uc3QgbXg9TWF0aC5tYXgoLi4uZGF0YSksbW49TWF0aC5taW4oLi4uZGF0YSkscm5nPW14LW1ufHwxOwogIGNvbnN0IHB0cz1kYXRhLm1hcCgodixpKT0+YCR7KGkvKGRhdGEubGVuZ3RoLTEpKSp3fSwke2gtKCh2LW1uKS9ybmcpKihoLTQpLTJ9YCkuam9pbigiICIpOwogIHJldHVybjxzdmcgd2lkdGg9e3d9IGhlaWdodD17aH0gc3R5bGU9e3tvdmVyZmxvdzoidmlzaWJsZSJ9fT48cG9seWxpbmUgcG9pbnRzPXtwdHN9IGZpbGw9Im5vbmUiIHN0cm9rZT17Y29sb3J9IHN0cm9rZVdpZHRoPSIxLjgiIHN0cm9rZUxpbmVjYXA9InJvdW5kIiBzdHJva2VMaW5lam9pbj0icm91bmQiLz48L3N2Zz47Cn0KCi8qIOKUgOKUgCBDT05GSUcgTU9EQUwg4pSA4pSAICovCmNvbnN0IFBSRVNFVFM9ewogIG9ubGluZTp7bGFiZWw6Ik9ubGluZSAoUmVuZGVyKSIsdXJsOiJodHRwczovL2twci1jcm0tYXBpLm9ucmVuZGVyLmNvbSIscG9ydDoiIixoaW50OiJJbnRlcm5ldCBjb25uZWN0aW9uIOCwheCwteCwuOCwsOCwgiJ9LAogIGxhbjp7bGFiZWw6IkxBTiAoTG9jYWwgTmV0d29yaykiLHVybDoiMTkyLjE2OC4wLjI1Iixwb3J0OiI4MDAwIixoaW50OiJTYW1lIFdpLUZpIC8gTEFOIOCwsuCxiyDgsIngsILgsKHgsL7gsLLgsL8ifSwKfTsKZnVuY3Rpb24gQ2ZnTW9kYWwoe2lwLHBvcnQsb25TYXZlLG9uQ2xvc2V9KXsKICBjb25zdCBkZXRlY3Q9aXAuaW5jbHVkZXMoInJlbmRlci5jb20iKXx8aXAuc3RhcnRzV2l0aCgiaHR0cHM6Ly8iKXx8aXAuc3RhcnRzV2l0aCgiaHR0cDovLyIpPyJvbmxpbmUiOiJsYW4iOwogIGNvbnN0W21vZGUsc2V0TW9kZV09dXNlU3RhdGUoZGV0ZWN0KTsKICBjb25zdFtlZGl0aW5nLHNldEVkaXRpbmddPXVzZVN0YXRlKGZhbHNlKTsKICBjb25zdFtsaSxzZXRMaV09dXNlU3RhdGUoaXB8fFBSRVNFVFNbZGV0ZWN0XS51cmwpOwogIGNvbnN0W2xwLHNldExwXT11c2VTdGF0ZShwb3J0fHxQUkVTRVRTW2RldGVjdF0ucG9ydCk7CiAgY29uc3Qgc2VsZWN0TW9kZT1tPT57c2V0TW9kZShtKTtzZXRFZGl0aW5nKGZhbHNlKTtzZXRMaShQUkVTRVRTW21dLnVybCk7c2V0THAoUFJFU0VUU1ttXS5wb3J0KTt9OwogIGNvbnN0IHByPVBSRVNFVFNbbW9kZV07CiAgcmV0dXJuPGRpdiBzdHlsZT17e3Bvc2l0aW9uOiJmaXhlZCIsaW5zZXQ6MCxiYWNrZ3JvdW5kOiJyZ2JhKDI4LDI1LDIzLC42KSIsekluZGV4Ojk5OSxkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGp1c3RpZnlDb250ZW50OiJjZW50ZXIifX0+CiAgICA8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDoiI2ZmZiIsYm9yZGVyUmFkaXVzOjE0LHdpZHRoOjM4MCxwYWRkaW5nOiIyNHB4IDI2cHgiLGJveFNoYWRvdzoiMCAyMHB4IDYwcHggcmdiYSgwLDAsMCwuMjIpIixhbmltYXRpb246ImZhZGVJbiAuMnMgZWFzZSJ9fT4KICAgICAgey8qIEhlYWRlciAqL30KICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGFsaWduSXRlbXM6ImNlbnRlciIsZ2FwOjEwLG1hcmdpbkJvdHRvbToyMH19PgogICAgICAgIDxkaXYgc3R5bGU9e3t3aWR0aDozOCxoZWlnaHQ6MzgsYm9yZGVyUmFkaXVzOjksYmFja2dyb3VuZDpCLnByaUwsZGlzcGxheToiZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixqdXN0aWZ5Q29udGVudDoiY2VudGVyIixmb250U2l6ZToyMH19PvCfk6E8L2Rpdj4KICAgICAgICA8ZGl2PjxkaXYgc3R5bGU9e3tmb250U2l6ZToxNCxmb250V2VpZ2h0OjgwMCxjb2xvcjoiIzFjMTkxNyJ9fT5TZXJ2ZXIgQ29ubmVjdGlvbjwvZGl2PjxkaXYgc3R5bGU9e3tmb250U2l6ZToxMSxjb2xvcjoiIzc4NzE2YyJ9fT5Db25uZWN0aW9uIG1vZGUg4LCO4LCC4LCa4LGB4LCV4LGL4LCC4LCh4LC/PC9kaXY+PC9kaXY+CiAgICAgIDwvZGl2PgogICAgICB7LyogUmFkaW8gT3B0aW9ucyAqL30KICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImdyaWQiLGdyaWRUZW1wbGF0ZUNvbHVtbnM6IjFmciAxZnIiLGdhcDo5LG1hcmdpbkJvdHRvbToxNn19PgogICAgICAgIHtPYmplY3QuZW50cmllcyhQUkVTRVRTKS5tYXAoKFtrLHZdKT0+e2NvbnN0IHNlbD1tb2RlPT09aztyZXR1cm4oCiAgICAgICAgICA8YnV0dG9uIGtleT17a30gb25DbGljaz17KCk9PnNlbGVjdE1vZGUoayl9IHN0eWxlPXt7cGFkZGluZzoiMTJweCAxMHB4Iixib3JkZXJSYWRpdXM6MTAsYm9yZGVyOmAycHggc29saWQgJHtzZWw/Qi5wcmk6IiNlN2U1ZTQifWAsYmFja2dyb3VuZDpzZWw/Qi5wcmlMOiIjZmFmYWY5IixjdXJzb3I6InBvaW50ZXIiLHRleHRBbGlnbjoibGVmdCIsdHJhbnNpdGlvbjoiYWxsIC4xNXMifX0+CiAgICAgICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZToxMCxmb250V2VpZ2h0OjgwMCxjb2xvcjpzZWw/Qi5wcmlEOiIjNTc1MzRlIixtYXJnaW5Cb3R0b206MyxkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGdhcDo1fX0+CiAgICAgICAgICAgICAgPHNwYW4gc3R5bGU9e3t3aWR0aDoxMyxoZWlnaHQ6MTMsYm9yZGVyUmFkaXVzOiI1MCUiLGJvcmRlcjpgMnB4IHNvbGlkICR7c2VsP0IucHJpOiIjZDZkM2QxIn1gLGJhY2tncm91bmQ6c2VsP0IucHJpOiIjZmZmIixkaXNwbGF5OiJpbmxpbmUtZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixqdXN0aWZ5Q29udGVudDoiY2VudGVyIixmbGV4U2hyaW5rOjB9fT4KICAgICAgICAgICAgICAgIHtzZWwmJjxzcGFuIHN0eWxlPXt7d2lkdGg6NSxoZWlnaHQ6NSxib3JkZXJSYWRpdXM6IjUwJSIsYmFja2dyb3VuZDoiI2ZmZiIsZGlzcGxheToiYmxvY2sifX0vPn0KICAgICAgICAgICAgICA8L3NwYW4+CiAgICAgICAgICAgICAge3YubGFiZWx9CiAgICAgICAgICAgIDwvZGl2PgogICAgICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6OSxjb2xvcjoiI2E4YTI5ZSIscGFkZGluZ0xlZnQ6MTh9fT57di5oaW50fTwvZGl2PgogICAgICAgICAgPC9idXR0b24+CiAgICAgICAgKTt9KX0KICAgICAgPC9kaXY+CiAgICAgIHsvKiBDdXJyZW50IHZhbHVlIGRpc3BsYXkgKi99CiAgICAgIDxkaXYgc3R5bGU9e3tiYWNrZ3JvdW5kOiIjZjVmNWY0Iixib3JkZXJSYWRpdXM6OCxwYWRkaW5nOiI5cHggMTJweCIsbWFyZ2luQm90dG9tOjEyLGRpc3BsYXk6ImZsZXgiLGp1c3RpZnlDb250ZW50OiJzcGFjZS1iZXR3ZWVuIixhbGlnbkl0ZW1zOiJjZW50ZXIifX0+CiAgICAgICAgPGRpdj4KICAgICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZTo5LGNvbG9yOiIjNzg3MTZjIixmb250V2VpZ2h0OjYwMCxtYXJnaW5Cb3R0b206Mn19PkN1cnJlbnQgVVJMPC9kaXY+CiAgICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTEsZm9udFdlaWdodDo3MDAsY29sb3I6IiMxYzE5MTciLHdvcmRCcmVhazoiYnJlYWstYWxsIn19PntlZGl0aW5nP2xpOihsaS5zdGFydHNXaXRoKCJodHRwIik/bGk6YGh0dHA6Ly8ke2xpfSR7bHA/IjoiK2xwOiIifWApfTwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxidXR0b24gb25DbGljaz17KCk9PnNldEVkaXRpbmcodj0+IXYpfSBzdHlsZT17e2ZvbnRTaXplOjEwLGNvbG9yOmVkaXRpbmc/Qi5wcmlEOiIjNzg3MTZjIixmb250V2VpZ2h0OjcwMCxiYWNrZ3JvdW5kOiJub25lIixib3JkZXI6YDFweCBzb2xpZCAke2VkaXRpbmc/Qi5wcmlNOiIjZTdlNWU0In1gLGJvcmRlclJhZGl1czo2LHBhZGRpbmc6IjRweCA5cHgiLGN1cnNvcjoicG9pbnRlciIsd2hpdGVTcGFjZToibm93cmFwIixtYXJnaW5MZWZ0Ojh9fT57ZWRpdGluZz8i4pyTIERvbmUiOiLinI8gRWRpdCJ9PC9idXR0b24+CiAgICAgIDwvZGl2PgogICAgICB7LyogRWRpdCBmaWVsZHMg4oCUIG9ubHkgd2hlbiBlZGl0aW5nICovfQogICAgICB7ZWRpdGluZyYmPGRpdiBzdHlsZT17e2JhY2tncm91bmQ6IiNmZmZiZjgiLGJvcmRlcjpgMXB4IHNvbGlkICR7Qi5wcmlNfWAsYm9yZGVyUmFkaXVzOjgscGFkZGluZzoiMTJweCIsbWFyZ2luQm90dG9tOjEyfX0+CiAgICAgICAgPEZsZCBsYWJlbD17bW9kZT09PSJsYW4iPyJJUCBBZGRyZXNzIjoiU2VydmVyIFVSTCJ9PgogICAgICAgICAgPGlucHV0IHZhbHVlPXtsaX0gb25DaGFuZ2U9e2U9PnNldExpKGUudGFyZ2V0LnZhbHVlKX0gcGxhY2Vob2xkZXI9e1BSRVNFVFNbbW9kZV0udXJsfSBzdHlsZT17SU5QfS8+CiAgICAgICAgPC9GbGQ+CiAgICAgICAge21vZGU9PT0ibGFuIiYmPEZsZCBsYWJlbD0iUG9ydCI+PGlucHV0IHZhbHVlPXtscH0gb25DaGFuZ2U9e2U9PnNldExwKGUudGFyZ2V0LnZhbHVlKX0gcGxhY2Vob2xkZXI9IjgwMDAiIHN0eWxlPXtJTlB9Lz48L0ZsZD59CiAgICAgIDwvZGl2Pn0KICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGdhcDo4LG1hcmdpblRvcDo0fX0+CiAgICAgICAgPGJ1dHRvbiBvbkNsaWNrPXtvbkNsb3NlfSBzdHlsZT17ey4uLkJUTigiZ2hvc3QiKSxmbGV4OjF9fT5DYW5jZWw8L2J1dHRvbj4KICAgICAgICA8YnV0dG9uIG9uQ2xpY2s9eygpPT5vblNhdmUobGksbHApfSBzdHlsZT17ey4uLkJUTigpLGZsZXg6MX19PvCfkr4gU2F2ZSAmIENvbm5lY3Q8L2J1dHRvbj4KICAgICAgPC9kaXY+CiAgICA8L2Rpdj4KICA8L2Rpdj47Cn0KCi8qIOKUgOKUgCBXSEFUU0FQUCBIRUxQRVIg4pSA4pSAICovCmZ1bmN0aW9uIHNlbmRXaGF0c0FwcChqb2IpewogIGNvbnN0IHBob25lPShqb2IuY3VzdG9tZXJfbW9iaWxlfHxqb2IuY3VzdG9tZXJfcGhvbmV8fCIiKS5yZXBsYWNlKC9cRC9nLCIiKTsKICBjb25zdCBzdGF0dXNFbW9qaT17IlBlbmRpbmciOiLij7MiLCJJbiBQcm9ncmVzcyI6IvCflIQiLCJDb21wbGV0ZWQiOiLinIUiLCJEZWxpdmVyZWQiOiLwn5OmIn1bam9iLnN0YXR1c118fCLwn5OLIjsKICBjb25zdCBtc2c9YOCwqOCwruCwuOCxjeCwleCwvuCwsOCwgiAke2pvYi5jdXN0b21lcl9uYW1lfSDgsJfgsL7gsLDgsYEhIPCfmY9cblxuYCsKICAgIGDgsK7gsYAgSm9iIOCwteCwv+CwteCwsOCwvuCwsuCxgTpcbmArCiAgICBg8J+TjCBKb2IgSUQ6ICMke2pvYi5pZH1cbmArCiAgICBg8J+WqO+4jyBUeXBlOiAke2pvYi5qb2JfdHlwZX0ke2pvYi5zaXplP2AgKCR7am9iLnNpemV9KWA6IiJ9XG5gKwogICAgYCR7c3RhdHVzRW1vaml9IFN0YXR1czogJHtqb2Iuc3RhdHVzfVxuYCsKICAgIChqb2IuZHVlX2RhdGU/YPCfk4UgRHVlIERhdGU6ICR7am9iLmR1ZV9kYXRlfVxuYDoiIikrCiAgICBgXG5UaGFuayB5b3UgZm9yIGNob29zaW5nIEtQUiBDb2xvdXIgTGFiISDwn5O3YDsKICBjb25zdCB1cmw9cGhvbmUKICAgID9gaHR0cHM6Ly93YS5tZS85MSR7cGhvbmV9P3RleHQ9JHtlbmNvZGVVUklDb21wb25lbnQobXNnKX1gCiAgICA6YGh0dHBzOi8vd2EubWUvP3RleHQ9JHtlbmNvZGVVUklDb21wb25lbnQobXNnKX1gOwogIHdpbmRvdy5vcGVuKHVybCwiX2JsYW5rIik7Cn0KCi8qIOKUgOKUgCBKT0IgREVUQUlMIE1PREFMIOKUgOKUgCAqLwpmdW5jdGlvbiBKb2JEZXRhaWxNb2RhbCh7am9iLHJvbGUsb25DbG9zZX0pewogIGNvbnN0IGlzRmluYW5jZT1yb2xlPT09ImFkbWluInx8cm9sZT09PSJzdGFmZiI7CiAgY29uc3QgUm93PSh7bGFiZWwsdmFsdWUscmVkfSk9PigKICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixqdXN0aWZ5Q29udGVudDoic3BhY2UtYmV0d2VlbiIsYWxpZ25JdGVtczoiY2VudGVyIixwYWRkaW5nOiI3cHggMCIsYm9yZGVyQm90dG9tOiIxcHggc29saWQgI2ZhZmFmOSJ9fT4KICAgICAgPHNwYW4gc3R5bGU9e3tmb250U2l6ZToxMSxjb2xvcjoiIzc4NzE2YyIsZm9udFdlaWdodDo2MDB9fT57bGFiZWx9PC9zcGFuPgogICAgICA8c3BhbiBzdHlsZT17e2ZvbnRTaXplOjEyLGZvbnRXZWlnaHQ6NjAwLGNvbG9yOnJlZD8iI2RjMjYyNiI6IiM1NzUzNGUifX0+e3ZhbHVlfHwi4oCUIn08L3NwYW4+CiAgICA8L2Rpdj4KICApOwogIGNvbnN0IG92PWpvYi5kdWVfZGF0ZSYmbmV3IERhdGUoam9iLmR1ZV9kYXRlKTxuZXcgRGF0ZSgpJiYhWyJEZWxpdmVyZWQiLCJDb21wbGV0ZWQiXS5pbmNsdWRlcyhqb2Iuc3RhdHVzKTsKICByZXR1cm48TW9kYWwgdGl0bGU9e2BKb2IgIyR7am9iLmlkfSDigJQgRGV0YWlsc2B9IG9uQ2xvc2U9e29uQ2xvc2V9IHc9ezQ2MH0+CiAgICB7LyogSGVhZGVyIGNhcmQgKi99CiAgICA8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDoidmFyKC0tYmctY2FyZDIpIixib3JkZXJSYWRpdXM6OSxwYWRkaW5nOiIxMXB4IDE0cHgiLG1hcmdpbkJvdHRvbToxNCxib3JkZXI6IjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpIn19PgogICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsanVzdGlmeUNvbnRlbnQ6InNwYWNlLWJldHdlZW4iLGFsaWduSXRlbXM6ImZsZXgtc3RhcnQiLG1hcmdpbkJvdHRvbTo4fX0+CiAgICAgICAgPGRpdj4KICAgICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZToxNSxmb250V2VpZ2h0OjgwMCxjb2xvcjoiIzFjMTkxNyJ9fT57am9iLmN1c3RvbWVyX25hbWV8fCLigJQifTwvZGl2PgogICAgICAgICAgPGRpdiBzdHlsZT17e2ZvbnRTaXplOjExLGNvbG9yOiIjNzg3MTZjIixtYXJnaW5Ub3A6Mn19Pntqb2Iuam9iX3R5cGV9e2pvYi5zaXplP2AgwrcgJHtqb2Iuc2l6ZX1gOiIifTwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxCYWRnZSBzdGF0dXM9e2pvYi5zdGF0dXN9Lz4KICAgICAgPC9kaXY+CiAgICAgIHsvKiBEZXNjcmlwdGlvbiDigJQgYWx3YXlzIHZpc2libGUgKi99CiAgICAgIDxkaXYgc3R5bGU9e3ttYXJnaW5Cb3R0b206OH19PgogICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZTo5LGZvbnRXZWlnaHQ6ODAwLGNvbG9yOiIjYThhMjllIix0ZXh0VHJhbnNmb3JtOiJ1cHBlcmNhc2UiLGxldHRlclNwYWNpbmc6Ii4wNmVtIixtYXJnaW5Cb3R0b206NH19PkRlc2NyaXB0aW9uPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT17e2ZvbnRTaXplOjEyLGNvbG9yOmpvYi5kZXNjcmlwdGlvbj8iIzM3NDE1MSI6IiNhOGEyOWUiLHBhZGRpbmc6IjdweCA5cHgiLGJhY2tncm91bmQ6IiNmZmYiLGJvcmRlclJhZGl1czo2LGJvcmRlcjoiMXB4IHNvbGlkICNlN2U1ZTQiLG1pbkhlaWdodDozNCxmb250U3R5bGU6am9iLmRlc2NyaXB0aW9uPyJub3JtYWwiOiJpdGFsaWMifX0+e2pvYi5kZXNjcmlwdGlvbnx8Ik5vIGRlc2NyaXB0aW9uIn08L2Rpdj4KICAgICAgPC9kaXY+CiAgICAgIHsvKiBOb3RlcyDigJQgYWx3YXlzIHZpc2libGUgKi99CiAgICAgIDxkaXY+CiAgICAgICAgPGRpdiBzdHlsZT17e2ZvbnRTaXplOjksZm9udFdlaWdodDo4MDAsY29sb3I6IiNhOGEyOWUiLHRleHRUcmFuc2Zvcm06InVwcGVyY2FzZSIsbGV0dGVyU3BhY2luZzoiLjA2ZW0iLG1hcmdpbkJvdHRvbTo0fX0+Tm90ZXM8L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTIsY29sb3I6am9iLm5vdGVzPyIjMzc0MTUxIjoiI2E4YTI5ZSIscGFkZGluZzoiN3B4IDlweCIsYmFja2dyb3VuZDoiI2ZmZiIsYm9yZGVyUmFkaXVzOjYsYm9yZGVyOiIxcHggc29saWQgI2U3ZTVlNCIsbWluSGVpZ2h0OjI4LGZvbnRTdHlsZTpqb2Iubm90ZXM/Im5vcm1hbCI6Iml0YWxpYyJ9fT57am9iLm5vdGVzfHwiTm8gbm90ZXMifTwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPGRpdiBzdHlsZT17e21hcmdpbkJvdHRvbToxMn19PgogICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTAsZm9udFdlaWdodDo4MDAsY29sb3I6IiNhOGEyOWUiLHRleHRUcmFuc2Zvcm06InVwcGVyY2FzZSIsbGV0dGVyU3BhY2luZzoiLjA3ZW0iLG1hcmdpbkJvdHRvbTo2fX0+Sm9iIEluZm88L2Rpdj4KICAgICAgPFJvdyBsYWJlbD0iSm9iIFR5cGUiIHZhbHVlPXtqb2Iuam9iX3R5cGV9Lz4KICAgICAgPFJvdyBsYWJlbD0iU2l6ZSAvIFNwZWNzIiB2YWx1ZT17am9iLnNpemV9Lz4KICAgICAgPFJvdyBsYWJlbD0iRHVlIERhdGUiIHZhbHVlPXtvdj9g4pqgICR7am9iLmR1ZV9kYXRlfSAoT3ZlcmR1ZSlgOmpvYi5kdWVfZGF0ZX0gcmVkPXtvdn0vPgogICAgICA8Um93IGxhYmVsPSJDcmVhdGVkIiB2YWx1ZT17KGpvYi5jcmVhdGVkX2F0fHwiIikuc2xpY2UoMCwxNil9Lz4KICAgICAge2pvYi5hc3NpZ25lZF90b19uYW1lJiY8Um93IGxhYmVsPSJBc3NpZ25lZCBUbyIgdmFsdWU9e2pvYi5hc3NpZ25lZF90b19uYW1lfS8+fQogICAgPC9kaXY+CiAgICB7aXNGaW5hbmNlJiYoKCk9PnsKICAgICAgY29uc3QgZnAyPU51bWJlcihqb2IuZmluYWxfcHJpY2V8fDApfHxOdW1iZXIoam9iLmluaXRpYWxfcHJpY2V8fDApLU51bWJlcihqb2IuZGlzY291bnRfYW1vdW50fHwwKTsKICAgICAgY29uc3QgYWR2Mj1OdW1iZXIoam9iLmFkdmFuY2UxfHwwKTsKICAgICAgY29uc3QgYmFsMj1NYXRoLm1heCgwLGZwMi1hZHYyKTsKICAgICAgcmV0dXJuIDxkaXYgc3R5bGU9e3tiYWNrZ3JvdW5kOiIjZmZmN2VkIixib3JkZXI6IjFweCBzb2xpZCAjZmVkN2FhIixib3JkZXJSYWRpdXM6OSxwYWRkaW5nOiIxMnB4IDE0cHgiLG1hcmdpbkJvdHRvbToxMn19PgogICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZToxMCxmb250V2VpZ2h0OjgwMCxjb2xvcjoiIzkyNDAwZSIsdGV4dFRyYW5zZm9ybToidXBwZXJjYXNlIixsZXR0ZXJTcGFjaW5nOiIuMDdlbSIsbWFyZ2luQm90dG9tOjh9fT5GaW5hbmNlPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImdyaWQiLGdyaWRUZW1wbGF0ZUNvbHVtbnM6IjFmciAxZnIiLGdhcDoiMCAxNnB4In19PgogICAgICAgICAge1tbIkluaXRpYWwgUHJpY2UiLE51bWJlcihqb2IuaW5pdGlhbF9wcmljZXx8MCldLFsiRGlzY291bnQiLE51bWJlcihqb2IuZGlzY291bnRfYW1vdW50fHwwKV0sWyJGaW5hbCBQcmljZSIsZnAyXSxbIkFkdmFuY2UgUGFpZCIsYWR2Ml1dLm1hcCgoW2wsdl0pPT4oCiAgICAgICAgICAgIDxkaXYga2V5PXtsfSBzdHlsZT17e2JvcmRlckJvdHRvbToiMXB4IHNvbGlkICNmZGU4YzgiLHBhZGRpbmc6IjZweCAwIn19PgogICAgICAgICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZTo5LGNvbG9yOiIjOTI0MDBlIixmb250V2VpZ2h0OjYwMH19PntsfTwvZGl2PgogICAgICAgICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZToxNCxmb250V2VpZ2h0OjgwMCxjb2xvcjoiIzFjMTkxNyJ9fT57dj4wPyLigrkiK051bWJlcih2KS50b0xvY2FsZVN0cmluZygiZW4tSU4iKToiLSJ9PC9kaXY+CiAgICAgICAgICAgIDwvZGl2PgogICAgICAgICAgKSl9CiAgICAgICAgICA8ZGl2IHN0eWxlPXt7Z3JpZENvbHVtbjoiMS8tMSIsbWFyZ2luVG9wOjYsZGlzcGxheToiZmxleCIsanVzdGlmeUNvbnRlbnQ6InNwYWNlLWJldHdlZW4iLGFsaWduSXRlbXM6ImNlbnRlciJ9fT4KICAgICAgICAgICAgPHNwYW4gc3R5bGU9e3tmb250U2l6ZToxMixmb250V2VpZ2h0OjcwMCxjb2xvcjoiIzkyNDAwZSJ9fT5CYWxhbmNlIER1ZTwvc3Bhbj4KICAgICAgICAgICAgPHNwYW4gc3R5bGU9e3tmb250U2l6ZToxOCxmb250V2VpZ2h0OjkwMCxjb2xvcjpiYWwyPjA/IiNkYzI2MjYiOiIjMTZhMzRhIn19PntiYWwyPjA/IuKCuSIrTnVtYmVyKGJhbDIpLnRvTG9jYWxlU3RyaW5nKCJlbi1JTiIpOiJGdWxseSBQYWlkIn08L3NwYW4+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgPC9kaXY+OwogICAgfSkoKX0gICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGp1c3RpZnlDb250ZW50OiJzcGFjZS1iZXR3ZWVuIixhbGlnbkl0ZW1zOiJjZW50ZXIifX0+CiAgICAgIHsocm9sZT09PSJhZG1pbiJ8fHJvbGU9PT0ic3RhZmYiKSYmPGJ1dHRvbiBvbkNsaWNrPXsoKT0+c2VuZFdoYXRzQXBwKGpvYil9IHN0eWxlPXt7Li4uQlROKCJnaG9zdCIpLGRpc3BsYXk6ImZsZXgiLGFsaWduSXRlbXM6ImNlbnRlciIsZ2FwOjYscGFkZGluZzoiOHB4IDE0cHgiLGNvbG9yOiIjMTZhMzRhIixib3JkZXI6IjFweCBzb2xpZCAjODZlZmFjIixiYWNrZ3JvdW5kOiIjZjBmZGY0In19PgogICAgICAgIDxzcGFuIHN0eWxlPXt7Zm9udFNpemU6MTR9fT7wn5OxPC9zcGFuPiBXaGF0c0FwcAogICAgICA8L2J1dHRvbj59CiAgICAgIDxidXR0b24gb25DbGljaz17b25DbG9zZX0gc3R5bGU9e3suLi5CVE4oImdob3N0IikscGFkZGluZzoiOHB4IDE4cHgiLG1hcmdpbkxlZnQ6ImF1dG8ifX0+Q2xvc2U8L2J1dHRvbj4KICAgIDwvZGl2PgogIDwvTW9kYWw+Owp9CgovKiDilIDilIAgSU5WT0lDRSBQUklOVCBNT0RBTCDilIDilIAgKi8KZnVuY3Rpb24gYnVpbGRJbnZvaWNlSFRNTChqb2IpewogIGNvbnN0IGxvYz1OdW1iZXIoam9iLmJhbGFuY2V8fDApPjA/IlJzLiIrTnVtYmVyKGpvYi5iYWxhbmNlKS50b0xvY2FsZVN0cmluZygiZW4tSU4iKToiUEFJRCBGVUxMIjsKICBjb25zdCBkaXNjPU51bWJlcihqb2IuZGlzY291bnRfYW1vdW50KT4wPyI8ZGl2IGNsYXNzPVwicm93XCI+PHNwYW4+RGlzY291bnQ8L3NwYW4+PHNwYW4gc3R5bGU9XCJjb2xvcjojMTZhMzRhXCI+LSBScy4iK051bWJlcihqb2IuZGlzY291bnRfYW1vdW50KS50b0xvY2FsZVN0cmluZygiZW4tSU4iKSsiPC9zcGFuPjwvZGl2PiI6IiI7CiAgY29uc3QgZGVzYz1qb2IuZGVzY3JpcHRpb24/IjxkaXYgY2xhc3M9XCJzZWN0aW9uXCI+PGg0PkRlc2NyaXB0aW9uPC9oND48ZGl2IHN0eWxlPVwiYmFja2dyb3VuZDojZmFmYWY5O3BhZGRpbmc6OHB4IDEwcHg7Ym9yZGVyLXJhZGl1czo2cHg7Zm9udC1zaXplOjEycHhcIj4iK2pvYi5kZXNjcmlwdGlvbisiPC9kaXY+PC9kaXY+IjoiIjsKICBjb25zdCBwaG9uZT1qb2IuY3VzdG9tZXJfbW9iaWxlPyI8ZGl2IHN0eWxlPVwiY29sb3I6Izc4NzE2YzttYXJnaW4tdG9wOjJweFwiPk1vYmlsZTogIitqb2IuY3VzdG9tZXJfbW9iaWxlKyI8L2Rpdj4iOiIiOwogIGNvbnN0IGR1ZT1qb2IuZHVlX2RhdGU/IjxkaXYgY2xhc3M9XCJyb3dcIj48c3Bhbj5EdWUgRGF0ZTwvc3Bhbj48c3Bhbj4iK2pvYi5kdWVfZGF0ZSsiPC9zcGFuPjwvZGl2PiI6IiI7CiAgcmV0dXJuICI8IURPQ1RZUEUgaHRtbD48aHRtbD48aGVhZD48bWV0YSBjaGFyc2V0PVwidXRmLThcIj48dGl0bGU+SW52b2ljZSAjIitqb2IuaWQrIjwvdGl0bGU+IisKICAgICI8c3R5bGU+KnttYXJnaW46MDtwYWRkaW5nOjA7Ym94LXNpemluZzpib3JkZXItYm94O31ib2R5e2ZvbnQtZmFtaWx5OkFyaWFsLHNhbnMtc2VyaWY7cGFkZGluZzozMnB4O2NvbG9yOiMxYzE5MTc7Zm9udC1zaXplOjEzcHg7fSIrCiAgICAiLmhkcntkaXNwbGF5OmZsZXg7anVzdGlmeS1jb250ZW50OnNwYWNlLWJldHdlZW47YWxpZ24taXRlbXM6ZmxleC1zdGFydDttYXJnaW4tYm90dG9tOjI0cHg7cGFkZGluZy1ib3R0b206MTZweDtib3JkZXItYm90dG9tOjJweCBzb2xpZCAjZWE1ODBjO30iKwogICAgIi5icmFuZHtmb250LXNpemU6MjJweDtmb250LXdlaWdodDo5MDA7Y29sb3I6I2VhNTgwYzt9LnN1Yntmb250LXNpemU6MTFweDtjb2xvcjojNzg3MTZjO21hcmdpbi10b3A6MnB4O30iKwogICAgIi5pbnYtbm97dGV4dC1hbGlnbjpyaWdodDt9Lmludi1ubyBoMntmb250LXNpemU6MThweDtjb2xvcjojZWE1ODBjO30iKwogICAgIi5zZWN0aW9ue21hcmdpbjoxOHB4IDA7fS5zZWN0aW9uIGg0e2ZvbnQtc2l6ZToxMHB4O2ZvbnQtd2VpZ2h0OjgwMDtjb2xvcjojNzg3MTZjO3RleHQtdHJhbnNmb3JtOnVwcGVyY2FzZTtsZXR0ZXItc3BhY2luZzouMDZlbTttYXJnaW4tYm90dG9tOjhweDt9IisKICAgICIucm93e2Rpc3BsYXk6ZmxleDtqdXN0aWZ5LWNvbnRlbnQ6c3BhY2UtYmV0d2VlbjtwYWRkaW5nOjZweCAwO2JvcmRlci1ib3R0b206MXB4IHNvbGlkICNmNWY1ZjQ7Zm9udC1zaXplOjEycHg7fSIrCiAgICAiLnJvdy5ib2xke2ZvbnQtd2VpZ2h0OjcwMDt9LnJvdy50b3RhbHtmb250LXNpemU6MTVweDtmb250LXdlaWdodDo5MDA7Y29sb3I6I2VhNTgwYztib3JkZXItdG9wOjJweCBzb2xpZCAjZWE1ODBjO2JvcmRlci1ib3R0b206bm9uZTtwYWRkaW5nLXRvcDoxMHB4O21hcmdpbi10b3A6NHB4O30iKwogICAgIi5iYWRnZXtkaXNwbGF5OmlubGluZS1ibG9jaztwYWRkaW5nOjNweCAxMHB4O2JvcmRlci1yYWRpdXM6MjBweDtmb250LXNpemU6MTBweDtmb250LXdlaWdodDo4MDA7YmFja2dyb3VuZDojZjBmZGY0O2NvbG9yOiMxNTgwM2Q7Ym9yZGVyOjFweCBzb2xpZCAjODZlZmFjO30iKwogICAgIi5mb290ZXJ7bWFyZ2luLXRvcDozMnB4O3RleHQtYWxpZ246Y2VudGVyO2ZvbnQtc2l6ZToxMHB4O2NvbG9yOiNhOGEyOWU7Ym9yZGVyLXRvcDoxcHggc29saWQgI2Y1ZjVmNDtwYWRkaW5nLXRvcDoxMnB4O30iKwogICAgIkBtZWRpYSBwcmludHtib2R5e3BhZGRpbmc6MTZweDt9fTwvc3R5bGU+PC9oZWFkPjxib2R5PiIrCiAgICAiPGRpdiBjbGFzcz1cImhkclwiPjxkaXY+PGRpdiBjbGFzcz1cImJyYW5kXCI+S1BSIENvbG91ciBMYWI8L2Rpdj48ZGl2IGNsYXNzPVwic3ViXCI+UHJpbnQgJiBQaG90b2dyYXBoeSBTZXJ2aWNlczwvZGl2PjwvZGl2PiIrCiAgICAiPGRpdiBjbGFzcz1cImludi1ub1wiPjxoMj5JTlZPSUNFPC9oMj48ZGl2IHN0eWxlPVwiZm9udC1zaXplOjEycHg7Y29sb3I6Izc4NzE2Y1wiPiMiK2pvYi5pZCsiPC9kaXY+PGRpdiBzdHlsZT1cImZvbnQtc2l6ZToxMXB4O2NvbG9yOiNhOGEyOWU7bWFyZ2luLXRvcDoycHhcIj4iK25ldyBEYXRlKCkudG9Mb2NhbGVEYXRlU3RyaW5nKCJlbi1JTiIpKyI8L2Rpdj48L2Rpdj48L2Rpdj4iKwogICAgIjxkaXYgc3R5bGU9XCJkaXNwbGF5OmdyaWQ7Z3JpZC10ZW1wbGF0ZS1jb2x1bW5zOjFmciAxZnI7Z2FwOjI0cHhcIj4iKwogICAgIjxkaXYgY2xhc3M9XCJzZWN0aW9uXCI+PGg0PkJpbGwgVG88L2g0PjxkaXYgc3R5bGU9XCJmb250LXNpemU6MTRweDtmb250LXdlaWdodDo3MDBcIj4iKyhqb2IuY3VzdG9tZXJfbmFtZXx8IuKAlCIpKyI8L2Rpdj4iK3Bob25lKyI8L2Rpdj4iKwogICAgIjxkaXYgY2xhc3M9XCJzZWN0aW9uXCI+PGg0PkpvYiBJbmZvPC9oND4iKwogICAgIjxkaXYgY2xhc3M9XCJyb3dcIj48c3Bhbj5Kb2IgVHlwZTwvc3Bhbj48c3Bhbj4iKyhqb2Iuam9iX3R5cGV8fCLigJQiKSsiPC9zcGFuPjwvZGl2PiIrCiAgICAiPGRpdiBjbGFzcz1cInJvd1wiPjxzcGFuPlNpemU8L3NwYW4+PHNwYW4+Iisoam9iLnNpemV8fCLigJQiKSsiPC9zcGFuPjwvZGl2PiIrCiAgICAiPGRpdiBjbGFzcz1cInJvd1wiPjxzcGFuPlN0YXR1czwvc3Bhbj48c3Bhbj48c3BhbiBjbGFzcz1cImJhZGdlXCI+Iisoam9iLnN0YXR1c3x8IuKAlCIpKyI8L3NwYW4+PC9zcGFuPjwvZGl2PiIrZHVlKyI8L2Rpdj48L2Rpdj4iKwogICAgZGVzYysKICAgICI8ZGl2IGNsYXNzPVwic2VjdGlvblwiPjxoND5QYXltZW50IFN1bW1hcnk8L2g0PiIrCiAgICAiPGRpdiBjbGFzcz1cInJvd1wiPjxzcGFuPkluaXRpYWwgUHJpY2U8L3NwYW4+PHNwYW4+UnMuIitOdW1iZXIoam9iLmluaXRpYWxfcHJpY2V8fDApLnRvTG9jYWxlU3RyaW5nKCJlbi1JTiIpKyI8L3NwYW4+PC9kaXY+IitkaXNjKwogICAgIjxkaXYgY2xhc3M9XCJyb3cgYm9sZFwiPjxzcGFuPkZpbmFsIEFtb3VudDwvc3Bhbj48c3Bhbj5Scy4iK051bWJlcihqb2IuZmluYWxfcHJpY2V8fDApLnRvTG9jYWxlU3RyaW5nKCJlbi1JTiIpKyI8L3NwYW4+PC9kaXY+IisKICAgICI8ZGl2IGNsYXNzPVwicm93XCI+PHNwYW4+QWR2YW5jZSBQYWlkPC9zcGFuPjxzcGFuIHN0eWxlPVwiY29sb3I6IzE2YTM0YVwiPlJzLiIrTnVtYmVyKGpvYi5hZHZhbmNlMXx8MCkudG9Mb2NhbGVTdHJpbmcoImVuLUlOIikrIjwvc3Bhbj48L2Rpdj4iKwogICAgIjxkaXYgY2xhc3M9XCJyb3cgdG90YWxcIj48c3Bhbj5CYWxhbmNlIER1ZTwvc3Bhbj48c3Bhbj4iK2xvYysiPC9zcGFuPjwvZGl2PjwvZGl2PiIrCiAgICAiPGRpdiBjbGFzcz1cImZvb3RlclwiPlRoYW5rIHlvdSBmb3IgeW91ciBidXNpbmVzcyEgfCBLUFIgQ29sb3VyIExhYiB8IEdlbmVyYXRlZCAiK25ldyBEYXRlKCkudG9Mb2NhbGVTdHJpbmcoImVuLUlOIikrIjwvZGl2PiIrCiAgICAiPC9ib2R5PjwvaHRtbD4iOwp9CmZ1bmN0aW9uIEludm9pY2VNb2RhbCh7am9iLG9uQ2xvc2V9KXsKICBjb25zdCBkb1ByaW50PSgpPT57CiAgICBjb25zdCB3PXdpbmRvdy5vcGVuKCIiLCJfYmxhbmsiLCJ3aWR0aD03MDAsaGVpZ2h0PTkwMCIpOwogICAgdy5kb2N1bWVudC5vcGVuKCk7dy5kb2N1bWVudC53cml0ZShidWlsZEludm9pY2VIVE1MKGpvYikpO3cuZG9jdW1lbnQuY2xvc2UoKTsKICAgIHcuZm9jdXMoKTtzZXRUaW1lb3V0KCgpPT53LnByaW50KCksNDAwKTsKICB9OwogIHJldHVybiBSZWFjdC5jcmVhdGVFbGVtZW50KE1vZGFsLHt0aXRsZToiSW52b2ljZSDigJQgSm9iICMiK2pvYi5pZCxvbkNsb3NlLHc6NDYwfSwKICAgIFJlYWN0LmNyZWF0ZUVsZW1lbnQoImRpdiIse3N0eWxlOntiYWNrZ3JvdW5kOiIjZmFmYWY5Iixib3JkZXJSYWRpdXM6OSxwYWRkaW5nOiIxNHB4IixtYXJnaW5Cb3R0b206MTQsYm9yZGVyOiIxcHggc29saWQgI2YwZWZlZSJ9fSwKICAgICAgUmVhY3QuY3JlYXRlRWxlbWVudCgiZGl2Iix7c3R5bGU6e2Rpc3BsYXk6ImZsZXgiLGp1c3RpZnlDb250ZW50OiJzcGFjZS1iZXR3ZWVuIixhbGlnbkl0ZW1zOiJjZW50ZXIiLG1hcmdpbkJvdHRvbToxMH19LAogICAgICAgIFJlYWN0LmNyZWF0ZUVsZW1lbnQoImRpdiIsbnVsbCwKICAgICAgICAgIFJlYWN0LmNyZWF0ZUVsZW1lbnQoImRpdiIse3N0eWxlOntmb250U2l6ZToxNCxmb250V2VpZ2h0OjgwMCxjb2xvcjoiIzFjMTkxNyJ9fSxqb2IuY3VzdG9tZXJfbmFtZSksCiAgICAgICAgICBSZWFjdC5jcmVhdGVFbGVtZW50KCJkaXYiLHtzdHlsZTp7Zm9udFNpemU6MTEsY29sb3I6IiM3ODcxNmMifX0sam9iLmpvYl90eXBlKyhqb2Iuc2l6ZT8iIMK3ICIram9iLnNpemU6IiIpKQogICAgICAgICksCiAgICAgICAgUmVhY3QuY3JlYXRlRWxlbWVudChCYWRnZSx7c3RhdHVzOmpvYi5zdGF0dXN9KQogICAgICApLAogICAgICBbWyJJbml0aWFsIFByaWNlIiwiUnMuIitOdW1iZXIoam9iLmluaXRpYWxfcHJpY2V8fDApLnRvTG9jYWxlU3RyaW5nKCJlbi1JTiIpXSwKICAgICAgIFsiRGlzY291bnQiLGpvYi5kaXNjb3VudF9hbW91bnQ+MD8iUnMuIitOdW1iZXIoam9iLmRpc2NvdW50X2Ftb3VudCkudG9Mb2NhbGVTdHJpbmcoImVuLUlOIik6IuKAlCJdLAogICAgICAgWyJGaW5hbCBBbW91bnQiLCJScy4iK051bWJlcihqb2IuZmluYWxfcHJpY2V8fDApLnRvTG9jYWxlU3RyaW5nKCJlbi1JTiIpXSwKICAgICAgIFsiQWR2YW5jZSBQYWlkIiwiUnMuIitOdW1iZXIoam9iLmFkdmFuY2UxfHwwKS50b0xvY2FsZVN0cmluZygiZW4tSU4iKV0KICAgICAgXS5tYXAoKFtsLHZdKT0+UmVhY3QuY3JlYXRlRWxlbWVudCgiZGl2Iix7a2V5Omwsc3R5bGU6e2Rpc3BsYXk6ImZsZXgiLGp1c3RpZnlDb250ZW50OiJzcGFjZS1iZXR3ZWVuIixwYWRkaW5nOiI1cHggMCIsYm9yZGVyQm90dG9tOiIxcHggc29saWQgI2ZhZmFmOSIsZm9udFNpemU6MTJ9fSwKICAgICAgICBSZWFjdC5jcmVhdGVFbGVtZW50KCJzcGFuIix7c3R5bGU6e2NvbG9yOiIjNzg3MTZjIixmb250V2VpZ2h0OjYwMH19LGwpLAogICAgICAgIFJlYWN0LmNyZWF0ZUVsZW1lbnQoInNwYW4iLHtzdHlsZTp7Zm9udFdlaWdodDo3MDB9fSx2KQogICAgICApKSwKICAgICAgUmVhY3QuY3JlYXRlRWxlbWVudCgiZGl2Iix7c3R5bGU6e2Rpc3BsYXk6ImZsZXgiLGp1c3RpZnlDb250ZW50OiJzcGFjZS1iZXR3ZWVuIixwYWRkaW5nOiIxMHB4IDAgMCIsZm9udFNpemU6MTQsZm9udFdlaWdodDo5MDB9fSwKICAgICAgICBSZWFjdC5jcmVhdGVFbGVtZW50KCJzcGFuIix7c3R5bGU6e2NvbG9yOiIjOTI0MDBlIn19LCJCYWxhbmNlIER1ZSIpLAogICAgICAgIFJlYWN0LmNyZWF0ZUVsZW1lbnQoInNwYW4iLHtzdHlsZTp7Y29sb3I6am9iLmJhbGFuY2U+MD8iI2RjMjYyNiI6IiMxNmEzNGEifX0sam9iLmJhbGFuY2U+MD8iUnMuIitOdW1iZXIoam9iLmJhbGFuY2UpLnRvTG9jYWxlU3RyaW5nKCJlbi1JTiIpOiJGdWxseSBQYWlkIikKICAgICAgKQogICAgKSwKICAgIFJlYWN0LmNyZWF0ZUVsZW1lbnQoImRpdiIse3N0eWxlOntkaXNwbGF5OiJmbGV4IixnYXA6OCxqdXN0aWZ5Q29udGVudDoiZmxleC1lbmQifX0sCiAgICAgIFJlYWN0LmNyZWF0ZUVsZW1lbnQoImJ1dHRvbiIse29uQ2xpY2s6b25DbG9zZSxzdHlsZTpCVE4oImdob3N0Iil9LCJDYW5jZWwiKSwKICAgICAgUmVhY3QuY3JlYXRlRWxlbWVudCgiYnV0dG9uIix7b25DbGljazpkb1ByaW50LHN0eWxlOnsuLi5CVE4oKSxkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGdhcDo2fX0sIlByaW50IEludm9pY2UiKQogICAgKQogICk7Cn0KCi8qIOKUgOKUgCBDVVNUT01FUiBISVNUT1JZIE1PREFMIOKUgOKUgCAqLwpmdW5jdGlvbiBDdXN0b21lckhpc3RvcnlNb2RhbCh7Y3VzdG9tZXIsYXBpLG9uQ2xvc2V9KXsKICBjb25zdFtqb2JzLHNldEpvYnNdPXVzZVN0YXRlKFtdKTtjb25zdFtsb2FkaW5nLHNldExvYWRpbmddPXVzZVN0YXRlKHRydWUpOwogIHVzZUVmZmVjdCgoKT0+ewogICAgYXBpLmN1c3RvbWVySm9icyhjdXN0b21lci5pZCkudGhlbihqPT57c2V0Sm9icyhqKTtzZXRMb2FkaW5nKGZhbHNlKTt9KS5jYXRjaCgoKT0+ewogICAgICAvLyBmYWxsYmFjazogZmlsdGVyIGZyb20gYWxsIGpvYnMKICAgICAgYXBpLmpvYnMoImxpbWl0PTIwMCIpLnRoZW4oYWxsPT57IHNldEpvYnMoYWxsLmZpbHRlcihqPT5qLmN1c3RvbWVyX2lkPT09Y3VzdG9tZXIuaWR8fGouY3VzdG9tZXJfbmFtZT09PWN1c3RvbWVyLm5hbWUpKTtzZXRMb2FkaW5nKGZhbHNlKTt9KS5jYXRjaCgoKT0+c2V0TG9hZGluZyhmYWxzZSkpOwogICAgfSk7CiAgfSxbY3VzdG9tZXIuaWRdKTsKICBjb25zdCB0b3RhbER1ZT1qb2JzLnJlZHVjZSgocyxqKT0+cysoTnVtYmVyKGouYmFsYW5jZSl8fDApLDApOwogIGNvbnN0IHRvdGFsUGFpZD1qb2JzLnJlZHVjZSgocyxqKT0+cysoTnVtYmVyKGouYWR2YW5jZTEpfHwwKSwwKTsKICByZXR1cm48TW9kYWwgdGl0bGU9e2Ake2N1c3RvbWVyLm5hbWV9IOKAlCBKb2IgSGlzdG9yeWB9IG9uQ2xvc2U9e29uQ2xvc2V9IHc9ezUyMH0+CiAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZ3JpZCIsZ3JpZFRlbXBsYXRlQ29sdW1uczoiMWZyIDFmciAxZnIiLGdhcDo4LG1hcmdpbkJvdHRvbToxNH19PgogICAgICB7W1siVG90YWwgSm9icyIsam9icy5sZW5ndGgsIiMxYzE5MTciXSxbIlRvdGFsIFBhaWQiLGDigrkke3RvdGFsUGFpZC50b0xvY2FsZVN0cmluZygiZW4tSU4iKX1gLCIjMTZhMzRhIl0sWyJCYWxhbmNlIER1ZSIsYOKCuSR7dG90YWxEdWUudG9Mb2NhbGVTdHJpbmcoImVuLUlOIil9YCx0b3RhbER1ZT4wPyIjZGMyNjI2IjoiIzE2YTM0YSJdXS5tYXAoKFtsLHYsY10pPT4oCiAgICAgICAgPGRpdiBrZXk9e2x9IHN0eWxlPXt7YmFja2dyb3VuZDoiI2ZhZmFmOSIsYm9yZGVyUmFkaXVzOjgscGFkZGluZzoiMTBweCAxMnB4Iixib3JkZXI6IjFweCBzb2xpZCAjZjBlZmVlIix0ZXh0QWxpZ246ImNlbnRlciJ9fT4KICAgICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZTo5LGNvbG9yOiIjNzg3MTZjIixmb250V2VpZ2h0OjcwMCxtYXJnaW5Cb3R0b206NCx0ZXh0VHJhbnNmb3JtOiJ1cHBlcmNhc2UifX0+e2x9PC9kaXY+CiAgICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTYsZm9udFdlaWdodDo5MDAsY29sb3I6Y319Pnt2fTwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICApKX0KICAgIDwvZGl2PgogICAgPGRpdiBzdHlsZT17e21heEhlaWdodDozMjAsb3ZlcmZsb3dZOiJhdXRvIn19PgogICAgICB7bG9hZGluZz9bMSwyLDNdLm1hcChpPT48ZGl2IGtleT17aX0gc3R5bGU9e3twYWRkaW5nOiIxMHB4IDAifX0+PFNrZWwgaD17MTN9Lz48L2Rpdj4pOgogICAgICBqb2JzLmxlbmd0aD09PTA/PGRpdiBzdHlsZT17e3RleHRBbGlnbjoiY2VudGVyIixwYWRkaW5nOiIyOHB4Iixjb2xvcjoiI2E4YTI5ZSIsZm9udFNpemU6MTJ9fT5ObyBqb2JzIGZvdW5kLjwvZGl2PjoKICAgICAgam9icy5tYXAoaj0+e2NvbnN0IG92PWouZHVlX2RhdGUmJm5ldyBEYXRlKGouZHVlX2RhdGUpPG5ldyBEYXRlKCkmJiFbIkRlbGl2ZXJlZCIsIkNvbXBsZXRlZCJdLmluY2x1ZGVzKGouc3RhdHVzKTtyZXR1cm4oCiAgICAgICAgPGRpdiBrZXk9e2ouaWR9IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsZ2FwOjEwLHBhZGRpbmc6IjlweCAwIixib3JkZXJCb3R0b206IjFweCBzb2xpZCAjZmFmYWY5IixhbGlnbkl0ZW1zOiJjZW50ZXIifX0+CiAgICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTAsZm9udFdlaWdodDo4MDAsY29sb3I6Qi5wcmksbWluV2lkdGg6Mjh9fT4je2ouaWR9PC9kaXY+CiAgICAgICAgICA8ZGl2IHN0eWxlPXt7ZmxleDoxfX0+CiAgICAgICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZToxMixmb250V2VpZ2h0OjcwMCxjb2xvcjoiIzFjMTkxNyJ9fT57ai5qb2JfdHlwZX17ai5zaXplP2AgwrcgJHtqLnNpemV9YDoiIn08L2Rpdj4KICAgICAgICAgICAgPGRpdiBzdHlsZT17e2ZvbnRTaXplOjEwLGNvbG9yOm92PyIjYzI0MTBjIjoiIzc4NzE2YyIsbWFyZ2luVG9wOjF9fT57b3Y/IuKaoCAiOiIifXtqLmR1ZV9kYXRlfHwi4oCUIn0gwrcge2ouY3JlYXRlZF9hdD9qLmNyZWF0ZWRfYXQuc2xpY2UoMCwxMCk6IuKAlCJ9PC9kaXY+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDxkaXYgc3R5bGU9e3t0ZXh0QWxpZ246InJpZ2h0In19PgogICAgICAgICAgICA8QmFkZ2Ugc3RhdHVzPXtqLnN0YXR1c30vPgogICAgICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTEsZm9udFdlaWdodDo3MDAsY29sb3I6ai5iYWxhbmNlPjA/IiNkYzI2MjYiOiIjMTZhMzRhIixtYXJnaW5Ub3A6M319PntqLmJhbGFuY2U+MD9g4oK5JHtOdW1iZXIoai5iYWxhbmNlKS50b0xvY2FsZVN0cmluZygiZW4tSU4iKX0gZHVlYDoi4pyTIFBhaWQifTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgPC9kaXY+KTt9KX0KICAgIDwvZGl2PgogICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGp1c3RpZnlDb250ZW50OiJmbGV4LWVuZCIsbWFyZ2luVG9wOjEwfX0+CiAgICAgIDxidXR0b24gb25DbGljaz17b25DbG9zZX0gc3R5bGU9e0JUTigiZ2hvc3QiKX0+Q2xvc2U8L2J1dHRvbj4KICAgIDwvZGl2PgogIDwvTW9kYWw+Owp9CgoKCi8qIOKUgOKUgCBMT0dJTiDilIDilIAgKi8KZnVuY3Rpb24gTG9naW4oe29uTG9naW4sc2VydmVyVXJsLG9uQ29uZmlnfSl7CiAgY29uc3RbdXNlcixzZXRVc2VyXT11c2VTdGF0ZSgiIik7Y29uc3RbcGFzcyxzZXRQYXNzXT11c2VTdGF0ZSgiIik7Y29uc3Rbc2hvd1Asc2V0U2hvd1BdPXVzZVN0YXRlKGZhbHNlKTsKICBjb25zdFtsb2FkaW5nLHNldExvYWRpbmddPXVzZVN0YXRlKGZhbHNlKTtjb25zdFtlcnIsc2V0RXJyXT11c2VTdGF0ZSgiIik7CiAgY29uc3Qgc3VibWl0PWFzeW5jKCk9PnsKICAgIGlmKCF1c2VyfHwhcGFzcyl7c2V0RXJyKCJVc2VybmFtZSAmIFBhc3N3b3JkIGVudGVyIOCwmuCxh+Cwr+CwguCwoeCwvy4iKTtyZXR1cm47fQogICAgc2V0TG9hZGluZyh0cnVlKTtzZXRFcnIoIiIpOwogICAgdHJ5e2NvbnN0IGFwaT1tYWtlQXBpKHNlcnZlclVybCk7Y29uc3QgcmVzPWF3YWl0IGFwaS5sb2dpbih1c2VyLHBhc3MpO29uTG9naW4ocmVzLGFwaSk7fQogICAgY2F0Y2goZSl7c2V0RXJyKGUubWVzc2FnZXx8IkxvZ2luIGZhaWxlZC4iKTtzZXRMb2FkaW5nKGZhbHNlKTt9CiAgfTsKICByZXR1cm48ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsaGVpZ2h0OiIxMDB2aCIsYWxpZ25JdGVtczoiY2VudGVyIixqdXN0aWZ5Q29udGVudDoiY2VudGVyIixiYWNrZ3JvdW5kOiIjZmFmYWY5IixwYWRkaW5nOiIxNnB4In19PgogICAgPGJ1dHRvbiBvbkNsaWNrPXtvbkNvbmZpZ30gc3R5bGU9e3twb3NpdGlvbjoiYWJzb2x1dGUiLHRvcDoxNCxyaWdodDoxNCwuLi5CVE4oImdob3N0IiksZGlzcGxheToiZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixnYXA6NSxmb250U2l6ZToxMX19PvCfk6EgQ29uZmlndXJlIFNlcnZlcjwvYnV0dG9uPgogICAgPGRpdiBzdHlsZT17e3dpZHRoOiIxMDAlIixtYXhXaWR0aDozOTAsYW5pbWF0aW9uOiJmYWRlSW4gLjRzIGVhc2UifX0+CiAgICAgIDxkaXYgc3R5bGU9e3tiYWNrZ3JvdW5kOiIjZmZmIixib3JkZXJSYWRpdXM6MTYsYm9yZGVyOiIxcHggc29saWQgI2U3ZTVlNCIscGFkZGluZzoiMzZweCAzMnB4IDMycHgiLGJveFNoYWRvdzoiMCA4cHggMzJweCByZ2JhKDI4LDI1LDIzLC4wNykifX0+CiAgICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGZsZXhEaXJlY3Rpb246ImNvbHVtbiIsYWxpZ25JdGVtczoiY2VudGVyIixtYXJnaW5Cb3R0b206MjZ9fT4KICAgICAgICAgIDxkaXYgc3R5bGU9e3t3aWR0aDo2MixoZWlnaHQ6NjIsYm9yZGVyUmFkaXVzOjE2LGJhY2tncm91bmQ6YGxpbmVhci1ncmFkaWVudCgxMzVkZWcsJHtCLnByaX0sJHtCLnByaUR9KWAsZGlzcGxheToiZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixqdXN0aWZ5Q29udGVudDoiY2VudGVyIixtYXJnaW5Cb3R0b206MTQsYm94U2hhZG93OmAwIDZweCAyMHB4ICR7Qi5wcml9NDBgLGZvbnRTaXplOjI4fX0+8J+TtzwvZGl2PgogICAgICAgICAgPGRpdiBzdHlsZT17e2ZvbnRTaXplOjIyLGZvbnRXZWlnaHQ6ODAwLGNvbG9yOiIjMWMxOTE3IixsZXR0ZXJTcGFjaW5nOiItLjNweCJ9fT5LUFIgQ29sb3VyIExhYjwvZGl2PgogICAgICAgICAgPGRpdiBzdHlsZT17e2ZvbnRTaXplOjEwLGNvbG9yOiIjNzg3MTZjIixtYXJnaW5Ub3A6MyxsZXR0ZXJTcGFjaW5nOiIuMDZlbSIsZm9udFdlaWdodDo3MDB9fT5DUk0gTUFOQUdFTUVOVCBTWVNURU08L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICB7ZXJyJiY8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDoiI2ZlZjJmMiIsYm9yZGVyOiIxcHggc29saWQgI2ZjYTVhNSIsYm9yZGVyUmFkaXVzOjgscGFkZGluZzoiOXB4IDEycHgiLGZvbnRTaXplOjExLGNvbG9yOiIjZGMyNjI2IixtYXJnaW5Cb3R0b206MTMsZm9udFdlaWdodDo2MDB9fT7imqAge2Vycn08L2Rpdj59CiAgICAgICAgPEZsZCBsYWJlbD0iVXNlcm5hbWUiIHJlcT48aW5wdXQgdmFsdWU9e3VzZXJ9IG9uQ2hhbmdlPXtlPT5zZXRVc2VyKGUudGFyZ2V0LnZhbHVlKX0gb25LZXlEb3duPXtlPT5lLmtleT09PSJFbnRlciImJnN1Ym1pdCgpfSBwbGFjZWhvbGRlcj0iRW50ZXIgdXNlcm5hbWUiIHN0eWxlPXtJTlB9IGF1dG9Gb2N1cy8+PC9GbGQ+CiAgICAgICAgPEZsZCBsYWJlbD0iUGFzc3dvcmQiIHJlcT4KICAgICAgICAgIDxkaXYgc3R5bGU9e3twb3NpdGlvbjoicmVsYXRpdmUifX0+CiAgICAgICAgICAgIDxpbnB1dCB2YWx1ZT17cGFzc30gb25DaGFuZ2U9e2U9PnNldFBhc3MoZS50YXJnZXQudmFsdWUpfSBvbktleURvd249e2U9PmUua2V5PT09IkVudGVyIiYmc3VibWl0KCl9IHR5cGU9e3Nob3dQPyJ0ZXh0IjoicGFzc3dvcmQifSBwbGFjZWhvbGRlcj0iRW50ZXIgcGFzc3dvcmQiIHN0eWxlPXt7Li4uSU5QLHBhZGRpbmdSaWdodDozNH19Lz4KICAgICAgICAgICAgPGJ1dHRvbiBvbkNsaWNrPXsoKT0+c2V0U2hvd1Aodj0+IXYpfSBzdHlsZT17e3Bvc2l0aW9uOiJhYnNvbHV0ZSIscmlnaHQ6OSx0b3A6IjUwJSIsdHJhbnNmb3JtOiJ0cmFuc2xhdGVZKC01MCUpIixiYWNrZ3JvdW5kOiJub25lIixib3JkZXI6Im5vbmUiLGN1cnNvcjoicG9pbnRlciIsY29sb3I6IiNhOGEyOWUiLGZvbnRTaXplOjE0fX0+e3Nob3dQPyLwn5mIIjoi8J+RgSJ9PC9idXR0b24+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICA8L0ZsZD4KICAgICAgICA8YnV0dG9uIG9uQ2xpY2s9e3N1Ym1pdH0gZGlzYWJsZWQ9e2xvYWRpbmd9IHN0eWxlPXt7Li4uQlROKCksd2lkdGg6IjEwMCUiLG1hcmdpblRvcDo2LHBhZGRpbmc6IjExcHgiLGZvbnRTaXplOjEzfX0+CiAgICAgICAgICB7bG9hZGluZz88c3BhbiBzdHlsZT17e2Rpc3BsYXk6ImlubGluZS1mbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGdhcDo2fX0+PFNwaW4vPkxvZ2dpbmcgaW4uLi48L3NwYW4+OiJMb2dpbiB0byBLUFIgTGFiIn0KICAgICAgICA8L2J1dHRvbj4KICAgICAgICA8ZGl2IHN0eWxlPXt7bWFyZ2luVG9wOjEzLHBhZGRpbmc6IjhweCAxMXB4IixiYWNrZ3JvdW5kOiIjZmFmYWY5Iixib3JkZXJSYWRpdXM6Nyxib3JkZXI6IjFweCBzb2xpZCAjZjVmNWY0Iixmb250U2l6ZToxMCxjb2xvcjoiIzc4NzE2YyIsdGV4dEFsaWduOiJjZW50ZXIifX0+CiAgICAgICAgICB7c2VydmVyVXJsLmluY2x1ZGVzKCJyZW5kZXIuY29tIik/CiAgICAgICAgICAgIDxzcGFuIHN0eWxlPXt7Y29sb3I6IiMxNmEzNGEiLGZvbnRXZWlnaHQ6NzAwfX0+8J+MjSBPbmxpbmUgTW9kZSAoUmVuZGVyKTwvc3Bhbj46CiAgICAgICAgICAgIDxzcGFuIHN0eWxlPXt7Y29sb3I6IiMyNTYzZWIiLGZvbnRXZWlnaHQ6NzAwfX0+8J+PoCBMQU4gTW9kZTwvc3Bhbj59CiAgICAgICAgICA8YnIvPjxzcGFuIHN0eWxlPXt7d29yZEJyZWFrOiJicmVhay1hbGwifX0+e3NlcnZlclVybH08L3NwYW4+CiAgICAgICAgPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgPC9kaXY+Owp9CgovKiDilIDilIAgUElFIENIQVJUIOKUgOKUgCAqLwpmdW5jdGlvbiBKb2JQaWUoe2pvYnN9KXsKICBjb25zdCBzbD1be2w6IlBlbmRpbmciLHY6am9icy5wZW5kaW5nfHwwLGM6IiNmNTllMGIifSx7bDoiSW4gUHJvZ3Jlc3MiLHY6am9icy5pbl9wcm9ncmVzc3x8MCxjOkIucHJpfSx7bDoiQ29tcGxldGVkIix2OmpvYnMuY29tcGxldGVkfHwwLGM6IiMxNmEzNGEifV07CiAgY29uc3QgdG90YWw9c2wucmVkdWNlKChhLHMpPT5hK3MudiwwKXx8MTtsZXQgY3VtPS05MDsKICBjb25zdCB0b1I9ZD0+KGQqTWF0aC5QSSkvMTgwOwogIGNvbnN0IHNlZ3M9c2wubWFwKHM9Pntjb25zdCBhbmc9KHMudi90b3RhbCkqMzYwLHN0PWN1bTtjdW0rPWFuZztjb25zdCByPTQwLGN4PTUwLGN5PTUwO2NvbnN0IHgxPWN4K3IqTWF0aC5jb3ModG9SKHN0KSkseTE9Y3krcipNYXRoLnNpbih0b1Ioc3QpKSx4Mj1jeCtyKk1hdGguY29zKHRvUihjdW0pKSx5Mj1jeStyKk1hdGguc2luKHRvUihjdW0pKTtyZXR1cm57Li4ucyxkOmBNJHtjeH0sJHtjeX0gTCR7eDF9LCR7eTF9IEEke3J9LCR7cn0gMCAke2FuZz4xODA/MTowfSwxICR7eDJ9LCR7eTJ9IFpgfTt9KTsKICByZXR1cm48ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixnYXA6MTR9fT4KICAgIDxzdmcgdmlld0JveD0iMCAwIDEwMCAxMDAiIHN0eWxlPXt7d2lkdGg6ODgsaGVpZ2h0Ojg4LGZsZXhTaHJpbms6MH19PgogICAgICB7c2Vncy5tYXAoKHMsaSk9PjxwYXRoIGtleT17aX0gZD17cy5kfSBmaWxsPXtzLmN9IG9wYWNpdHk9Ii45Ii8+KX0KICAgICAgPGNpcmNsZSBjeD0iNTAiIGN5PSI1MCIgcj0iMjIiIGZpbGw9IiNmZmYiLz4KICAgICAgPHRleHQgeD0iNTAiIHk9IjQ3IiB0ZXh0QW5jaG9yPSJtaWRkbGUiIGZvbnRTaXplPSIxMSIgZm9udFdlaWdodD0iNzAwIiBmaWxsPSIjMWMxOTE3Ij57dG90YWx9PC90ZXh0PgogICAgICA8dGV4dCB4PSI1MCIgeT0iNTciIHRleHRBbmNob3I9Im1pZGRsZSIgZm9udFNpemU9IjciIGZpbGw9IiM3ODcxNmMiPkpvYnM8L3RleHQ+CiAgICA8L3N2Zz4KICAgIDxkaXYgc3R5bGU9e3tmbGV4OjF9fT4KICAgICAge3NsLm1hcCgocyxpKT0+PGRpdiBrZXk9e2l9IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixqdXN0aWZ5Q29udGVudDoic3BhY2UtYmV0d2VlbiIsbWFyZ2luQm90dG9tOjd9fT4KICAgICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixnYXA6NX19PjxkaXYgc3R5bGU9e3t3aWR0aDo3LGhlaWdodDo3LGJvcmRlclJhZGl1czoyLGJhY2tncm91bmQ6cy5jfX0vPjxzcGFuIHN0eWxlPXt7Zm9udFNpemU6MTEsY29sb3I6IiM1NzUzNGUifX0+e3MubH08L3NwYW4+PC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGdhcDo0fX0+PHNwYW4gc3R5bGU9e3tmb250U2l6ZToxMSxmb250V2VpZ2h0OjgwMCxjb2xvcjoiIzFjMTkxNyJ9fT57cy52fTwvc3Bhbj48c3BhbiBzdHlsZT17e2ZvbnRTaXplOjksY29sb3I6IiNhOGEyOWUifX0+e01hdGgucm91bmQoKHMudi90b3RhbCkqMTAwKX0lPC9zcGFuPjwvZGl2PgogICAgICA8L2Rpdj4pfQogICAgPC9kaXY+CiAgPC9kaXY+Owp9CgoKLyog4pSA4pSAIFNFQVJDSEFCTEUgQ1VTVE9NRVIgU0VMRUNUIOKUgOKUgCAqLwpmdW5jdGlvbiBDdXN0U2VhcmNoKHtjdXN0cyx2YWx1ZSxvbkNoYW5nZX0pewogIGNvbnN0W3Esc2V0UV09dXNlU3RhdGUoIiIpO2NvbnN0W29wZW4sc2V0T3Blbl09dXNlU3RhdGUoZmFsc2UpO2NvbnN0IHJlZj11c2VSZWYobnVsbCk7CiAgY29uc3Qgc2VsPWN1c3RzLmZpbmQoYz0+U3RyaW5nKGMuaWQpPT09U3RyaW5nKHZhbHVlKSk7CiAgY29uc3QgZmlsdGVyZWQ9Y3VzdHMuZmlsdGVyKGM9PiFxfHxjLm5hbWUudG9Mb3dlckNhc2UoKS5pbmNsdWRlcyhxLnRvTG93ZXJDYXNlKCkpfHxjLm1vYmlsZS5pbmNsdWRlcyhxKSkuc2xpY2UoMCw1MCk7CiAgdXNlRWZmZWN0KCgpPT57CiAgICBjb25zdCBoYW5kbGVyPWU9PntpZihyZWYuY3VycmVudCYmIXJlZi5jdXJyZW50LmNvbnRhaW5zKGUudGFyZ2V0KSlzZXRPcGVuKGZhbHNlKTt9OwogICAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcigibW91c2Vkb3duIixoYW5kbGVyKTtyZXR1cm4oKT0+ZG9jdW1lbnQucmVtb3ZlRXZlbnRMaXN0ZW5lcigibW91c2Vkb3duIixoYW5kbGVyKTsKICB9LFtdKTsKICByZXR1cm48ZGl2IHJlZj17cmVmfSBzdHlsZT17e3Bvc2l0aW9uOiJyZWxhdGl2ZSJ9fT4KICAgIDxkaXYgb25DbGljaz17KCk9PnNldE9wZW4odj0+IXYpfSBzdHlsZT17ey4uLklOUCxjdXJzb3I6InBvaW50ZXIiLGRpc3BsYXk6ImZsZXgiLGp1c3RpZnlDb250ZW50OiJzcGFjZS1iZXR3ZWVuIixhbGlnbkl0ZW1zOiJjZW50ZXIiLGJhY2tncm91bmQ6IiNmZmYiLHVzZXJTZWxlY3Q6Im5vbmUifX0+CiAgICAgIHtzZWw/PHNwYW4gc3R5bGU9e3tmb250V2VpZ2h0OjYwMCxjb2xvcjoiIzFjMTkxNyJ9fT57c2VsLm5hbWV9IDxzcGFuIHN0eWxlPXt7Y29sb3I6IiM3ODcxNmMiLGZvbnRXZWlnaHQ6NDAwLGZvbnRTaXplOjExfX0+KHtzZWwubW9iaWxlfSk8L3NwYW4+PC9zcGFuPgogICAgICAgICAgOjxzcGFuIHN0eWxlPXt7Y29sb3I6IiNhOGEyOWUifX0+LS0gU2VsZWN0IEN1c3RvbWVyIC0tPC9zcGFuPn0KICAgICAgPHNwYW4gc3R5bGU9e3tjb2xvcjoiIzc4NzE2YyIsZm9udFNpemU6MTB9fT57b3Blbj8i4payIjoi4pa8In08L3NwYW4+CiAgICA8L2Rpdj4KICAgIHtvcGVuJiY8ZGl2IHN0eWxlPXt7cG9zaXRpb246ImFic29sdXRlIix0b3A6IjEwMCUiLGxlZnQ6MCxyaWdodDowLHpJbmRleDo5OTksYmFja2dyb3VuZDoiI2ZmZiIsYm9yZGVyOiIxcHggc29saWQgI2U3ZTVlNCIsYm9yZGVyUmFkaXVzOjgsYm94U2hhZG93OiIwIDhweCAyNHB4IHJnYmEoMCwwLDAsLjEyKSIsbWFyZ2luVG9wOjIsbWF4SGVpZ2h0OjI2MCxkaXNwbGF5OiJmbGV4IixmbGV4RGlyZWN0aW9uOiJjb2x1bW4ifX0+CiAgICAgIDxkaXYgc3R5bGU9e3twYWRkaW5nOiI4cHggMTBweCIsYm9yZGVyQm90dG9tOiIxcHggc29saWQgI2ZhZmFmOSJ9fT4KICAgICAgICA8aW5wdXQgYXV0b0ZvY3VzIHZhbHVlPXtxfSBvbkNoYW5nZT17ZT0+c2V0UShlLnRhcmdldC52YWx1ZSl9CiAgICAgICAgICBwbGFjZWhvbGRlcj0i8J+UjSBOYW1lIOCwsuCxh+CwpuCwviBNb2JpbGUgc2VhcmNoLi4uIgogICAgICAgICAgc3R5bGU9e3suLi5JTlAscGFkZGluZzoiOHB4IDEwcHgiLGZvbnRTaXplOjEzLGJvcmRlcjoiMXB4IHNvbGlkICNmZWQ3YWEifX0vPgogICAgICA8L2Rpdj4KICAgICAgPGRpdiBzdHlsZT17e292ZXJmbG93WToiYXV0byIsZmxleDoxfX0+CiAgICAgICAgPGRpdiBvbkNsaWNrPXsoKT0+e29uQ2hhbmdlKCIiKTtzZXRRKCIiKTtzZXRPcGVuKGZhbHNlKTt9fQogICAgICAgICAgc3R5bGU9e3twYWRkaW5nOiI5cHggMTJweCIsY3Vyc29yOiJwb2ludGVyIixjb2xvcjoiI2E4YTI5ZSIsZm9udFNpemU6MTIsYm9yZGVyQm90dG9tOiIxcHggc29saWQgI2ZhZmFmOSJ9fT4KICAgICAgICAgIC0tIFNlbGVjdCBDdXN0b21lciAtLQogICAgICAgIDwvZGl2PgogICAgICAgIHtmaWx0ZXJlZC5sZW5ndGg9PT0wJiY8ZGl2IHN0eWxlPXt7cGFkZGluZzoiMTRweCIsdGV4dEFsaWduOiJjZW50ZXIiLGNvbG9yOiIjYThhMjllIixmb250U2l6ZToxMn19Pk5vIHJlc3VsdHMgZm9yICJ7cX0iPC9kaXY+fQogICAgICAgIHtmaWx0ZXJlZC5tYXAoY3U9PjxkaXYga2V5PXtjdS5pZH0KICAgICAgICAgIG9uQ2xpY2s9eygpPT57b25DaGFuZ2UoU3RyaW5nKGN1LmlkKSk7c2V0USgiIik7c2V0T3BlbihmYWxzZSk7fX0KICAgICAgICAgIHN0eWxlPXt7cGFkZGluZzoiMTBweCAxMnB4IixjdXJzb3I6InBvaW50ZXIiLGJhY2tncm91bmQ6U3RyaW5nKGN1LmlkKT09PVN0cmluZyh2YWx1ZSk/IiNmZmY3ZWQiOiIjZmZmIixib3JkZXJCb3R0b206IjFweCBzb2xpZCAjZmFmYWY5IixkaXNwbGF5OiJmbGV4IixqdXN0aWZ5Q29udGVudDoic3BhY2UtYmV0d2VlbiIsYWxpZ25JdGVtczoiY2VudGVyIn19CiAgICAgICAgICBvbk1vdXNlRW50ZXI9e2U9PmUuY3VycmVudFRhcmdldC5zdHlsZS5iYWNrZ3JvdW5kPSIjZmZmN2VkIn0KICAgICAgICAgIG9uTW91c2VMZWF2ZT17ZT0+ZS5jdXJyZW50VGFyZ2V0LnN0eWxlLmJhY2tncm91bmQ9U3RyaW5nKGN1LmlkKT09PVN0cmluZyh2YWx1ZSk/IiNmZmY3ZWQiOiIjZmZmIn0+CiAgICAgICAgICA8ZGl2PgogICAgICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTMsZm9udFdlaWdodDo2MDAsY29sb3I6IiMxYzE5MTcifX0+e2N1Lm5hbWV9PC9kaXY+CiAgICAgICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZToxMSxjb2xvcjoiIzc4NzE2YyJ9fT57Y3UubW9iaWxlfTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICB7U3RyaW5nKGN1LmlkKT09PVN0cmluZyh2YWx1ZSkmJjxzcGFuIHN0eWxlPXt7Y29sb3I6Qi5wcmksZm9udFdlaWdodDo4MDB9fT7inJM8L3NwYW4+fQogICAgICAgIDwvZGl2Pil9CiAgICAgIDwvZGl2PgogICAgPC9kaXY+fQogIDwvZGl2PjsKfQoKLyog4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQIERBU0hCT0FSRCDilZDilZDilZAgKi8KZnVuY3Rpb24gRGFzaGJvYXJkKHthcGksdXNlcixzZXROYXYscm9sZX0pewogIGNvbnN0W3N1bSxzZXRTdW1dPXVzZVN0YXRlKG51bGwpO2NvbnN0W2pvYnMsc2V0Sm9ic109dXNlU3RhdGUoW10pO2NvbnN0W2xzLHNldExzXT11c2VTdGF0ZShbXSk7CiAgY29uc3RbbG9hZGluZyxzZXRMb2FkaW5nXT11c2VTdGF0ZSh0cnVlKTtjb25zdFtzcGlubmluZyxzZXRTcGlubmluZ109dXNlU3RhdGUoZmFsc2UpO2NvbnN0W2VycixzZXRFcnJdPXVzZVN0YXRlKCIiKTsKICBjb25zdFtqZixzZXRKZl09dXNlU3RhdGUoIkFsbCIpO2NvbnN0W2pzLHNldEpzXT11c2VTdGF0ZSgiIik7CiAgY29uc3RbZGV0YWlsSm9iLHNldERldGFpbEpvYl09dXNlU3RhdGUobnVsbCk7CiAgCiAgY29uc3QgaXNTdWJTdGFmZj1yb2xlPT09InN1Yl9zdGFmZiI7CiAgY29uc3QgbG9hZD11c2VDYWxsYmFjayhhc3luYyhzaWxlbnQ9ZmFsc2UpPT57aWYoIXNpbGVudClzZXRMb2FkaW5nKHRydWUpO3NldFNwaW5uaW5nKHRydWUpO3NldEVycigiIik7CiAgICB0cnl7Y29uc3RbcyxqLGxdPWF3YWl0IFByb21pc2UuYWxsKFthcGkuc3VtbWFyeSgpLGFwaS5qb2JzKCJsaW1pdD0yMDAiKSxhcGkubG93U3RvY2soKV0pO3NldFN1bShzKTtzZXRKb2JzKGopO3NldExzKGwpO30KICAgIGNhdGNoKGUpe3NldEVycihlLm1lc3NhZ2UpO31maW5hbGx5e3NldExvYWRpbmcoZmFsc2UpO3NldFNwaW5uaW5nKGZhbHNlKTt9CiAgfSxbYXBpXSk7CiAgdXNlRWZmZWN0KCgpPT57bG9hZCgpO2NvbnN0IHQ9c2V0SW50ZXJ2YWwoKCk9PmxvYWQodHJ1ZSksNDUwMDApO3JldHVybigpPT5jbGVhckludGVydmFsKHQpO30sW2xvYWRdKTsKICAvLyBOb24tYWRtaW46IHNob3cgb25seSBqb2JzIGFzc2lnbmVkIHRvIGN1cnJlbnQgdXNlcjsgYWRtaW4gc2VlcyBhbGwKICAvLyBUeXBlLXNhZmU6IGNvbXBhcmUgYXMgc3RyaW5ncyB0byBhdm9pZCBpbnQgdnMgc3RyaW5nIG1pc21hdGNoCiAgY29uc3QgbXlKb2JzPXJvbGU9PT0iYWRtaW4iP2pvYnM6am9icy5maWx0ZXIoaj0+ewogICAgY29uc3QgdWlkPVN0cmluZyh1c2VyPy5pZHx8MCk7CiAgICBjb25zdCB1bmFtZT11c2VyPy51c2VybmFtZXx8IiI7CiAgICByZXR1cm4gU3RyaW5nKGouYXNzaWduZWRfc3RhZmZfaWQpPT09dWlkfHwKICAgICAgICAgICBTdHJpbmcoai5hc3NpZ25lZF90b19pZCk9PT11aWR8fAogICAgICAgICAgIFN0cmluZyhqLmFzc2lnbmVkX3RvKT09PXVpZHx8CiAgICAgICAgICAgKHVuYW1lJiZqLmFzc2lnbmVkX3N0YWZmX25hbWU9PT11bmFtZSl8fAogICAgICAgICAgICh1bmFtZSYmai5hc3NpZ25lZF90b191c2VybmFtZT09PXVuYW1lKTsKICB9KTsKICBjb25zdCBmaj1teUpvYnMuZmlsdGVyKGo9PihqZj09PSJBbGwifHxqLnN0YXR1cz09PWpmKSYmKCFqc3x8KGouY3VzdG9tZXJfbmFtZXx8IiIpLnRvTG93ZXJDYXNlKCkuaW5jbHVkZXMoanMudG9Mb3dlckNhc2UoKSl8fFN0cmluZyhqLmlkKS5pbmNsdWRlcyhqcykpKTsKCiAgcmV0dXJuPFBnPgogICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGp1c3RpZnlDb250ZW50OiJzcGFjZS1iZXR3ZWVuIixhbGlnbkl0ZW1zOiJjZW50ZXIiLG1hcmdpbkJvdHRvbToxNn19PgogICAgICA8ZGl2PgogICAgICAgIDxoMiBzdHlsZT17e2ZvbnRTaXplOjE5LGZvbnRXZWlnaHQ6ODAwLGNvbG9yOiIjMWMxOTE3IixtYXJnaW46MH19PkRhc2hib2FyZDwvaDI+CiAgICAgICAgPHAgc3R5bGU9e3tmb250U2l6ZToxMSxjb2xvcjoiIzc4NzE2YyIsbWFyZ2luOiIycHggMCAwIn19PntuZXcgRGF0ZSgpLnRvTG9jYWxlRGF0ZVN0cmluZygiZW4tSU4iLHt3ZWVrZGF5OiJsb25nIix5ZWFyOiJudW1lcmljIixtb250aDoibG9uZyIsZGF5OiJudW1lcmljIn0pfTwvcD4KICAgICAgPC9kaXY+CiAgICAgIDxidXR0b24gb25DbGljaz17KCk9PmxvYWQoKX0gc3R5bGU9e3suLi5CVE4oImdob3N0IiksZGlzcGxheToiZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixnYXA6NSxwYWRkaW5nOiI3cHggMTJweCIsZm9udFNpemU6MTF9fT4KICAgICAgICA8c3BhbiBzdHlsZT17e2Rpc3BsYXk6ImlubGluZS1ibG9jayIsYW5pbWF0aW9uOnNwaW5uaW5nPyJzcGluIC44cyBsaW5lYXIgaW5maW5pdGUiOiJub25lIixmb250U2l6ZToxMn19PuKGuzwvc3Bhbj4gUmVmcmVzaAogICAgICA8L2J1dHRvbj4KICAgIDwvZGl2PgogICAge2VyciYmPGRpdiBzdHlsZT17e2JhY2tncm91bmQ6IiNmZWYyZjIiLGJvcmRlcjoiMXB4IHNvbGlkICNmY2E1YTUiLGJvcmRlclJhZGl1czo4LHBhZGRpbmc6IjlweCAxMnB4Iixmb250U2l6ZToxMSxjb2xvcjoiI2RjMjYyNiIsbWFyZ2luQm90dG9tOjEzLGZvbnRXZWlnaHQ6NjAwfX0+4pqgIHtlcnJ9PC9kaXY+fQoKICAgIHsvKiBLUElzICovfQogICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImdyaWQiLGdyaWRUZW1wbGF0ZUNvbHVtbnM6d2luZG93LmlubmVyV2lkdGg8PTc2OD8icmVwZWF0KDIsMWZyKSI6InJlcGVhdCg1LDFmcikiLGdhcDp3aW5kb3cuaW5uZXJXaWR0aDw9NzY4Pzg6MTAsbWFyZ2luQm90dG9tOjE0fX0+CiAgICAgIHtbe2w6IlRvdGFsIEN1c3RvbWVycyIsdjpzdW0/LnRvdGFsX2N1c3RvbWVycyxjOiIjMWMxOTE3IixzcDpbMjgwLDI5NSwzMTAsMzI1LDMzNSxzdW0/LnRvdGFsX2N1c3RvbWVyc3x8MzQwXSxzYzpCLnByaSxyb2xlczpbImFkbWluIiwic3RhZmYiLCJzdWJfc3RhZmYiXX0sCiAgICAgICAge2w6IlBlbmRpbmcgSm9icyIsdjpzdW0/LmpvYnM/LnBlbmRpbmcsc3ViOmAke3N1bT8uam9icz8uaW5fcHJvZ3Jlc3N8fDB9IGluIHByb2dyZXNzYCxjOiIjOTI0MDBlIixzcDpbMjAsMTgsMjIsMTksc3VtPy5qb2JzPy5wZW5kaW5nfHwxOF0sc2M6IiNmNTllMGIiLHJvbGVzOlsiYWRtaW4iLCJzdGFmZiIsInN1Yl9zdGFmZiJdfSwKICAgICAgICB7bDoiVG9kYXkncyBSZXZlbnVlIix2OmZtdChzdW0/LnBheW1lbnRzPy50b2RheSksYzoiIzA2NWY0NiIsc3A6WzgsMTEsOSwxMixzdW0/LnBheW1lbnRzPy50b2RheT9zdW0ucGF5bWVudHMudG9kYXkvMTAwMDoxNF0sc2M6IiMxNmEzNGEiLHJvbGVzOlsiYWRtaW4iLCJzdGFmZiJdfSwKICAgICAgICB7bDoiTW9udGhseSBSZXZlbnVlIix2OnN1bT8ucGF5bWVudHM/LnRoaXNfbW9udGg/YOKCuSR7KHN1bS5wYXltZW50cy50aGlzX21vbnRoLzEwMDApLnRvRml4ZWQoMCl9a2A6IuKAlCIsYzoiIzFlM2E4YSIsc3A6WzI0OCwyNzUsMjg5LDI5NSxzdW0/LnBheW1lbnRzPy50aGlzX21vbnRoP3N1bS5wYXltZW50cy50aGlzX21vbnRoLzEwMDA6MzEyXSxzYzoiIzI1NjNlYiIscm9sZXM6WyJhZG1pbiIsInN0YWZmIl19LAogICAgICAgIHtsOiJQZW5kaW5nIENvbGxlY3Rpb24iLHY6Zm10KHN1bT8ucGF5bWVudHM/LnBlbmRpbmdfY29sbGVjdGlvbiksc3ViOiJiYWxhbmNlIGR1ZSIsYzoiIzk5MWIxYiIsZGFuZ2VyOiFsb2FkaW5nJiZzdW0/LnBheW1lbnRzPy5wZW5kaW5nX2NvbGxlY3Rpb24+NTAwMDAsc3A6WzU1LDYyLDY1LDY3XSxzYzoiI2RjMjYyNiIscm9sZXM6WyJhZG1pbiIsInN0YWZmIl19LAogICAgICBdLmZpbHRlcihrPT5rLnJvbGVzLmluY2x1ZGVzKHJvbGV8fCJzdWJfc3RhZmYiKSkubWFwKChrLGkpPT4oCiAgICAgICAgPGRpdiBrZXk9e2l9IHN0eWxlPXt7YmFja2dyb3VuZDoiI2ZmZiIsYm9yZGVyOmAxcHggc29saWQgJHtrLmRhbmdlcj8iI2ZjYTVhNSI6IiNlN2U1ZTQifWAsYm9yZGVyUmFkaXVzOjEwLHBhZGRpbmc6IjEzcHggMTRweCIsdHJhbnNpdGlvbjoiYWxsIC4xOHMiLGN1cnNvcjoiZGVmYXVsdCIsYm94U2hhZG93OmsuZGFuZ2VyPyIwIDAgMCAycHggI2ZlZTJlMiI6Im5vbmUifX0KICAgICAgICAgIG9uTW91c2VFbnRlcj17ZT0+ZS5jdXJyZW50VGFyZ2V0LnN0eWxlLnRyYW5zZm9ybT0idHJhbnNsYXRlWSgtMXB4KSJ9CiAgICAgICAgICBvbk1vdXNlTGVhdmU9e2U9PmUuY3VycmVudFRhcmdldC5zdHlsZS50cmFuc2Zvcm09Im5vbmUifT4KICAgICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZToxMCxjb2xvcjoiIzc4NzE2YyIsZm9udFdlaWdodDo2MDAsbWFyZ2luQm90dG9tOjZ9fT57ay5sfTwvZGl2PgogICAgICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGFsaWduSXRlbXM6ImZsZXgtZW5kIixqdXN0aWZ5Q29udGVudDoic3BhY2UtYmV0d2VlbiJ9fT4KICAgICAgICAgICAgPGRpdj4KICAgICAgICAgICAgICB7bG9hZGluZz88U2tlbCB3PXs3MH0gaD17MjB9Lz46PGRpdiBzdHlsZT17e2ZvbnRTaXplOjIwLGZvbnRXZWlnaHQ6ODAwLGNvbG9yOmsuYyxsaW5lSGVpZ2h0OjF9fT57ay52fHwiLSJ9PC9kaXY+fQogICAgICAgICAgICAgIHtrLnN1YiYmPGRpdiBzdHlsZT17e2ZvbnRTaXplOjksY29sb3I6IiNhOGEyOWUiLG1hcmdpblRvcDoyfX0+e2xvYWRpbmc/PFNrZWwgdz17OTB9IGg9ezl9Lz46ay5zdWJ9PC9kaXY+fQogICAgICAgICAgICA8L2Rpdj4KICAgICAgICAgICAgeyFsb2FkaW5nJiY8U3BhcmsgZGF0YT17ay5zcH0gY29sb3I9e2suc2N9Lz59CiAgICAgICAgICA8L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgKSl9CiAgICA8L2Rpdj4KCiAgICB7LyogQ2hhcnRzIHJvdyAqL30KICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJncmlkIixncmlkVGVtcGxhdGVDb2x1bW5zOndpbmRvdy5pbm5lcldpZHRoPD03Njg/IjFmciI6IjFmciAxZnIgMWZyIixnYXA6d2luZG93LmlubmVyV2lkdGg8PTc2OD84OjEyLG1hcmdpbkJvdHRvbToxNH19PgogICAgICA8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDoidmFyKC0tYmctY2FyZCkiLGJvcmRlcjoiMXB4IHNvbGlkIHZhcigtLWJvcmRlcikiLGJvcmRlclJhZGl1czoxMCxwYWRkaW5nOiIxNHB4IDE2cHgifX0+CiAgICAgICAgPFNIIHRpdGxlPSJKb2IgU3RhdHVzIi8+CiAgICAgICAge2xvYWRpbmc/PFNrZWwgaD17MTAwfS8+OnN1bT8uam9icz88Sm9iUGllIGpvYnM9e3N1bS5qb2JzfS8+OjxkaXYgc3R5bGU9e3tjb2xvcjoiI2E4YTI5ZSIsZm9udFNpemU6MTIsdGV4dEFsaWduOiJjZW50ZXIiLHBhZGRpbmc6IjI0cHggMCJ9fT5ObyBkYXRhPC9kaXY+fQogICAgICA8L2Rpdj4KICAgICAgCiAgICAgIHtyb2xlIT09InN1Yl9zdGFmZiImJjxkaXYgc3R5bGU9e3tiYWNrZ3JvdW5kOiJ2YXIoLS1iZy1jYXJkKSIsYm9yZGVyOiIxcHggc29saWQgdmFyKC0tYm9yZGVyKSIsYm9yZGVyUmFkaXVzOjEwLHBhZGRpbmc6IjE0cHggMTZweCJ9fT4KICAgICAgICA8U0ggdGl0bGU9IkxvdyBTdG9jayIgYmFkZ2U9e2xzLmxlbmd0aH0vPgogICAgICAgIHtsb2FkaW5nPzxTa2VsIGg9ezEwMH0vPjpscy5sZW5ndGg9PT0wPzxkaXYgc3R5bGU9e3tjb2xvcjoiIzE2YTM0YSIsZm9udFNpemU6MTIsdGV4dEFsaWduOiJjZW50ZXIiLHBhZGRpbmc6IjI4cHggMCJ9fT7inJMgQWxsIHN0b2NrIGxldmVscyBPSzwvZGl2PjoKICAgICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsZmxleERpcmVjdGlvbjoiY29sdW1uIixnYXA6N319PgogICAgICAgICAge2xzLnNsaWNlKDAsNikubWFwKChpdGVtLGkpPT57Y29uc3QgYz1pdGVtLmN1cnJlbnRfc3RvY2s8PTA/IiNkYzI2MjYiOiIjZjU5ZTBiIjtyZXR1cm48ZGl2IGtleT17aX0gc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGdhcDo4fX0+CiAgICAgICAgICAgIDxkaXYgc3R5bGU9e3t3aWR0aDo2LGhlaWdodDo2LGJvcmRlclJhZGl1czoiNTAlIixiYWNrZ3JvdW5kOmMsZmxleFNocmluazowfX0vPgogICAgICAgICAgICA8ZGl2IHN0eWxlPXt7ZmxleDoxLGZvbnRTaXplOjExLGZvbnRXZWlnaHQ6NTAwLGNvbG9yOiIjMWMxOTE3IixvdmVyZmxvdzoiaGlkZGVuIix0ZXh0T3ZlcmZsb3c6ImVsbGlwc2lzIix3aGl0ZVNwYWNlOiJub3dyYXAifX0+e2l0ZW0ubmFtZX08L2Rpdj4KICAgICAgICAgICAgPHNwYW4gc3R5bGU9e3tmb250U2l6ZToxMSxmb250V2VpZ2h0OjgwMCxjb2xvcjpjfX0+e2l0ZW0uY3VycmVudF9zdG9ja30ge2l0ZW0udW5pdF9vZl9tZWFzdXJlfHwiIn08L3NwYW4+CiAgICAgICAgICA8L2Rpdj47fSl9CiAgICAgICAgPC9kaXY+fQogICAgICA8L2Rpdj59CgogICAgICAKICAgICAgeyhyb2xlPT09ImFkbWluInx8cm9sZT09PSJzdGFmZiIpJiY8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDoidmFyKC0tYmctY2FyZCkiLGJvcmRlcjoiMXB4IHNvbGlkIHZhcigtLWJvcmRlcikiLGJvcmRlclJhZGl1czoxMCxwYWRkaW5nOiIxNHB4IDE2cHgifX0+CiAgICAgICAgPFNIIHRpdGxlPSJRdWljayBBY3Rpb25zIi8+CiAgICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImdyaWQiLGdyaWRUZW1wbGF0ZUNvbHVtbnM6IjFmciAxZnIiLGdhcDo3fX0+CiAgICAgICAgICB7W3tsOiJDdXN0b21lcnMiLG5hdjoiY3VzdG9tZXJzIixiZzpCLnByaUwsdGM6Qi5wcmlELGJjOkIucHJpTSxyb2xlczpbImFkbWluIiwic3RhZmYiXX0sCiAgICAgICAgICAgIHtsOiJOZXcgSm9iIixuYXY6ImpvYnMiLGJnOiIjZjBmZGY0Iix0YzoiIzA2NWY0NiIsYmM6IiM2ZWU3YjciLHJvbGVzOlsiYWRtaW4iLCJzdGFmZiJdfSwKICAgICAgICAgICAge2w6IlBheW1lbnRzIixuYXY6InBheW1lbnRzIixiZzoiI2ZmZmJlYiIsdGM6IiM5MjQwMGUiLGJjOiIjZmNkMzRkIixyb2xlczpbImFkbWluIiwic3RhZmYiXX0sCiAgICAgICAgICAgIHtsOiJJbnZlbnRvcnkiLG5hdjoiaW52ZW50b3J5IixiZzoiI2VmZjZmZiIsdGM6IiMxZTNhOGEiLGJjOiIjOTNjNWZkIixyb2xlczpbImFkbWluIl19CiAgICAgICAgICBdLmZpbHRlcihxPT5xLnJvbGVzLmluY2x1ZGVzKHVzZXI/LnJvbGV8fCJzdWJfc3RhZmYiKSkubWFwKChxLGkpPT48YnV0dG9uIGtleT17aX0gb25DbGljaz17KCk9PnNldE5hdihxLm5hdil9IHN0eWxlPXt7cGFkZGluZzoiMTBweCAwIixib3JkZXJSYWRpdXM6Nyxib3JkZXI6YDFweCBzb2xpZCAke3EuYmN9YCxiYWNrZ3JvdW5kOnEuYmcsY29sb3I6cS50Yyxmb250U2l6ZToxMSxmb250V2VpZ2h0OjcwMCxjdXJzb3I6InBvaW50ZXIifX0+e3EubH08L2J1dHRvbj4pfQogICAgICAgIDwvZGl2PgogICAgICAgIHt1c2VyLnJvbGU9PT0iYWRtaW4iJiY8ZGl2IHN0eWxlPXt7bWFyZ2luVG9wOjEwLHBhZGRpbmc6IjEwcHggMTJweCIsYmFja2dyb3VuZDpCLnByaUwsYm9yZGVyUmFkaXVzOjgsYm9yZGVyOmAxcHggc29saWQgJHtCLnByaU19YH19PgogICAgICAgICAgPGRpdiBzdHlsZT17e2ZvbnRTaXplOjksZm9udFdlaWdodDo3MDAsY29sb3I6Qi5wcmlELG1hcmdpbkJvdHRvbTozfX0+TG93IFN0b2NrIEFsZXJ0czwvZGl2PgogICAgICAgICAgPGRpdiBzdHlsZT17e2ZvbnRTaXplOjIyLGZvbnRXZWlnaHQ6ODAwLGNvbG9yOkIucHJpfX0+e2xvYWRpbmc/PFNrZWwgdz17MzB9IGg9ezE4fS8+OihzdW0/Lmxvd19zdG9ja19hbGVydHN8fGxzLmxlbmd0aHx8MCl9PC9kaXY+CiAgICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6OSxjb2xvcjpCLnByaUR9fT5pdGVtcyBuZWVkIHJlb3JkZXI8L2Rpdj4KICAgICAgICA8L2Rpdj59CiAgICAgIDwvZGl2Pn0KCiAgICA8L2Rpdj4Key8qIEpvYnMgVGFibGUgKi99CiAgICA8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDoidmFyKC0tYmctY2FyZCkiLGJvcmRlcjoiMXB4IHNvbGlkIHZhcigtLWJvcmRlcikiLGJvcmRlclJhZGl1czoxMCxwYWRkaW5nOiIxNHB4IDE2cHgifX0+CgogICAgICA8U0ggdGl0bGU9e3JvbGU9PT0iYWRtaW4iPyJSZWNlbnQgSm9icyI6Ik15IEFzc2lnbmVkIEpvYnMifSBhY3Rpb249eygpPT5zZXROYXYoImpvYnMiKX0gYWw9IkFsbCBKb2JzIOKGkiIvPgogICAgICB7LyogRHVlIFRvZGF5IC8gT3ZlcmR1ZSBBbGVydCAqL30KICAgICAgeygoKT0+ewogICAgICAgIGNvbnN0IF90b2RheT1UT0RBWSgpOwogICAgICAgIGNvbnN0IF9vdj1teUpvYnMuZmlsdGVyKGo9PmouZHVlX2RhdGUmJmouZHVlX2RhdGU8X3RvZGF5JiYhWyJEZWxpdmVyZWQiLCJDb21wbGV0ZWQiXS5pbmNsdWRlcyhqLnN0YXR1cykpOwogICAgICAgIGNvbnN0IF9kdWU9bXlKb2JzLmZpbHRlcihqPT5qLmR1ZV9kYXRlPT09X3RvZGF5JiYhWyJEZWxpdmVyZWQiLCJDb21wbGV0ZWQiXS5pbmNsdWRlcyhqLnN0YXR1cykpOwogICAgICAgIGlmKF9vdi5sZW5ndGg9PT0wJiZfZHVlLmxlbmd0aD09PTApcmV0dXJuIG51bGw7CiAgICAgICAgcmV0dXJuIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixnYXA6OCxtYXJnaW5Cb3R0b206MTIsZmxleFdyYXA6IndyYXAifX0+CiAgICAgICAgICB7X292Lmxlbmd0aD4wJiY8ZGl2IHN0eWxlPXt7ZmxleDoxLG1pbldpZHRoOjE0MCxiYWNrZ3JvdW5kOiIjZmVmMmYyIixib3JkZXI6IjFweCBzb2xpZCAjZmNhNWE1Iixib3JkZXJSYWRpdXM6OCxwYWRkaW5nOiI5cHggMTJweCIsZGlzcGxheToiZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixnYXA6OH19PgogICAgICAgICAgICA8ZGl2PjxkaXYgc3R5bGU9e3tmb250U2l6ZToxMSxmb250V2VpZ2h0OjgwMCxjb2xvcjoiI2RjMjYyNiJ9fT57X292Lmxlbmd0aH0gT3ZlcmR1ZTwvZGl2PjxkaXYgc3R5bGU9e3tmb250U2l6ZToxMCxjb2xvcjoiI2VmNDQ0NCJ9fT5QYXN0IGR1ZSBkYXRlITwvZGl2PjwvZGl2PgogICAgICAgICAgPC9kaXY+fQogICAgICAgICAge19kdWUubGVuZ3RoPjAmJjxkaXYgc3R5bGU9e3tmbGV4OjEsbWluV2lkdGg6MTQwLGJhY2tncm91bmQ6IiNmZmY3ZWQiLGJvcmRlcjoiMXB4IHNvbGlkICNmZWQ3YWEiLGJvcmRlclJhZGl1czo4LHBhZGRpbmc6IjlweCAxMnB4IixkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGdhcDo4fX0+CiAgICAgICAgICAgIDxkaXY+PGRpdiBzdHlsZT17e2ZvbnRTaXplOjExLGZvbnRXZWlnaHQ6ODAwLGNvbG9yOiIjYzI0MTBjIn19PntfZHVlLmxlbmd0aH0gRHVlIFRvZGF5PC9kaXY+PGRpdiBzdHlsZT17e2ZvbnRTaXplOjEwLGNvbG9yOiIjZWE1ODBjIn19PkNvbXBsZXRlIHRvZGF5ITwvZGl2PjwvZGl2PgogICAgICAgICAgPC9kaXY+fQogICAgICAgIDwvZGl2PjsKICAgICAgfSkoKX0KICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGdhcDo2LG1hcmdpbkJvdHRvbToxMCxmbGV4V3JhcDoid3JhcCJ9fT4KICAgICAgICA8ZGl2IHN0eWxlPXt7cG9zaXRpb246InJlbGF0aXZlIixmbGV4OjEsbWluV2lkdGg6MTUwfX0+CiAgICAgICAgICA8c3BhbiBzdHlsZT17e3Bvc2l0aW9uOiJhYnNvbHV0ZSIsbGVmdDo4LHRvcDoiNTAlIix0cmFuc2Zvcm06InRyYW5zbGF0ZVkoLTUwJSkiLGNvbG9yOiIjYThhMjllIixmb250U2l6ZToxMn19PvCflI08L3NwYW4+CiAgICAgICAgICA8aW5wdXQgdmFsdWU9e2pzfSBvbkNoYW5nZT17ZT0+c2V0SnMoZS50YXJnZXQudmFsdWUpfSBwbGFjZWhvbGRlcj0iU2VhcmNoLi4uIiBzdHlsZT17ey4uLklOUCxwYWRkaW5nTGVmdDoyNixmb250U2l6ZToxMX19Lz4KICAgICAgICA8L2Rpdj4KICAgICAgICB7WyJBbGwiLCJQZW5kaW5nIiwiSW4gUHJvZ3Jlc3MiLCJDb21wbGV0ZWQiLCJEZWxpdmVyZWQiXS5tYXAoZj0+KAogICAgICAgICAgPGJ1dHRvbiBrZXk9e2Z9IG9uQ2xpY2s9eygpPT5zZXRKZihmKX0gc3R5bGU9e3twYWRkaW5nOiI1cHggOXB4Iixib3JkZXJSYWRpdXM6MjAsZm9udFNpemU6MTAsZm9udFdlaWdodDo3MDAsY3Vyc29yOiJwb2ludGVyIixib3JkZXI6amY9PT1mP2AxcHggc29saWQgJHtCLnByaX1gOiIxcHggc29saWQgI2U3ZTVlNCIsYmFja2dyb3VuZDpqZj09PWY/Qi5wcmlMOiIjZmZmIixjb2xvcjpqZj09PWY/Qi5wcmlEOiIjNzg3MTZjIn19PntmfTwvYnV0dG9uPgogICAgICAgICkpfQogICAgICA8L2Rpdj4KICAgICAgPGRpdiBzdHlsZT17e292ZXJmbG93WDoiYXV0byJ9fT4KICAgICAgICA8dGFibGUgc3R5bGU9e3t3aWR0aDoiMTAwJSIsYm9yZGVyQ29sbGFwc2U6ImNvbGxhcHNlIixmb250U2l6ZToxMn19PgogICAgICAgICAgPHRoZWFkPjx0ciBzdHlsZT17e2JvcmRlckJvdHRvbToiMnB4IHNvbGlkICNmNWY1ZjQifX0+CiAgICAgICAgICAgIHtbIiMiLCJDdXN0b21lciIsIlR5cGUiLCJEdWUiLC4uLihpc1N1YlN0YWZmP1tdOlsiQmFsYW5jZSJdKSwiU3RhdHVzIl0ubWFwKGg9Pjx0aCBrZXk9e2h9IHN0eWxlPXt7dGV4dEFsaWduOiJsZWZ0IixwYWRkaW5nOiIwIDlweCA3cHgiLGZvbnRTaXplOjksZm9udFdlaWdodDo4MDAsY29sb3I6IiNhOGEyOWUiLHRleHRUcmFuc2Zvcm06InVwcGVyY2FzZSIsbGV0dGVyU3BhY2luZzoiLjA2ZW0iLHdoaXRlU3BhY2U6Im5vd3JhcCJ9fT57aH08L3RoPil9CiAgICAgICAgICA8L3RyPjwvdGhlYWQ+CiAgICAgICAgICA8dGJvZHk+CiAgICAgICAgICAgIHtsb2FkaW5nP1sxLDIsMyw0XS5tYXAoaT0+PHRyIGtleT17aX0+PHRkIGNvbFNwYW49e2lzU3ViU3RhZmY/NTo2fSBzdHlsZT17e3BhZGRpbmc6IjlweCJ9fT48U2tlbCBoPXsxMn0vPjwvdGQ+PC90cj4pOgogICAgICAgICAgICBmai5sZW5ndGg9PT0wPzx0cj48dGQgY29sU3Bhbj17aXNTdWJTdGFmZj81OjZ9IHN0eWxlPXt7cGFkZGluZzoiMjhweCIsdGV4dEFsaWduOiJjZW50ZXIiLGNvbG9yOiIjYThhMjllIixmb250U2l6ZToxMn19Pntqb2JzLmxlbmd0aD09PTA/IlNlcnZlciBjb25uZWN0IOCwheCwr+Cwv+CwqCDgsKTgsLDgsY3gsLXgsL7gsKQgZGF0YSBsb2FkIOCwheCwteCxgeCwpOCxgeCwguCwpuCwvyI6Ik5vIG1hdGNoaW5nIGpvYnMifTwvdGQ+PC90cj46CiAgICAgICAgICAgIGZqLm1hcChqPT57Y29uc3Qgb3Y9ai5kdWVfZGF0ZSYmbmV3IERhdGUoai5kdWVfZGF0ZSk8bmV3IERhdGUoKSYmIVsiRGVsaXZlcmVkIiwiQ29tcGxldGVkIl0uaW5jbHVkZXMoai5zdGF0dXMpO3JldHVybigKICAgICAgICAgICAgICA8dHIga2V5PXtqLmlkfSBvbkNsaWNrPXsoKT0+c2V0RGV0YWlsSm9iKGopfSBzdHlsZT17e2JvcmRlckJvdHRvbToiMXB4IHNvbGlkICNmYWZhZjkiLGJhY2tncm91bmQ6b3Y/IiNmZmY3ZWQiOiJ0cmFuc3BhcmVudCIsY3Vyc29yOiJwb2ludGVyIn19CiAgICAgICAgICAgICAgICBvbk1vdXNlRW50ZXI9e2U9PmUuY3VycmVudFRhcmdldC5zdHlsZS5iYWNrZ3JvdW5kPW92PyIjZmVkN2FhNDAiOiIjZmFmYWY5In0KICAgICAgICAgICAgICAgIG9uTW91c2VMZWF2ZT17ZT0+ZS5jdXJyZW50VGFyZ2V0LnN0eWxlLmJhY2tncm91bmQ9b3Y/IiNmZmY3ZWQiOiJ0cmFuc3BhcmVudCJ9PgogICAgICAgICAgICAgICAgPHRkIHN0eWxlPXt7cGFkZGluZzoiOHB4IDlweCIsZm9udFdlaWdodDo4MDAsY29sb3I6Qi5wcmksZm9udFNpemU6MTF9fT4je2ouaWR9PC90ZD4KICAgICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjhweCA5cHgiLGZvbnRXZWlnaHQ6NjAwLGNvbG9yOiIjMWMxOTE3IixtYXhXaWR0aDoxMTAsb3ZlcmZsb3c6ImhpZGRlbiIsdGV4dE92ZXJmbG93OiJlbGxpcHNpcyIsd2hpdGVTcGFjZToibm93cmFwIn19PntqLmN1c3RvbWVyX25hbWV8fCLigJQifTwvdGQ+CiAgICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI4cHggOXB4Iixjb2xvcjoiIzU3NTM0ZSIsbWF4V2lkdGg6MTAwLG92ZXJmbG93OiJoaWRkZW4iLHRleHRPdmVyZmxvdzoiZWxsaXBzaXMiLHdoaXRlU3BhY2U6Im5vd3JhcCJ9fT57ai5qb2JfdHlwZX08L3RkPgogICAgICAgICAgICAgICAgPHRkIHN0eWxlPXt7cGFkZGluZzoiOHB4IDlweCIsY29sb3I6b3Y/IiNjMjQxMGMiOiIjNzg3MTZjIixmb250V2VpZ2h0Om92PzcwMDo0MDAsZm9udFNpemU6MTF9fT57b3Y/IuKaoCAiOiIifXtqLmR1ZV9kYXRlfHwi4oCUIn08L3RkPgogICAgICAgICAgICAgICAgeyFpc1N1YlN0YWZmJiY8dGQgc3R5bGU9e3twYWRkaW5nOiI4cHggOXB4Iixmb250V2VpZ2h0OjcwMCxjb2xvcjpqLmJhbGFuY2U+MD8iI2RjMjYyNiI6IiMxNmEzNGEiLGZvbnRTaXplOjExfX0+e2ouYmFsYW5jZT4wP2ZtdChqLmJhbGFuY2UpOiJQYWlkIOKckyJ9PC90ZD59CiAgICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI4cHggOXB4In19PjxCYWRnZSBzdGF0dXM9e2ouc3RhdHVzfS8+PC90ZD4KICAgICAgICAgICAgICA8L3RyPik7fSl9CiAgICAgICAgICA8L3Rib2R5PgogICAgICAgIDwvdGFibGU+CiAgICAgIDwvZGl2PgogICAgPC9kaXY+CiAgICB7ZGV0YWlsSm9iJiY8Sm9iRGV0YWlsTW9kYWwgam9iPXtkZXRhaWxKb2J9IHJvbGU9e3JvbGV9IG9uQ2xvc2U9eygpPT5zZXREZXRhaWxKb2IobnVsbCl9Lz59CiAgICAKICA8L1BnPjsKfQoKLyog4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQIENVU1RPTUVSUyDilZDilZDilZAgKi8KZnVuY3Rpb24gQ3VzdG9tZXJzKHthcGksdG9hc3R9KXsKICBjb25zdFtkYXRhLHNldERhdGFdPXVzZVN0YXRlKFtdKTtjb25zdFtsb2FkaW5nLHNldExvYWRpbmddPXVzZVN0YXRlKHRydWUpOwogIGNvbnN0W3NlYXJjaCxzZXRTZWFyY2hdPXVzZVN0YXRlKCIiKTtjb25zdFtwYWdlLHNldFBhZ2VdPXVzZVN0YXRlKDApOwogIGNvbnN0W21vZGFsLHNldE1vZGFsXT11c2VTdGF0ZShudWxsKTtjb25zdFtzYXZpbmcsc2V0U2F2aW5nXT11c2VTdGF0ZShmYWxzZSk7CiAgY29uc3RbaGlzdEN1c3Qsc2V0SGlzdEN1c3RdPXVzZVN0YXRlKG51bGwpOwogIGNvbnN0W2Zvcm0sc2V0Rm9ybV09dXNlU3RhdGUoe25hbWU6IiIsbW9iaWxlOiIiLGVtYWlsOiIiLGFkZHJlc3M6IiIsdGFnczoiIixnc3Rfbm86IiIscGFuX25vOiIifSk7CiAgY29uc3QgUEVSPTE1OwogIGNvbnN0IGxvYWQ9dXNlQ2FsbGJhY2soYXN5bmMoKT0+e3NldExvYWRpbmcodHJ1ZSk7dHJ5e3NldERhdGEoYXdhaXQgYXBpLmN1c3RvbWVycyhzZWFyY2gsMjAwKSk7fWNhdGNoKGUpe3RvYXN0KGUubWVzc2FnZSwiZXJyb3IiKTt9ZmluYWxseXtzZXRMb2FkaW5nKGZhbHNlKTt9O30sW2FwaSxzZWFyY2hdKTsKICB1c2VFZmZlY3QoKCk9Pntsb2FkKCk7fSxbbG9hZF0pO3VzZUVmZmVjdCgoKT0+c2V0UGFnZSgwKSxbc2VhcmNoXSk7CiAgY29uc3QgcGFnZWQ9ZGF0YS5zbGljZShwYWdlKlBFUiwocGFnZSsxKSpQRVIpOwogIGNvbnN0IHNhdmU9YXN5bmMoKT0+ewogICAgaWYoIWZvcm0ubmFtZXx8IWZvcm0ubW9iaWxlKXt0b2FzdCgiTmFtZSAmIE1vYmlsZSDgsIXgsLXgsLjgsLDgsIIiLCJlcnJvciIpO3JldHVybjt9CiAgICBzZXRTYXZpbmcodHJ1ZSk7CiAgICB0cnl7CiAgICAgIGlmKG1vZGFsPT09ImFkZCIpe2F3YWl0IGFwaS5hZGRDdXN0b21lcihmb3JtKTt0b2FzdChgJyR7Zm9ybS5uYW1lfScgYWRkZWQhYCk7fQogICAgICBlbHNle2F3YWl0IGFwaS51cGRhdGVDdXN0b21lcihtb2RhbC5pZCxmb3JtKTt0b2FzdCgiQ3VzdG9tZXIgdXBkYXRlZCEiKTt9CiAgICAgIHNldE1vZGFsKG51bGwpO2xvYWQoKTsKICAgIH1jYXRjaChlKXt0b2FzdChlLm1lc3NhZ2UsImVycm9yIik7fWZpbmFsbHl7c2V0U2F2aW5nKGZhbHNlKTt9CiAgfTsKICBjb25zdCBvcGVuQWRkPSgpPT57c2V0Rm9ybSh7bmFtZToiIixtb2JpbGU6IiIsZW1haWw6IiIsYWRkcmVzczoiIix0YWdzOiIiLGdzdF9ubzoiIixwYW5fbm86IiJ9KTtzZXRNb2RhbCgiYWRkIik7fTsKICBjb25zdCBvcGVuRWRpdD1jPT57c2V0Rm9ybSh7bmFtZTpjLm5hbWUsbW9iaWxlOmMubW9iaWxlLGVtYWlsOmMuZW1haWx8fCIiLGFkZHJlc3M6Yy5hZGRyZXNzfHwiIix0YWdzOmMudGFnc3x8IiIsZ3N0X25vOmMuZ3N0X25vfHwiIixwYW5fbm86Yy5wYW5fbm98fCIifSk7c2V0TW9kYWwoYyk7fTsKICByZXR1cm48UGc+CiAgICA8UGFnZUhkciB0aXRsZT0iQ3VzdG9tZXJzIiBzdWI9e2Ake2RhdGEubGVuZ3RofSB0b3RhbGB9IGFjdGlvbj17b3BlbkFkZH0gYWN0aW9uTGFiZWw9IkFkZCBDdXN0b21lciIvPgogICAgPGRpdiBzdHlsZT17e2JhY2tncm91bmQ6InZhcigtLWJnLWNhcmQpIixib3JkZXI6IjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpIixib3JkZXJSYWRpdXM6MTIscGFkZGluZzoiMTRweCAxNnB4In19PgogICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsZ2FwOjgsbWFyZ2luQm90dG9tOjEyfX0+CiAgICAgICAgPGRpdiBzdHlsZT17e3Bvc2l0aW9uOiJyZWxhdGl2ZSIsZmxleDoxfX0+CiAgICAgICAgICA8c3BhbiBzdHlsZT17e3Bvc2l0aW9uOiJhYnNvbHV0ZSIsbGVmdDo4LHRvcDoiNTAlIix0cmFuc2Zvcm06InRyYW5zbGF0ZVkoLTUwJSkiLGNvbG9yOiIjYThhMjllIixmb250U2l6ZToxMn19PvCflI08L3NwYW4+CiAgICAgICAgICA8aW5wdXQgdmFsdWU9e3NlYXJjaH0gb25DaGFuZ2U9e2U9PnNldFNlYXJjaChlLnRhcmdldC52YWx1ZSl9IHBsYWNlaG9sZGVyPSJTZWFyY2ggbmFtZSwgbW9iaWxlLCBlbWFpbC4uLiIgc3R5bGU9e3suLi5JTlAscGFkZGluZ0xlZnQ6MjZ9fS8+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGJ1dHRvbiBvbkNsaWNrPXtsb2FkfSBzdHlsZT17ey4uLkJUTigiZ2hvc3QiKSxwYWRkaW5nOiI5cHggMTJweCIsZm9udFNpemU6MTF9fT7ihrsgUmVmcmVzaDwvYnV0dG9uPgogICAgICA8L2Rpdj4KICAgICAgPGRpdiBzdHlsZT17e292ZXJmbG93WDoiYXV0byJ9fT4KICAgICAgICA8dGFibGUgc3R5bGU9e3t3aWR0aDoiMTAwJSIsYm9yZGVyQ29sbGFwc2U6ImNvbGxhcHNlIixmb250U2l6ZToxMn19PgogICAgICAgICAgPHRoZWFkPjx0ciBzdHlsZT17e2JvcmRlckJvdHRvbToiMnB4IHNvbGlkICNmNWY1ZjQifX0+CiAgICAgICAgICAgIHtbIiMiLCJOYW1lIiwiTW9iaWxlIiwiRW1haWwiLCJUYWdzIiwiR1NUIiwiIl0ubWFwKGg9Pjx0aCBrZXk9e2h9IHN0eWxlPXt7dGV4dEFsaWduOiJsZWZ0IixwYWRkaW5nOiIwIDlweCA4cHgiLGZvbnRTaXplOjksZm9udFdlaWdodDo4MDAsY29sb3I6IiNhOGEyOWUiLHRleHRUcmFuc2Zvcm06InVwcGVyY2FzZSIsbGV0dGVyU3BhY2luZzoiLjA2ZW0iLHdoaXRlU3BhY2U6Im5vd3JhcCJ9fT57aH08L3RoPil9CiAgICAgICAgICA8L3RyPjwvdGhlYWQ+CiAgICAgICAgICA8dGJvZHk+CiAgICAgICAgICAgIHtsb2FkaW5nP1sxLDIsMyw0LDVdLm1hcChpPT48dHIga2V5PXtpfT48dGQgY29sU3Bhbj17N30gc3R5bGU9e3twYWRkaW5nOiIxMHB4In19PjxTa2VsIGg9ezEyfS8+PC90ZD48L3RyPik6CiAgICAgICAgICAgIHBhZ2VkLmxlbmd0aD09PTA/PHRyPjx0ZCBjb2xTcGFuPXs3fSBzdHlsZT17e3BhZGRpbmc6IjI4cHgiLHRleHRBbGlnbjoiY2VudGVyIixjb2xvcjoiI2E4YTI5ZSIsZm9udFNpemU6MTJ9fT57c2VhcmNoPyJObyByZXN1bHRzIjoiTm8gY3VzdG9tZXJzIHlldCDigJQgQWRkIG9uZSEifTwvdGQ+PC90cj46CiAgICAgICAgICAgIHBhZ2VkLm1hcChjPT48dHIga2V5PXtjLmlkfSBzdHlsZT17e2JvcmRlckJvdHRvbToiMXB4IHNvbGlkICNmYWZhZjkifX0gb25Nb3VzZUVudGVyPXtlPT5lLmN1cnJlbnRUYXJnZXQuc3R5bGUuYmFja2dyb3VuZD0iI2ZhZmFmOSJ9IG9uTW91c2VMZWF2ZT17ZT0+ZS5jdXJyZW50VGFyZ2V0LnN0eWxlLmJhY2tncm91bmQ9InRyYW5zcGFyZW50In0+CiAgICAgICAgICAgICAgPHRkIHN0eWxlPXt7cGFkZGluZzoiOXB4Iixjb2xvcjoiI2E4YTI5ZSIsZm9udFNpemU6MTB9fT4je2MuaWR9PC90ZD4KICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI5cHgiLGZvbnRXZWlnaHQ6NzAwLGNvbG9yOiIjMWMxOTE3In19PntjLm5hbWV9PC90ZD4KICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI5cHgiLGNvbG9yOiIjNTc1MzRlIixmb250RmFtaWx5OiJtb25vc3BhY2UiLGZvbnRTaXplOjExfX0+e2MubW9iaWxlfTwvdGQ+CiAgICAgICAgICAgICAgPHRkIHN0eWxlPXt7cGFkZGluZzoiOXB4Iixjb2xvcjoiIzc4NzE2YyIsbWF4V2lkdGg6MTMwLG92ZXJmbG93OiJoaWRkZW4iLHRleHRPdmVyZmxvdzoiZWxsaXBzaXMiLHdoaXRlU3BhY2U6Im5vd3JhcCJ9fT57Yy5lbWFpbHx8IuKAlCJ9PC90ZD4KICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI5cHgifX0+e2MudGFncz9jLnRhZ3Muc3BsaXQoIiwiKS5zbGljZSgwLDIpLm1hcCgodCxpKT0+PHNwYW4ga2V5PXtpfSBzdHlsZT17e2ZvbnRTaXplOjksZm9udFdlaWdodDo3MDAscGFkZGluZzoiMnB4IDZweCIsYm9yZGVyUmFkaXVzOjIwLGJhY2tncm91bmQ6Qi5wcmlMLGNvbG9yOkIucHJpRCxib3JkZXI6YDFweCBzb2xpZCAke0IucHJpTX1gLG1hcmdpblJpZ2h0OjN9fT57dC50cmltKCl9PC9zcGFuPik6IuKAlCJ9PC90ZD4KICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI5cHgiLGNvbG9yOiIjNzg3MTZjIixmb250U2l6ZToxMX19PntjLmdzdF9ub3x8IuKAlCJ9PC90ZD4KICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI5cHgiLGRpc3BsYXk6ImZsZXgiLGdhcDo1fX0+CiAgICAgICAgICAgICAgICA8YnV0dG9uIG9uQ2xpY2s9eygpPT5vcGVuRWRpdChjKX0gc3R5bGU9e3tmb250U2l6ZToxMCxjb2xvcjpCLnByaSxmb250V2VpZ2h0OjcwMCxiYWNrZ3JvdW5kOiJub25lIixib3JkZXI6YDFweCBzb2xpZCAke0IucHJpTX1gLGJvcmRlclJhZGl1czo1LHBhZGRpbmc6IjNweCA4cHgiLGN1cnNvcjoicG9pbnRlciJ9fT5FZGl0PC9idXR0b24+CiAgICAgICAgICAgICAgICA8YnV0dG9uIG9uQ2xpY2s9eygpPT5zZXRIaXN0Q3VzdChjKX0gc3R5bGU9e3tmb250U2l6ZToxMCxjb2xvcjoiIzI1NjNlYiIsZm9udFdlaWdodDo3MDAsYmFja2dyb3VuZDoibm9uZSIsYm9yZGVyOiIxcHggc29saWQgI2JmZGJmZSIsYm9yZGVyUmFkaXVzOjUscGFkZGluZzoiM3B4IDhweCIsY3Vyc29yOiJwb2ludGVyIn19PvCfk4sgSm9iczwvYnV0dG9uPgogICAgICAgICAgICAgIDwvdGQ+CiAgICAgICAgICAgIDwvdHI+KX0KICAgICAgICAgIDwvdGJvZHk+CiAgICAgICAgPC90YWJsZT4KICAgICAgPC9kaXY+CiAgICAgIDxQYWdlciBwYWdlPXtwYWdlfSB0b3RhbD17ZGF0YS5sZW5ndGh9IHBlcj17UEVSfSBvbkNoYW5nZT17c2V0UGFnZX0vPgogICAgPC9kaXY+CiAgICB7bW9kYWwmJjxNb2RhbCB0aXRsZT17bW9kYWw9PT0iYWRkIj8iQWRkIEN1c3RvbWVyIjpgRWRpdCDigJQgJHttb2RhbC5uYW1lfWB9IG9uQ2xvc2U9eygpPT5zZXRNb2RhbChudWxsKX0+CiAgICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJncmlkIixncmlkVGVtcGxhdGVDb2x1bW5zOiIxZnIgMWZyIixnYXA6IjAgMTNweCJ9fT4KICAgICAgICA8RmxkIGxhYmVsPSJOYW1lIiByZXE+PGlucHV0IHZhbHVlPXtmb3JtLm5hbWV9IG9uQ2hhbmdlPXtlPT5zZXRGb3JtKGY9Pih7Li4uZixuYW1lOmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17SU5QfSBwbGFjZWhvbGRlcj0iRnVsbCBuYW1lIi8+PC9GbGQ+CiAgICAgICAgPEZsZCBsYWJlbD0iTW9iaWxlIiByZXE+PGlucHV0IHZhbHVlPXtmb3JtLm1vYmlsZX0gb25DaGFuZ2U9e2U9PnNldEZvcm0oZj0+KHsuLi5mLG1vYmlsZTplLnRhcmdldC52YWx1ZX0pKX0gc3R5bGU9e0lOUH0gcGxhY2Vob2xkZXI9IjEwLWRpZ2l0IG1vYmlsZSIvPjwvRmxkPgogICAgICAgIDxGbGQgbGFiZWw9IkVtYWlsIj48aW5wdXQgdmFsdWU9e2Zvcm0uZW1haWx9IG9uQ2hhbmdlPXtlPT5zZXRGb3JtKGY9Pih7Li4uZixlbWFpbDplLnRhcmdldC52YWx1ZX0pKX0gc3R5bGU9e0lOUH0gcGxhY2Vob2xkZXI9ImVtYWlsQGV4YW1wbGUuY29tIi8+PC9GbGQ+CiAgICAgICAgPEZsZCBsYWJlbD0iR1NUIE5vIj48aW5wdXQgdmFsdWU9e2Zvcm0uZ3N0X25vfSBvbkNoYW5nZT17ZT0+c2V0Rm9ybShmPT4oey4uLmYsZ3N0X25vOmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17SU5QfSBwbGFjZWhvbGRlcj0iMjJBQUFBQTAwMDBBMVo1Ii8+PC9GbGQ+CiAgICAgICAgPEZsZCBsYWJlbD0iUEFOIE5vIj48aW5wdXQgdmFsdWU9e2Zvcm0ucGFuX25vfSBvbkNoYW5nZT17ZT0+c2V0Rm9ybShmPT4oey4uLmYscGFuX25vOmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17SU5QfS8+PC9GbGQ+CiAgICAgICAgPEZsZCBsYWJlbD0iVGFncyI+PGlucHV0IHZhbHVlPXtmb3JtLnRhZ3N9IG9uQ2hhbmdlPXtlPT5zZXRGb3JtKGY9Pih7Li4uZix0YWdzOmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17SU5QfSBwbGFjZWhvbGRlcj0iVklQLCBSZWd1bGFyIi8+PC9GbGQ+CiAgICAgIDwvZGl2PgogICAgICA8RmxkIGxhYmVsPSJBZGRyZXNzIj48dGV4dGFyZWEgdmFsdWU9e2Zvcm0uYWRkcmVzc30gb25DaGFuZ2U9e2U9PnNldEZvcm0oZj0+KHsuLi5mLGFkZHJlc3M6ZS50YXJnZXQudmFsdWV9KSl9IHN0eWxlPXt7Li4uSU5QLG1pbkhlaWdodDo1NCxyZXNpemU6InZlcnRpY2FsIn19Lz48L0ZsZD4KICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGdhcDo4LGp1c3RpZnlDb250ZW50OiJmbGV4LWVuZCJ9fT48YnV0dG9uIG9uQ2xpY2s9eygpPT5zZXRNb2RhbChudWxsKX0gc3R5bGU9e0JUTigiZ2hvc3QiKX0+Q2FuY2VsPC9idXR0b24+PGJ1dHRvbiBvbkNsaWNrPXtzYXZlfSBkaXNhYmxlZD17c2F2aW5nfSBzdHlsZT17QlROKCl9PntzYXZpbmc/PFNwaW4vPjptb2RhbD09PSJhZGQiPyJBZGQgQ3VzdG9tZXIiOiJTYXZlIENoYW5nZXMifTwvYnV0dG9uPjwvZGl2PgogICAgPC9Nb2RhbD59CiAgICB7aGlzdEN1c3QmJjxDdXN0b21lckhpc3RvcnlNb2RhbCBjdXN0b21lcj17aGlzdEN1c3R9IGFwaT17YXBpfSBvbkNsb3NlPXsoKT0+c2V0SGlzdEN1c3QobnVsbCl9Lz59CiAgPC9QZz47Cn0KCi8qIOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkCBKT0JTIOKVkOKVkOKVkCAqLwpmdW5jdGlvbiBKb2JzKHthcGksdG9hc3QsdXNlcixyb2xlfSl7CiAgY29uc3Rbam9icyxzZXRKb2JzXT11c2VTdGF0ZShbXSk7Y29uc3RbY3VzdHMsc2V0Q3VzdHNdPXVzZVN0YXRlKFtdKTtjb25zdFtqdHMsc2V0SnRzXT11c2VTdGF0ZShbXSk7CiAgY29uc3Rbc3RhZmZVc2VycyxzZXRTdGFmZlVzZXJzXT11c2VTdGF0ZShbXSk7CiAgY29uc3RbbG9hZGluZyxzZXRMb2FkaW5nXT11c2VTdGF0ZSh0cnVlKTtjb25zdFtmaWx0ZXIsc2V0RmlsdGVyXT11c2VTdGF0ZSgiQWxsIik7Y29uc3Rbc2VhcmNoLHNldFNlYXJjaF09dXNlU3RhdGUoIiIpOwogIGNvbnN0W3BhZ2Usc2V0UGFnZV09dXNlU3RhdGUoMCk7Y29uc3RbbW9kYWwsc2V0TW9kYWxdPXVzZVN0YXRlKG51bGwpO2NvbnN0W3N0TW9kYWwsc2V0U3RNb2RhbF09dXNlU3RhdGUobnVsbCk7Y29uc3RbbWF0TW9kYWwsc2V0TWF0TW9kYWxdPXVzZVN0YXRlKG51bGwpOwogIGNvbnN0W3NhdmluZyxzZXRTYXZpbmddPXVzZVN0YXRlKGZhbHNlKTtjb25zdFtkZXRhaWxKb2Isc2V0RGV0YWlsSm9iXT11c2VTdGF0ZShudWxsKTsKICBjb25zdFtzZWxlY3RlZElkcyxzZXRTZWxlY3RlZElkc109dXNlU3RhdGUobmV3IFNldCgpKTtjb25zdFtidWxrU3RhdHVzLHNldEJ1bGtTdGF0dXNdPXVzZVN0YXRlKCIiKTtjb25zdFtidWxrU2F2aW5nLHNldEJ1bGtTYXZpbmddPXVzZVN0YXRlKGZhbHNlKTsKICBjb25zdCBpc1N1YlN0YWZmPXJvbGU9PT0ic3ViX3N0YWZmIjtjb25zdFtmb3JtLHNldEZvcm1dPXVzZVN0YXRlKHtjdXN0b21lcl9pZDoiIixqb2JfdHlwZToiIixkZXNjcmlwdGlvbjoiIixzaXplOiIiLGluaXRpYWxfcHJpY2U6IiIsZGlzY291bnRfYW1vdW50OiIwIixhZHZhbmNlMToiMCIsYXNzaWduZWRfdG86IiIscHJpb3JpdHk6Im5vcm1hbCIsZHVlX2RhdGU6IiIsbm90ZXM6IiJ9KTsKICBjb25zdCBQRVI9MTU7CiAgY29uc3QgbG9hZD11c2VDYWxsYmFjayhhc3luYygpPT57c2V0TG9hZGluZyh0cnVlKTt0cnl7Y29uc3RbaixjLGp0LHN1XT1hd2FpdCBQcm9taXNlLmFsbChbYXBpLmpvYnMoImxpbWl0PTIwMCIpLGFwaS5jdXN0b21lcnMoIiIsMjAwKSxhcGkuam9iVHlwZXMoKSxhcGkuc3RhZmZMaXN0KCkuY2F0Y2goKCk9PltdKV0pO3NldEpvYnMoaik7c2V0Q3VzdHMoYyk7c2V0SnRzKGp0KTtzZXRTdGFmZlVzZXJzKHN1KTt9Y2F0Y2goZSl7dG9hc3QoZS5tZXNzYWdlLCJlcnJvciIpO31maW5hbGx5e3NldExvYWRpbmcoZmFsc2UpO307fSxbYXBpXSk7CiAgdXNlRWZmZWN0KCgpPT57bG9hZCgpO30sW2xvYWRdKTt1c2VFZmZlY3QoKCk9PnNldFBhZ2UoMCksW2ZpbHRlcixzZWFyY2hdKTsKICBjb25zdCBteUpvYnM9cm9sZT09PSJhZG1pbiI/am9iczpqb2JzLmZpbHRlcihqPT57CiAgICBjb25zdCB1aWQ9U3RyaW5nKHVzZXI/LmlkfHwwKTsKICAgIGNvbnN0IHVuYW1lPXVzZXI/LnVzZXJuYW1lfHwiIjsKICAgIHJldHVybiBTdHJpbmcoai5hc3NpZ25lZF9zdGFmZl9pZCk9PT11aWR8fAogICAgICAgICAgIFN0cmluZyhqLmFzc2lnbmVkX3RvX2lkKT09PXVpZHx8CiAgICAgICAgICAgU3RyaW5nKGouYXNzaWduZWRfdG8pPT09dWlkfHwKICAgICAgICAgICAodW5hbWUmJmouYXNzaWduZWRfc3RhZmZfbmFtZT09PXVuYW1lKXx8CiAgICAgICAgICAgKHVuYW1lJiZqLmFzc2lnbmVkX3RvX3VzZXJuYW1lPT09dW5hbWUpOwogIH0pOwogIGNvbnN0IGNvdW50cz1bIkFsbCIsIlBlbmRpbmciLCJJbiBQcm9ncmVzcyIsIkNvbXBsZXRlZCIsIkRlbGl2ZXJlZCJdLnJlZHVjZSgoYSxzKT0+e2Fbc109cz09PSJBbGwiP215Sm9icy5sZW5ndGg6bXlKb2JzLmZpbHRlcihqPT5qLnN0YXR1cz09PXMpLmxlbmd0aDtyZXR1cm4gYTt9LHt9KTsKICBjb25zdCBmaj1teUpvYnMuZmlsdGVyKGo9PihmaWx0ZXI9PT0iQWxsInx8ai5zdGF0dXM9PT1maWx0ZXIpJiYoIXNlYXJjaHx8KGouY3VzdG9tZXJfbmFtZXx8IiIpLnRvTG93ZXJDYXNlKCkuaW5jbHVkZXMoc2VhcmNoLnRvTG93ZXJDYXNlKCkpfHxTdHJpbmcoai5pZCkuaW5jbHVkZXMoc2VhcmNoKSkpOwogIGNvbnN0IHBhZ2VkPWZqLnNsaWNlKHBhZ2UqUEVSLChwYWdlKzEpKlBFUik7CiAgY29uc3QgZnA9TnVtYmVyKGZvcm0uaW5pdGlhbF9wcmljZXx8MCktTnVtYmVyKGZvcm0uZGlzY291bnRfYW1vdW50fHwwKTsKICBjb25zdCBiYWw9ZnAtTnVtYmVyKGZvcm0uYWR2YW5jZTF8fDApOwogIGNvbnN0IHNhdmVKb2I9YXN5bmMoKT0+ewogICAgaWYoIWZvcm0uY3VzdG9tZXJfaWR8fCFmb3JtLmpvYl90eXBlfHwhZm9ybS5pbml0aWFsX3ByaWNlKXt0b2FzdCgiQ3VzdG9tZXIsIFR5cGUgJiBQcmljZSDgsIXgsLXgsLjgsLDgsIIiLCJlcnJvciIpO3JldHVybjt9CiAgICBzZXRTYXZpbmcodHJ1ZSk7CiAgICB0cnl7YXdhaXQgYXBpLmFkZEpvYih7Li4uZm9ybSxjdXN0b21lcl9pZDpOdW1iZXIoZm9ybS5jdXN0b21lcl9pZCksaW5pdGlhbF9wcmljZTpOdW1iZXIoZm9ybS5pbml0aWFsX3ByaWNlKSxkaXNjb3VudF9hbW91bnQ6TnVtYmVyKGZvcm0uZGlzY291bnRfYW1vdW50fHwwKSxhZHZhbmNlMTpOdW1iZXIoZm9ybS5hZHZhbmNlMXx8MCksYXNzaWduZWRfdG86Zm9ybS5hc3NpZ25lZF90bz9OdW1iZXIoZm9ybS5hc3NpZ25lZF90byk6bnVsbCxwcmlvcml0eTpmb3JtLnByaW9yaXR5fHwibm9ybWFsIn0pO3RvYXN0KCJKb2IgY3JlYXRlZCEiKTtzZXRNb2RhbChudWxsKTtsb2FkKCk7fQogICAgY2F0Y2goZSl7dG9hc3QoZS5tZXNzYWdlLCJlcnJvciIpO31maW5hbGx5e3NldFNhdmluZyhmYWxzZSk7fQogIH07CiAgcmV0dXJuPFBnPgogICAgPFBhZ2VIZHIgdGl0bGU9IkpvYnMiIHN1Yj17YCR7bXlKb2JzLmxlbmd0aH0gdG90YWwgwrcgJHsoY291bnRzWyJQZW5kaW5nIl18fDApKyhjb3VudHNbIkluIFByb2dyZXNzIl18fDApfSBhY3RpdmVgfSBhY3Rpb249e2lzU3ViU3RhZmY/bnVsbDooKT0+e3NldEZvcm0oe2N1c3RvbWVyX2lkOiIiLGpvYl90eXBlOiIiLGRlc2NyaXB0aW9uOiIiLHNpemU6IiIsaW5pdGlhbF9wcmljZToiIixkaXNjb3VudF9hbW91bnQ6IjAiLGFkdmFuY2UxOiIwIixhc3NpZ25lZF90bzoiIixwcmlvcml0eToibm9ybWFsIixkdWVfZGF0ZToiIixub3RlczoiIn0pO3NldE1vZGFsKCJhZGQiKTt9fSBhY3Rpb25MYWJlbD0iTmV3IEpvYiIvPgogICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGdhcDo1LG1hcmdpbkJvdHRvbToxMixmbGV4V3JhcDoid3JhcCJ9fT4KICAgICAge1siQWxsIiwiUGVuZGluZyIsIkluIFByb2dyZXNzIiwiQ29tcGxldGVkIiwiRGVsaXZlcmVkIl0ubWFwKHM9PjxidXR0b24ga2V5PXtzfSBvbkNsaWNrPXsoKT0+c2V0RmlsdGVyKHMpfSBzdHlsZT17e3BhZGRpbmc6IjVweCAxMXB4Iixib3JkZXJSYWRpdXM6MjAsZm9udFNpemU6MTAsZm9udFdlaWdodDo3MDAsY3Vyc29yOiJwb2ludGVyIixib3JkZXI6ZmlsdGVyPT09cz9gMXB4IHNvbGlkICR7Qi5wcml9YDoiMXB4IHNvbGlkICNlN2U1ZTQiLGJhY2tncm91bmQ6ZmlsdGVyPT09cz9CLnByaUw6IiNmZmYiLGNvbG9yOmZpbHRlcj09PXM/Qi5wcmlEOiIjNzg3MTZjIn19PntzfSAoe2NvdW50c1tzXXx8MH0pPC9idXR0b24+KX0KICAgIDwvZGl2PgogICAgPGRpdiBzdHlsZT17e2JhY2tncm91bmQ6InZhcigtLWJnLWNhcmQpIixib3JkZXI6IjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpIixib3JkZXJSYWRpdXM6MTIscGFkZGluZzoiMTRweCAxNnB4In19PgogICAgICB7LyogU2VhcmNoICsgRXhwb3J0ICovfQogICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsZ2FwOjgsbWFyZ2luQm90dG9tOjgsYWxpZ25JdGVtczoiY2VudGVyIn19PgogICAgICAgIDxkaXYgc3R5bGU9e3twb3NpdGlvbjoicmVsYXRpdmUiLGZsZXg6MSxtYXhXaWR0aDozMjB9fT4KICAgICAgICAgIDxzcGFuIHN0eWxlPXt7cG9zaXRpb246ImFic29sdXRlIixsZWZ0OjgsdG9wOiI1MCUiLHRyYW5zZm9ybToidHJhbnNsYXRlWSgtNTAlKSIsY29sb3I6IiNhOGEyOWUiLGZvbnRTaXplOjEyfX0+8J+UjTwvc3Bhbj4KICAgICAgICAgIDxpbnB1dCB2YWx1ZT17c2VhcmNofSBvbkNoYW5nZT17ZT0+e3NldFNlYXJjaChlLnRhcmdldC52YWx1ZSk7c2V0UGFnZSgwKTt9fSBwbGFjZWhvbGRlcj0iQ3VzdG9tZXIsIHR5cGUsIElELi4uIiBzdHlsZT17ey4uLklOUCxwYWRkaW5nTGVmdDoyNn19Lz4KICAgICAgICA8L2Rpdj4KICAgICAgPC9kaXY+CiAgICAgIHsvKiBCdWxrIGFjdGlvbnMgYmFyICovfQogICAgICB7c2VsZWN0ZWRJZHMuc2l6ZT4wJiY8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsZ2FwOjgsbWFyZ2luQm90dG9tOjgsYmFja2dyb3VuZDoiI2ZmZjdlZCIsYm9yZGVyOiIxcHggc29saWQgI2ZlZDdhYSIsYm9yZGVyUmFkaXVzOjgscGFkZGluZzoiOHB4IDEycHgiLGFsaWduSXRlbXM6ImNlbnRlciIsZmxleFdyYXA6IndyYXAifX0+CiAgICAgICAgPHNwYW4gc3R5bGU9e3tmb250U2l6ZToxMSxmb250V2VpZ2h0OjcwMCxjb2xvcjoiIzkyNDAwZSJ9fT57c2VsZWN0ZWRJZHMuc2l6ZX0gc2VsZWN0ZWQ8L3NwYW4+CiAgICAgICAgPHNlbGVjdCB2YWx1ZT17YnVsa1N0YXR1c30gb25DaGFuZ2U9e2U9PnNldEJ1bGtTdGF0dXMoZS50YXJnZXQudmFsdWUpfSBzdHlsZT17ey4uLlNFTCx3aWR0aDoiYXV0byIsZm9udFNpemU6MTEscGFkZGluZzoiNXB4IDhweCJ9fT4KICAgICAgICAgIDxvcHRpb24gdmFsdWU9IiI+U3RhdHVzIOCwruCwvuCwsOCxjeCwmuCxgS4uLjwvb3B0aW9uPgogICAgICAgICAge1siUGVuZGluZyIsIkluIFByb2dyZXNzIiwiQ29tcGxldGVkIiwiRGVsaXZlcmVkIl0ubWFwKHM9PjxvcHRpb24ga2V5PXtzfSB2YWx1ZT17c30+e3N9PC9vcHRpb24+KX0KICAgICAgICA8L3NlbGVjdD4KICAgICAgICA8YnV0dG9uIGRpc2FibGVkPXshYnVsa1N0YXR1c3x8YnVsa1NhdmluZ30gb25DbGljaz17YXN5bmMoKT0+e2lmKCFidWxrU3RhdHVzKXJldHVybjtzZXRCdWxrU2F2aW5nKHRydWUpO3RyeXthd2FpdCBhcGkuYnVsa1VwZGF0ZVN0YXR1cyhbLi4uc2VsZWN0ZWRJZHNdLGJ1bGtTdGF0dXMpO3RvYXN0KGAke3NlbGVjdGVkSWRzLnNpemV9IGpvYnMgdXBkYXRlZCFgKTtzZXRTZWxlY3RlZElkcyhuZXcgU2V0KCkpO3NldEJ1bGtTdGF0dXMoIiIpO2xvYWQoKTt9Y2F0Y2goZSl7dG9hc3QoZS5tZXNzYWdlLCJlcnJvciIpO31maW5hbGx5e3NldEJ1bGtTYXZpbmcoZmFsc2UpO319fSBzdHlsZT17ey4uLkJUTigpLGZvbnRTaXplOjExLHBhZGRpbmc6IjVweCAxMnB4In19PntidWxrU2F2aW5nPzxTcGluLz46IuKckyBBcHBseSJ9PC9idXR0b24+CiAgICAgICAgPGJ1dHRvbiBvbkNsaWNrPXsoKT0+c2V0U2VsZWN0ZWRJZHMobmV3IFNldCgpKX0gc3R5bGU9e3suLi5CVE4oImdob3N0IiksZm9udFNpemU6MTEscGFkZGluZzoiNXB4IDEwcHgifX0+4pyVIENsZWFyPC9idXR0b24+CiAgICAgIDwvZGl2Pn0KICAgICAgPGRpdiBzdHlsZT17e292ZXJmbG93WDoiYXV0byIsV2Via2l0T3ZlcmZsb3dTY3JvbGxpbmc6InRvdWNoIn19PgogICAgICAgIDx0YWJsZSBzdHlsZT17e3dpZHRoOiIxMDAlIixib3JkZXJDb2xsYXBzZToiY29sbGFwc2UiLGZvbnRTaXplOjEyLG1pbldpZHRoOndpbmRvdy5pbm5lcldpZHRoPD03Njg/NjAwOiJhdXRvIn19PgogICAgICAgICAgPHRoZWFkPjx0ciBzdHlsZT17e2JvcmRlckJvdHRvbToiMnB4IHNvbGlkICNmNWY1ZjQifX0+CiAgICAgICAgICAgIDx0aCBzdHlsZT17e3BhZGRpbmc6IjAgNnB4IDdweCIsd2lkdGg6Mjh9fT48aW5wdXQgdHlwZT0iY2hlY2tib3giIGNoZWNrZWQ9e3NlbGVjdGVkSWRzLnNpemU+MCYmcGFnZWQuZXZlcnkoaj0+c2VsZWN0ZWRJZHMuaGFzKGouaWQpKX0gb25DaGFuZ2U9e2U9Pntjb25zdCBzPW5ldyBTZXQoc2VsZWN0ZWRJZHMpO3BhZ2VkLmZvckVhY2goaj0+ZS50YXJnZXQuY2hlY2tlZD9zLmFkZChqLmlkKTpzLmRlbGV0ZShqLmlkKSk7c2V0U2VsZWN0ZWRJZHMocyk7fX0vPjwvdGg+CiAgICAgICAgICAgIHtbIiMiLCJDdXN0b21lciIsIlR5cGUiLCJTaXplIiwiUHJpb3JpdHkiLC4uLihpc1N1YlN0YWZmP1tdOlsiUHJpY2UiLCJCYWxhbmNlIl0pLCJEdWUiLCJTdGF0dXMiLCJBY3Rpb24iLCJNYXRlcmlhbCIsLi4uKHJvbGU9PT0iYWRtaW4ifHxyb2xlPT09InN0YWZmIj9bIldBIl06W10pXS5tYXAoaD0+PHRoIGtleT17aH0gc3R5bGU9e3t0ZXh0QWxpZ246ImxlZnQiLHBhZGRpbmc6IjAgOXB4IDdweCIsZm9udFNpemU6OSxmb250V2VpZ2h0OjgwMCxjb2xvcjoiI2E4YTI5ZSIsdGV4dFRyYW5zZm9ybToidXBwZXJjYXNlIixsZXR0ZXJTcGFjaW5nOiIuMDZlbSIsd2hpdGVTcGFjZToibm93cmFwIn19PntofTwvdGg+KX0KICAgICAgICAgIDwvdHI+PC90aGVhZD4KICAgICAgICAgIDx0Ym9keT4KICAgICAgICAgICAge2xvYWRpbmc/WzEsMiwzLDQsNV0ubWFwKGk9Pjx0ciBrZXk9e2l9Pjx0ZCBjb2xTcGFuPXsyMH0gc3R5bGU9e3twYWRkaW5nOiIxMHB4In19PjxTa2VsIGg9ezEyfS8+PC90ZD48L3RyPik6CiAgICAgICAgICAgIHBhZ2VkLmxlbmd0aD09PTA/PHRyPjx0ZCBjb2xTcGFuPXsyMH0gc3R5bGU9e3twYWRkaW5nOiIyOHB4Iix0ZXh0QWxpZ246ImNlbnRlciIsY29sb3I6IiNhOGEyOWUiLGZvbnRTaXplOjEyfX0+Tm8gam9icyBtYXRjaCBmaWx0ZXIuPC90ZD48L3RyPjoKICAgICAgICAgICAgcGFnZWQubWFwKGo9Pntjb25zdCBvdj1qLmR1ZV9kYXRlJiZuZXcgRGF0ZShqLmR1ZV9kYXRlKTxuZXcgRGF0ZSgpJiYhWyJEZWxpdmVyZWQiLCJDb21wbGV0ZWQiXS5pbmNsdWRlcyhqLnN0YXR1cyk7cmV0dXJuKAogICAgICAgICAgICAgIDx0ciBrZXk9e2ouaWR9IHN0eWxlPXt7Ym9yZGVyQm90dG9tOiIxcHggc29saWQgI2ZhZmFmOSIsYmFja2dyb3VuZDpvdj8iI2ZmZjdlZCI6c2VsZWN0ZWRJZHMuaGFzKGouaWQpPyIjZmZmN2VkIjoidHJhbnNwYXJlbnQiLGN1cnNvcjoicG9pbnRlciJ9fQogICAgICAgICAgICAgICAgb25Nb3VzZUVudGVyPXtlPT5lLmN1cnJlbnRUYXJnZXQuc3R5bGUuYmFja2dyb3VuZD1vdj8iI2ZlZDdhYTQwIjpzZWxlY3RlZElkcy5oYXMoai5pZCk/IiNmZmY3ZWQiOiIjZmFmYWY5In0KICAgICAgICAgICAgICAgIG9uTW91c2VMZWF2ZT17ZT0+ZS5jdXJyZW50VGFyZ2V0LnN0eWxlLmJhY2tncm91bmQ9b3Y/IiNmZmY3ZWQiOnNlbGVjdGVkSWRzLmhhcyhqLmlkKT8iI2ZmZjdlZCI6InRyYW5zcGFyZW50In0+CiAgICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI5cHggNnB4In19IG9uQ2xpY2s9e2U9PmUuc3RvcFByb3BhZ2F0aW9uKCl9PjxpbnB1dCB0eXBlPSJjaGVja2JveCIgY2hlY2tlZD17c2VsZWN0ZWRJZHMuaGFzKGouaWQpfSBvbkNoYW5nZT17ZT0+e2NvbnN0IHM9bmV3IFNldChzZWxlY3RlZElkcyk7ZS50YXJnZXQuY2hlY2tlZD9zLmFkZChqLmlkKTpzLmRlbGV0ZShqLmlkKTtzZXRTZWxlY3RlZElkcyhzKTt9fS8+PC90ZD4KICAgICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCIsZm9udFdlaWdodDo4MDAsY29sb3I6Qi5wcmksZm9udFNpemU6MTF9fSBvbkNsaWNrPXsoKT0+c2V0RGV0YWlsSm9iKGopfT4je2ouaWR9PC90ZD4KICAgICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCIsZm9udFdlaWdodDo2MDAsY29sb3I6IiMxYzE5MTciLG1heFdpZHRoOjExMCxvdmVyZmxvdzoiaGlkZGVuIix0ZXh0T3ZlcmZsb3c6ImVsbGlwc2lzIix3aGl0ZVNwYWNlOiJub3dyYXAifX0gb25DbGljaz17KCk9PnNldERldGFpbEpvYihqKX0+e2ouY3VzdG9tZXJfbmFtZXx8IuKAlCJ9PC90ZD4KICAgICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCIsY29sb3I6IiM1NzUzNGUiLG1heFdpZHRoOjkwLG92ZXJmbG93OiJoaWRkZW4iLHRleHRPdmVyZmxvdzoiZWxsaXBzaXMiLHdoaXRlU3BhY2U6Im5vd3JhcCJ9fSBvbkNsaWNrPXsoKT0+c2V0RGV0YWlsSm9iKGopfT57ai5qb2JfdHlwZX08L3RkPgogICAgICAgICAgICAgICAgPHRkIHN0eWxlPXt7cGFkZGluZzoiOXB4Iixjb2xvcjoiIzc4NzE2YyIsZm9udFNpemU6MTF9fSBvbkNsaWNrPXsoKT0+c2V0RGV0YWlsSm9iKGopfT57ai5zaXplfHwi4oCUIn08L3RkPgogICAgICAgICAgICAgICAgPHRkIHN0eWxlPXt7cGFkZGluZzoiOXB4In19IG9uQ2xpY2s9eygpPT5zZXREZXRhaWxKb2Ioail9PjxQQmFkZ2UgcD17ai5wcmlvcml0eX0vPjwvdGQ+CiAgICAgICAgICAgICAgICB7IWlzU3ViU3RhZmYmJjx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCIsZm9udFdlaWdodDo2MDAsY29sb3I6IiMxYzE5MTcifX0gb25DbGljaz17KCk9PnNldERldGFpbEpvYihqKX0+e2ZtdChqLmZpbmFsX3ByaWNlKX08L3RkPn0KICAgICAgICAgICAgICAgIHshaXNTdWJTdGFmZiYmPHRkIHN0eWxlPXt7cGFkZGluZzoiOXB4Iixmb250V2VpZ2h0OjcwMCxjb2xvcjpqLmJhbGFuY2U+MD8iI2RjMjYyNiI6IiMxNmEzNGEiLGZvbnRTaXplOjExfX0gb25DbGljaz17KCk9PnNldERldGFpbEpvYihqKX0+e2ouYmFsYW5jZT4wP2ZtdChqLmJhbGFuY2UpOiLinJMgUGFpZCJ9PC90ZD59CiAgICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI5cHgiLGNvbG9yOm92PyIjYzI0MTBjIjoiIzc4NzE2YyIsZm9udFdlaWdodDpvdj83MDA6NDAwLGZvbnRTaXplOjExfX0gb25DbGljaz17KCk9PnNldERldGFpbEpvYihqKX0+e292PyLimqAgIjoiIn17ai5kdWVfZGF0ZXx8IuKAlCJ9PC90ZD4KICAgICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCJ9fSBvbkNsaWNrPXsoKT0+c2V0RGV0YWlsSm9iKGopfT48QmFkZ2Ugc3RhdHVzPXtqLnN0YXR1c30vPjwvdGQ+CiAgICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI5cHgifX0+PGJ1dHRvbiBvbkNsaWNrPXtlPT57ZS5zdG9wUHJvcGFnYXRpb24oKTtzZXRTdE1vZGFsKGopO319IHN0eWxlPXt7Zm9udFNpemU6MTAsY29sb3I6Qi5wcmksZm9udFdlaWdodDo3MDAsYmFja2dyb3VuZDoibm9uZSIsYm9yZGVyOmAxcHggc29saWQgJHtCLnByaU19YCxib3JkZXJSYWRpdXM6NSxwYWRkaW5nOiIzcHggOHB4IixjdXJzb3I6InBvaW50ZXIifX0+VXBkYXRlPC9idXR0b24+PC90ZD4KICAgICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCJ9fT48YnV0dG9uIG9uQ2xpY2s9e2U9PntlLnN0b3BQcm9wYWdhdGlvbigpO3NldE1hdE1vZGFsKGopO319IHN0eWxlPXt7Zm9udFNpemU6MTAsY29sb3I6IiMxNmEzNGEiLGZvbnRXZWlnaHQ6NzAwLGJhY2tncm91bmQ6Im5vbmUiLGJvcmRlcjoiMXB4IHNvbGlkICM4NmVmYWMiLGJvcmRlclJhZGl1czo1LHBhZGRpbmc6IjNweCA4cHgiLGN1cnNvcjoicG9pbnRlciJ9fT7wn6eqIE1hdGVyaWFsPC9idXR0b24+PC90ZD4KICAgICAgICAgICAgICAgIHsocm9sZT09PSJhZG1pbiJ8fHJvbGU9PT0ic3RhZmYiKSYmPHRkIHN0eWxlPXt7cGFkZGluZzoiOXB4In19PjxidXR0b24gb25DbGljaz17ZT0+e2Uuc3RvcFByb3BhZ2F0aW9uKCk7c2VuZFdoYXRzQXBwKGopO319IHRpdGxlPSJXaGF0c0FwcCDgsKrgsILgsKrgsYEiIHN0eWxlPXt7Zm9udFNpemU6MTMsYmFja2dyb3VuZDoiI2YwZmRmNCIsYm9yZGVyOiIxcHggc29saWQgIzg2ZWZhYyIsYm9yZGVyUmFkaXVzOjUscGFkZGluZzoiM3B4IDdweCIsY3Vyc29yOiJwb2ludGVyIn19PvCfk7E8L2J1dHRvbj48L3RkPn0KICAgICAgICAgICAgICA8L3RyPik7fSl9CiAgICAgICAgICA8L3Rib2R5PgogICAgICAgIDwvdGFibGU+CiAgICAgIDwvZGl2PgogICAgICA8UGFnZXIgcGFnZT17cGFnZX0gdG90YWw9e2ZqLmxlbmd0aH0gcGVyPXtQRVJ9IG9uQ2hhbmdlPXtzZXRQYWdlfS8+CiAgICA8L2Rpdj4KCiAgICB7bW9kYWw9PT0iYWRkIiYmPE1vZGFsIHRpdGxlPSJDcmVhdGUgTmV3IEpvYiIgb25DbG9zZT17KCk9PnNldE1vZGFsKG51bGwpfSB3PXs1MjB9PgogICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZ3JpZCIsZ3JpZFRlbXBsYXRlQ29sdW1uczoiMWZyIDFmciIsZ2FwOiIwIDEzcHgifX0+CiAgICAgICAgPGRpdiBzdHlsZT17e2dyaWRDb2x1bW46IjEvLTEifX0+PEZsZCBsYWJlbD0iQ3VzdG9tZXIiIHJlcT48Q3VzdFNlYXJjaCBjdXN0cz17Y3VzdHN9IHZhbHVlPXtmb3JtLmN1c3RvbWVyX2lkfSBvbkNoYW5nZT17dj0+c2V0Rm9ybShmPT4oey4uLmYsY3VzdG9tZXJfaWQ6dn0pKX0vPjwvRmxkPjwvZGl2PgogICAgICAgIDxGbGQgbGFiZWw9IkpvYiBUeXBlIiByZXE+PHNlbGVjdCB2YWx1ZT17Zm9ybS5qb2JfdHlwZX0gb25DaGFuZ2U9e2U9PnNldEZvcm0oZj0+KHsuLi5mLGpvYl90eXBlOmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17U0VMfT48b3B0aW9uIHZhbHVlPSIiPi0tIFNlbGVjdCBUeXBlIC0tPC9vcHRpb24+e1suLi5uZXcgU2V0KGp0cy5tYXAoanQ9Pmp0Lm5hbWUpKV0ubWFwKG49PjxvcHRpb24ga2V5PXtufSB2YWx1ZT17bn0+e259PC9vcHRpb24+KX08L3NlbGVjdD48L0ZsZD4KICAgICAgICA8RmxkIGxhYmVsPSJTaXplIj48aW5wdXQgdmFsdWU9e2Zvcm0uc2l6ZX0gb25DaGFuZ2U9e2U9PnNldEZvcm0oZj0+KHsuLi5mLHNpemU6ZS50YXJnZXQudmFsdWV9KSl9IHN0eWxlPXtJTlB9IHBsYWNlaG9sZGVyPSI0eDYgZnQsIEE0Ii8+PC9GbGQ+CiAgICAgICAgPEZsZCBsYWJlbD0iUHJpY2UgKOKCuSkiIHJlcT48aW5wdXQgdHlwZT0ibnVtYmVyIiB2YWx1ZT17Zm9ybS5pbml0aWFsX3ByaWNlfSBvbkNoYW5nZT17ZT0+c2V0Rm9ybShmPT4oey4uLmYsaW5pdGlhbF9wcmljZTplLnRhcmdldC52YWx1ZX0pKX0gc3R5bGU9e0lOUH0gcGxhY2Vob2xkZXI9IjAiLz48L0ZsZD4KICAgICAgICA8RmxkIGxhYmVsPSJEaXNjb3VudCAo4oK5KSI+PGlucHV0IHR5cGU9Im51bWJlciIgdmFsdWU9e2Zvcm0uZGlzY291bnRfYW1vdW50fSBvbkNoYW5nZT17ZT0+c2V0Rm9ybShmPT4oey4uLmYsZGlzY291bnRfYW1vdW50OmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17SU5QfS8+PC9GbGQ+CiAgICAgICAgPEZsZCBsYWJlbD0iQWR2YW5jZSAo4oK5KSI+PGlucHV0IHR5cGU9Im51bWJlciIgdmFsdWU9e2Zvcm0uYWR2YW5jZTF9IG9uQ2hhbmdlPXtlPT5zZXRGb3JtKGY9Pih7Li4uZixhZHZhbmNlMTplLnRhcmdldC52YWx1ZX0pKX0gc3R5bGU9e0lOUH0vPjwvRmxkPgogICAgICAgIDxGbGQgbGFiZWw9IlByaW9yaXR5Ij4KICAgICAgICAgIDxzZWxlY3QgdmFsdWU9e2Zvcm0ucHJpb3JpdHl9IG9uQ2hhbmdlPXtlPT5zZXRGb3JtKGY9Pih7Li4uZixwcmlvcml0eTplLnRhcmdldC52YWx1ZX0pKX0gc3R5bGU9e1NFTH0+CiAgICAgICAgICAgIHtPYmplY3QuZW50cmllcyhQUklPKS5tYXAoKFtrLHZdKT0+PG9wdGlvbiBrZXk9e2t9IHZhbHVlPXtrfT57di5sfTwvb3B0aW9uPil9CiAgICAgICAgICA8L3NlbGVjdD4KICAgICAgICA8L0ZsZD4KICAgICAgICA8RmxkIGxhYmVsPSJEdWUgRGF0ZSI+PGlucHV0IHR5cGU9ImRhdGUiIHZhbHVlPXtmb3JtLmR1ZV9kYXRlfSBvbkNoYW5nZT17ZT0+c2V0Rm9ybShmPT4oey4uLmYsZHVlX2RhdGU6ZS50YXJnZXQudmFsdWV9KSl9IHN0eWxlPXtJTlB9IG1pbj17VE9EQVkoKX0vPjwvRmxkPgogICAgICAgIDxkaXYgc3R5bGU9e3tncmlkQ29sdW1uOiIxLy0xIn19PgogICAgICAgICAgPEZsZCBsYWJlbD0iQXNzaWduIFRvIj4KICAgICAgICAgICAgPHNlbGVjdCB2YWx1ZT17Zm9ybS5hc3NpZ25lZF90b30gb25DaGFuZ2U9e2U9PnNldEZvcm0oZj0+KHsuLi5mLGFzc2lnbmVkX3RvOmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17U0VMfT4KICAgICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSIiPi0tIFVuYXNzaWduZWQgLS08L29wdGlvbj4KICAgICAgICAgICAgICB7c3RhZmZVc2Vycy5sZW5ndGg+MAogICAgICAgICAgICAgICAgPyBzdGFmZlVzZXJzLm1hcChzPT48b3B0aW9uIGtleT17cy5pZH0gdmFsdWU9e3MuaWR9PntzLnVzZXJuYW1lfHxzLm5hbWV9PC9vcHRpb24+KQogICAgICAgICAgICAgICAgOiA8b3B0aW9uIGRpc2FibGVkPkxvYWRpbmcgc3RhZmYuLi48L29wdGlvbj4KICAgICAgICAgICAgICB9CiAgICAgICAgICAgIDwvc2VsZWN0PgogICAgICAgICAgPC9GbGQ+CiAgICAgICAgPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT17e2dyaWRDb2x1bW46IjEvLTEifX0+CiAgICAgICAgICA8RmxkIGxhYmVsPSJEZXNjcmlwdGlvbiI+PHRleHRhcmVhIHZhbHVlPXtmb3JtLmRlc2NyaXB0aW9ufSBvbkNoYW5nZT17ZT0+c2V0Rm9ybShmPT4oey4uLmYsZGVzY3JpcHRpb246ZS50YXJnZXQudmFsdWV9KSl9IHN0eWxlPXt7Li4uSU5QLG1pbkhlaWdodDo1MCxyZXNpemU6InZlcnRpY2FsIn19IHBsYWNlaG9sZGVyPSJKb2IgZGV0YWlscy4uLiIvPjwvRmxkPgogICAgICAgICAgPEZsZCBsYWJlbD0iTm90ZXMiPjxpbnB1dCB2YWx1ZT17Zm9ybS5ub3Rlc30gb25DaGFuZ2U9e2U9PnNldEZvcm0oZj0+KHsuLi5mLG5vdGVzOmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17SU5QfSBwbGFjZWhvbGRlcj0iSW50ZXJuYWwgbm90ZXMuLi4iLz48L0ZsZD4KICAgICAgICA8L2Rpdj4KICAgICAgPC9kaXY+CiAgICAgIHtmb3JtLmluaXRpYWxfcHJpY2UmJjxkaXYgc3R5bGU9e3tiYWNrZ3JvdW5kOkIucHJpTCxib3JkZXI6YDFweCBzb2xpZCAke0IucHJpTX1gLGJvcmRlclJhZGl1czo4LHBhZGRpbmc6IjEwcHggMTJweCIsbWFyZ2luQm90dG9tOjEyLGRpc3BsYXk6ImZsZXgiLGdhcDoyMH19PgogICAgICAgIDxkaXY+PGRpdiBzdHlsZT17e2ZvbnRTaXplOjksY29sb3I6IiM3ODcxNmMiLGZvbnRXZWlnaHQ6NjAwfX0+RmluYWwgUHJpY2U8L2Rpdj48ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTYsZm9udFdlaWdodDo4MDAsY29sb3I6Qi5wcmlEfX0+e2ZtdChmcCl9PC9kaXY+PC9kaXY+CiAgICAgICAgPGRpdj48ZGl2IHN0eWxlPXt7Zm9udFNpemU6OSxjb2xvcjoiIzc4NzE2YyIsZm9udFdlaWdodDo2MDB9fT5CYWxhbmNlIER1ZTwvZGl2PjxkaXYgc3R5bGU9e3tmb250U2l6ZToxNixmb250V2VpZ2h0OjgwMCxjb2xvcjoiI2RjMjYyNiJ9fT57Zm10KGJhbCl9PC9kaXY+PC9kaXY+CiAgICAgIDwvZGl2Pn0KICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGdhcDo4LGp1c3RpZnlDb250ZW50OiJmbGV4LWVuZCJ9fT48YnV0dG9uIG9uQ2xpY2s9eygpPT5zZXRNb2RhbChudWxsKX0gc3R5bGU9e0JUTigiZ2hvc3QiKX0+Q2FuY2VsPC9idXR0b24+PGJ1dHRvbiBvbkNsaWNrPXtzYXZlSm9ifSBkaXNhYmxlZD17c2F2aW5nfSBzdHlsZT17QlROKCl9PntzYXZpbmc/PFNwaW4vPjoiQ3JlYXRlIEpvYiJ9PC9idXR0b24+PC9kaXY+CiAgICA8L01vZGFsPn0KCiAgICB7c3RNb2RhbCYmPFN0YXR1c01vZGFsIGpvYj17c3RNb2RhbH0gb25DbG9zZT17KCk9PnNldFN0TW9kYWwobnVsbCl9IGFwaT17YXBpfSB0b2FzdD17dG9hc3R9IG9uRG9uZT17KCk9PntzZXRTdE1vZGFsKG51bGwpO2xvYWQoKTt9fS8+fQogICAge21hdE1vZGFsJiY8TWF0ZXJpYWxFbnRyeU1vZGFsIGpvYj17bWF0TW9kYWx9IG9uQ2xvc2U9eygpPT5zZXRNYXRNb2RhbChudWxsKX0gYXBpPXthcGl9IHRvYXN0PXt0b2FzdH0gdXNlcj17dXNlcn0vPn0KICAgIHtkZXRhaWxKb2ImJjxKb2JEZXRhaWxNb2RhbCBqb2I9e2RldGFpbEpvYn0gcm9sZT17cm9sZX0gb25DbG9zZT17KCk9PnNldERldGFpbEpvYihudWxsKX0vPn0KICA8L1BnPjsKfQoKZnVuY3Rpb24gU3RhdHVzTW9kYWwoe2pvYixvbkNsb3NlLGFwaSx0b2FzdCxvbkRvbmV9KXsKICBjb25zdFtzdGF0dXMsc2V0U3RhdHVzXT11c2VTdGF0ZShqb2Iuc3RhdHVzKTtjb25zdFtub3RlcyxzZXROb3Rlc109dXNlU3RhdGUoIiIpO2NvbnN0W3NhdmluZyxzZXRTYXZpbmddPXVzZVN0YXRlKGZhbHNlKTsKICBjb25zdCBzYXZlPWFzeW5jKCk9PntzZXRTYXZpbmcodHJ1ZSk7dHJ5e2F3YWl0IGFwaS51cGRhdGVKb2JTdGF0dXMoam9iLmlkLHN0YXR1cyxub3Rlcyk7dG9hc3QoYEpvYiAjJHtqb2IuaWR9IOKGkiAke3N0YXR1c31gKTtvbkRvbmUoKTt9Y2F0Y2goZSl7dG9hc3QoZS5tZXNzYWdlLCJlcnJvciIpO31maW5hbGx5e3NldFNhdmluZyhmYWxzZSk7fTt9OwogIHJldHVybjxNb2RhbCB0aXRsZT17YFVwZGF0ZSBKb2IgIyR7am9iLmlkfWB9IG9uQ2xvc2U9e29uQ2xvc2V9IHc9ezQwMH0+CiAgICA8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDoiI2ZhZmFmOSIsYm9yZGVyUmFkaXVzOjgscGFkZGluZzoiOXB4IDEycHgiLG1hcmdpbkJvdHRvbToxMn19PgogICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTMsZm9udFdlaWdodDo3MDAsY29sb3I6IiMxYzE5MTcifX0+e2pvYi5jdXN0b21lcl9uYW1lfTwvZGl2PgogICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTEsY29sb3I6IiM1NzUzNGUifX0+e2pvYi5qb2JfdHlwZX17am9iLnNpemU/YCDCtyAke2pvYi5zaXplfWA6IiJ9PC9kaXY+CiAgICA8L2Rpdj4KICAgIDxGbGQgbGFiZWw9Ik5ldyBTdGF0dXMiPgogICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZ3JpZCIsZ3JpZFRlbXBsYXRlQ29sdW1uczoiMWZyIDFmciIsZ2FwOjd9fT4KICAgICAgICB7WyJQZW5kaW5nIiwiSW4gUHJvZ3Jlc3MiLCJDb21wbGV0ZWQiLCJEZWxpdmVyZWQiXS5tYXAocz0+PGJ1dHRvbiBrZXk9e3N9IG9uQ2xpY2s9eygpPT5zZXRTdGF0dXMocyl9IHN0eWxlPXt7cGFkZGluZzoiOXB4IDAiLGJvcmRlclJhZGl1czo3LGJvcmRlcjpzdGF0dXM9PT1zP2AycHggc29saWQgJHtCLnByaX1gOiIxcHggc29saWQgI2U3ZTVlNCIsYmFja2dyb3VuZDpzdGF0dXM9PT1zP0IucHJpTDoiI2ZmZiIsY29sb3I6c3RhdHVzPT09cz9CLnByaUQ6IiM1NzUzNGUiLGZvbnRTaXplOjEyLGZvbnRXZWlnaHQ6c3RhdHVzPT09cz83MDA6NTAwLGN1cnNvcjoicG9pbnRlciJ9fT57c308L2J1dHRvbj4pfQogICAgICA8L2Rpdj4KICAgIDwvRmxkPgogICAgPEZsZCBsYWJlbD0iTm90ZXMgKG9wdGlvbmFsKSI+PHRleHRhcmVhIHZhbHVlPXtub3Rlc30gb25DaGFuZ2U9e2U9PnNldE5vdGVzKGUudGFyZ2V0LnZhbHVlKX0gc3R5bGU9e3suLi5JTlAsbWluSGVpZ2h0OjUwLHJlc2l6ZToidmVydGljYWwifX0gcGxhY2Vob2xkZXI9IlJlbWFya3MuLi4iLz48L0ZsZD4KICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixnYXA6OCxqdXN0aWZ5Q29udGVudDoiZmxleC1lbmQifX0+PGJ1dHRvbiBvbkNsaWNrPXtvbkNsb3NlfSBzdHlsZT17QlROKCJnaG9zdCIpfT5DYW5jZWw8L2J1dHRvbj48YnV0dG9uIG9uQ2xpY2s9e3NhdmV9IGRpc2FibGVkPXtzYXZpbmd8fHN0YXR1cz09PWpvYi5zdGF0dXN9IHN0eWxlPXt7Li4uQlROKCksb3BhY2l0eTpzdGF0dXM9PT1qb2Iuc3RhdHVzPy41OjF9fT57c2F2aW5nPzxTcGluLz46IlVwZGF0ZSJ9PC9idXR0b24+PC9kaXY+CiAgPC9Nb2RhbD47Cn0KCi8qIOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkCBNQVRFUklBTCBFTlRSWSBNT0RBTCAoSm9icyDgsLLgsYspIOKVkOKVkOKVkCAqLwpmdW5jdGlvbiBNYXRlcmlhbEVudHJ5TW9kYWwoe2pvYixvbkNsb3NlLGFwaSx0b2FzdCx1c2VyLHJvbGV9KXsKICBjb25zdFtpdGVtcyxzZXRJdGVtc109dXNlU3RhdGUoW10pO2NvbnN0W2Zvcm0sc2V0Rm9ybV09dXNlU3RhdGUoe2l0ZW1faWQ6IiIsdHJhbnNfdHlwZToiVXNhZ2UiLHF0eToiIixyZW1hcmtzOiIifSk7CiAgY29uc3Rbc2F2aW5nLHNldFNhdmluZ109dXNlU3RhdGUoZmFsc2UpOwogIHVzZUVmZmVjdCgoKT0+e2FwaS5pbnZlbnRvcnlJdGVtcygpLnRoZW4oc2V0SXRlbXMpLmNhdGNoKCgpPT57fSk7fSxbXSk7CiAgY29uc3Qgc2F2ZT1hc3luYygpPT57CiAgICBpZighZm9ybS5pdGVtX2lkfHwhZm9ybS5xdHl8fE51bWJlcihmb3JtLnF0eSk8PTApe3RvYXN0KCJNYXRlcmlhbCAmIFF0eSDgsIXgsLXgsLjgsLDgsIIiLCJlcnJvciIpO3JldHVybjt9CiAgICBzZXRTYXZpbmcodHJ1ZSk7CiAgICB0cnl7CiAgICAgIGF3YWl0IGFwaS5hZGRUcmFuc2FjdGlvbih7aXRlbV9pZDpOdW1iZXIoZm9ybS5pdGVtX2lkKSx1c2VyX2lkOnVzZXIuaWQsdHJhbnNfdHlwZTpmb3JtLnRyYW5zX3R5cGUscXR5Ok51bWJlcihmb3JtLnF0eSkscmVtYXJrczpmb3JtLnJlbWFya3Msam9iX2lkOmpvYi5pZH0pOwogICAgICB0b2FzdChg4pyFICR7Zm9ybS50cmFuc190eXBlfSByZWNvcmRlZCBmb3IgSm9iICMke2pvYi5pZH1gKTtvbkNsb3NlKCk7CiAgICB9Y2F0Y2goZSl7dG9hc3QoZS5tZXNzYWdlLCJlcnJvciIpO31maW5hbGx5e3NldFNhdmluZyhmYWxzZSk7fQogIH07CiAgY29uc3Qgc2VsSXRlbT1pdGVtcy5maW5kKGk9PlN0cmluZyhpLmlkKT09PVN0cmluZyhmb3JtLml0ZW1faWQpKTsKICByZXR1cm48TW9kYWwgdGl0bGU9e2Dwn6eqIE1hdGVyaWFsIEVudHJ5IOKAlCBKb2IgIyR7am9iLmlkfWB9IG9uQ2xvc2U9e29uQ2xvc2V9IHc9ezQ0MH0+CiAgICA8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDoiI2YwZmRmNCIsYm9yZGVyOiIxcHggc29saWQgIzg2ZWZhYyIsYm9yZGVyUmFkaXVzOjgscGFkZGluZzoiOXB4IDEycHgiLG1hcmdpbkJvdHRvbToxMn19PgogICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTIsZm9udFdlaWdodDo3MDAsY29sb3I6IiMxNTgwM2QifX0+e2pvYi5jdXN0b21lcl9uYW1lfSDigJQge2pvYi5qb2JfdHlwZX08L2Rpdj4KICAgICAge2pvYi5zaXplJiY8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTAsY29sb3I6IiMxNmEzNGEifX0+U2l6ZToge2pvYi5zaXplfTwvZGl2Pn0KICAgIDwvZGl2PgogICAgPEZsZCBsYWJlbD0iVHJhbnNhY3Rpb24gVHlwZSIgcmVxPgogICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsZ2FwOjd9fT4KICAgICAgICB7WyJVc2FnZSIsIldhc3RhZ2UiXS5tYXAodD0+PGJ1dHRvbiBrZXk9e3R9IG9uQ2xpY2s9eygpPT5zZXRGb3JtKGY9Pih7Li4uZix0cmFuc190eXBlOnR9KSl9IHN0eWxlPXt7ZmxleDoxLHBhZGRpbmc6IjhweCAwIixib3JkZXJSYWRpdXM6Nyxib3JkZXI6Zm9ybS50cmFuc190eXBlPT09dD9gMnB4IHNvbGlkICR7dD09PSJVc2FnZSI/IiMxNmEzNGEiOiIjZGMyNjI2In1gOiIxcHggc29saWQgI2U3ZTVlNCIsYmFja2dyb3VuZDpmb3JtLnRyYW5zX3R5cGU9PT10P3Q9PT0iVXNhZ2UiPyIjZjBmZGY0IjoiI2ZlZjJmMiI6IiNmZmYiLGNvbG9yOmZvcm0udHJhbnNfdHlwZT09PXQ/dD09PSJVc2FnZSI/IiMxNTgwM2QiOiIjZGMyNjI2IjoiIzU3NTM0ZSIsZm9udFNpemU6MTIsZm9udFdlaWdodDo3MDAsY3Vyc29yOiJwb2ludGVyIn19Pnt0PT09IlVzYWdlIj8i4pyFIFVzYWdlIjoi4pqg77iPIFdhc3RhZ2UifTwvYnV0dG9uPil9CiAgICAgIDwvZGl2PgogICAgPC9GbGQ+CiAgICA8RmxkIGxhYmVsPSJNYXRlcmlhbCIgcmVxPgogICAgICA8c2VsZWN0IHZhbHVlPXtmb3JtLml0ZW1faWR9IG9uQ2hhbmdlPXtlPT5zZXRGb3JtKGY9Pih7Li4uZixpdGVtX2lkOmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17U0VMfT4KICAgICAgICA8b3B0aW9uIHZhbHVlPSIiPi0tIFNlbGVjdCBNYXRlcmlhbCAtLTwvb3B0aW9uPgogICAgICAgIHtpdGVtcy5maWx0ZXIoaT0+aS5pc19hY3RpdmUhPT0wKS5tYXAoaT0+PG9wdGlvbiBrZXk9e2kuaWR9IHZhbHVlPXtpLmlkfT57aS5uYW1lKyhyb2xlIT09InN1Yl9zdGFmZiI/IiAoIisoIGkudW9tfHwiUGNzIikrIikiICsiIOKAlCBTdG9jazogIitpLmN1cnJlbnRfc3RvY2s6IiIpfTwvb3B0aW9uPil9CiAgICAgIDwvc2VsZWN0PgogICAgPC9GbGQ+CiAgICB7c2VsSXRlbSYmPGRpdiBzdHlsZT17e2JhY2tncm91bmQ6IiNmYWZhZjkiLGJvcmRlclJhZGl1czo2LHBhZGRpbmc6IjdweCAxMHB4IixtYXJnaW5Ub3A6LTYsbWFyZ2luQm90dG9tOjEwLGZvbnRTaXplOjExLGNvbG9yOiIjNTc1MzRlIn19PgogICAgICBDdXJyZW50IFN0b2NrOiA8c3Ryb25nIHN0eWxlPXt7Y29sb3I6c2VsSXRlbS5jdXJyZW50X3N0b2NrPD1zZWxJdGVtLnJlb3JkZXJfbGV2ZWw/IiNkYzI2MjYiOiIjMTZhMzRhIn19PntzZWxJdGVtLmN1cnJlbnRfc3RvY2t9IHtzZWxJdGVtLnVvbXx8IlBjcyJ9PC9zdHJvbmc+CiAgICAgIHtzZWxJdGVtLmN1cnJlbnRfc3RvY2s8PXNlbEl0ZW0ucmVvcmRlcl9sZXZlbCYmPHNwYW4gc3R5bGU9e3tjb2xvcjoiI2RjMjYyNiIsZm9udFdlaWdodDo3MDB9fT4g4pqgIExvdyE8L3NwYW4+fQogICAgPC9kaXY+fQogICAgPEZsZCBsYWJlbD0iUXVhbnRpdHkiIHJlcT4KICAgICAgPGlucHV0IHR5cGU9Im51bWJlciIgbWluPSIwLjEiIHN0ZXA9IjAuMSIgdmFsdWU9e2Zvcm0ucXR5fSBvbkNoYW5nZT17ZT0+c2V0Rm9ybShmPT4oey4uLmYscXR5OmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17SU5QfSBwbGFjZWhvbGRlcj0iMCIvPgogICAgPC9GbGQ+CiAgICA8RmxkIGxhYmVsPSJSZW1hcmtzIj4KICAgICAgPGlucHV0IHZhbHVlPXtmb3JtLnJlbWFya3N9IG9uQ2hhbmdlPXtlPT5zZXRGb3JtKGY9Pih7Li4uZixyZW1hcmtzOmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17SU5QfSBwbGFjZWhvbGRlcj0iT3B0aW9uYWwgbm90ZXMuLi4iLz4KICAgIDwvRmxkPgogICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGdhcDo4LGp1c3RpZnlDb250ZW50OiJmbGV4LWVuZCJ9fT4KICAgICAgPGJ1dHRvbiBvbkNsaWNrPXtvbkNsb3NlfSBzdHlsZT17QlROKCJnaG9zdCIpfT5DYW5jZWw8L2J1dHRvbj4KICAgICAgPGJ1dHRvbiBvbkNsaWNrPXtzYXZlfSBkaXNhYmxlZD17c2F2aW5nfSBzdHlsZT17ey4uLkJUTigpLGJhY2tncm91bmQ6Zm9ybS50cmFuc190eXBlPT09Ildhc3RhZ2UiPyIjZGMyNjI2IjpCLnByaX19PntzYXZpbmc/PFNwaW4vPjpgUmVjb3JkICR7Zm9ybS50cmFuc190eXBlfWB9PC9idXR0b24+CiAgICA8L2Rpdj4KICA8L01vZGFsPjsKfQoKLyog4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQIE1BVEVSSUFMIFVTQUdFIFBBR0Ug4pWQ4pWQ4pWQICovCmZ1bmN0aW9uIE1hdGVyaWFsVXNhZ2Uoe2FwaSx1c2VyLHJvbGUsdG9hc3R9KXsKICBjb25zdFtpdGVtcyxzZXRJdGVtc109dXNlU3RhdGUoW10pO2NvbnN0W2pvYnMsc2V0Sm9ic109dXNlU3RhdGUoW10pOwogIGNvbnN0W2VudHJpZXMsc2V0RW50cmllc109dXNlU3RhdGUoW10pO2NvbnN0W2xvYWRpbmcsc2V0TG9hZGluZ109dXNlU3RhdGUoZmFsc2UpOwogIGNvbnN0W3NhdmluZyxzZXRTYXZpbmddPXVzZVN0YXRlKGZhbHNlKTtjb25zdFtkYXlzLHNldERheXNdPXVzZVN0YXRlKDMwKTsKICBjb25zdFtmb3JtLHNldEZvcm1dPXVzZVN0YXRlKHtpdGVtX2lkOiIiLHRyYW5zX3R5cGU6IlVzYWdlIixxdHk6IiIsam9iX2lkOiIiLHJlbWFya3M6IiJ9KTsKICBjb25zdCBpc0FkbWluPXJvbGU9PT0iYWRtaW4iOwoKICBjb25zdCBsb2FkQWxsPXVzZUNhbGxiYWNrKGFzeW5jKCk9PnsKICAgIHNldExvYWRpbmcodHJ1ZSk7CiAgICB0cnl7CiAgICAgIGNvbnN0W2ludixhY3RpdmVKb2JzLG15RV09YXdhaXQgUHJvbWlzZS5hbGwoWwogICAgICAgIGFwaS5pbnZlbnRvcnlJdGVtcygpLAogICAgICAgIGFwaS5hY3RpdmVKb2JzKHVzZXI/LmlkLHJvbGUpLAogICAgICAgIGFwaS5teUVudHJpZXModXNlcj8uaWQsZGF5cyksCiAgICAgIF0pOwogICAgICBzZXRJdGVtcyhpbnYpO3NldEpvYnMoYWN0aXZlSm9icyk7c2V0RW50cmllcyhteUUpOwogICAgfWNhdGNoKGUpe3RvYXN0KGUubWVzc2FnZSwiZXJyb3IiKTt9ZmluYWxseXtzZXRMb2FkaW5nKGZhbHNlKTt9CiAgfSxbYXBpLHVzZXIsZGF5cyxyb2xlXSk7CiAgdXNlRWZmZWN0KCgpPT57bG9hZEFsbCgpO30sW2xvYWRBbGxdKTsKCiAgY29uc3Qgc2VsSXRlbT1pdGVtcy5maW5kKGk9PlN0cmluZyhpLmlkKT09PVN0cmluZyhmb3JtLml0ZW1faWQpKTsKCiAgY29uc3Qgc2F2ZT1hc3luYygpPT57CiAgICBpZighZm9ybS5pdGVtX2lkfHwhZm9ybS5xdHl8fE51bWJlcihmb3JtLnF0eSk8PTApe3RvYXN0KCJNYXRlcmlhbCAmIFF1YW50aXR5IOCwheCwteCwuOCwsOCwgiIsImVycm9yIik7cmV0dXJuO30KICAgIGlmKHJvbGU9PT0ic3RhZmYiJiZmb3JtLnRyYW5zX3R5cGU9PT0iU3RvY2sgSW4iKXt0b2FzdCgiU3RvY2sgSW4gcGVybWlzc2lvbiDgsLLgsYfgsKbgsYEiLCJlcnJvciIpO3JldHVybjt9CiAgICBzZXRTYXZpbmcodHJ1ZSk7CiAgICB0cnl7CiAgICAgIGF3YWl0IGFwaS5hZGRUcmFuc2FjdGlvbih7aXRlbV9pZDpOdW1iZXIoZm9ybS5pdGVtX2lkKSx1c2VyX2lkOnVzZXIuaWQsdHJhbnNfdHlwZTpmb3JtLnRyYW5zX3R5cGUscXR5Ok51bWJlcihmb3JtLnF0eSksam9iX2lkOmZvcm0uam9iX2lkP051bWJlcihmb3JtLmpvYl9pZCk6bnVsbCxyZW1hcmtzOmZvcm0ucmVtYXJrc30pOwogICAgICB0b2FzdChg4pyFICR7Zm9ybS50cmFuc190eXBlfSByZWNvcmRlZCFgKTsKICAgICAgc2V0Rm9ybSh7aXRlbV9pZDoiIix0cmFuc190eXBlOiJVc2FnZSIscXR5OiIiLGpvYl9pZDoiIixyZW1hcmtzOiIifSk7CiAgICAgIGxvYWRBbGwoKTsKICAgIH1jYXRjaChlKXt0b2FzdChlLm1lc3NhZ2UsImVycm9yIik7fWZpbmFsbHl7c2V0U2F2aW5nKGZhbHNlKTt9CiAgfTsKCiAgY29uc3QgdHlwZUNvbG9yPXsiVXNhZ2UiOiIjMTZhMzRhIiwiV2FzdGFnZSI6IiNkYzI2MjYiLCJTdG9jayBJbiI6IiMyNTYzZWIifTsKICBjb25zdCB0b3RhbFVzYWdlPWVudHJpZXMuZmlsdGVyKGU9PmUudHJhbnNhY3Rpb25fdHlwZT09PSJVc2FnZSIpLnJlZHVjZSgocyxlKT0+cysoZS5xdWFudGl0eXx8MCksMCk7CiAgY29uc3QgdG90YWxXYXN0YWdlPWVudHJpZXMuZmlsdGVyKGU9PmUudHJhbnNhY3Rpb25fdHlwZT09PSJXYXN0YWdlIikucmVkdWNlKChzLGUpPT5zKyhlLnF1YW50aXR5fHwwKSwwKTsKCiAgcmV0dXJuPFBnPgogICAgPFBhZ2VIZHIgdGl0bGU9IvCfp6ogTWF0ZXJpYWwgVXNhZ2UiIHN1Yj0iTWF0ZXJpYWwgdXNhZ2UgJiB3YXN0YWdlIHJlY29yZCDgsJrgsYfgsK/gsILgsKHgsL8iLz4KICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJncmlkIixncmlkVGVtcGxhdGVDb2x1bW5zOndpbmRvdy5pbm5lcldpZHRoPD03Njg/IjFmciI6IjQyMHB4IDFmciIsZ2FwOndpbmRvdy5pbm5lcldpZHRoPD03Njg/MTI6MTYsYWxpZ25JdGVtczoic3RhcnQifX0+CgogICAgICB7LyogRW50cnkgRm9ybSAqL30KICAgICAgPGRpdiBzdHlsZT17e2JhY2tncm91bmQ6InZhcigtLWJnLWNhcmQpIixib3JkZXI6IjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpIixib3JkZXJSYWRpdXM6MTIscGFkZGluZzoiMThweCJ9fT4KICAgICAgICA8aDMgc3R5bGU9e3tmb250U2l6ZToxMyxmb250V2VpZ2h0OjgwMCxjb2xvcjoiIzFjMTkxNyIsbWFyZ2luQm90dG9tOjE0fX0+TmV3IEVudHJ5PC9oMz4KCiAgICAgICAgPEZsZCBsYWJlbD0iVHJhbnNhY3Rpb24gVHlwZSIgcmVxPgogICAgICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGdhcDo3fX0+CiAgICAgICAgICAgIHsoaXNBZG1pbj9bIlVzYWdlIiwiV2FzdGFnZSIsIlN0b2NrIEluIl06WyJVc2FnZSIsIldhc3RhZ2UiXSkubWFwKHQ9PnsKICAgICAgICAgICAgICBjb25zdCBjPXQ9PT0iVXNhZ2UiPyIjMTZhMzRhIjp0PT09Ildhc3RhZ2UiPyIjZGMyNjI2IjoiIzI1NjNlYiI7CiAgICAgICAgICAgICAgY29uc3QgYmc9dD09PSJVc2FnZSI/IiNmMGZkZjQiOnQ9PT0iV2FzdGFnZSI/IiNmZWYyZjIiOiIjZWZmNmZmIjsKICAgICAgICAgICAgICByZXR1cm48YnV0dG9uIGtleT17dH0gb25DbGljaz17KCk9PnNldEZvcm0oZj0+KHsuLi5mLHRyYW5zX3R5cGU6dH0pKX0KICAgICAgICAgICAgICAgIHN0eWxlPXt7ZmxleDoxLHBhZGRpbmc6IjhweCA0cHgiLGJvcmRlclJhZGl1czo3LGJvcmRlcjpmb3JtLnRyYW5zX3R5cGU9PT10P2AycHggc29saWQgJHtjfWA6IjFweCBzb2xpZCAjZTdlNWU0IixiYWNrZ3JvdW5kOmZvcm0udHJhbnNfdHlwZT09PXQ/Ymc6IiNmZmYiLGNvbG9yOmZvcm0udHJhbnNfdHlwZT09PXQ/YzoiIzU3NTM0ZSIsZm9udFNpemU6MTEsZm9udFdlaWdodDo3MDAsY3Vyc29yOiJwb2ludGVyIn19PgogICAgICAgICAgICAgICAge3Q9PT0iVXNhZ2UiPyLinIUiOnQ9PT0iV2FzdGFnZSI/IuKaoO+4jyI6IvCfk6YifSB7dH0KICAgICAgICAgICAgICA8L2J1dHRvbj47fSl9CiAgICAgICAgICA8L2Rpdj4KICAgICAgICA8L0ZsZD4KCiAgICAgICAgPEZsZCBsYWJlbD0iTWF0ZXJpYWwiIHJlcT4KICAgICAgICAgIDxzZWxlY3QgdmFsdWU9e2Zvcm0uaXRlbV9pZH0gb25DaGFuZ2U9e2U9PnNldEZvcm0oZj0+KHsuLi5mLGl0ZW1faWQ6ZS50YXJnZXQudmFsdWV9KSl9IHN0eWxlPXtTRUx9PgogICAgICAgICAgICA8b3B0aW9uIHZhbHVlPSIiPi0tIFNlbGVjdCBNYXRlcmlhbCAtLTwvb3B0aW9uPgogICAgICAgICAgICB7aXRlbXMuZmlsdGVyKGk9PmkuaXNfYWN0aXZlIT09MCkubWFwKGk9PjxvcHRpb24ga2V5PXtpLmlkfSB2YWx1ZT17aS5pZH0+e2kubmFtZSsocm9sZSE9PSJzdWJfc3RhZmYiPyIgKCIrKCBpLnVvbXx8IlBjcyIpKyIpIiArIiDigJQgU3RvY2s6ICIraS5jdXJyZW50X3N0b2NrOiIiKX08L29wdGlvbj4pfQogICAgICAgICAgPC9zZWxlY3Q+CiAgICAgICAgPC9GbGQ+CgogICAgICAgIHtzZWxJdGVtJiY8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDoiI2ZhZmFmOSIsYm9yZGVyOiIxcHggc29saWQgI2U3ZTVlNCIsYm9yZGVyUmFkaXVzOjgscGFkZGluZzoiOXB4IDEycHgiLG1hcmdpblRvcDotNixtYXJnaW5Cb3R0b206MTJ9fT4KICAgICAgICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixqdXN0aWZ5Q29udGVudDoic3BhY2UtYmV0d2VlbiIsYWxpZ25JdGVtczoiY2VudGVyIn19PgogICAgICAgICAgICA8ZGl2PgogICAgICAgICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZToxMSxmb250V2VpZ2h0OjcwMCxjb2xvcjoiIzFjMTkxNyJ9fT57c2VsSXRlbS5uYW1lfTwvZGl2PgogICAgICAgICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZToxMCxjb2xvcjoiIzc4NzE2YyJ9fT57c2VsSXRlbS5pdGVtX3R5cGV8fCIifSB7c2VsSXRlbS5pdGVtX3NpemV8fCIifTwvZGl2PgogICAgICAgICAgICA8L2Rpdj4KICAgICAgICAgICAgPGRpdiBzdHlsZT17e3RleHRBbGlnbjoicmlnaHQifX0+CiAgICAgICAgICAgICAgPGRpdiBzdHlsZT17e2ZvbnRTaXplOjE4LGZvbnRXZWlnaHQ6ODAwLGNvbG9yOnNlbEl0ZW0uY3VycmVudF9zdG9jazw9c2VsSXRlbS5yZW9yZGVyX2xldmVsPyIjZGMyNjI2IjoiIzE2YTM0YSJ9fT57c2VsSXRlbS5jdXJyZW50X3N0b2NrfTwvZGl2PgogICAgICAgICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZTo5LGNvbG9yOiIjNzg3MTZjIixmb250V2VpZ2h0OjYwMH19PntzZWxJdGVtLnVvbXx8IlBjcyJ9IGluIHN0b2NrPC9kaXY+CiAgICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgICB7c2VsSXRlbS5jdXJyZW50X3N0b2NrPD1zZWxJdGVtLnJlb3JkZXJfbGV2ZWwmJjxkaXYgc3R5bGU9e3ttYXJnaW5Ub3A6Nixmb250U2l6ZToxMCxjb2xvcjoiI2RjMjYyNiIsZm9udFdlaWdodDo3MDAsYmFja2dyb3VuZDoiI2ZlZjJmMiIsYm9yZGVyUmFkaXVzOjUscGFkZGluZzoiM3B4IDdweCIsZGlzcGxheToiaW5saW5lLWJsb2NrIn19PuKaoO+4jyBMb3cgU3RvY2sg4oCUIFJlb3JkZXI6IHtzZWxJdGVtLnJlb3JkZXJfbGV2ZWx9PC9kaXY+fQogICAgICAgIDwvZGl2Pn0KCiAgICAgICAgPEZsZCBsYWJlbD0iUXVhbnRpdHkiIHJlcT4KICAgICAgICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixnYXA6NyxhbGlnbkl0ZW1zOiJjZW50ZXIifX0+CiAgICAgICAgICAgIDxpbnB1dCB0eXBlPSJudW1iZXIiIG1pbj0iMC4wMSIgc3RlcD0iMC4wMSIgdmFsdWU9e2Zvcm0ucXR5fSBvbkNoYW5nZT17ZT0+c2V0Rm9ybShmPT4oey4uLmYscXR5OmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17ey4uLklOUCxmbGV4OjF9fSBwbGFjZWhvbGRlcj0iMC4wMCIvPgogICAgICAgICAgICB7c2VsSXRlbSYmPHNwYW4gc3R5bGU9e3tmb250U2l6ZToxMSxjb2xvcjoiIzc4NzE2YyIsZm9udFdlaWdodDo2MDAsd2hpdGVTcGFjZToibm93cmFwIn19PntzZWxJdGVtLnVvbXx8IlBjcyJ9PC9zcGFuPn0KICAgICAgICAgIDwvZGl2PgogICAgICAgIDwvRmxkPgoKICAgICAgICA8RmxkIGxhYmVsPSJMaW5rIHRvIEpvYiAoT3B0aW9uYWwpIj4KICAgICAgICAgIDxzZWxlY3QgdmFsdWU9e2Zvcm0uam9iX2lkfSBvbkNoYW5nZT17ZT0+c2V0Rm9ybShmPT4oey4uLmYsam9iX2lkOmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17U0VMfT4KICAgICAgICAgICAgPG9wdGlvbiB2YWx1ZT0iIj4tLSBObyBzcGVjaWZpYyBqb2IgLS08L29wdGlvbj4KICAgICAgICAgICAge2pvYnMubWFwKGo9PjxvcHRpb24ga2V5PXtqLmlkfSB2YWx1ZT17ai5pZH0+I3tqLmlkfSDigJQge2ouY3VzdG9tZXJfbmFtZX0gKHtqLmpvYl90eXBlfSk8L29wdGlvbj4pfQogICAgICAgICAgPC9zZWxlY3Q+CiAgICAgICAgPC9GbGQ+CgogICAgICAgIDxGbGQgbGFiZWw9IlJlbWFya3MiPgogICAgICAgICAgPGlucHV0IHZhbHVlPXtmb3JtLnJlbWFya3N9IG9uQ2hhbmdlPXtlPT5zZXRGb3JtKGY9Pih7Li4uZixyZW1hcmtzOmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17SU5QfSBwbGFjZWhvbGRlcj0iT3B0aW9uYWwgbm90ZXMuLi4iLz4KICAgICAgICA8L0ZsZD4KCiAgICAgICAgPGJ1dHRvbiBvbkNsaWNrPXtzYXZlfSBkaXNhYmxlZD17c2F2aW5nfSBzdHlsZT17ey4uLkJUTigpLHdpZHRoOiIxMDAlIixiYWNrZ3JvdW5kOmZvcm0udHJhbnNfdHlwZT09PSJXYXN0YWdlIj8iI2RjMjYyNiI6Zm9ybS50cmFuc190eXBlPT09IlN0b2NrIEluIj8iIzI1NjNlYiI6Qi5wcmkscGFkZGluZzoiMTFweCJ9fT4KICAgICAgICAgIHtzYXZpbmc/PFNwaW4vPjpgUmVjb3JkICR7Zm9ybS50cmFuc190eXBlfWB9CiAgICAgICAgPC9idXR0b24+CiAgICAgIDwvZGl2PgoKICAgICAgey8qIE15IFJlY2VudCBFbnRyaWVzICovfQogICAgICA8ZGl2PgogICAgICAgIDxkaXYgc3R5bGU9e3tiYWNrZ3JvdW5kOiJ2YXIoLS1iZy1jYXJkKSIsYm9yZGVyOiIxcHggc29saWQgdmFyKC0tYm9yZGVyKSIsYm9yZGVyUmFkaXVzOjEyLHBhZGRpbmc6IjE0cHggMTZweCIsbWFyZ2luQm90dG9tOjEyfX0+CiAgICAgICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsanVzdGlmeUNvbnRlbnQ6InNwYWNlLWJldHdlZW4iLGFsaWduSXRlbXM6ImNlbnRlciIsbWFyZ2luQm90dG9tOjEwfX0+CiAgICAgICAgICAgIDxoMyBzdHlsZT17e2ZvbnRTaXplOjEzLGZvbnRXZWlnaHQ6ODAwLGNvbG9yOiIjMWMxOTE3IixtYXJnaW46MH19Pk15IEVudHJpZXM8L2gzPgogICAgICAgICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsZ2FwOjYsYWxpZ25JdGVtczoiY2VudGVyIn19PgogICAgICAgICAgICAgIDxzcGFuIHN0eWxlPXt7Zm9udFNpemU6MTAsY29sb3I6IiM3ODcxNmMifX0+TGFzdDwvc3Bhbj4KICAgICAgICAgICAgICA8c2VsZWN0IHZhbHVlPXtkYXlzfSBvbkNoYW5nZT17ZT0+c2V0RGF5cyhOdW1iZXIoZS50YXJnZXQudmFsdWUpKX0gc3R5bGU9e3suLi5TRUwsd2lkdGg6ImF1dG8iLHBhZGRpbmc6IjRweCA4cHgiLGZvbnRTaXplOjExfX0+CiAgICAgICAgICAgICAgICA8b3B0aW9uIHZhbHVlPXs3fT43IGRheXM8L29wdGlvbj48b3B0aW9uIHZhbHVlPXszMH0+MzAgZGF5czwvb3B0aW9uPjxvcHRpb24gdmFsdWU9ezkwfT45MCBkYXlzPC9vcHRpb24+CiAgICAgICAgICAgICAgPC9zZWxlY3Q+CiAgICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPC9kaXY+CgogICAgICAgICAgey8qIFN0YXRzICovfQogICAgICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGdhcDo4LG1hcmdpbkJvdHRvbToxMn19PgogICAgICAgICAgICB7W3tsOiJUb3RhbCBVc2FnZSIsdjp0b3RhbFVzYWdlLnRvRml4ZWQoMSksYzoiIzE2YTM0YSJ9LHtsOiJUb3RhbCBXYXN0YWdlIix2OnRvdGFsV2FzdGFnZS50b0ZpeGVkKDEpLGM6IiNkYzI2MjYifSx7bDoiRW50cmllcyIsdjplbnRyaWVzLmxlbmd0aCxjOiIjMjU2M2ViIn1dLm1hcCgocyxpKT0+PGRpdiBrZXk9e2l9IHN0eWxlPXt7ZmxleDoxLGJhY2tncm91bmQ6IiNmYWZhZjkiLGJvcmRlclJhZGl1czo4LHBhZGRpbmc6IjlweCAxMXB4Iix0ZXh0QWxpZ246ImNlbnRlciJ9fT4KICAgICAgICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTAsY29sb3I6IiM3ODcxNmMiLGZvbnRXZWlnaHQ6NjAwfX0+e3MubH08L2Rpdj4KICAgICAgICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTgsZm9udFdlaWdodDo4MDAsY29sb3I6cy5jfX0+e3Mudn08L2Rpdj4KICAgICAgICAgICAgPC9kaXY+KX0KICAgICAgICAgIDwvZGl2PgoKICAgICAgICAgIHsvKiBUYWJsZSAqL30KICAgICAgICAgIHtsb2FkaW5nPzxkaXYgc3R5bGU9e3t0ZXh0QWxpZ246ImNlbnRlciIscGFkZGluZzoiMjBweCIsY29sb3I6IiNhOGEyOWUifX0+PFNwaW4vPiBMb2FkaW5nLi4uPC9kaXY+OgogICAgICAgICAgZW50cmllcy5sZW5ndGg9PT0wPzxkaXYgc3R5bGU9e3t0ZXh0QWxpZ246ImNlbnRlciIscGFkZGluZzoiMjBweCIsY29sb3I6IiNhOGEyOWUiLGZvbnRTaXplOjEyfX0+Tm8gZW50cmllcyBpbiB0aGlzIHBlcmlvZC48L2Rpdj46CiAgICAgICAgICA8ZGl2IHN0eWxlPXt7b3ZlcmZsb3dYOiJhdXRvIn19PgogICAgICAgICAgICA8dGFibGUgc3R5bGU9e3t3aWR0aDoiMTAwJSIsYm9yZGVyQ29sbGFwc2U6ImNvbGxhcHNlIixmb250U2l6ZToxMX19PgogICAgICAgICAgICAgIDx0aGVhZD48dHIgc3R5bGU9e3tib3JkZXJCb3R0b206IjJweCBzb2xpZCAjZjVmNWY0In19PgogICAgICAgICAgICAgICAge1siRGF0ZSIsIk1hdGVyaWFsIiwiUXR5IiwiVHlwZSIsIkpvYiIsIlJlbWFya3MiXS5tYXAoaD0+PHRoIGtleT17aH0gc3R5bGU9e3t0ZXh0QWxpZ246ImxlZnQiLHBhZGRpbmc6IjAgOHB4IDZweCIsZm9udFNpemU6OSxmb250V2VpZ2h0OjgwMCxjb2xvcjoiI2E4YTI5ZSIsdGV4dFRyYW5zZm9ybToidXBwZXJjYXNlIix3aGl0ZVNwYWNlOiJub3dyYXAifX0+e2h9PC90aD4pfQogICAgICAgICAgICAgIDwvdHI+PC90aGVhZD4KICAgICAgICAgICAgICA8dGJvZHk+CiAgICAgICAgICAgICAgICB7ZW50cmllcy5zbGljZSgwLDUwKS5tYXAoKGUsaSk9Pjx0ciBrZXk9e2l9IHN0eWxlPXt7Ym9yZGVyQm90dG9tOiIxcHggc29saWQgI2ZhZmFmOSJ9fT4KICAgICAgICAgICAgICAgICAgPHRkIHN0eWxlPXt7cGFkZGluZzoiN3B4IDhweCIsY29sb3I6IiM3ODcxNmMiLHdoaXRlU3BhY2U6Im5vd3JhcCJ9fT57KGUudGltZXN0YW1wfHwiIikuc2xpY2UoMCwxNil9PC90ZD4KICAgICAgICAgICAgICAgICAgPHRkIHN0eWxlPXt7cGFkZGluZzoiN3B4IDhweCIsZm9udFdlaWdodDo2MDAsY29sb3I6IiMxYzE5MTcifX0+e2UubWF0ZXJpYWxfbmFtZX08L3RkPgogICAgICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI3cHggOHB4Iixmb250V2VpZ2h0OjcwMCxjb2xvcjp0eXBlQ29sb3JbZS50cmFuc2FjdGlvbl90eXBlXXx8IiM1NzUzNGUifX0+e2UucXVhbnRpdHl9IDxzcGFuIHN0eWxlPXt7Zm9udFNpemU6OSxjb2xvcjoiI2E4YTI5ZSJ9fT57ZS51b218fCIifTwvc3Bhbj48L3RkPgogICAgICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI3cHggOHB4In19PjxzcGFuIHN0eWxlPXt7Zm9udFNpemU6OSxmb250V2VpZ2h0OjgwMCxwYWRkaW5nOiIycHggN3B4Iixib3JkZXJSYWRpdXM6MjAsYmFja2dyb3VuZDplLnRyYW5zYWN0aW9uX3R5cGU9PT0iVXNhZ2UiPyIjZGNmY2U3IjplLnRyYW5zYWN0aW9uX3R5cGU9PT0iV2FzdGFnZSI/IiNmZWYyZjIiOiIjZWZmNmZmIixjb2xvcjp0eXBlQ29sb3JbZS50cmFuc2FjdGlvbl90eXBlXXx8IiM1NzUzNGUifX0+e2UudHJhbnNhY3Rpb25fdHlwZX08L3NwYW4+PC90ZD4KICAgICAgICAgICAgICAgICAgPHRkIHN0eWxlPXt7cGFkZGluZzoiN3B4IDhweCIsY29sb3I6IiM3ODcxNmMifX0+e2Uuam9iX2lkP2AjJHtlLmpvYl9pZH1gOiItIn08L3RkPgogICAgICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI3cHggOHB4Iixjb2xvcjoiIzc4NzE2YyIsbWF4V2lkdGg6MTIwLG92ZXJmbG93OiJoaWRkZW4iLHRleHRPdmVyZmxvdzoiZWxsaXBzaXMiLHdoaXRlU3BhY2U6Im5vd3JhcCJ9fT57ZS5yZW1hcmtzfHwiLSJ9PC90ZD4KICAgICAgICAgICAgICAgIDwvdHI+KX0KICAgICAgICAgICAgICA8L3Rib2R5PgogICAgICAgICAgICA8L3RhYmxlPgogICAgICAgICAgPC9kaXY+fQogICAgICAgIDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogIDwvUGc+Owp9CgovKiDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZAgUEFZTUVOVFMg4pWQ4pWQ4pWQICovCmZ1bmN0aW9uIFBheW1lbnRzKHthcGksdG9hc3QsdXNlcixyb2xlfSl7CiAgY29uc3RbcGF5cyxzZXRQYXlzXT11c2VTdGF0ZShbXSk7Y29uc3RbY3VzdHMsc2V0Q3VzdHNdPXVzZVN0YXRlKFtdKTtjb25zdFtqb2JzLHNldEpvYnNdPXVzZVN0YXRlKFtdKTsKICBjb25zdFtsb2FkaW5nLHNldExvYWRpbmddPXVzZVN0YXRlKHRydWUpO2NvbnN0W21vZGFsLHNldE1vZGFsXT11c2VTdGF0ZShmYWxzZSk7Y29uc3Rbc2F2aW5nLHNldFNhdmluZ109dXNlU3RhdGUoZmFsc2UpOwogIGNvbnN0W3NlYXJjaCxzZXRTZWFyY2hdPXVzZVN0YXRlKCIiKTtjb25zdFtwYWdlLHNldFBhZ2VdPXVzZVN0YXRlKDApOwogIGNvbnN0W2Zvcm0sc2V0Rm9ybV09dXNlU3RhdGUoe2N1c3RvbWVyX2lkOiIiLGpvYl9pZDoiIixhbW91bnQ6IiIscGF5bWVudF9kYXRlOlRPREFZKCkscGF5bWVudF9tb2RlOiJDYXNoIixub3RlczoiIn0pOwogIGNvbnN0IFBFUj0xNTsKICBjb25zdCBsb2FkPXVzZUNhbGxiYWNrKGFzeW5jKCk9PntzZXRMb2FkaW5nKHRydWUpO3RyeXtjb25zdFtwLGMsal09YXdhaXQgUHJvbWlzZS5hbGwoW2FwaS5wYXltZW50cygibGltaXQ9MjAwIiksYXBpLmN1c3RvbWVycygiIiwyMDApLGFwaS5qb2JzKCJsaW1pdD0yMDAiKV0pO3NldFBheXMocCk7c2V0Q3VzdHMoYyk7c2V0Sm9icyhqKTt9Y2F0Y2goZSl7dG9hc3QoZS5tZXNzYWdlLCJlcnJvciIpO31maW5hbGx5e3NldExvYWRpbmcoZmFsc2UpO307fSxbYXBpXSk7CiAgdXNlRWZmZWN0KCgpPT57bG9hZCgpO30sW2xvYWRdKTsKICBjb25zdCBmcD1wYXlzLmZpbHRlcihwPT4hc2VhcmNofHwocC5jdXN0b21lcl9uYW1lfHwiIikudG9Mb3dlckNhc2UoKS5pbmNsdWRlcyhzZWFyY2gudG9Mb3dlckNhc2UoKSkpOwogIGNvbnN0IHBhZ2VkPWZwLnNsaWNlKHBhZ2UqUEVSLChwYWdlKzEpKlBFUik7CiAgY29uc3QgdG90YWw9cGF5cy5yZWR1Y2UoKHMscCk9PnMrKHAuYW1vdW50fHwwKSwwKTsKICBjb25zdCB0b2RheUFtdD1wYXlzLmZpbHRlcihwPT5wLnBheW1lbnRfZGF0ZT09PVRPREFZKCkpLnJlZHVjZSgocyxwKT0+cytwLmFtb3VudCwwKTsKICBjb25zdCBjdXN0Sm9icz1qb2JzLmZpbHRlcihqPT5TdHJpbmcoai5jdXN0b21lcl9pZCk9PT1TdHJpbmcoZm9ybS5jdXN0b21lcl9pZCkmJmouYmFsYW5jZT4wKTsKICBjb25zdCBzYXZlPWFzeW5jKCk9PnsKICAgIGlmKCFmb3JtLmN1c3RvbWVyX2lkfHwhZm9ybS5hbW91bnQpe3RvYXN0KCJDdXN0b21lciAmIEFtb3VudCDgsIXgsLXgsLjgsLDgsIIiLCJlcnJvciIpO3JldHVybjt9CiAgICBzZXRTYXZpbmcodHJ1ZSk7CiAgICB0cnl7YXdhaXQgYXBpLmFkZFBheW1lbnQoey4uLmZvcm0sY3VzdG9tZXJfaWQ6TnVtYmVyKGZvcm0uY3VzdG9tZXJfaWQpLGFtb3VudDpOdW1iZXIoZm9ybS5hbW91bnQpLGpvYl9pZDpmb3JtLmpvYl9pZD9OdW1iZXIoZm9ybS5qb2JfaWQpOm51bGx9KTt0b2FzdChgJHtmbXQoZm9ybS5hbW91bnQpfSByZWNvcmRlZCFgKTtzZXRNb2RhbChmYWxzZSk7c2V0Rm9ybSh7Y3VzdG9tZXJfaWQ6IiIsam9iX2lkOiIiLGFtb3VudDoiIixwYXltZW50X2RhdGU6VE9EQVkoKSxwYXltZW50X21vZGU6IkNhc2giLG5vdGVzOiIifSk7bG9hZCgpO30KICAgIGNhdGNoKGUpe3RvYXN0KGUubWVzc2FnZSwiZXJyb3IiKTt9ZmluYWxseXtzZXRTYXZpbmcoZmFsc2UpO30KICB9OwogIHJldHVybjxQZz4KICAgIDxQYWdlSGRyIHRpdGxlPSJQYXltZW50cyIgc3ViPXtgJHtwYXlzLmxlbmd0aH0gcmVjb3JkcyDCtyAke2ZtdCh0b3RhbCl9IHRvdGFsYH0gYWN0aW9uPXsoKT0+c2V0TW9kYWwodHJ1ZSl9IGFjdGlvbkxhYmVsPSJSZWNvcmQgUGF5bWVudCIvPgogICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImdyaWQiLGdyaWRUZW1wbGF0ZUNvbHVtbnM6d2luZG93LmlubmVyV2lkdGg8PTc2OD8iMWZyIjoicmVwZWF0KDMsMWZyKSIsZ2FwOndpbmRvdy5pbm5lcldpZHRoPD03Njg/ODoxMCxtYXJnaW5Cb3R0b206MTR9fT4KICAgICAge1t7bDoiVG90YWwgQ29sbGVjdGVkIix2OmZtdCh0b3RhbCksYzoiIzE2YTM0YSJ9LHtsOiJUb2RheSdzIFJldmVudWUiLHY6Zm10KHRvZGF5QW10KSxjOkIucHJpfSx7bDoiVHJhbnNhY3Rpb25zIix2OnBheXMubGVuZ3RoLGM6IiMyNTYzZWIifV0ubWFwKChzLGkpPT48ZGl2IGtleT17aX0gc3R5bGU9e3tiYWNrZ3JvdW5kOiJ2YXIoLS1iZy1jYXJkKSIsYm9yZGVyOiIxcHggc29saWQgdmFyKC0tYm9yZGVyKSIsYm9yZGVyUmFkaXVzOjEwLHBhZGRpbmc6IjEzcHggMTVweCJ9fT48ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTAsY29sb3I6IiM3ODcxNmMiLGZvbnRXZWlnaHQ6NjAwLG1hcmdpbkJvdHRvbTo0fX0+e3MubH08L2Rpdj48ZGl2IHN0eWxlPXt7Zm9udFNpemU6MjAsZm9udFdlaWdodDo4MDAsY29sb3I6cy5jfX0+e3Mudn08L2Rpdj48L2Rpdj4pfQogICAgPC9kaXY+CiAgICA8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDoidmFyKC0tYmctY2FyZCkiLGJvcmRlcjoiMXB4IHNvbGlkIHZhcigtLWJvcmRlcikiLGJvcmRlclJhZGl1czoxMixwYWRkaW5nOiIxNHB4IDE2cHgifX0+CiAgICAgIDxkaXYgc3R5bGU9e3twb3NpdGlvbjoicmVsYXRpdmUiLG1heFdpZHRoOjI4MCxtYXJnaW5Cb3R0b206MTF9fT4KICAgICAgICA8c3BhbiBzdHlsZT17e3Bvc2l0aW9uOiJhYnNvbHV0ZSIsbGVmdDo4LHRvcDoiNTAlIix0cmFuc2Zvcm06InRyYW5zbGF0ZVkoLTUwJSkiLGNvbG9yOiIjYThhMjllIixmb250U2l6ZToxMn19PvCflI08L3NwYW4+CiAgICAgICAgPGlucHV0IHZhbHVlPXtzZWFyY2h9IG9uQ2hhbmdlPXtlPT57c2V0U2VhcmNoKGUudGFyZ2V0LnZhbHVlKTtzZXRQYWdlKDApO319IHBsYWNlaG9sZGVyPSJTZWFyY2ggY3VzdG9tZXIuLi4iIHN0eWxlPXt7Li4uSU5QLHBhZGRpbmdMZWZ0OjI2fX0vPgogICAgICA8L2Rpdj4KICAgICAgPGRpdiBzdHlsZT17e292ZXJmbG93WDoiYXV0byJ9fT4KICAgICAgICA8dGFibGUgc3R5bGU9e3t3aWR0aDoiMTAwJSIsYm9yZGVyQ29sbGFwc2U6ImNvbGxhcHNlIixmb250U2l6ZToxMn19PgogICAgICAgICAgPHRoZWFkPjx0ciBzdHlsZT17e2JvcmRlckJvdHRvbToiMnB4IHNvbGlkICNmNWY1ZjQifX0+CiAgICAgICAgICAgIHtbIiMiLCJDdXN0b21lciIsIkpvYiIsIkFtb3VudCIsIkRhdGUiLCJNb2RlIiwiTm90ZXMiXS5tYXAoaD0+PHRoIGtleT17aH0gc3R5bGU9e3t0ZXh0QWxpZ246ImxlZnQiLHBhZGRpbmc6IjAgOXB4IDdweCIsZm9udFNpemU6OSxmb250V2VpZ2h0OjgwMCxjb2xvcjoiI2E4YTI5ZSIsdGV4dFRyYW5zZm9ybToidXBwZXJjYXNlIixsZXR0ZXJTcGFjaW5nOiIuMDZlbSIsd2hpdGVTcGFjZToibm93cmFwIn19PntofTwvdGg+KX0KICAgICAgICAgIDwvdHI+PC90aGVhZD4KICAgICAgICAgIDx0Ym9keT4KICAgICAgICAgICAge2xvYWRpbmc/WzEsMiwzXS5tYXAoaT0+PHRyIGtleT17aX0+PHRkIGNvbFNwYW49ezd9IHN0eWxlPXt7cGFkZGluZzoiMTBweCJ9fT48U2tlbCBoPXsxMn0vPjwvdGQ+PC90cj4pOgogICAgICAgICAgICBwYWdlZC5sZW5ndGg9PT0wPzx0cj48dGQgY29sU3Bhbj17N30gc3R5bGU9e3twYWRkaW5nOiIyOHB4Iix0ZXh0QWxpZ246ImNlbnRlciIsY29sb3I6IiNhOGEyOWUiLGZvbnRTaXplOjEyfX0+Tm8gcGF5bWVudHMgZm91bmQuPC90ZD48L3RyPjoKICAgICAgICAgICAgcGFnZWQubWFwKHA9Pjx0ciBrZXk9e3AuaWR9IHN0eWxlPXt7Ym9yZGVyQm90dG9tOiIxcHggc29saWQgI2ZhZmFmOSJ9fSBvbk1vdXNlRW50ZXI9e2U9PmUuY3VycmVudFRhcmdldC5zdHlsZS5iYWNrZ3JvdW5kPSIjZmFmYWY5In0gb25Nb3VzZUxlYXZlPXtlPT5lLmN1cnJlbnRUYXJnZXQuc3R5bGUuYmFja2dyb3VuZD0idHJhbnNwYXJlbnQifT4KICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI5cHgiLGNvbG9yOiIjYThhMjllIixmb250U2l6ZToxMH19PiN7cC5pZH08L3RkPgogICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCIsZm9udFdlaWdodDo2MDAsY29sb3I6IiMxYzE5MTcifX0+e3AuY3VzdG9tZXJfbmFtZXx8IuKAlCJ9PC90ZD4KICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI5cHgiLGNvbG9yOkIucHJpLGZvbnRXZWlnaHQ6NzAwfX0+e3Auam9iX2lkP2AjJHtwLmpvYl9pZH1gOiLigJQifTwvdGQ+CiAgICAgICAgICAgICAgPHRkIHN0eWxlPXt7cGFkZGluZzoiOXB4Iixmb250V2VpZ2h0OjgwMCxjb2xvcjoiIzE2YTM0YSJ9fT57Zm10KHAuYW1vdW50KX08L3RkPgogICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCIsY29sb3I6IiM1NzUzNGUiLGZvbnRTaXplOjExfX0+e3AucGF5bWVudF9kYXRlfTwvdGQ+CiAgICAgICAgICAgICAgPHRkIHN0eWxlPXt7cGFkZGluZzoiOXB4In19PjxzcGFuIHN0eWxlPXt7Zm9udFNpemU6OSxmb250V2VpZ2h0OjgwMCxwYWRkaW5nOiIycHggN3B4Iixib3JkZXJSYWRpdXM6MjAsYmFja2dyb3VuZDoiI2YwZmRmNCIsY29sb3I6IiMxNTgwM2QiLGJvcmRlcjoiMXB4IHNvbGlkICM4NmVmYWMifX0+e3AucGF5bWVudF9tb2RlfHwiQ2FzaCJ9PC9zcGFuPjwvdGQ+CiAgICAgICAgICAgICAgPHRkIHN0eWxlPXt7cGFkZGluZzoiOXB4Iixjb2xvcjoiIzc4NzE2YyIsbWF4V2lkdGg6MTIwLG92ZXJmbG93OiJoaWRkZW4iLHRleHRPdmVyZmxvdzoiZWxsaXBzaXMiLHdoaXRlU3BhY2U6Im5vd3JhcCJ9fT57cC5ub3Rlc3x8IuKAlCJ9PC90ZD4KICAgICAgICAgICAgPC90cj4pfQogICAgICAgICAgPC90Ym9keT4KICAgICAgICA8L3RhYmxlPgogICAgICA8L2Rpdj4KICAgICAgPFBhZ2VyIHBhZ2U9e3BhZ2V9IHRvdGFsPXtmcC5sZW5ndGh9IHBlcj17UEVSfSBvbkNoYW5nZT17c2V0UGFnZX0vPgogICAgPC9kaXY+CiAgICB7bW9kYWwmJjxNb2RhbCB0aXRsZT0iUmVjb3JkIFBheW1lbnQiIG9uQ2xvc2U9eygpPT5zZXRNb2RhbChmYWxzZSl9IHc9ezQ0MH0+CiAgICAgIDxGbGQgbGFiZWw9IkN1c3RvbWVyIiByZXE+PEN1c3RTZWFyY2ggY3VzdHM9e2N1c3RzfSB2YWx1ZT17Zm9ybS5jdXN0b21lcl9pZH0gb25DaGFuZ2U9e3Y9PnNldEZvcm0oZj0+KHsuLi5mLGN1c3RvbWVyX2lkOnYsam9iX2lkOiIifSkpfS8+PC9GbGQ+CiAgICAgIHtmb3JtLmN1c3RvbWVyX2lkJiZjdXN0Sm9icy5sZW5ndGg+MCYmPEZsZCBsYWJlbD0iTGluayBKb2IgKG9wdGlvbmFsKSI+PHNlbGVjdCB2YWx1ZT17Zm9ybS5qb2JfaWR9IG9uQ2hhbmdlPXtlPT5zZXRGb3JtKGY9Pih7Li4uZixqb2JfaWQ6ZS50YXJnZXQudmFsdWV9KSl9IHN0eWxlPXtTRUx9PjxvcHRpb24gdmFsdWU9IiI+LS0gTm8gc3BlY2lmaWMgam9iIC0tPC9vcHRpb24+e2N1c3RKb2JzLm1hcChqPT48b3B0aW9uIGtleT17ai5pZH0gdmFsdWU9e2ouaWR9PiN7ai5pZH0ge2ouam9iX3R5cGV9IOKAlCB7Zm10KGouYmFsYW5jZSl9IGR1ZTwvb3B0aW9uPil9PC9zZWxlY3Q+PC9GbGQ+fQogICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZ3JpZCIsZ3JpZFRlbXBsYXRlQ29sdW1uczoiMWZyIDFmciIsZ2FwOiIwIDEzcHgifX0+CiAgICAgICAgPEZsZCBsYWJlbD0iQW1vdW50ICjigrkpIiByZXE+PGlucHV0IHR5cGU9Im51bWJlciIgdmFsdWU9e2Zvcm0uYW1vdW50fSBvbkNoYW5nZT17ZT0+c2V0Rm9ybShmPT4oey4uLmYsYW1vdW50OmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17SU5QfSBwbGFjZWhvbGRlcj0iMC4wMCIvPjwvRmxkPgogICAgICAgIDxGbGQgbGFiZWw9IkRhdGUiPjxpbnB1dCB0eXBlPSJkYXRlIiB2YWx1ZT17Zm9ybS5wYXltZW50X2RhdGV9IG9uQ2hhbmdlPXtlPT5zZXRGb3JtKGY9Pih7Li4uZixwYXltZW50X2RhdGU6ZS50YXJnZXQudmFsdWV9KSl9IHN0eWxlPXtJTlB9Lz48L0ZsZD4KICAgICAgICA8RmxkIGxhYmVsPSJNb2RlIj48c2VsZWN0IHZhbHVlPXtmb3JtLnBheW1lbnRfbW9kZX0gb25DaGFuZ2U9e2U9PnNldEZvcm0oZj0+KHsuLi5mLHBheW1lbnRfbW9kZTplLnRhcmdldC52YWx1ZX0pKX0gc3R5bGU9e1NFTH0+e1siQ2FzaCIsIlVQSSIsIkNhcmQiLCJDaGVxdWUiLCJCYW5rIFRyYW5zZmVyIiwiT3RoZXIiXS5tYXAobT0+PG9wdGlvbiBrZXk9e219PnttfTwvb3B0aW9uPil9PC9zZWxlY3Q+PC9GbGQ+CiAgICAgICAgPEZsZCBsYWJlbD0iTm90ZXMiPjxpbnB1dCB2YWx1ZT17Zm9ybS5ub3Rlc30gb25DaGFuZ2U9e2U9PnNldEZvcm0oZj0+KHsuLi5mLG5vdGVzOmUudGFyZ2V0LnZhbHVlfSkpfSBzdHlsZT17SU5QfSBwbGFjZWhvbGRlcj0iT3B0aW9uYWwiLz48L0ZsZD4KICAgICAgPC9kaXY+CiAgICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixnYXA6OCxqdXN0aWZ5Q29udGVudDoiZmxleC1lbmQiLG1hcmdpblRvcDo0fX0+PGJ1dHRvbiBvbkNsaWNrPXsoKT0+c2V0TW9kYWwoZmFsc2UpfSBzdHlsZT17QlROKCJnaG9zdCIpfT5DYW5jZWw8L2J1dHRvbj48YnV0dG9uIG9uQ2xpY2s9e3NhdmV9IGRpc2FibGVkPXtzYXZpbmd9IHN0eWxlPXtCVE4oKX0+e3NhdmluZz88U3Bpbi8+OiJSZWNvcmQgUGF5bWVudCJ9PC9idXR0b24+PC9kaXY+CiAgICA8L01vZGFsPn0KICA8L1BnPjsKfQoKLyog4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQIElOVkVOVE9SWSDilZDilZDilZAgKi8KZnVuY3Rpb24gSW52ZW50b3J5KHthcGksdG9hc3QsdXNlcixyb2xlfSl7CiAgY29uc3RbaXRlbXMsc2V0SXRlbXNdPXVzZVN0YXRlKFtdKTtjb25zdFtsb2FkaW5nLHNldExvYWRpbmddPXVzZVN0YXRlKHRydWUpOwogIGNvbnN0W3NlYXJjaCxzZXRTZWFyY2hdPXVzZVN0YXRlKCIiKTtjb25zdFtzdE1vZGFsLHNldFN0TW9kYWxdPXVzZVN0YXRlKG51bGwpOwogIGNvbnN0W3NhdmluZyxzZXRTYXZpbmddPXVzZVN0YXRlKGZhbHNlKTtjb25zdFtxdHksc2V0UXR5XT11c2VTdGF0ZSgiIik7Y29uc3Rbbm90ZXMsc2V0Tm90ZXNdPXVzZVN0YXRlKCIiKTtjb25zdFttb2RlLHNldE1vZGVdPXVzZVN0YXRlKCJhZGQiKTsKICBjb25zdCBsb2FkPXVzZUNhbGxiYWNrKGFzeW5jKCk9PntzZXRMb2FkaW5nKHRydWUpO3RyeXtzZXRJdGVtcyhhd2FpdCBhcGkuaW52ZW50b3J5KCkpO31jYXRjaChlKXt0b2FzdChlLm1lc3NhZ2UsImVycm9yIik7fWZpbmFsbHl7c2V0TG9hZGluZyhmYWxzZSk7fTt9LFthcGldKTsKICB1c2VFZmZlY3QoKCk9Pntsb2FkKCk7fSxbbG9hZF0pOwogIGNvbnN0IGZpPWl0ZW1zLmZpbHRlcihpPT4hc2VhcmNofHxpLm5hbWUudG9Mb3dlckNhc2UoKS5pbmNsdWRlcyhzZWFyY2gudG9Mb3dlckNhc2UoKSl8fChpLmNhdGVnb3J5X25hbWV8fCIiKS50b0xvd2VyQ2FzZSgpLmluY2x1ZGVzKHNlYXJjaC50b0xvd2VyQ2FzZSgpKSk7CiAgY29uc3QgbG93PWl0ZW1zLmZpbHRlcihpPT5pLmN1cnJlbnRfc3RvY2s8PWkucmVvcmRlcl9sZXZlbCkubGVuZ3RoOwogIGNvbnN0IHNjPWl0ZW09Pml0ZW0uY3VycmVudF9zdG9jazw9MD8iI2RjMjYyNiI6aXRlbS5jdXJyZW50X3N0b2NrPD1pdGVtLnJlb3JkZXJfbGV2ZWw/IiNmNTllMGIiOiIjMTZhMzRhIjsKICBjb25zdCB1cGRhdGU9YXN5bmMoKT0+ewogICAgaWYoIXF0eSl7dG9hc3QoIlF1YW50aXR5IGVudGVyIOCwmuCxh+Cwr+CwguCwoeCwvyIsImVycm9yIik7cmV0dXJuO30KICAgIHNldFNhdmluZyh0cnVlKTsKICAgIHRyeXthd2FpdCBhcGkudXBkYXRlU3RvY2soc3RNb2RhbC5pZCxtb2RlPT09ImFkZCI/TnVtYmVyKHF0eSk6LU51bWJlcihxdHkpLG5vdGVzKTt0b2FzdCgiU3RvY2sgdXBkYXRlZCEiKTtzZXRTdE1vZGFsKG51bGwpO3NldFF0eSgiIik7c2V0Tm90ZXMoIiIpO2xvYWQoKTt9CiAgICBjYXRjaChlKXt0b2FzdChlLm1lc3NhZ2UsImVycm9yIik7fWZpbmFsbHl7c2V0U2F2aW5nKGZhbHNlKTt9CiAgfTsKICByZXR1cm48UGc+CiAgICA8UGFnZUhkciB0aXRsZT0iSW52ZW50b3J5IiBzdWI9e2Ake2l0ZW1zLmxlbmd0aH0gaXRlbXMgwrcgJHtsb3c+MD9gJHtsb3d9IGxvdyBzdG9ja2A6IkFsbCBPSyJ9YH0vPgogICAgPGRpdiBzdHlsZT17e2JhY2tncm91bmQ6InZhcigtLWJnLWNhcmQpIixib3JkZXI6IjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpIixib3JkZXJSYWRpdXM6MTIscGFkZGluZzoiMTRweCAxNnB4In19PgogICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsZ2FwOjgsbWFyZ2luQm90dG9tOjExfX0+CiAgICAgICAgPGRpdiBzdHlsZT17e3Bvc2l0aW9uOiJyZWxhdGl2ZSIsZmxleDoxLG1heFdpZHRoOjI4MH19PgogICAgICAgICAgPHNwYW4gc3R5bGU9e3twb3NpdGlvbjoiYWJzb2x1dGUiLGxlZnQ6OCx0b3A6IjUwJSIsdHJhbnNmb3JtOiJ0cmFuc2xhdGVZKC01MCUpIixjb2xvcjoiI2E4YTI5ZSIsZm9udFNpemU6MTJ9fT7wn5SNPC9zcGFuPgogICAgICAgICAgPGlucHV0IHZhbHVlPXtzZWFyY2h9IG9uQ2hhbmdlPXtlPT5zZXRTZWFyY2goZS50YXJnZXQudmFsdWUpfSBwbGFjZWhvbGRlcj0iU2VhcmNoIGl0ZW1zLi4uIiBzdHlsZT17ey4uLklOUCxwYWRkaW5nTGVmdDoyNn19Lz4KICAgICAgICA8L2Rpdj4KICAgICAgICA8YnV0dG9uIG9uQ2xpY2s9e2xvYWR9IHN0eWxlPXt7Li4uQlROKCJnaG9zdCIpLHBhZGRpbmc6IjlweCAxMnB4Iixmb250U2l6ZToxMX19PuKGuyBSZWZyZXNoPC9idXR0b24+CiAgICAgIDwvZGl2PgogICAgICA8ZGl2IHN0eWxlPXt7b3ZlcmZsb3dYOiJhdXRvIn19PgogICAgICAgIDx0YWJsZSBzdHlsZT17e3dpZHRoOiIxMDAlIixib3JkZXJDb2xsYXBzZToiY29sbGFwc2UiLGZvbnRTaXplOjEyfX0+CiAgICAgICAgICA8dGhlYWQ+PHRyIHN0eWxlPXt7Ym9yZGVyQm90dG9tOiIycHggc29saWQgI2Y1ZjVmNCJ9fT4KICAgICAgICAgICAge1siSXRlbSIsIkNhdGVnb3J5IiwiU3RvY2siLCJVbml0IiwiUmVvcmRlciBMdmwiLCJWZW5kb3IiLCJTdGF0dXMiLCIiXS5tYXAoaD0+PHRoIGtleT17aH0gc3R5bGU9e3t0ZXh0QWxpZ246ImxlZnQiLHBhZGRpbmc6IjAgOXB4IDdweCIsZm9udFNpemU6OSxmb250V2VpZ2h0OjgwMCxjb2xvcjoiI2E4YTI5ZSIsdGV4dFRyYW5zZm9ybToidXBwZXJjYXNlIixsZXR0ZXJTcGFjaW5nOiIuMDZlbSIsd2hpdGVTcGFjZToibm93cmFwIn19PntofTwvdGg+KX0KICAgICAgICAgIDwvdHI+PC90aGVhZD4KICAgICAgICAgIDx0Ym9keT4KICAgICAgICAgICAge2xvYWRpbmc/WzEsMiwzLDRdLm1hcChpPT48dHIga2V5PXtpfT48dGQgY29sU3Bhbj17OH0gc3R5bGU9e3twYWRkaW5nOiIxMHB4In19PjxTa2VsIGg9ezEyfS8+PC90ZD48L3RyPik6CiAgICAgICAgICAgIGZpLmxlbmd0aD09PTA/PHRyPjx0ZCBjb2xTcGFuPXs4fSBzdHlsZT17e3BhZGRpbmc6IjI4cHgiLHRleHRBbGlnbjoiY2VudGVyIixjb2xvcjoiI2E4YTI5ZSJ9fT5ObyBpdGVtcyBmb3VuZC48L3RkPjwvdHI+OgogICAgICAgICAgICBmaS5tYXAoaXRlbT0+e2NvbnN0IGlzTG93PWl0ZW0uY3VycmVudF9zdG9jazw9aXRlbS5yZW9yZGVyX2xldmVsO2NvbnN0IGM9c2MoaXRlbSk7cmV0dXJuKAogICAgICAgICAgICAgIDx0ciBrZXk9e2l0ZW0uaWR9IHN0eWxlPXt7Ym9yZGVyQm90dG9tOiIxcHggc29saWQgI2ZhZmFmOSIsYmFja2dyb3VuZDppdGVtLmN1cnJlbnRfc3RvY2s8PTA/IiNmZWYyZjIiOmlzTG93PyIjZmZmYmViIjoidHJhbnNwYXJlbnQifX0+CiAgICAgICAgICAgICAgICA8dGQgc3R5bGU9e3twYWRkaW5nOiI5cHgiLGZvbnRXZWlnaHQ6NzAwLGNvbG9yOiIjMWMxOTE3In19PntpdGVtLm5hbWV9PC90ZD4KICAgICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCIsY29sb3I6IiM3ODcxNmMifX0+e2l0ZW0uY2F0ZWdvcnlfbmFtZXx8IuKAlCJ9PC90ZD4KICAgICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCIsZm9udFdlaWdodDo4MDAsY29sb3I6Yyxmb250U2l6ZToxNH19PntpdGVtLmN1cnJlbnRfc3RvY2t9PC90ZD4KICAgICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCIsY29sb3I6IiM3ODcxNmMifX0+e2l0ZW0udW5pdF9vZl9tZWFzdXJlfHxpdGVtLnVvbXx8IuKAlCJ9PC90ZD4KICAgICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCIsY29sb3I6IiM3ODcxNmMifX0+e2l0ZW0ucmVvcmRlcl9sZXZlbHx8IuKAlCJ9PC90ZD4KICAgICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCIsY29sb3I6IiM3ODcxNmMiLG1heFdpZHRoOjkwLG92ZXJmbG93OiJoaWRkZW4iLHRleHRPdmVyZmxvdzoiZWxsaXBzaXMiLHdoaXRlU3BhY2U6Im5vd3JhcCJ9fT57aXRlbS52ZW5kb3JfbmFtZXx8IuKAlCJ9PC90ZD4KICAgICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCJ9fT48c3BhbiBzdHlsZT17e2ZvbnRTaXplOjksZm9udFdlaWdodDo4MDAscGFkZGluZzoiMnB4IDdweCIsYm9yZGVyUmFkaXVzOjIwLGJhY2tncm91bmQ6aXRlbS5jdXJyZW50X3N0b2NrPD0wPyIjZmVmMmYyIjppc0xvdz8iI2ZmZmJlYiI6IiNmMGZkZjQiLGNvbG9yOmMsYm9yZGVyOmAxcHggc29saWQgJHtpdGVtLmN1cnJlbnRfc3RvY2s8PTA/IiNmY2E1YTUiOmlzTG93PyIjZmNkMzRkIjoiIzg2ZWZhYyJ9YH19PntpdGVtLmN1cnJlbnRfc3RvY2s8PTA/Ik91dCBvZiBTdG9jayI6aXNMb3c/IkxvdyBTdG9jayI6IkluIFN0b2NrIn08L3NwYW4+PC90ZD4KICAgICAgICAgICAgICAgIDx0ZCBzdHlsZT17e3BhZGRpbmc6IjlweCJ9fT48YnV0dG9uIG9uQ2xpY2s9eygpPT57c2V0U3RNb2RhbChpdGVtKTtzZXRRdHkoIiIpO3NldE5vdGVzKCIiKTtzZXRNb2RlKCJhZGQiKTt9fSBzdHlsZT17e2ZvbnRTaXplOjEwLGNvbG9yOkIucHJpLGZvbnRXZWlnaHQ6NzAwLGJhY2tncm91bmQ6Im5vbmUiLGJvcmRlcjpgMXB4IHNvbGlkICR7Qi5wcmlNfWAsYm9yZGVyUmFkaXVzOjUscGFkZGluZzoiM3B4IDhweCIsY3Vyc29yOiJwb2ludGVyIn19PlVwZGF0ZTwvYnV0dG9uPjwvdGQ+CiAgICAgICAgICAgICAgPC90cj4pO30pfQogICAgICAgICAgPC90Ym9keT4KICAgICAgICA8L3RhYmxlPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAge3N0TW9kYWwmJjxNb2RhbCB0aXRsZT17YFN0b2NrIFVwZGF0ZSDigJQgJHtzdE1vZGFsLm5hbWV9YH0gb25DbG9zZT17KCk9PnNldFN0TW9kYWwobnVsbCl9IHc9ezM4MH0+CiAgICAgIDxkaXYgc3R5bGU9e3tiYWNrZ3JvdW5kOiIjZmFmYWY5Iixib3JkZXJSYWRpdXM6OCxwYWRkaW5nOiI5cHggMTJweCIsbWFyZ2luQm90dG9tOjEyLGRpc3BsYXk6ImZsZXgiLGp1c3RpZnlDb250ZW50OiJzcGFjZS1iZXR3ZWVuIixhbGlnbkl0ZW1zOiJjZW50ZXIifX0+CiAgICAgICAgPHNwYW4gc3R5bGU9e3tmb250U2l6ZToxMSxjb2xvcjoiIzc4NzE2YyJ9fT5DdXJyZW50IFN0b2NrPC9zcGFuPgogICAgICAgIDxzcGFuIHN0eWxlPXt7Zm9udFNpemU6MTgsZm9udFdlaWdodDo4MDAsY29sb3I6c2Moc3RNb2RhbCl9fT57c3RNb2RhbC5jdXJyZW50X3N0b2NrfSB7c3RNb2RhbC51bml0X29mX21lYXN1cmV8fCIifTwvc3Bhbj4KICAgICAgPC9kaXY+CiAgICAgIDxGbGQgbGFiZWw9IlRyYW5zYWN0aW9uIFR5cGUiPgogICAgICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJncmlkIixncmlkVGVtcGxhdGVDb2x1bW5zOiIxZnIgMWZyIixnYXA6N319PgogICAgICAgICAge1t7djoiYWRkIixsOiLinpUgQWRkIFN0b2NrIn0se3Y6InVzZSIsbDoi4p6WIFVzZSAvIElzc3VlIn1dLm1hcChvPT48YnV0dG9uIGtleT17by52fSBvbkNsaWNrPXsoKT0+c2V0TW9kZShvLnYpfSBzdHlsZT17e3BhZGRpbmc6IjlweCAwIixib3JkZXJSYWRpdXM6Nyxib3JkZXI6bW9kZT09PW8udj9gMnB4IHNvbGlkICR7Qi5wcml9YDoiMXB4IHNvbGlkICNlN2U1ZTQiLGJhY2tncm91bmQ6bW9kZT09PW8udj9CLnByaUw6IiNmZmYiLGNvbG9yOm1vZGU9PT1vLnY/Qi5wcmlEOiIjNTc1MzRlIixmb250U2l6ZToxMSxmb250V2VpZ2h0Om1vZGU9PT1vLnY/NzAwOjUwMCxjdXJzb3I6InBvaW50ZXIifX0+e28ubH08L2J1dHRvbj4pfQogICAgICAgIDwvZGl2PgogICAgICA8L0ZsZD4KICAgICAgPEZsZCBsYWJlbD0iUXVhbnRpdHkiIHJlcT48aW5wdXQgdHlwZT0ibnVtYmVyIiB2YWx1ZT17cXR5fSBvbkNoYW5nZT17ZT0+c2V0UXR5KGUudGFyZ2V0LnZhbHVlKX0gc3R5bGU9e0lOUH0gbWluPSIwLjAxIiBzdGVwPSIwLjAxIiBwbGFjZWhvbGRlcj0iMCIvPjwvRmxkPgogICAgICB7cXR5JiY8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDptb2RlPT09ImFkZCI/IiNmMGZkZjQiOiIjZmVmMmYyIixib3JkZXJSYWRpdXM6NyxwYWRkaW5nOiI4cHggMTJweCIsbWFyZ2luQm90dG9tOjExLGZvbnRTaXplOjEyLGZvbnRXZWlnaHQ6NzAwLGNvbG9yOm1vZGU9PT0iYWRkIj8iIzE1ODAzZCI6IiNkYzI2MjYifX0+TmV3IHN0b2NrOiB7bW9kZT09PSJhZGQiPytzdE1vZGFsLmN1cnJlbnRfc3RvY2srICtxdHk6K3N0TW9kYWwuY3VycmVudF9zdG9jay0gK3F0eX0ge3N0TW9kYWwudW5pdF9vZl9tZWFzdXJlfHwiIn08L2Rpdj59CiAgICAgIDxGbGQgbGFiZWw9Ik5vdGVzIj48aW5wdXQgdmFsdWU9e25vdGVzfSBvbkNoYW5nZT17ZT0+c2V0Tm90ZXMoZS50YXJnZXQudmFsdWUpfSBzdHlsZT17SU5QfSBwbGFjZWhvbGRlcj0iU3VwcGxpZXIsIHJlYXNvbi4uLiIvPjwvRmxkPgogICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsZ2FwOjgsanVzdGlmeUNvbnRlbnQ6ImZsZXgtZW5kIn19PjxidXR0b24gb25DbGljaz17KCk9PnNldFN0TW9kYWwobnVsbCl9IHN0eWxlPXtCVE4oImdob3N0Iil9PkNhbmNlbDwvYnV0dG9uPjxidXR0b24gb25DbGljaz17dXBkYXRlfSBkaXNhYmxlZD17c2F2aW5nfSBzdHlsZT17QlROKCl9PntzYXZpbmc/PFNwaW4vPjoiVXBkYXRlIFN0b2NrIn08L2J1dHRvbj48L2Rpdj4KICAgIDwvTW9kYWw+fQogIDwvUGc+Owp9CgovKiDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZDilZAgUkVQT1JUUyDilZDilZDilZAgKi8KZnVuY3Rpb24gUmVwb3J0cyh7YXBpLHJvbGUsdG9hc3R9KXsKICBjb25zdFt0YWIsc2V0VGFiXT11c2VTdGF0ZSgiZGFpbHkiKTtjb25zdFtkYXRlLHNldERhdGVdPXVzZVN0YXRlKFRPREFZKCkpOwogIGNvbnN0W3JlcG9ydCxzZXRSZXBvcnRdPXVzZVN0YXRlKG51bGwpO2NvbnN0W2xvZyxzZXRMb2ddPXVzZVN0YXRlKFtdKTtjb25zdFtsb2FkaW5nLHNldExvYWRpbmddPXVzZVN0YXRlKGZhbHNlKTsKICBjb25zdFthbGxKb2JzLHNldEFsbEpvYnNdPXVzZVN0YXRlKFtdKTtjb25zdFtzdGFmZkxpc3Qsc2V0U3RhZmZMaXN0XT11c2VTdGF0ZShbXSk7CiAgY29uc3QgZmV0Y2hEPXVzZUNhbGxiYWNrKGFzeW5jKCk9PntzZXRMb2FkaW5nKHRydWUpO3RyeXtzZXRSZXBvcnQoYXdhaXQgYXBpLmRhaWx5UmVwb3J0KGRhdGUpKTt9Y2F0Y2goZSl7dG9hc3QoZS5tZXNzYWdlLCJlcnJvciIpO31maW5hbGx5e3NldExvYWRpbmcoZmFsc2UpO307fSxbYXBpLGRhdGVdKTsKICBjb25zdCBmZXRjaEw9YXN5bmMoKT0+e3NldExvYWRpbmcodHJ1ZSk7dHJ5e3NldExvZyhhd2FpdCBhcGkuYWN0aXZpdHlMb2coODApKTt9Y2F0Y2goZSl7dG9hc3QoZS5tZXNzYWdlLCJlcnJvciIpO31maW5hbGx5e3NldExvYWRpbmcoZmFsc2UpO307fTsKICBjb25zdCBmZXRjaFBlcmY9YXN5bmMoKT0+e3NldExvYWRpbmcodHJ1ZSk7dHJ5e2NvbnN0W2osc109YXdhaXQgUHJvbWlzZS5hbGwoW2FwaS5qb2JzKCJsaW1pdD01MDAiKSxhcGkuc3RhZmZMaXN0KCldKTtzZXRBbGxKb2JzKGopO3NldFN0YWZmTGlzdChzKTt9Y2F0Y2goZSl7dG9hc3QoZS5tZXNzYWdlLCJlcnJvciIpO31maW5hbGx5e3NldExvYWRpbmcoZmFsc2UpO307fTsKICB1c2VFZmZlY3QoKCk9PntpZih0YWI9PT0iZGFpbHkiKWZldGNoRCgpO2Vsc2UgaWYodGFiPT09ImxvZyIpZmV0Y2hMKCk7ZWxzZSBpZih0YWI9PT0icGVyZiIpZmV0Y2hQZXJmKCk7fSxbdGFiLGRhdGVdKTsKICByZXR1cm48UGc+CiAgICA8ZGl2IHN0eWxlPXt7bWFyZ2luQm90dG9tOjE2fX0+PGgyIHN0eWxlPXt7Zm9udFNpemU6MTksZm9udFdlaWdodDo4MDAsY29sb3I6IiMxYzE5MTciLG1hcmdpbjowfX0+UmVwb3J0czwvaDI+PHAgc3R5bGU9e3tmb250U2l6ZToxMSxjb2xvcjoiIzc4NzE2YyIsbWFyZ2luOiIycHggMCAwIn19PkJ1c2luZXNzIGluc2lnaHRzICYgYWN0aXZpdHk8L3A+PC9kaXY+CiAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsZ2FwOjUsbWFyZ2luQm90dG9tOjE0fX0+CiAgICAgIHtbe3Y6ImRhaWx5IixsOiLwn5OKIERhaWx5IFJlcG9ydCJ9LHt2OiJsb2ciLGw6IvCfk4sgQWN0aXZpdHkgTG9nIn0se3Y6InBlcmYiLGw6IvCfkaQgU3RhZmYgUGVyZm9ybWFuY2UifV0ubWFwKHQ9PjxidXR0b24ga2V5PXt0LnZ9IG9uQ2xpY2s9eygpPT5zZXRUYWIodC52KX0gc3R5bGU9e3twYWRkaW5nOiI3cHggMTRweCIsYm9yZGVyUmFkaXVzOjIwLGZvbnRTaXplOjExLGZvbnRXZWlnaHQ6NzAwLGN1cnNvcjoicG9pbnRlciIsYm9yZGVyOnRhYj09PXQudj9gMXB4IHNvbGlkICR7Qi5wcml9YDoiMXB4IHNvbGlkICNlN2U1ZTQiLGJhY2tncm91bmQ6dGFiPT09dC52P0IucHJpTDoiI2ZmZiIsY29sb3I6dGFiPT09dC52P0IucHJpRDoiIzc4NzE2YyJ9fT57dC5sfTwvYnV0dG9uPil9CiAgICA8L2Rpdj4KICAgIHt0YWI9PT0iZGFpbHkiJiY8PgogICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsZ2FwOjgsbWFyZ2luQm90dG9tOjE0LGFsaWduSXRlbXM6ImNlbnRlciJ9fT4KICAgICAgICA8aW5wdXQgdHlwZT0iZGF0ZSIgdmFsdWU9e2RhdGV9IG9uQ2hhbmdlPXtlPT5zZXREYXRlKGUudGFyZ2V0LnZhbHVlKX0gc3R5bGU9e3suLi5JTlAsd2lkdGg6ImF1dG8ifX0gbWF4PXtUT0RBWSgpfS8+CiAgICAgICAgPGJ1dHRvbiBvbkNsaWNrPXtmZXRjaER9IHN0eWxlPXtCVE4oKX0+TG9hZCBSZXBvcnQ8L2J1dHRvbj4KICAgICAgPC9kaXY+CiAgICAgIHtsb2FkaW5nPzxkaXYgc3R5bGU9e3tkaXNwbGF5OiJncmlkIixncmlkVGVtcGxhdGVDb2x1bW5zOiJyZXBlYXQoMywxZnIpIixnYXA6MTB9fT57WzEsMiwzLDQsNSw2XS5tYXAoaT0+PGRpdiBrZXk9e2l9IHN0eWxlPXt7YmFja2dyb3VuZDoidmFyKC0tYmctY2FyZCkiLGJvcmRlcjoiMXB4IHNvbGlkIHZhcigtLWJvcmRlcikiLGJvcmRlclJhZGl1czoxMCxwYWRkaW5nOiIxNnB4In19PjxTa2VsIGg9ezQwfS8+PC9kaXY+KX08L2Rpdj46CiAgICAgIHJlcG9ydCYmPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImdyaWQiLGdyaWRUZW1wbGF0ZUNvbHVtbnM6InJlcGVhdCgzLDFmcikiLGdhcDoxMH19PgogICAgICAgIHtbe2w6Ik5ldyBDdXN0b21lcnMiLHY6cmVwb3J0Lm5ld19jdXN0b21lcnMsYzpCLnByaSxlOiLwn5GlIn0sCiAgICAgICAgICB7bDoiTmV3IEpvYnMiLHY6cmVwb3J0Lm5ld19qb2JzLGM6IiMyNTYzZWIiLGU6IvCfk4sifSwKICAgICAgICAgIHtsOiJKb2JzIENvbXBsZXRlZCIsdjpyZXBvcnQuam9ic19jb21wbGV0ZWQsYzoiIzE2YTM0YSIsZToi4pyFIn0sCiAgICAgICAgICB7bDoiUGF5bWVudHMgQ291bnQiLHY6cmVwb3J0LnBheW1lbnRzX2NvdW50LGM6IiM3YzNhZWQiLGU6IvCfkrMifSwKICAgICAgICAgIHtsOiJSZXZlbnVlIix2OmZtdChyZXBvcnQucGF5bWVudHNfdG90YWwpLGM6IiMxNmEzNGEiLGU6IuKCuSIsYmlnOnRydWV9LAogICAgICAgICAge2w6IlJlcG9ydCBEYXRlIix2OnJlcG9ydC5kYXRlLGM6IiM3ODcxNmMiLGU6IvCfk4UifSwKICAgICAgICBdLm1hcCgocyxpKT0+PGRpdiBrZXk9e2l9IHN0eWxlPXt7YmFja2dyb3VuZDoidmFyKC0tYmctY2FyZCkiLGJvcmRlcjoiMXB4IHNvbGlkIHZhcigtLWJvcmRlcikiLGJvcmRlclJhZGl1czoxMCxwYWRkaW5nOiIxNnB4IDE4cHgifX0+CiAgICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MjAsbWFyZ2luQm90dG9tOjd9fT57cy5lfTwvZGl2PgogICAgICAgICAgPGRpdiBzdHlsZT17e2ZvbnRTaXplOjEwLGNvbG9yOiIjNzg3MTZjIixmb250V2VpZ2h0OjcwMCxtYXJnaW5Cb3R0b206NH19PntzLmx9PC9kaXY+CiAgICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6cy5iaWc/MjA6MjYsZm9udFdlaWdodDo4MDAsY29sb3I6cy5jfX0+e3Mudn08L2Rpdj4KICAgICAgICA8L2Rpdj4pfQogICAgICA8L2Rpdj59CiAgICA8Lz59CiAgICB7dGFiPT09ImxvZyImJjxkaXYgc3R5bGU9e3tiYWNrZ3JvdW5kOiJ2YXIoLS1iZy1jYXJkKSIsYm9yZGVyOiIxcHggc29saWQgdmFyKC0tYm9yZGVyKSIsYm9yZGVyUmFkaXVzOjEyLHBhZGRpbmc6IjE0cHggMTZweCJ9fT4KICAgICAgPFNIIHRpdGxlPSJBY3Rpdml0eSBMb2ciIGJhZGdlPXtsb2cubGVuZ3RofSBhY3Rpb249e2ZldGNoTH0gYWw9IlJlZnJlc2giLz4KICAgICAge2xvYWRpbmc/WzEsMiwzXS5tYXAoaT0+PGRpdiBrZXk9e2l9IHN0eWxlPXt7cGFkZGluZzoiMTBweCAwIixib3JkZXJCb3R0b206IjFweCBzb2xpZCAjZmFmYWY5In19PjxTa2VsIGg9ezEzfS8+PC9kaXY+KToKICAgICAgbG9nLmxlbmd0aD09PTA/PGRpdiBzdHlsZT17e3RleHRBbGlnbjoiY2VudGVyIixwYWRkaW5nOiIyOHB4Iixjb2xvcjoiI2E4YTI5ZSIsZm9udFNpemU6MTJ9fT5ObyBhY3Rpdml0eSBmb3VuZC48L2Rpdj46CiAgICAgIGxvZy5tYXAoKGwsaSk9PjxkaXYga2V5PXtpfSBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGdhcDoxMCxwYWRkaW5nOiI4cHggMCIsYm9yZGVyQm90dG9tOiIxcHggc29saWQgI2ZhZmFmOSIsYWxpZ25JdGVtczoiZmxleC1zdGFydCJ9fT4KICAgICAgICA8ZGl2IHN0eWxlPXt7d2lkdGg6MjgsaGVpZ2h0OjI4LGJvcmRlclJhZGl1czoiNTAlIixiYWNrZ3JvdW5kOkIucHJpTCxjb2xvcjpCLnByaSxkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGp1c3RpZnlDb250ZW50OiJjZW50ZXIiLGZvbnRTaXplOjksZm9udFdlaWdodDo4MDAsZmxleFNocmluazowfX0+e0lOSShsLnVzZXJuYW1lKX08L2Rpdj4KICAgICAgICA8ZGl2IHN0eWxlPXt7ZmxleDoxLG1pbldpZHRoOjB9fT48ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTIsY29sb3I6IiMxYzE5MTciLGZvbnRXZWlnaHQ6NjAwfX0+e2wuZGVzY3JpcHRpb258fGwuYWN0aXZpdHlfdHlwZX08L2Rpdj48ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTAsY29sb3I6IiNhOGEyOWUiLG1hcmdpblRvcDoxfX0+e2wudXNlcm5hbWV9IMK3IHtsLnRpbWVzdGFtcH08L2Rpdj48L2Rpdj4KICAgICAgICA8c3BhbiBzdHlsZT17e2ZvbnRTaXplOjksZm9udFdlaWdodDo4MDAscGFkZGluZzoiMnB4IDdweCIsYm9yZGVyUmFkaXVzOjIwLGJhY2tncm91bmQ6Qi5wcmlMLGNvbG9yOkIucHJpRCxib3JkZXI6YDFweCBzb2xpZCAke0IucHJpTX1gLHdoaXRlU3BhY2U6Im5vd3JhcCIsZmxleFNocmluazowfX0+e2wuYWN0aXZpdHlfdHlwZX08L3NwYW4+CiAgICAgIDwvZGl2Pil9CiAgICA8L2Rpdj59CiAgICB7dGFiPT09InBlcmYiJiY8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDoidmFyKC0tYmctY2FyZCkiLGJvcmRlcjoiMXB4IHNvbGlkIHZhcigtLWJvcmRlcikiLGJvcmRlclJhZGl1czoxMixwYWRkaW5nOiIxNHB4IDE2cHgifX0+CiAgICAgIDxTSCB0aXRsZT0iU3RhZmYgUGVyZm9ybWFuY2UiIGJhZGdlPXtzdGFmZkxpc3QubGVuZ3RofSBhY3Rpb249e2ZldGNoUGVyZn0gYWw9IlJlZnJlc2giLz4KICAgICAge2xvYWRpbmc/WzEsMiwzXS5tYXAoaT0+PGRpdiBrZXk9e2l9IHN0eWxlPXt7cGFkZGluZzoiMTBweCAwIn19PjxTa2VsIGg9ezQwfS8+PC9kaXY+KToKICAgICAgc3RhZmZMaXN0Lmxlbmd0aD09PTA/PGRpdiBzdHlsZT17e3RleHRBbGlnbjoiY2VudGVyIixwYWRkaW5nOiIyOHB4Iixjb2xvcjoiI2E4YTI5ZSIsZm9udFNpemU6MTJ9fT5ObyBzdGFmZiBkYXRhLjwvZGl2PjoKICAgICAgc3RhZmZMaXN0Lm1hcChzPT57CiAgICAgICAgY29uc3Qgc0pvYnM9YWxsSm9icy5maWx0ZXIoaj0+U3RyaW5nKGouYXNzaWduZWRfdG9faWQpPT09U3RyaW5nKHMuaWQpfHxTdHJpbmcoai5hc3NpZ25lZF90byk9PT1TdHJpbmcocy5pZCkpOwogICAgICAgIGNvbnN0IGRvbmU9c0pvYnMuZmlsdGVyKGo9PlsiQ29tcGxldGVkIiwiRGVsaXZlcmVkIl0uaW5jbHVkZXMoai5zdGF0dXMpKS5sZW5ndGg7CiAgICAgICAgY29uc3QgcGN0PXNKb2JzLmxlbmd0aD9NYXRoLnJvdW5kKGRvbmUvc0pvYnMubGVuZ3RoKjEwMCk6MDsKICAgICAgICByZXR1cm48ZGl2IGtleT17cy5pZH0gc3R5bGU9e3twYWRkaW5nOiIxMnB4IDAiLGJvcmRlckJvdHRvbToiMXB4IHNvbGlkICNmYWZhZjkifX0+CiAgICAgICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixnYXA6MTAsbWFyZ2luQm90dG9tOjZ9fT4KICAgICAgICAgICAgPGRpdiBzdHlsZT17e3dpZHRoOjMyLGhlaWdodDozMixib3JkZXJSYWRpdXM6IjUwJSIsYmFja2dyb3VuZDpgbGluZWFyLWdyYWRpZW50KDEzNWRlZywke0IucHJpfSwke0IucHJpRH0pYCxkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGp1c3RpZnlDb250ZW50OiJjZW50ZXIiLGZvbnRTaXplOjExLGZvbnRXZWlnaHQ6ODAwLGNvbG9yOiIjZmZmIixmbGV4U2hyaW5rOjB9fT57SU5JKHMudXNlcm5hbWV8fHMubmFtZSl9PC9kaXY+CiAgICAgICAgICAgIDxkaXYgc3R5bGU9e3tmbGV4OjF9fT4KICAgICAgICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTMsZm9udFdlaWdodDo3MDAsY29sb3I6IiMxYzE5MTcifX0+e3MudXNlcm5hbWV8fHMubmFtZX08L2Rpdj4KICAgICAgICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTAsY29sb3I6IiM3ODcxNmMiLHRleHRUcmFuc2Zvcm06ImNhcGl0YWxpemUifX0+e3Mucm9sZX08L2Rpdj4KICAgICAgICAgICAgPC9kaXY+CiAgICAgICAgICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixnYXA6MTIsdGV4dEFsaWduOiJjZW50ZXIifX0+CiAgICAgICAgICAgICAge1tbIlRvdGFsIixzSm9icy5sZW5ndGgsIiM1NzUzNGUiXSxbIkRvbmUiLGRvbmUsIiMxNmEzNGEiXSxbIkFjdGl2ZSIsc0pvYnMuZmlsdGVyKGo9PlsiUGVuZGluZyIsIkluIFByb2dyZXNzIl0uaW5jbHVkZXMoai5zdGF0dXMpKS5sZW5ndGgsIiNlYTU4MGMiXV0ubWFwKChbbCx2LGNvbF0pPT4oCiAgICAgICAgICAgICAgICA8ZGl2IGtleT17bH0+PGRpdiBzdHlsZT17e2ZvbnRTaXplOjE2LGZvbnRXZWlnaHQ6OTAwLGNvbG9yOmNvbH19Pnt2fTwvZGl2PjxkaXYgc3R5bGU9e3tmb250U2l6ZTo5LGNvbG9yOiIjYThhMjllIixmb250V2VpZ2h0OjYwMH19PntsfTwvZGl2PjwvZGl2PgogICAgICAgICAgICAgICkpfQogICAgICAgICAgICA8L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBzdHlsZT17e2JhY2tncm91bmQ6IiNmNWY1ZjQiLGJvcmRlclJhZGl1czoyMCxoZWlnaHQ6NixvdmVyZmxvdzoiaGlkZGVuIn19PgogICAgICAgICAgICA8ZGl2IHN0eWxlPXt7d2lkdGg6YCR7cGN0fSVgLGhlaWdodDoiMTAwJSIsYmFja2dyb3VuZDpgbGluZWFyLWdyYWRpZW50KDkwZGVnLCR7Qi5wcml9LCMxNmEzNGEpYCxib3JkZXJSYWRpdXM6MjAsdHJhbnNpdGlvbjoid2lkdGggLjRzIn19Lz4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBzdHlsZT17e2ZvbnRTaXplOjksY29sb3I6IiM3ODcxNmMiLG1hcmdpblRvcDozLHRleHRBbGlnbjoicmlnaHQifX0+e3BjdH0lIGNvbXBsZXRpb24gcmF0ZTwvZGl2PgogICAgICAgIDwvZGl2Pjt9KX0KICAgIDwvZGl2Pn0KICA8L1BnPjsKfQoKLyog4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQ4pWQIFNFVFRJTkdTIOKVkOKVkOKVkCAqLwpmdW5jdGlvbiBTZXR0aW5ncyh7YXBpLHVzZXIsdG9hc3Qsb25Mb2dvdXR9KXsKICBjb25zdFtvbGRQLHNldE9sZFBdPXVzZVN0YXRlKCIiKTtjb25zdFtuZXdQLHNldE5ld1BdPXVzZVN0YXRlKCIiKTtjb25zdFtjb25mUCxzZXRDb25mUF09dXNlU3RhdGUoIiIpO2NvbnN0W3NhdmluZyxzZXRTYXZpbmddPXVzZVN0YXRlKGZhbHNlKTsKICBjb25zdFtzdGFmZixzZXRTdGFmZl09dXNlU3RhdGUoW10pOwogIHVzZUVmZmVjdCgoKT0+e2lmKHVzZXIucm9sZT09PSJhZG1pbiIpYXBpLnN0YWZmTGlzdCgpLnRoZW4oc2V0U3RhZmYpLmNhdGNoKCgpPT57fSk7fSxbXSk7CiAgY29uc3QgY2hhbmdlUGFzcz1hc3luYygpPT57CiAgICBpZighb2xkUHx8IW5ld1Ape3RvYXN0KCJQYXNzd29yZHMgZW50ZXIg4LCa4LGH4LCv4LCC4LCh4LC/IiwiZXJyb3IiKTtyZXR1cm47fQogICAgaWYobmV3UCE9PWNvbmZQKXt0b2FzdCgiUGFzc3dvcmRzIG1hdGNoIOCwleCwvuCwteCwoeCwgiDgsLLgsYfgsKbgsYEiLCJlcnJvciIpO3JldHVybjt9CiAgICBpZihuZXdQLmxlbmd0aDw2KXt0b2FzdCgiTWluaW11bSA2IGNoYXJhY3RlcnMiLCJlcnJvciIpO3JldHVybjt9CiAgICBzZXRTYXZpbmcodHJ1ZSk7dHJ5e2F3YWl0IGFwaS5jaGFuZ2VQYXNzd29yZChvbGRQLG5ld1ApO3RvYXN0KCJQYXNzd29yZCBjaGFuZ2VkISIpO3NldE9sZFAoIiIpO3NldE5ld1AoIiIpO3NldENvbmZQKCIiKTt9Y2F0Y2goZSl7dG9hc3QoZS5tZXNzYWdlLCJlcnJvciIpO31maW5hbGx5e3NldFNhdmluZyhmYWxzZSk7fQogIH07CiAgcmV0dXJuPFBnPgogICAgPGgyIHN0eWxlPXt7Zm9udFNpemU6MTksZm9udFdlaWdodDo4MDAsY29sb3I6IiMxYzE5MTciLG1hcmdpbjoiMCAwIDIwcHgifX0+U2V0dGluZ3M8L2gyPgogICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImdyaWQiLGdyaWRUZW1wbGF0ZUNvbHVtbnM6IjFmciAxZnIiLGdhcDoxNH19PgogICAgICA8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDoidmFyKC0tYmctY2FyZCkiLGJvcmRlcjoiMXB4IHNvbGlkIHZhcigtLWJvcmRlcikiLGJvcmRlclJhZGl1czoxMixwYWRkaW5nOiIxOHB4IDIwcHgifX0+CiAgICAgICAgPFNIIHRpdGxlPSJNeSBQcm9maWxlIi8+CiAgICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGFsaWduSXRlbXM6ImNlbnRlciIsZ2FwOjE0LG1hcmdpbkJvdHRvbToxNn19PgogICAgICAgICAgPGRpdiBzdHlsZT17e3dpZHRoOjUyLGhlaWdodDo1Mixib3JkZXJSYWRpdXM6IjUwJSIsYmFja2dyb3VuZDpgbGluZWFyLWdyYWRpZW50KDEzNWRlZywke0IucHJpfSwke0IucHJpRH0pYCxkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGp1c3RpZnlDb250ZW50OiJjZW50ZXIiLGZvbnRTaXplOjE3LGZvbnRXZWlnaHQ6ODAwLGNvbG9yOiIjZmZmIn19PntJTkkodXNlci51c2VybmFtZSl9PC9kaXY+CiAgICAgICAgICA8ZGl2PjxkaXYgc3R5bGU9e3tmb250U2l6ZToxNSxmb250V2VpZ2h0OjgwMCxjb2xvcjoiIzFjMTkxNyJ9fT57dXNlci51c2VybmFtZX08L2Rpdj48ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTIsY29sb3I6IiM3ODcxNmMiLG1hcmdpblRvcDoxfX0+Um9sZTogPHN0cm9uZyBzdHlsZT17e2NvbG9yOkIucHJpLHRleHRUcmFuc2Zvcm06ImNhcGl0YWxpemUifX0+e3VzZXIucm9sZX08L3N0cm9uZz48L2Rpdj48ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTAsY29sb3I6IiNhOGEyOWUifX0+VXNlciBJRDogI3t1c2VyLmlkfTwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxidXR0b24gb25DbGljaz17b25Mb2dvdXR9IHN0eWxlPXt7Li4uQlROKCJkYW5nZXIiKSx3aWR0aDoiMTAwJSIsZGlzcGxheToiZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixqdXN0aWZ5Q29udGVudDoiY2VudGVyIixnYXA6Nn19PvCfmqogTG9nb3V0PC9idXR0b24+CiAgICAgIDwvZGl2PgogICAgICA8ZGl2IHN0eWxlPXt7YmFja2dyb3VuZDoidmFyKC0tYmctY2FyZCkiLGJvcmRlcjoiMXB4IHNvbGlkIHZhcigtLWJvcmRlcikiLGJvcmRlclJhZGl1czoxMixwYWRkaW5nOiIxOHB4IDIwcHgifX0+CiAgICAgICAgPFNIIHRpdGxlPSJDaGFuZ2UgUGFzc3dvcmQiLz4KICAgICAgICA8RmxkIGxhYmVsPSJDdXJyZW50IFBhc3N3b3JkIj48aW5wdXQgdHlwZT0icGFzc3dvcmQiIHZhbHVlPXtvbGRQfSBvbkNoYW5nZT17ZT0+c2V0T2xkUChlLnRhcmdldC52YWx1ZSl9IHN0eWxlPXtJTlB9IHBsYWNlaG9sZGVyPSJDdXJyZW50IHBhc3N3b3JkIi8+PC9GbGQ+CiAgICAgICAgPEZsZCBsYWJlbD0iTmV3IFBhc3N3b3JkIj48aW5wdXQgdHlwZT0icGFzc3dvcmQiIHZhbHVlPXtuZXdQfSBvbkNoYW5nZT17ZT0+c2V0TmV3UChlLnRhcmdldC52YWx1ZSl9IHN0eWxlPXtJTlB9IHBsYWNlaG9sZGVyPSJNaW4gNiBjaGFyYWN0ZXJzIi8+PC9GbGQ+CiAgICAgICAgPEZsZCBsYWJlbD0iQ29uZmlybSBQYXNzd29yZCI+PGlucHV0IHR5cGU9InBhc3N3b3JkIiB2YWx1ZT17Y29uZlB9IG9uQ2hhbmdlPXtlPT5zZXRDb25mUChlLnRhcmdldC52YWx1ZSl9IHN0eWxlPXtJTlB9IHBsYWNlaG9sZGVyPSJSZXBlYXQgcGFzc3dvcmQiLz48L0ZsZD4KICAgICAgICA8YnV0dG9uIG9uQ2xpY2s9e2NoYW5nZVBhc3N9IGRpc2FibGVkPXtzYXZpbmd9IHN0eWxlPXt7Li4uQlROKCksd2lkdGg6IjEwMCUifX0+e3NhdmluZz88U3Bpbi8+OiJVcGRhdGUgUGFzc3dvcmQifTwvYnV0dG9uPgogICAgICA8L2Rpdj4KICAgICAgPGRpdiBzdHlsZT17e2JhY2tncm91bmQ6InZhcigtLWJnLWNhcmQpIixib3JkZXI6IjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpIixib3JkZXJSYWRpdXM6MTIscGFkZGluZzoiMThweCAyMHB4In19PgogICAgICAgIDxTSCB0aXRsZT0iQWJvdXQgS1BSIExhYiBDUk0iLz4KICAgICAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsZ2FwOjEyLGFsaWduSXRlbXM6ImNlbnRlciIsbWFyZ2luQm90dG9tOjE0fX0+CiAgICAgICAgICA8ZGl2IHN0eWxlPXt7d2lkdGg6NDQsaGVpZ2h0OjQ0LGJvcmRlclJhZGl1czoxMCxiYWNrZ3JvdW5kOmBsaW5lYXItZ3JhZGllbnQoMTM1ZGVnLCR7Qi5wcml9LCR7Qi5wcmlEfSlgLGRpc3BsYXk6ImZsZXgiLGFsaWduSXRlbXM6ImNlbnRlciIsanVzdGlmeUNvbnRlbnQ6ImNlbnRlciIsZm9udFNpemU6MjB9fT7wn5O3PC9kaXY+CiAgICAgICAgICA8ZGl2PjxkaXYgc3R5bGU9e3tmb250U2l6ZToxNCxmb250V2VpZ2h0OjgwMCxjb2xvcjoiIzFjMTkxNyJ9fT5LUFIgQ29sb3VyIExhYiBDUk08L2Rpdj48ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTEsY29sb3I6IiM3ODcxNmMifX0+VmVyc2lvbiAxLjAuMDwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIHtbWyJEZXZlbG9wZXIiLCJTRUtIQVIgS0FNTUFNUEFUSSJdLFsiQ29weXJpZ2h0IiwiwqkgMjAyM+KAkzIwMjUgS1BSIENvbG91ciBMYWIiXSxbIkJhY2tlbmQiLCJQeXRob24gwrcgRmFzdEFQSSDCtyBTUUxpdGUiXSxbIkZyb250ZW5kIiwiUmVhY3QgwrcgU3RhbmRhbG9uZSBIVE1MIl1dLm1hcCgoW2ssdl0pPT48ZGl2IGtleT17a30gc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixqdXN0aWZ5Q29udGVudDoic3BhY2UtYmV0d2VlbiIscGFkZGluZzoiN3B4IDAiLGJvcmRlckJvdHRvbToiMXB4IHNvbGlkICNmYWZhZjkiLGZvbnRTaXplOjEyfX0+PHNwYW4gc3R5bGU9e3tjb2xvcjoiIzc4NzE2YyIsZm9udFdlaWdodDo2MDB9fT57a308L3NwYW4+PHNwYW4gc3R5bGU9e3tjb2xvcjoiIzFjMTkxNyIsZm9udFdlaWdodDo1MDB9fT57dn08L3NwYW4+PC9kaXY+KX0KICAgICAgPC9kaXY+CiAgICAgIHt1c2VyLnJvbGU9PT0iYWRtaW4iJiZzdGFmZi5sZW5ndGg+MCYmPGRpdiBzdHlsZT17e2JhY2tncm91bmQ6InZhcigtLWJnLWNhcmQpIixib3JkZXI6IjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpIixib3JkZXJSYWRpdXM6MTIscGFkZGluZzoiMThweCAyMHB4In19PgogICAgICAgIDxTSCB0aXRsZT0iU3RhZmYgTWVtYmVycyIgYmFkZ2U9e3N0YWZmLmxlbmd0aH0vPgogICAgICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixmbGV4RGlyZWN0aW9uOiJjb2x1bW4iLGdhcDo3fX0+CiAgICAgICAgICB7c3RhZmYubWFwKChzLGkpPT48ZGl2IGtleT17aX0gc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGdhcDo5LHBhZGRpbmc6IjhweCAxMHB4IixiYWNrZ3JvdW5kOiIjZmFmYWY5Iixib3JkZXJSYWRpdXM6OH19PgogICAgICAgICAgICA8ZGl2IHN0eWxlPXt7d2lkdGg6MjgsaGVpZ2h0OjI4LGJvcmRlclJhZGl1czoiNTAlIixiYWNrZ3JvdW5kOmBsaW5lYXItZ3JhZGllbnQoMTM1ZGVnLCR7Qi5wcml9LCR7Qi5wcmlEfSlgLGRpc3BsYXk6ImZsZXgiLGFsaWduSXRlbXM6ImNlbnRlciIsanVzdGlmeUNvbnRlbnQ6ImNlbnRlciIsZm9udFNpemU6MTAsZm9udFdlaWdodDo4MDAsY29sb3I6IiNmZmYiLGZsZXhTaHJpbms6MH19PntJTkkocy51c2VybmFtZXx8cy5uYW1lKX08L2Rpdj4KICAgICAgICAgICAgPGRpdiBzdHlsZT17e2ZsZXg6MX19PjxkaXYgc3R5bGU9e3tmb250U2l6ZToxMixmb250V2VpZ2h0OjcwMCxjb2xvcjoiIzFjMTkxNyJ9fT57cy51c2VybmFtZXx8cy5uYW1lfTwvZGl2PjxkaXYgc3R5bGU9e3tmb250U2l6ZToxMCxjb2xvcjoiIzc4NzE2YyIsdGV4dFRyYW5zZm9ybToiY2FwaXRhbGl6ZSJ9fT57cy5yb2xlfTwvZGl2PjwvZGl2PgogICAgICAgICAgICA8c3BhbiBzdHlsZT17e2ZvbnRTaXplOjksZm9udFdlaWdodDo4MDAscGFkZGluZzoiMnB4IDdweCIsYm9yZGVyUmFkaXVzOjIwLGJhY2tncm91bmQ6cy5pc19hY3RpdmU/IiNmMGZkZjQiOiIjZmVmMmYyIixjb2xvcjpzLmlzX2FjdGl2ZT8iIzE1ODAzZCI6IiNkYzI2MjYiLGJvcmRlcjpgMXB4IHNvbGlkICR7cy5pc19hY3RpdmU/IiM4NmVmYWMiOiIjZmNhNWE1In1gfX0+e3MuaXNfYWN0aXZlPyJBY3RpdmUiOiJJbmFjdGl2ZSJ9PC9zcGFuPgogICAgICAgICAgPC9kaXY+KX0KICAgICAgICA8L2Rpdj4KICAgICAgPC9kaXY+fQogICAgPC9kaXY+CiAgPC9QZz47Cn0KCi8qIOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkCBOQVYg4pWQ4pWQ4pWQICovCmNvbnN0IEFMTF9OQVY9WwogIHtpZDoiZGFzaGJvYXJkIixsOiJEYXNoYm9hcmQiLGU6IuKKniIscm9sZXM6WyJhZG1pbiIsInN0YWZmIiwic3ViX3N0YWZmIl19LAogIHtpZDoiY3VzdG9tZXJzIixsOiJDdXN0b21lcnMiLGU6IvCfkaUiLHJvbGVzOlsiYWRtaW4iLCJzdGFmZiJdfSwKICB7aWQ6ImpvYnMiLGw6IkpvYnMiLGU6IvCfk4siLHJvbGVzOlsiYWRtaW4iLCJzdGFmZiIsInN1Yl9zdGFmZiJdfSwKICB7aWQ6InBheW1lbnRzIixsOiJQYXltZW50cyIsZToi8J+SsyIscm9sZXM6WyJhZG1pbiIsInN0YWZmIl19LAogIHtpZDoiaW52ZW50b3J5IixsOiJJbnZlbnRvcnkiLGU6IvCfk6YiLHJvbGVzOlsiYWRtaW4iXX0sCiAge2lkOiJyZXBvcnRzIixsOiJSZXBvcnRzIixlOiLwn5OKIixyb2xlczpbImFkbWluIl19LAogIHtpZDoic2V0dGluZ3MiLGw6IlNldHRpbmdzIixlOiLimpkiLHJvbGVzOlsiYWRtaW4iXX0sCl07CmNvbnN0IGdldE5hdj0ocm9sZSk9PkFMTF9OQVYuZmlsdGVyKG49Pm4ucm9sZXMuaW5jbHVkZXMocm9sZXx8InN1Yl9zdGFmZiIpKTsKY29uc3QgY2FuQWNjZXNzPShyb2xlLG5hdklkKT0+Z2V0TmF2KHJvbGUpLnNvbWUobj0+bi5pZD09PW5hdklkKTsKCi8qIOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkOKVkCBST09UIEFQUCDilZDilZDilZAgKi8KZnVuY3Rpb24gQXBwKCl7CiAgLy8g4pSA4pSAIFBlcnNpc3QgY29uZmlnICYgc2Vzc2lvbiBhY3Jvc3MgcGFnZSByZWZyZXNoZXMg4pSA4pSACiAgY29uc3Qgc3RvcmVkPUpTT04ucGFyc2UobG9jYWxTdG9yYWdlLmdldEl0ZW0oImtwcl9zZXNzaW9uIil8fCJ7fSIpOwogIGNvbnN0W3NpcCxzZXRTaXBdPXVzZVN0YXRlKHN0b3JlZC5zaXB8fCJodHRwczovL2twci1jcm0tYXBpLm9ucmVuZGVyLmNvbSIpOwogIGNvbnN0W3Nwb3J0LHNldFNwb3J0XT11c2VTdGF0ZShzdG9yZWQuc3BvcnR8fCIiKTsKICBjb25zdFt0b2tlbixzZXRUb2tlbl09dXNlU3RhdGUoc3RvcmVkLnRva2VufHxudWxsKTsKICBjb25zdFt1c2VyLHNldFVzZXJdPXVzZVN0YXRlKHN0b3JlZC51c2VyfHxudWxsKTsKICBjb25zdFthcGksc2V0QXBpXT11c2VTdGF0ZSgoKT0+ewogICAgaWYoc3RvcmVkLnRva2VuJiZzdG9yZWQuc2lwKXsKICAgICAgY29uc3QgYT1tYWtlQXBpKHN0b3JlZC5zaXAuc3RhcnRzV2l0aCgiaHR0cCIpP3N0b3JlZC5zaXA6YGh0dHA6Ly8ke3N0b3JlZC5zaXB9JHtzdG9yZWQuc3BvcnQ/IjoiK3N0b3JlZC5zcG9ydDoiIn1gKTsKICAgICAgYS5zZXRUb2tlbihzdG9yZWQudG9rZW4pO3JldHVybiBhOwogICAgfXJldHVybiBudWxsOwogIH0pOwogIGNvbnN0W25hdixzZXROYXZdPXVzZVN0YXRlKCJkYXNoYm9hcmQiKTtjb25zdFtjb2wsc2V0Q29sXT11c2VTdGF0ZShmYWxzZSk7CiAgY29uc3RbY2ZnLHNldENmZ109dXNlU3RhdGUoZmFsc2UpO2NvbnN0W3RvYXN0LHNldFRvYXN0XT11c2VTdGF0ZShudWxsKTsKICBjb25zdFtub3RpZnMsc2V0Tm90aWZzXT11c2VTdGF0ZShbXSk7Y29uc3Rbbm90aWZPcGVuLHNldE5vdGlmT3Blbl09dXNlU3RhdGUoZmFsc2UpOwogIGNvbnN0W2Rhcmssc2V0RGFya109dXNlU3RhdGUoKCk9PmxvY2FsU3RvcmFnZS5nZXRJdGVtKCJrcHJfZGFyayIpPT09IjEiKTsKICBjb25zdCBub3RpZlJlZj11c2VSZWYobnVsbCk7CiAgdXNlRWZmZWN0KCgpPT57ZG9jdW1lbnQuYm9keS5jbGFzc0xpc3QudG9nZ2xlKCJkYXJrIixkYXJrKTtkb2N1bWVudC5ib2R5LnN0eWxlLmJhY2tncm91bmQ9IiI7ZG9jdW1lbnQuYm9keS5zdHlsZS5jb2xvcj0iIjtsb2NhbFN0b3JhZ2Uuc2V0SXRlbSgia3ByX2RhcmsiLGRhcms/IjEiOiIwIik7fSxbZGFya10pOwogIGNvbnN0IHNlcnZlclVybD0oKCk9PnsKICAgIGNvbnN0IHM9c2lwLnRyaW0oKTsKICAgIGlmKHMuc3RhcnRzV2l0aCgiaHR0cDovLyIpfHxzLnN0YXJ0c1dpdGgoImh0dHBzOi8vIikpcmV0dXJuIHMucmVwbGFjZSgvXC8kLywgIiIpOwogICAgaWYoc3BvcnQpcmV0dXJuIGBodHRwOi8vJHtzfToke3Nwb3J0fWA7CiAgICByZXR1cm4gYGh0dHA6Ly8ke3N9YDsKICB9KSgpOwogIC8vIFJlc3RvcmUgbm90aWZpY2F0aW9ucyBvbiByZWZyZXNoICsgYXV0by1wb2xsIGV2ZXJ5IDMwcwogIGNvbnN0IHJlZnJlc2hOb3RpZnM9dXNlQ2FsbGJhY2soKCk9PntpZihhcGkmJnVzZXIpYXBpLm5vdGlmaWNhdGlvbnModXNlci5pZCkudGhlbihzZXROb3RpZnMpLmNhdGNoKCgpPT57fSk7fSxbYXBpLHVzZXJdKTsKICB1c2VFZmZlY3QoKCk9PntyZWZyZXNoTm90aWZzKCk7Y29uc3QgdD1zZXRJbnRlcnZhbChyZWZyZXNoTm90aWZzLDYwMDAwKTtyZXR1cm4oKT0+Y2xlYXJJbnRlcnZhbCh0KTt9LFtyZWZyZXNoTm90aWZzXSk7CiAgdXNlRWZmZWN0KCgpPT57Y29uc3QgaD1lPT57aWYobm90aWZSZWYuY3VycmVudCYmIW5vdGlmUmVmLmN1cnJlbnQuY29udGFpbnMoZS50YXJnZXQpKXNldE5vdGlmT3BlbihmYWxzZSk7fTtkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKCJtb3VzZWRvd24iLGgpO3JldHVybigpPT5kb2N1bWVudC5yZW1vdmVFdmVudExpc3RlbmVyKCJtb3VzZWRvd24iLGgpO30sW10pOwogIGNvbnN0IHNob3dUb2FzdD0obXNnLHR5cGU9InN1Y2Nlc3MiKT0+c2V0VG9hc3Qoe21zZyx0eXBlLGlkOkRhdGUubm93KCl9KTsKICBjb25zdCBoYW5kbGVMb2dpbj0ocmVzLGFwaUluc3QpPT57CiAgICBhcGlJbnN0LnNldFRva2VuKHJlcy5hY2Nlc3NfdG9rZW4pO3NldEFwaShhcGlJbnN0KTsKICAgIGNvbnN0IHU9e2lkOnJlcy51c2VyX2lkLHVzZXJuYW1lOnJlcy51c2VybmFtZSxyb2xlOnJlcy5yb2xlfTsKICAgIHNldFRva2VuKHJlcy5hY2Nlc3NfdG9rZW4pO3NldFVzZXIodSk7CiAgICAvLyBTYXZlIHRvIGxvY2FsU3RvcmFnZSBzbyByZWZyZXNoIGRvZXNuJ3QgbG9nb3V0CiAgICBsb2NhbFN0b3JhZ2Uuc2V0SXRlbSgia3ByX3Nlc3Npb24iLEpTT04uc3RyaW5naWZ5KHt0b2tlbjpyZXMuYWNjZXNzX3Rva2VuLHVzZXI6dSxzaXAsc3BvcnR9KSk7CiAgICBhcGlJbnN0Lm5vdGlmaWNhdGlvbnMocmVzLnVzZXJfaWQpLnRoZW4oc2V0Tm90aWZzKS5jYXRjaCgoKT0+e30pOwogIH07CiAgY29uc3QgaGFuZGxlTG9nb3V0PSgpPT57CiAgICBpZihhcGkpYXBpLmxvZ291dCgpLmNhdGNoKCgpPT57fSk7CiAgICBsb2NhbFN0b3JhZ2UucmVtb3ZlSXRlbSgia3ByX3Nlc3Npb24iKTsKICAgIHNldFRva2VuKG51bGwpO3NldFVzZXIobnVsbCk7c2V0QXBpKG51bGwpO3NldE5hdigiZGFzaGJvYXJkIik7CiAgfTsKICBjb25zdCB1bnJlYWQ9bm90aWZzLmZpbHRlcihuPT4hbi5pc19yZWFkKS5sZW5ndGg7CiAgY29uc3QgcmVuZGVyUGFnZT0oKT0+ewogICAgY29uc3QgcD17YXBpLHVzZXIscm9sZTp1c2VyPy5yb2xlLHRvYXN0OnNob3dUb2FzdH07CiAgICBjb25zdCByb2xlPXVzZXI/LnJvbGU7CiAgICAvLyBVbmF1dGhvcml6ZWQgYWNjZXNzIOKGkiByZWRpcmVjdCB0byBkYXNoYm9hcmQKICAgIGlmKG5hdiE9PSJkYXNoYm9hcmQiJiYhY2FuQWNjZXNzKHJvbGUsbmF2KSl7CiAgICAgIHJldHVybjxkaXYgc3R5bGU9e3twYWRkaW5nOiI0MHB4Iix0ZXh0QWxpZ246ImNlbnRlciJ9fT4KICAgICAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MzYsbWFyZ2luQm90dG9tOjEyfX0+8J+aqzwvZGl2PgogICAgICAgIDxkaXYgc3R5bGU9e3tmb250U2l6ZToxNixmb250V2VpZ2h0OjgwMCxjb2xvcjoiIzFjMTkxNyIsbWFyZ2luQm90dG9tOjZ9fT5BY2Nlc3MgRGVuaWVkPC9kaXY+CiAgICAgICAgPGRpdiBzdHlsZT17e2ZvbnRTaXplOjEyLGNvbG9yOiIjNzg3MTZjIixtYXJnaW5Cb3R0b206MjB9fT7gsK7gsYAgcm9sZSDgsJXgsL8g4LCIIHBhZ2UgYWNjZXNzIOCwsuCxh+CwpuCxgS48L2Rpdj4KICAgICAgICA8YnV0dG9uIG9uQ2xpY2s9eygpPT5zZXROYXYoImRhc2hib2FyZCIpfSBzdHlsZT17ey4uLkJUTigpLHBhZGRpbmc6IjlweCAyMHB4In19PuKGkCBEYXNoYm9hcmQg4LCV4LC/IOCwteCxhuCws+CxjeCws+CxgTwvYnV0dG9uPgogICAgICA8L2Rpdj47CiAgICB9CiAgICBzd2l0Y2gobmF2KXsKICAgICAgY2FzZSJjdXN0b21lcnMiOnJldHVybjxDdXN0b21lcnMgey4uLnB9Lz47CiAgICAgIGNhc2Uiam9icyI6cmV0dXJuPEpvYnMgey4uLnB9Lz47CiAgICAgIGNhc2UicGF5bWVudHMiOnJldHVybjxQYXltZW50cyB7Li4ucH0vPjsKICAgICAgY2FzZSJtYXRlcmlhbF91c2FnZSI6cmV0dXJuPE1hdGVyaWFsVXNhZ2Ugey4uLnB9Lz47CiAgICAgIGNhc2UiaW52ZW50b3J5IjpyZXR1cm48SW52ZW50b3J5IHsuLi5wfS8+OwogICAgICBjYXNlInJlcG9ydHMiOnJldHVybjxSZXBvcnRzIHsuLi5wfS8+OwogICAgICBjYXNlInNldHRpbmdzIjpyZXR1cm48U2V0dGluZ3Mgey4uLnB9IG9uTG9nb3V0PXtoYW5kbGVMb2dvdXR9Lz47CiAgICAgIGRlZmF1bHQ6cmV0dXJuPERhc2hib2FyZCBhcGk9e2FwaX0gdXNlcj17dXNlcn0gc2V0TmF2PXtzZXROYXZ9IHJvbGU9e3JvbGV9Lz47CiAgICB9CiAgfTsKCiAgaWYoIXRva2VuKXJldHVybjw+e2NmZyYmPENmZ01vZGFsIGlwPXtzaXB9IHBvcnQ9e3Nwb3J0fSBvblNhdmU9eyhpLHApPT57c2V0U2lwKGkpO3NldFNwb3J0KHApO3NldENmZyhmYWxzZSk7fX0gb25DbG9zZT17KCk9PnNldENmZyhmYWxzZSl9Lz59PExvZ2luIG9uTG9naW49e2hhbmRsZUxvZ2lufSBzZXJ2ZXJVcmw9e3NlcnZlclVybH0gb25Db25maWc9eygpPT5zZXRDZmcodHJ1ZSl9Lz48Lz47CgogIHJldHVybjw+CiAgICB7Y2ZnJiY8Q2ZnTW9kYWwgaXA9e3NpcH0gcG9ydD17c3BvcnR9IG9uU2F2ZT17KGkscCk9PntzZXRTaXAoaSk7c2V0U3BvcnQocCk7c2V0Q2ZnKGZhbHNlKTtsb2NhbFN0b3JhZ2UucmVtb3ZlSXRlbSgia3ByX3Nlc3Npb24iKTtzZXRUb2tlbihudWxsKTtzZXRVc2VyKG51bGwpO3NldEFwaShudWxsKTt9fSBvbkNsb3NlPXsoKT0+c2V0Q2ZnKGZhbHNlKX0vPn0KICAgIHt0b2FzdCYmPFRvYXN0IGtleT17dG9hc3QuaWR9IG1zZz17dG9hc3QubXNnfSB0eXBlPXt0b2FzdC50eXBlfSBvbkRvbmU9eygpPT5zZXRUb2FzdChudWxsKX0vPn0KICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixoZWlnaHQ6IjEwMHZoIixiYWNrZ3JvdW5kOiIjZmFmYWY5IixvdmVyZmxvdzoiaGlkZGVuIn19PgogICAgICB7LyogU2lkZWJhciDigJQgaGlkZGVuIG9uIG1vYmlsZSwgYm90dG9tIG5hdiBzaG93cyBpbnN0ZWFkICovfQogICAgICA8YXNpZGUgc3R5bGU9e3t3aWR0aDpjb2w/NTI6MjA2LGJhY2tncm91bmQ6Qi5zaWRlLGRpc3BsYXk6ImZsZXgiLGZsZXhEaXJlY3Rpb246ImNvbHVtbiIsZmxleFNocmluazowLHRyYW5zaXRpb246IndpZHRoIC4yMnMgZWFzZSIsb3ZlcmZsb3c6ImhpZGRlbiIsekluZGV4OjIwLHBvc2l0aW9uOiJyZWxhdGl2ZSJ9fQogICAgICAgIGNsYXNzTmFtZT17d2luZG93LmlubmVyV2lkdGg8PTc2OD8ibW9iLWhpZGUiOiIifT4KICAgICAgICA8ZGl2IHN0eWxlPXt7cGFkZGluZzpjb2w/IjE0cHggMCI6IjE0cHggMTVweCIsYm9yZGVyQm90dG9tOiIxcHggc29saWQgIzI5MjUyNCIsZGlzcGxheToiZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixnYXA6OCxjdXJzb3I6InBvaW50ZXIiLGp1c3RpZnlDb250ZW50OmNvbD8iY2VudGVyIjoiZmxleC1zdGFydCJ9fSBvbkNsaWNrPXsoKT0+c2V0Q29sKHY9PiF2KX0+CiAgICAgICAgICA8ZGl2IHN0eWxlPXt7d2lkdGg6MzAsaGVpZ2h0OjMwLGJvcmRlclJhZGl1czo3LGZsZXhTaHJpbms6MCxiYWNrZ3JvdW5kOmBsaW5lYXItZ3JhZGllbnQoMTM1ZGVnLCR7Qi5wcml9LCR7Qi5wcmlEfSlgLGRpc3BsYXk6ImZsZXgiLGFsaWduSXRlbXM6ImNlbnRlciIsanVzdGlmeUNvbnRlbnQ6ImNlbnRlciIsZm9udFNpemU6MTZ9fT7wn5O3PC9kaXY+CiAgICAgICAgICB7IWNvbCYmPGRpdj48ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTEsZm9udFdlaWdodDo4MDAsY29sb3I6IiNmZmYifX0+S1BSIENvbG91ciBMYWI8L2Rpdj48ZGl2IHN0eWxlPXt7Zm9udFNpemU6OSxjb2xvcjpCLnNpZGVNdXQsbGV0dGVyU3BhY2luZzoiLjA0ZW0iLGZvbnRXZWlnaHQ6NjAwfX0+Q1JNIFNZU1RFTTwvZGl2PjwvZGl2Pn0KICAgICAgICA8L2Rpdj4KICAgICAgICA8bmF2IHN0eWxlPXt7ZmxleDoxLHBhZGRpbmc6IjhweCAwIixvdmVyZmxvd1k6ImF1dG8ifX0+CiAgICAgICAgICB7Z2V0TmF2KHVzZXI/LnJvbGUpLm1hcChpdGVtPT57Y29uc3QgYWN0aXZlPW5hdj09PWl0ZW0uaWQ7cmV0dXJuKAogICAgICAgICAgICA8YnV0dG9uIGtleT17aXRlbS5pZH0gb25DbGljaz17KCk9PnNldE5hdihpdGVtLmlkKX0KICAgICAgICAgICAgICBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGFsaWduSXRlbXM6ImNlbnRlciIsZ2FwOjksd2lkdGg6IjEwMCUiLHBhZGRpbmc6Y29sPyIxMHB4IDAiOiI5cHggMTRweCIsanVzdGlmeUNvbnRlbnQ6Y29sPyJjZW50ZXIiOiJmbGV4LXN0YXJ0IixiYWNrZ3JvdW5kOmFjdGl2ZT9CLnNpZGVBOiJ0cmFuc3BhcmVudCIsYm9yZGVyOiJub25lIixib3JkZXJMZWZ0OmFjdGl2ZT9gM3B4IHNvbGlkICR7Qi5wcml9YDoiM3B4IHNvbGlkIHRyYW5zcGFyZW50Iixjb2xvcjphY3RpdmU/IiNmZmYiOkIuc2lkZU11dCxjdXJzb3I6InBvaW50ZXIiLGZvbnRTaXplOjEyLGZvbnRXZWlnaHQ6YWN0aXZlPzcwMDo0MDAsdHJhbnNpdGlvbjoiYWxsIC4xMnMiLHRleHRBbGlnbjoibGVmdCJ9fQogICAgICAgICAgICAgIG9uTW91c2VFbnRlcj17ZT0+e2lmKCFhY3RpdmUpZS5jdXJyZW50VGFyZ2V0LnN0eWxlLmJhY2tncm91bmQ9IiMyMzFmMWUiO319CiAgICAgICAgICAgICAgb25Nb3VzZUxlYXZlPXtlPT57aWYoIWFjdGl2ZSllLmN1cnJlbnRUYXJnZXQuc3R5bGUuYmFja2dyb3VuZD0idHJhbnNwYXJlbnQiO319PgogICAgICAgICAgICAgIDxzcGFuIHN0eWxlPXt7Zm9udFNpemU6MTR9fT57aXRlbS5lfTwvc3Bhbj57IWNvbCYmaXRlbS5sfQogICAgICAgICAgICA8L2J1dHRvbj4pO30pfQogICAgICAgIDwvbmF2PgogICAgICAgIDxkaXYgc3R5bGU9e3twYWRkaW5nOmNvbD8iMTBweCAwIjoiMTBweCAxMnB4Iixib3JkZXJUb3A6IjFweCBzb2xpZCAjMjkyNTI0IixkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGdhcDo4LGp1c3RpZnlDb250ZW50OmNvbD8iY2VudGVyIjoiZmxleC1zdGFydCJ9fT4KICAgICAgICAgIDxkaXYgc3R5bGU9e3t3aWR0aDoyOCxoZWlnaHQ6MjgsYm9yZGVyUmFkaXVzOiI1MCUiLGZsZXhTaHJpbms6MCxiYWNrZ3JvdW5kOmBsaW5lYXItZ3JhZGllbnQoMTM1ZGVnLCR7Qi5wcml9LCR7Qi5wcmlEfSlgLGRpc3BsYXk6ImZsZXgiLGFsaWduSXRlbXM6ImNlbnRlciIsanVzdGlmeUNvbnRlbnQ6ImNlbnRlciIsZm9udFNpemU6OSxmb250V2VpZ2h0OjgwMCxjb2xvcjoiI2ZmZiJ9fT57SU5JKHVzZXI/LnVzZXJuYW1lKX08L2Rpdj4KICAgICAgICAgIHshY29sJiY8PjxkaXYgc3R5bGU9e3tmbGV4OjEsbWluV2lkdGg6MH19PjxkaXYgc3R5bGU9e3tmb250U2l6ZToxMixmb250V2VpZ2h0OjcwMCxjb2xvcjoiI2ZmZiIsb3ZlcmZsb3c6ImhpZGRlbiIsdGV4dE92ZXJmbG93OiJlbGxpcHNpcyIsd2hpdGVTcGFjZToibm93cmFwIn19Pnt1c2VyPy51c2VybmFtZX08L2Rpdj48L2Rpdj4KICAgICAgICAgIDxidXR0b24gb25DbGljaz17aGFuZGxlTG9nb3V0fSB0aXRsZT0iTG9nb3V0IiBzdHlsZT17e2JhY2tncm91bmQ6Im5vbmUiLGJvcmRlcjoibm9uZSIsY3Vyc29yOiJwb2ludGVyIixjb2xvcjpCLnNpZGVNdXQsZm9udFNpemU6MTMscGFkZGluZzoyLGZsZXhTaHJpbms6MH19IG9uTW91c2VFbnRlcj17ZT0+ZS5jdXJyZW50VGFyZ2V0LnN0eWxlLmNvbG9yPSIjZWY0NDQ0In0gb25Nb3VzZUxlYXZlPXtlPT5lLmN1cnJlbnRUYXJnZXQuc3R5bGUuY29sb3I9Qi5zaWRlTXV0fT7wn5qqPC9idXR0b24+PC8+fQogICAgICAgIDwvZGl2PgogICAgICA8L2FzaWRlPgoKICAgICAgey8qIE1haW4gKi99CiAgICAgIDxkaXYgc3R5bGU9e3tmbGV4OjEsZGlzcGxheToiZmxleCIsZmxleERpcmVjdGlvbjoiY29sdW1uIixvdmVyZmxvdzoiaGlkZGVuIixtaW5XaWR0aDowLHBhZGRpbmdCb3R0b206d2luZG93LmlubmVyV2lkdGg8PTc2OD81NjowfX0+CiAgICAgICAgPGhlYWRlciBjbGFzc05hbWU9Imtwci1oZWFkZXIiIHN0eWxlPXt7aGVpZ2h0OjQ4LGJhY2tncm91bmQ6InZhcigtLWJnLWNhcmQpIixib3JkZXJCb3R0b206IjFweCBzb2xpZCAjZjVmNWY0IixkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGp1c3RpZnlDb250ZW50OiJzcGFjZS1iZXR3ZWVuIixwYWRkaW5nOiIwIDEycHgiLGZsZXhTaHJpbms6MCxnYXA6OCx6SW5kZXg6MTB9fT4KICAgICAgICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGdhcDo2fX0+CiAgICAgICAgICAgIDxidXR0b24gb25DbGljaz17KCk9PnNldENvbCh2PT4hdil9IHN0eWxlPXt7YmFja2dyb3VuZDoibm9uZSIsYm9yZGVyOiJub25lIixjdXJzb3I6InBvaW50ZXIiLGNvbG9yOiIjNzg3MTZjIixmb250U2l6ZToxOCxsaW5lSGVpZ2h0OjF9fT7imLA8L2J1dHRvbj4KICAgICAgICAgICAgPHNwYW4gc3R5bGU9e3tmb250U2l6ZToxMCxjb2xvcjoiI2E4YTI5ZSIsZm9udFdlaWdodDo1MDB9fT5LUFIgTGFiPC9zcGFuPgogICAgICAgICAgICA8c3BhbiBzdHlsZT17e2NvbG9yOiIjZDZkM2QxIn19Pi88L3NwYW4+CiAgICAgICAgICAgIDxzcGFuIHN0eWxlPXt7Zm9udFNpemU6MTEsZm9udFdlaWdodDo4MDAsY29sb3I6IiMxYzE5MTciLHRleHRUcmFuc2Zvcm06ImNhcGl0YWxpemUifX0+e0FMTF9OQVYuZmluZChuPT5uLmlkPT09bmF2KT8ubHx8bmF2fTwvc3Bhbj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPGRpdiBzdHlsZT17e2Rpc3BsYXk6ImZsZXgiLGFsaWduSXRlbXM6ImNlbnRlciIsZ2FwOjd9fT4KICAgICAgICAgICAgey8qIE5vdGlmaWNhdGlvbnMgKi99CiAgICAgICAgICAgIDxkaXYgcmVmPXtub3RpZlJlZn0gc3R5bGU9e3twb3NpdGlvbjoicmVsYXRpdmUifX0+CiAgICAgICAgICAgICAgPGJ1dHRvbiBvbkNsaWNrPXsoKT0+c2V0RGFyayhkPT4hZCl9IHRpdGxlPXtkYXJrPyJMaWdodCBtb2RlIjoiRGFyayBtb2RlIn0gc3R5bGU9e3tiYWNrZ3JvdW5kOiJub25lIixib3JkZXI6IjFweCBzb2xpZCAjZTdlNWU0Iixib3JkZXJSYWRpdXM6NyxwYWRkaW5nOiI1cHggOXB4IixjdXJzb3I6InBvaW50ZXIiLGZvbnRTaXplOjE0fX0+e2Rhcms/IkxpZ2h0IjoiRGFyayJ9PC9idXR0b24+CiAgICAgICAgICAgICAgPGJ1dHRvbiBvbkNsaWNrPXsoKT0+e3NldE5vdGlmT3Blbih2PT4hdik7cmVmcmVzaE5vdGlmcygpO319IHN0eWxlPXt7cG9zaXRpb246InJlbGF0aXZlIixiYWNrZ3JvdW5kOiJub25lIixib3JkZXI6IjFweCBzb2xpZCAjZTdlNWU0Iixib3JkZXJSYWRpdXM6NyxwYWRkaW5nOiI1cHggOXB4IixjdXJzb3I6InBvaW50ZXIiLGNvbG9yOiIjNzg3MTZjIixmb250U2l6ZToxNH19PgogICAgICAgICAgICAgICAg8J+UlAogICAgICAgICAgICAgICAge3VucmVhZD4wJiY8c3BhbiBzdHlsZT17e3Bvc2l0aW9uOiJhYnNvbHV0ZSIsdG9wOi0zLHJpZ2h0Oi0zLGJhY2tncm91bmQ6IiNlZjQ0NDQiLGNvbG9yOiIjZmZmIixib3JkZXJSYWRpdXM6IjUwJSIsd2lkdGg6MTQsaGVpZ2h0OjE0LGZvbnRTaXplOjgsZm9udFdlaWdodDo4MDAsZGlzcGxheToiZmxleCIsYWxpZ25JdGVtczoiY2VudGVyIixqdXN0aWZ5Q29udGVudDoiY2VudGVyIixib3JkZXI6IjJweCBzb2xpZCAjZmZmIn19Pnt1bnJlYWR9PC9zcGFuPn0KICAgICAgICAgICAgICA8L2J1dHRvbj4KICAgICAgICAgICAgICB7bm90aWZPcGVuJiY8ZGl2IHN0eWxlPXt7cG9zaXRpb246ImFic29sdXRlIix0b3A6ImNhbGMoMTAwJSArIDdweCkiLHJpZ2h0OjAsd2lkdGg6MzEwLGJhY2tncm91bmQ6InZhcigtLWJnLWNhcmQpIixib3JkZXI6IjFweCBzb2xpZCB2YXIoLS1ib3JkZXIpIixib3JkZXJSYWRpdXM6MTIsYm94U2hhZG93OiIwIDhweCAyOHB4IHJnYmEoMCwwLDAsLjEpIix6SW5kZXg6MjAwLG92ZXJmbG93OiJoaWRkZW4ifX0+CiAgICAgICAgICAgICAgICA8ZGl2IHN0eWxlPXt7cGFkZGluZzoiMTBweCAxNHB4Iixib3JkZXJCb3R0b206IjFweCBzb2xpZCAjZmFmYWY5IixkaXNwbGF5OiJmbGV4IixqdXN0aWZ5Q29udGVudDoic3BhY2UtYmV0d2VlbiIsYWxpZ25JdGVtczoiY2VudGVyIn19PgogICAgICAgICAgICAgICAgICA8c3BhbiBzdHlsZT17e2ZvbnRTaXplOjEyLGZvbnRXZWlnaHQ6ODAwLGNvbG9yOiIjMWMxOTE3In19Pk5vdGlmaWNhdGlvbnM8L3NwYW4+CiAgICAgICAgICAgICAgICAgIDxidXR0b24gb25DbGljaz17KCk9PntpZih1c2VyPy5pZClhcGkubWFya0FsbFJlYWQodXNlci5pZCkudGhlbigoKT0+c2V0Tm90aWZzKG49Pm4ubWFwKHg9Pih7Li4ueCxpc19yZWFkOjF9KSkpKS5jYXRjaCgoKT0+e30pO319IHN0eWxlPXt7Zm9udFNpemU6MTAsY29sb3I6Qi5wcmksZm9udFdlaWdodDo2MDAsYmFja2dyb3VuZDoibm9uZSIsYm9yZGVyOiJub25lIixjdXJzb3I6InBvaW50ZXIifX0+TWFyayBhbGwgcmVhZDwvYnV0dG9uPgogICAgICAgICAgICAgICAgPC9kaXY+CiAgICAgICAgICAgICAgICB7bm90aWZzLmxlbmd0aD09PTA/PGRpdiBzdHlsZT17e3BhZGRpbmc6IjIwcHggMTRweCIsdGV4dEFsaWduOiJjZW50ZXIiLGNvbG9yOiIjYThhMjllIixmb250U2l6ZToxMn19Pk5vIG5vdGlmaWNhdGlvbnM8L2Rpdj46CiAgICAgICAgICAgICAgICBub3RpZnMuc2xpY2UoMCw4KS5tYXAobj0+PGRpdiBrZXk9e24uaWR9IHN0eWxlPXt7cGFkZGluZzoiOXB4IDE0cHgiLGJhY2tncm91bmQ6bi5pc19yZWFkPyJ0cmFuc3BhcmVudCI6IiNmZmY3ZWQiLGJvcmRlckJvdHRvbToiMXB4IHNvbGlkICNmYWZhZjkifX0+CiAgICAgICAgICAgICAgICAgIDxwIHN0eWxlPXt7bWFyZ2luOjAsZm9udFNpemU6MTEsY29sb3I6IiMxYzE5MTciLGZvbnRXZWlnaHQ6bi5pc19yZWFkPzQwMDo2MDB9fT57bi5tZXNzYWdlfHxuLnRpdGxlfHwiTm90aWZpY2F0aW9uIn08L3A+CiAgICAgICAgICAgICAgICAgIDxzcGFuIHN0eWxlPXt7Zm9udFNpemU6MTAsY29sb3I6IiNhOGEyOWUifX0+eyhuLmNyZWF0ZWRfYXR8fCIiKS5zbGljZSgwLDE2KX08L3NwYW4+CiAgICAgICAgICAgICAgICA8L2Rpdj4pfQogICAgICAgICAgICAgIDwvZGl2Pn0KICAgICAgICAgICAgPC9kaXY+CiAgICAgICAgICAgIDxidXR0b24gb25DbGljaz17KCk9PnNldENmZyh0cnVlKX0gc3R5bGU9e3tiYWNrZ3JvdW5kOiJub25lIixib3JkZXI6IjFweCBzb2xpZCAjZTdlNWU0Iixib3JkZXJSYWRpdXM6NyxwYWRkaW5nOiI1cHggOXB4IixjdXJzb3I6InBvaW50ZXIiLGNvbG9yOiIjNzg3MTZjIixmb250U2l6ZToxNH19IHRpdGxlPSJTZXJ2ZXIgQ29uZmlnIj7wn5OhPC9idXR0b24+CiAgICAgICAgICAgIDxkaXYgc3R5bGU9e3tkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGdhcDo2fX0+CiAgICAgICAgICAgIHt3aW5kb3cuaW5uZXJXaWR0aDw9NzY4JiY8YnV0dG9uIG9uQ2xpY2s9e2hhbmRsZUxvZ291dH0gc3R5bGU9e3tiYWNrZ3JvdW5kOiIjZmVmMmYyIixib3JkZXI6IjFweCBzb2xpZCAjZmNhNWE1Iixib3JkZXJSYWRpdXM6OCxwYWRkaW5nOiI2cHggMTBweCIsZm9udFNpemU6MTEsZm9udFdlaWdodDo3MDAsY29sb3I6IiNkYzI2MjYiLGN1cnNvcjoicG9pbnRlciJ9fT7wn5qqIExvZ291dDwvYnV0dG9uPn0KICAgICAgICAgICAgPGRpdiBzdHlsZT17e3dpZHRoOjMwLGhlaWdodDozMCxib3JkZXJSYWRpdXM6IjUwJSIsYmFja2dyb3VuZDpgbGluZWFyLWdyYWRpZW50KDEzNWRlZywke0IucHJpfSwke0IucHJpRH0pYCxkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGp1c3RpZnlDb250ZW50OiJjZW50ZXIiLGZvbnRTaXplOjEwLGZvbnRXZWlnaHQ6ODAwLGNvbG9yOiIjZmZmIixjdXJzb3I6InBvaW50ZXIifX0gdGl0bGU9e3VzZXI/LnVzZXJuYW1lfT57SU5JKHVzZXI/LnVzZXJuYW1lKX08L2Rpdj4KICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgPC9oZWFkZXI+CiAgICAgICAgPG1haW4gc3R5bGU9e3tmbGV4OjEsb3ZlcmZsb3dZOiJhdXRvIn19PntyZW5kZXJQYWdlKCl9PC9tYWluPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgogICAgPEJvdHRvbU5hdiBuYXY9e25hdn0gc2V0TmF2PXtzZXROYXZ9IHVzZXI9e3VzZXJ9IHVucmVhZD17dW5yZWFkfS8+CiAgPC8+Owp9CgovKiDilIDilIAgUFdBIElOU1RBTEwgUFJPTVBUIOKUgOKUgCAqLwpmdW5jdGlvbiBJbnN0YWxsQmFubmVyKCl7CiAgY29uc3RbcHJvbXB0LHNldFByb21wdF09dXNlU3RhdGUobnVsbCk7Y29uc3Rbc2hvd24sc2V0U2hvd25dPXVzZVN0YXRlKGZhbHNlKTsKICB1c2VFZmZlY3QoKCk9PnsKICAgIGNvbnN0IGhhbmRsZXI9ZT0+e2UucHJldmVudERlZmF1bHQoKTtzZXRQcm9tcHQoZSk7c2V0U2hvd24odHJ1ZSk7fTsKICAgIHdpbmRvdy5hZGRFdmVudExpc3RlbmVyKCJiZWZvcmVpbnN0YWxscHJvbXB0IixoYW5kbGVyKTsKICAgIHJldHVybigpPT53aW5kb3cucmVtb3ZlRXZlbnRMaXN0ZW5lcigiYmVmb3JlaW5zdGFsbHByb21wdCIsaGFuZGxlcik7CiAgfSxbXSk7CiAgaWYoIXNob3dufHwhcHJvbXB0KXJldHVybiBudWxsOwogIGNvbnN0IGluc3RhbGw9YXN5bmMoKT0+e3Byb21wdC5wcm9tcHQoKTtjb25zdCByPWF3YWl0IHByb21wdC51c2VyQ2hvaWNlO2lmKHIub3V0Y29tZT09PSJhY2NlcHRlZCIpc2V0U2hvd24oZmFsc2UpO307CiAgcmV0dXJuPGRpdiBzdHlsZT17e3Bvc2l0aW9uOiJmaXhlZCIsdG9wOjAsbGVmdDowLHJpZ2h0OjAsYmFja2dyb3VuZDpgbGluZWFyLWdyYWRpZW50KDEzNWRlZywke0IucHJpfSwke0IucHJpRH0pYCxjb2xvcjoiI2ZmZiIscGFkZGluZzoiMTBweCAxNnB4IixkaXNwbGF5OiJmbGV4IixqdXN0aWZ5Q29udGVudDoic3BhY2UtYmV0d2VlbiIsYWxpZ25JdGVtczoiY2VudGVyIix6SW5kZXg6OTk5OSxib3hTaGFkb3c6IjAgMnB4IDEycHggcmdiYSgwLDAsMCwuMikifX0+CiAgICA8ZGl2IHN0eWxlPXt7Zm9udFNpemU6MTIsZm9udFdlaWdodDo2MDB9fT7wn5OxIEFwcCDgsJfgsL4gSW5zdGFsbCDgsJrgsYfgsK/gsILgsKHgsL8hPC9kaXY+CiAgICA8ZGl2IHN0eWxlPXt7ZGlzcGxheToiZmxleCIsZ2FwOjh9fT4KICAgICAgPGJ1dHRvbiBvbkNsaWNrPXtpbnN0YWxsfSBzdHlsZT17e2JhY2tncm91bmQ6IiNmZmYiLGNvbG9yOkIucHJpLGJvcmRlcjoibm9uZSIsYm9yZGVyUmFkaXVzOjYscGFkZGluZzoiNnB4IDEycHgiLGZvbnRTaXplOjExLGZvbnRXZWlnaHQ6NzAwLGN1cnNvcjoicG9pbnRlciJ9fT5JbnN0YWxsPC9idXR0b24+CiAgICAgIDxidXR0b24gb25DbGljaz17KCk9PnNldFNob3duKGZhbHNlKX0gc3R5bGU9e3tiYWNrZ3JvdW5kOiJyZ2JhKDI1NSwyNTUsMjU1LC4yKSIsY29sb3I6IiNmZmYiLGJvcmRlcjoibm9uZSIsYm9yZGVyUmFkaXVzOjYscGFkZGluZzoiNnB4IDEwcHgiLGZvbnRTaXplOjExLGN1cnNvcjoicG9pbnRlciJ9fT7inJU8L2J1dHRvbj4KICAgIDwvZGl2PgogIDwvZGl2PjsKfQoKLyog4pSA4pSAIE1PQklMRSBCT1RUT00gTkFWIOKUgOKUgCAqLwpmdW5jdGlvbiBCb3R0b21OYXYoe25hdixzZXROYXYsdXNlcix1bnJlYWR9KXsKICBpZih3aW5kb3cuaW5uZXJXaWR0aD43NjgpcmV0dXJuIG51bGw7CiAgY29uc3QgaXRlbXM9Z2V0TmF2KHVzZXI/LnJvbGUpLnNsaWNlKDAsNSk7CiAgcmV0dXJuPGRpdiBzdHlsZT17e3Bvc2l0aW9uOiJmaXhlZCIsYm90dG9tOjAsbGVmdDowLHJpZ2h0OjAsaGVpZ2h0OjU2LGJhY2tncm91bmQ6Qi5zaWRlLGRpc3BsYXk6ImZsZXgiLGFsaWduSXRlbXM6InN0cmV0Y2giLHpJbmRleDoxMDAsYm9yZGVyVG9wOiIxcHggc29saWQgIzI5MjUyNCIsYm94U2hhZG93OiIwIC00cHggMTZweCByZ2JhKDAsMCwwLC4yKSJ9fT4KICAgIHtpdGVtcy5tYXAoaXRlbT0+e2NvbnN0IGFjdGl2ZT1uYXY9PT1pdGVtLmlkO3JldHVybigKICAgICAgPGJ1dHRvbiBrZXk9e2l0ZW0uaWR9IG9uQ2xpY2s9eygpPT5zZXROYXYoaXRlbS5pZCl9CiAgICAgICAgc3R5bGU9e3tmbGV4OjEsZGlzcGxheToiZmxleCIsZmxleERpcmVjdGlvbjoiY29sdW1uIixhbGlnbkl0ZW1zOiJjZW50ZXIiLGp1c3RpZnlDb250ZW50OiJjZW50ZXIiLGdhcDoyLGJhY2tncm91bmQ6YWN0aXZlP0Iuc2lkZUE6InRyYW5zcGFyZW50Iixib3JkZXI6Im5vbmUiLGJvcmRlclRvcDphY3RpdmU/YDJweCBzb2xpZCAke0IucHJpfWA6IjJweCBzb2xpZCB0cmFuc3BhcmVudCIsY29sb3I6YWN0aXZlPyIjZmZmIjpCLnNpZGVNdXQsY3Vyc29yOiJwb2ludGVyIixwb3NpdGlvbjoicmVsYXRpdmUiLHBhZGRpbmc6IjZweCAwIn19PgogICAgICAgIDxzcGFuIHN0eWxlPXt7Zm9udFNpemU6MTYsbGluZUhlaWdodDoxfX0+e2l0ZW0uZX08L3NwYW4+CiAgICAgICAgPHNwYW4gc3R5bGU9e3tmb250U2l6ZTo4LGZvbnRXZWlnaHQ6YWN0aXZlPzcwMDo1MDAsbGV0dGVyU3BhY2luZzoiLjAyZW0ifX0+e2l0ZW0ubH08L3NwYW4+CiAgICAgICAge2l0ZW0uaWQ9PT0iZGFzaGJvYXJkIiYmdW5yZWFkPjAmJjxzcGFuIHN0eWxlPXt7cG9zaXRpb246ImFic29sdXRlIix0b3A6NCxyaWdodDoiY2FsYyg1MCUgLSAxNHB4KSIsYmFja2dyb3VuZDoiI2VmNDQ0NCIsY29sb3I6IiNmZmYiLGJvcmRlclJhZGl1czoiNTAlIix3aWR0aDoxNCxoZWlnaHQ6MTQsZm9udFNpemU6OCxmb250V2VpZ2h0OjgwMCxkaXNwbGF5OiJmbGV4IixhbGlnbkl0ZW1zOiJjZW50ZXIiLGp1c3RpZnlDb250ZW50OiJjZW50ZXIifX0+e3VucmVhZH08L3NwYW4+fQogICAgICA8L2J1dHRvbj4pO30pfQogIDwvZGl2PjsKfQoKUmVhY3RET00uY3JlYXRlUm9vdChkb2N1bWVudC5nZXRFbGVtZW50QnlJZCgicm9vdCIpKS5yZW5kZXIoPEFwcC8+KTsKPC9zY3JpcHQ+CjwvYm9keT4KPC9odG1sPg==").decode("utf-8")

@app.get("/app", tags=["Health"])
def serve_app():
    """HTML app — embedded directly in server."""
    from fastapi.responses import HTMLResponse
    # Try local file first
    for name in ["KPR_Lab.html", "KPR_Lab_CRM_Dashboard.html", "index.html"]:
        if os.path.exists(name):
            return FileResponse(name, media_type="text/html")
    # Serve embedded HTML
    return HTMLResponse(content=_EMBEDDED_HTML, status_code=200)


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
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (data.name, data.mobile, data.email, data.address, data.tags,
             data.alternate_mobile, data.gst_no, data.pan_no)
        )
        new_id = _lastrowid(conn)
        log_activity(conn, current_user, "Customer Add", f"Customer '{data.name}' added")
    if NEON_SYNC:
        neon_sync.sync_customer({"id":new_id,"name":data.name,"mobile":data.mobile,"email":data.email,"address":data.address,"tags":data.tags,"alternate_mobile":data.alternate_mobile,"gst_no":data.gst_no,"pan_no":data.pan_no})
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
        new_id = _lastrowid(conn)
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
    if NEON_SYNC:
        neon_sync.sync_job({"id":new_id,"customer_id":data.customer_id,"job_type":data.job_type,
            "description":data.description,"size":data.size,"initial_price":data.initial_price,
            "discount_amount":data.discount_amount,"advance1":data.advance1,
            "final_price":final_price,"balance":balance,
            "payment_status":"Advance Paid" if data.advance1>0 else "Unpaid",
            "status":"Pending","start_date":start_date,"due_date":data.due_date,
            "notes":data.notes,"assigned_staff_id":data.assigned_staff_id})
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
        new_id = _lastrowid(conn)
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
    if NEON_SYNC:
        neon_sync.sync_payment({"id":new_id,"customer_id":data.customer_id,
            "job_id":data.job_id,"invoice_id":data.invoice_id,
            "amount":data.amount,"payment_date":data.payment_date,
            "payment_mode":data.payment_mode,"notes":data.notes})
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
        cols_rows = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='inventory_transactions' AND table_schema='public'").fetchall(); cols = [r["column_name"] for r in cols_rows]
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
        # New stock after update
        new_stock_row = conn.execute("SELECT current_stock FROM inventory_items WHERE id=?", (data.item_id,)).fetchone()
        new_stock = new_stock_row["current_stock"] if new_stock_row else 0
    if NEON_SYNC:
        import datetime as _dt
        neon_sync.sync_inventory_transaction({"id":0,"item_id":data.item_id,
            "user_id":data.user_id,"job_id":data.job_id,
            "transaction_type":data.trans_type,"quantity":float(data.qty),
            "remarks":data.remarks,
            "timestamp":_dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
        neon_sync.sync_inventory_stock(data.item_id, new_stock)
    return {"success": True}


@app.get("/inventory/my_entries/{user_id}", tags=["Inventory"])
def my_material_entries(user_id: int, days: int = 30,
                         current_user: dict = Depends(get_current_user)):
    with get_db() as conn:
        cols_rows = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='inventory_transactions' AND table_schema='public'").fetchall(); cols = [r["column_name"] for r in cols_rows]
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
              AND t.timestamp >= NOW() - INTERVAL '{int(days)} days'
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
        new_id = _lastrowid(conn)
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
            FROM inventory_transactions WHERE DATE(timestamp)=CURRENT_DATE
        """).fetchone()
        r30 = conn.execute("""
            SELECT SUM(CASE WHEN transaction_type='Usage'   THEN quantity ELSE 0 END) AS u,
                   SUM(CASE WHEN transaction_type='Wastage' THEN quantity ELSE 0 END) AS w
            FROM inventory_transactions WHERE timestamp>=datetime('now','-30 days'
        """).fetchone()
        top = conn.execute("""
            SELECT i.name AS material, SUM(t.quantity) AS wasted
            FROM inventory_transactions t JOIN inventory_items i ON t.item_id=i.id
            WHERE t.transaction_type='Wastage' AND t.timestamp>=datetime('now','-30 days'
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
        new_id = _lastrowid(conn)
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
    print(f"  Database: Neon PostgreSQL (Cloud)")
    print(f"  Token expiry: {ACCESS_TOKEN_EXPIRE_MINUTES // 60} hours")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
