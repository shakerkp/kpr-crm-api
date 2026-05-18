"""
neon_sync.py — KPR Lab CRM
===========================
SQLite లో save అవగానే real-time గా Neon DB కి push చేస్తుంది.
Background queue వాడుతుంది — API speed affect కాదు.
"""

import psycopg2
from psycopg2.extras import execute_values
import threading
import queue
import datetime
import os
from dotenv import load_dotenv

load_dotenv()

NEON_URL = "postgresql://neondb_owner:npg_t3Us4VicjbAe@ep-square-hat-ao8gdlbd.c-2.ap-southeast-1.aws.neon.tech/neondb?sslmode=require"

# ── Background queue ──────────────────────────────────────────────────────────
_q: queue.Queue = queue.Queue()
_worker_started = False


def _log(msg, level="INFO"):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] NEON-SYNC [{level}]: {msg}")


def _get_neon():
    return psycopg2.connect(NEON_URL)


# ── Worker thread ─────────────────────────────────────────────────────────────

def _worker():
    """Background thread — queue లో items తీసుకుని Neon DB కి push చేస్తుంది."""
    while True:
        try:
            task = _q.get(timeout=5)
            if task is None:
                break
            _process(task)
        except queue.Empty:
            continue
        except Exception as e:
            _log(f"Worker error: {e}", "ERROR")


def _process(task):
    """ఒక్క task process చేస్తుంది."""
    table  = task["table"]
    data   = task["data"]
    method = task.get("method", "upsert")

    try:
        conn = _get_neon()
        cur  = conn.cursor()

        if method == "upsert":
            cols    = list(data.keys())
            vals    = [tuple(data.values())]
            col_str = ", ".join(cols)
            upd     = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != "id")
            sql     = f"INSERT INTO {table} ({col_str}) VALUES %s ON CONFLICT (id) DO UPDATE SET {upd}"
            execute_values(cur, sql, vals)

        elif method == "upsert_key":
            # settings లాంటి key-value tables కోసం
            key_col = task.get("key_col", "key")
            cols    = list(data.keys())
            vals    = [tuple(data.values())]
            col_str = ", ".join(cols)
            upd     = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c != key_col)
            sql     = f"INSERT INTO {table} ({col_str}) VALUES %s ON CONFLICT ({key_col}) DO UPDATE SET {upd}"
            execute_values(cur, sql, vals)

        elif method == "update_cols":
            # specific columns మాత్రమే update (status update లాంటివి)
            update_data = task["update_data"]
            where_col   = task.get("where_col", "id")
            where_val   = task["where_val"]
            set_clause  = ", ".join(f"{k}=%s" for k in update_data)
            cur.execute(
                f"UPDATE {table} SET {set_clause} WHERE {where_col}=%s",
                list(update_data.values()) + [where_val]
            )

        conn.commit()
        _log(f"✅ {table} synced ({method})")
    except Exception as e:
        _log(f"❌ {table} sync failed: {e}", "ERROR")
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _push(task):
    """Task ని queue లో add చేస్తుంది."""
    global _worker_started
    if not _worker_started:
        t = threading.Thread(target=_worker, daemon=True, name="NeonSyncWorker")
        t.start()
        _worker_started = True
        _log("Worker thread started.")
    _q.put(task)


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API — kpr_api_server.py ఇవి call చేస్తుంది
# ─────────────────────────────────────────────────────────────────────────────

def sync_customer(row: dict):
    """Customer add/update → Neon DB."""
    _push({"table": "customers", "data": row, "method": "upsert"})


def sync_job(row: dict):
    """Job add/update → Neon DB."""
    _push({"table": "jobs", "data": row, "method": "upsert"})


def sync_job_status(job_id: int, status: str, notes: str = None, completion_date: str = None):
    """Job status update → Neon DB."""
    upd = {"status": status}
    if notes:
        upd["notes"] = notes
    if completion_date:
        upd["completion_date"] = completion_date
    _push({
        "table":       "jobs",
        "method":      "update_cols",
        "update_data": upd,
        "where_col":   "id",
        "where_val":   job_id
    })


def sync_payment(row: dict):
    """Payment → Neon DB."""
    _push({"table": "payments", "data": row, "method": "upsert"})


def sync_inventory_transaction(row: dict):
    """Inventory transaction → Neon DB."""
    _push({"table": "inventory_transactions", "data": row, "method": "upsert"})


def sync_inventory_stock(item_id: int, new_stock: float):
    """Stock level update → Neon DB."""
    _push({
        "table":       "inventory_items",
        "method":      "update_cols",
        "update_data": {"current_stock": new_stock,
                        "last_updated": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
        "where_col":   "id",
        "where_val":   item_id
    })


def sync_notification(row: dict):
    """Notification → Neon DB."""
    _push({"table": "notifications", "data": row, "method": "upsert"})


def sync_setting(key: str, value: str):
    """Setting → Neon DB."""
    _push({
        "table":   "settings",
        "data":    {"key": key, "value": value},
        "method":  "upsert_key",
        "key_col": "key"
    })
