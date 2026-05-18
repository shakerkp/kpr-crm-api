"""
sync_service.py — KPR Lab CRM
==============================
SQLite (PC1 local) → Neon DB (Cloud) One-Way Sync

Usage:
  python sync_service.py            # ← background లో run చేయండి
  python sync_service.py --once     # ← ఒక్కసారి sync చేసి exit

PC1 లో start_server.bat లో add చేయండి:
  start /min python sync_service.py
"""

import sqlite3
import psycopg2
from psycopg2.extras import execute_values
import time
import datetime
import os
import sys
import json
import argparse

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────────────

SQLITE_DB   = "kprlab.db"          # PC1 లో SQLite file path
NEON_DB_URL = (
    "postgresql://neondb_owner:npg_t3Us4VicjbAe"
    "@ep-square-hat-ao8gdlbd.c-2.ap-southeast-1.aws.neon.tech"
    "/neondb?sslmode=require"
)
SYNC_INTERVAL_SEC = 60             # ప్రతి 60 seconds కి sync
STATE_FILE        = "sync_state.json"  # last sync timestamps save అవుతాయి

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

def log(msg, level="INFO"):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] SYNC [{level}]: {msg}")


# ─────────────────────────────────────────────────────────────────────────────
# STATE (last sync timestamps per table)
# ─────────────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ─────────────────────────────────────────────────────────────────────────────
# CONNECTIONS
# ─────────────────────────────────────────────────────────────────────────────

def get_sqlite():
    if not os.path.exists(SQLITE_DB):
        raise FileNotFoundError(f"SQLite DB '{SQLITE_DB}' కనుగొనబడలేదు. kprlab.db ఉన్న folder లో run చేయండి.")
    conn = sqlite3.connect(SQLITE_DB)
    conn.row_factory = sqlite3.Row
    return conn


def get_neon():
    return psycopg2.connect(NEON_DB_URL)


# ─────────────────────────────────────────────────────────────────────────────
# NEON DB TABLES ENSURE  (అన్ని tables Neon లో ఉండేలా చూస్తుంది)
# ─────────────────────────────────────────────────────────────────────────────

def ensure_neon_tables(nc):
    cur = nc.cursor()
    ddl_list = [

        # users
        """CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            is_active INTEGER DEFAULT 1,
            full_name TEXT, email TEXT, phone TEXT
        )""",

        # customers
        """CREATE TABLE IF NOT EXISTS customers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            mobile TEXT NOT NULL,
            email TEXT, address TEXT, tags TEXT,
            alternate_mobile TEXT, gst_no TEXT, pan_no TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )""",

        # job_types
        """CREATE TABLE IF NOT EXISTS job_types (
            id INTEGER PRIMARY KEY,
            category TEXT NOT NULL,
            name TEXT NOT NULL
        )""",

        # jobs
        """CREATE TABLE IF NOT EXISTS jobs (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER,
            job_type TEXT NOT NULL,
            description TEXT, size TEXT,
            initial_price REAL NOT NULL,
            discount_amount REAL DEFAULT 0.0,
            advance1 REAL DEFAULT 0.0,
            final_price REAL, balance REAL,
            payment_status TEXT DEFAULT 'Unpaid',
            payment_mode TEXT,
            assigned_staff_id INTEGER,
            status TEXT NOT NULL DEFAULT 'Pending',
            start_date TEXT NOT NULL,
            due_date TEXT, completion_date TEXT,
            delivery_date TEXT, notes TEXT,
            invoice_id INTEGER, attachments TEXT,
            rounded_off_amount REAL DEFAULT 0.0,
            gst_type TEXT DEFAULT 'None',
            gst_category TEXT,
            gst_percentage REAL DEFAULT 0.0,
            gst_amount REAL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT NOW()
        )""",

        # payments
        """CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY,
            customer_id INTEGER NOT NULL,
            job_id INTEGER, invoice_id INTEGER,
            amount REAL NOT NULL,
            payment_date TEXT NOT NULL,
            payment_mode TEXT, notes TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )""",

        # invoices
        """CREATE TABLE IF NOT EXISTS invoices (
            id INTEGER PRIMARY KEY,
            invoice_number TEXT NOT NULL,
            customer_id INTEGER NOT NULL,
            invoice_date TEXT NOT NULL,
            due_date TEXT,
            total_amount REAL NOT NULL,
            amount_paid REAL DEFAULT 0.0,
            balance_due REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending',
            notes TEXT, terms_and_conditions TEXT,
            created_by INTEGER,
            created_at TIMESTAMP DEFAULT NOW()
        )""",

        # invoice_line_items
        """CREATE TABLE IF NOT EXISTS invoice_line_items (
            id INTEGER PRIMARY KEY,
            invoice_id INTEGER NOT NULL,
            job_id INTEGER,
            item_description TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL,
            amount_billed_for_job REAL NOT NULL,
            hsn_sac_code TEXT,
            gst_rate REAL DEFAULT 0.0,
            gst_calculation_method TEXT DEFAULT 'Inclusive'
        )""",

        # inventory_categories
        """CREATE TABLE IF NOT EXISTS inventory_categories (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        )""",

        # vendors
        """CREATE TABLE IF NOT EXISTS vendors (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            contact_person TEXT, phone TEXT,
            email TEXT, address TEXT
        )""",

        # inventory_items
        """CREATE TABLE IF NOT EXISTS inventory_items (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category_id INTEGER, vendor_id INTEGER,
            current_stock REAL NOT NULL DEFAULT 0.0,
            unit_price REAL NOT NULL DEFAULT 0.0,
            last_restocked TEXT,
            reorder_level INTEGER DEFAULT 10,
            last_updated TIMESTAMP DEFAULT NOW(),
            sku TEXT, uom TEXT DEFAULT 'Pcs',
            item_type TEXT, item_size TEXT,
            is_active INTEGER DEFAULT 1
        )""",

        # inventory_transactions
        """CREATE TABLE IF NOT EXISTS inventory_transactions (
            id INTEGER PRIMARY KEY,
            item_id INTEGER, user_id INTEGER,
            job_id INTEGER,
            transaction_type TEXT,
            quantity REAL, remarks TEXT,
            timestamp TIMESTAMP DEFAULT NOW()
        )""",

        # notes
        """CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY,
            related_to TEXT, related_id INTEGER,
            note_text TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            created_by INTEGER
        )""",

        # notifications
        """CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            job_id INTEGER,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )""",

        # settings
        """CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""",

        # activity_log
        """CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY,
            user_id INTEGER, username TEXT,
            activity_type TEXT NOT NULL,
            description TEXT,
            timestamp TIMESTAMP DEFAULT NOW()
        )""",
    ]

    for ddl in ddl_list:
        cur.execute(ddl)
    nc.commit()
    log("Neon DB tables ensured ✅")


# ─────────────────────────────────────────────────────────────────────────────
# GENERIC UPSERT SYNC
# ─────────────────────────────────────────────────────────────────────────────

def sync_table(sc, nc, table: str, columns: list,
               conflict_col: str = "id",
               ts_col: str = None,
               last_sync: str = None) -> int:
    """
    SQLite table → Neon DB upsert sync.
    ts_col  : timestamp column ఉంటే incremental sync చేస్తుంది
    last_sync: last sync time string
    Returns : synced row count
    """
    sc_cur = sc.cursor()
    nc_cur = nc.cursor()

    # ── SQLite నుండి rows fetch ──────────────────────────────────────────────
    col_str = ", ".join(columns)

    if ts_col and last_sync:
        sc_cur.execute(
            f"SELECT {col_str} FROM {table} WHERE {ts_col} > ?",
            (last_sync,)
        )
    else:
        sc_cur.execute(f"SELECT {col_str} FROM {table}")

    rows = sc_cur.fetchall()
    if not rows:
        return 0

    values = [tuple(row) for row in rows]

    # ── Neon DB కి upsert ────────────────────────────────────────────────────
    placeholders = ", ".join(["%s"] * len(columns))
    update_set   = ", ".join(
        f"{c} = EXCLUDED.{c}" for c in columns if c != conflict_col
    )

    sql = f"""
        INSERT INTO {table} ({col_str})
        VALUES %s
        ON CONFLICT ({conflict_col}) DO UPDATE SET {update_set}
    """

    try:
        execute_values(nc_cur, sql, values)
        nc.commit()
        return len(values)
    except Exception as e:
        nc.rollback()
        log(f"  {table} upsert error: {e}", "WARN")
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# SETTINGS SYNC  (key-value, conflict on key)
# ─────────────────────────────────────────────────────────────────────────────

def sync_settings(sc, nc) -> int:
    sc_cur = sc.cursor()
    nc_cur = nc.cursor()
    sc_cur.execute("SELECT key, value FROM settings")
    rows = sc_cur.fetchall()
    if not rows:
        return 0
    try:
        execute_values(
            nc_cur,
            "INSERT INTO settings (key, value) VALUES %s "
            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
            [tuple(r) for r in rows]
        )
        nc.commit()
        return len(rows)
    except Exception as e:
        nc.rollback()
        log(f"  settings sync error: {e}", "WARN")
        return 0


# ─────────────────────────────────────────────────────────────────────────────
# FULL SYNC CYCLE
# ─────────────────────────────────────────────────────────────────────────────

def run_sync_cycle(state: dict) -> dict:
    log("═" * 50)
    log("Sync cycle starting...")

    try:
        sc = get_sqlite()
        nc = get_neon()
    except FileNotFoundError as e:
        log(str(e), "ERROR")
        return state
    except Exception as e:
        log(f"Connection error: {e}", "ERROR")
        return state

    try:
        ensure_neon_tables(nc)

        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total   = 0

        # ── Users (full sync — small table) ───────────────────────────────────
        n = sync_table(sc, nc, "users",
            ["id","username","password_hash","role","is_active","full_name","email","phone"])
        log(f"  users        → {n} rows synced")
        total += n

        # ── Customers (incremental by created_at) ─────────────────────────────
        cols = ["id","name","mobile","email","address","tags",
                "alternate_mobile","gst_no","pan_no","created_at"]
        # customers update ని track చేయడానికి full sync వాడదాం
        n = sync_table(sc, nc, "customers", cols)
        log(f"  customers    → {n} rows synced")
        total += n

        # ── Job Types ──────────────────────────────────────────────────────────
        n = sync_table(sc, nc, "job_types", ["id","category","name"])
        log(f"  job_types    → {n} rows synced")
        total += n

        # ── Jobs (full upsert — status/payment changes capture చేయాలి) ────────
        job_cols = [
            "id","customer_id","job_type","description","size",
            "initial_price","discount_amount","advance1","final_price","balance",
            "payment_status","payment_mode","assigned_staff_id","status",
            "start_date","due_date","completion_date","delivery_date","notes",
            "invoice_id","attachments","rounded_off_amount",
            "gst_type","gst_category","gst_percentage","gst_amount","created_at"
        ]
        # SQLite లో ఉన్న columns మాత్రమే select చేయాలి
        sc_cur = sc.cursor()
        sc_cur.execute("PRAGMA table_info(jobs)")
        existing_job_cols = [r[1] for r in sc_cur.fetchall()]
        job_cols = [c for c in job_cols if c in existing_job_cols]
        n = sync_table(sc, nc, "jobs", job_cols)
        log(f"  jobs         → {n} rows synced")
        total += n

        # ── Payments (incremental by created_at) ──────────────────────────────
        pay_cols = ["id","customer_id","job_id","invoice_id",
                    "amount","payment_date","payment_mode","notes","created_at"]
        sc_cur.execute("PRAGMA table_info(payments)")
        existing_pay_cols = [r[1] for r in sc_cur.fetchall()]
        pay_cols = [c for c in pay_cols if c in existing_pay_cols]
        n = sync_table(sc, nc, "payments", pay_cols,
                       ts_col="created_at", last_sync=state.get("payments"))
        log(f"  payments     → {n} rows synced")
        total += n
        if n > 0:
            state["payments"] = now_str

        # ── Invoices ──────────────────────────────────────────────────────────
        inv_cols = ["id","invoice_number","customer_id","invoice_date","due_date",
                    "total_amount","amount_paid","balance_due","status","notes",
                    "terms_and_conditions","created_by","created_at"]
        sc_cur.execute("PRAGMA table_info(invoices)")
        existing_inv_cols = [r[1] for r in sc_cur.fetchall()]
        inv_cols = [c for c in inv_cols if c in existing_inv_cols]
        n = sync_table(sc, nc, "invoices", inv_cols)
        log(f"  invoices     → {n} rows synced")
        total += n

        # ── Invoice Line Items ────────────────────────────────────────────────
        n = sync_table(sc, nc, "invoice_line_items",
            ["id","invoice_id","job_id","item_description","quantity",
             "unit_price","amount_billed_for_job","hsn_sac_code",
             "gst_rate","gst_calculation_method"])
        log(f"  invoice_items→ {n} rows synced")
        total += n

        # ── Inventory Categories ──────────────────────────────────────────────
        n = sync_table(sc, nc, "inventory_categories", ["id","name"])
        log(f"  inv_cats     → {n} rows synced")
        total += n

        # ── Vendors ───────────────────────────────────────────────────────────
        n = sync_table(sc, nc, "vendors",
            ["id","name","contact_person","phone","email","address"])
        log(f"  vendors      → {n} rows synced")
        total += n

        # ── Inventory Items ───────────────────────────────────────────────────
        inv_item_cols = ["id","name","category_id","vendor_id","current_stock",
                         "unit_price","last_restocked","reorder_level",
                         "last_updated","sku","uom","item_type","item_size","is_active"]
        sc_cur.execute("PRAGMA table_info(inventory_items)")
        existing_ii_cols = [r[1] for r in sc_cur.fetchall()]
        inv_item_cols = [c for c in inv_item_cols if c in existing_ii_cols]
        n = sync_table(sc, nc, "inventory_items", inv_item_cols,
                       ts_col="last_updated", last_sync=state.get("inventory_items"))
        log(f"  inv_items    → {n} rows synced")
        total += n
        if n > 0:
            state["inventory_items"] = now_str

        # ── Inventory Transactions (incremental) ──────────────────────────────
        try:
            n = sync_table(sc, nc, "inventory_transactions",
                ["id","item_id","user_id","job_id","transaction_type",
                 "quantity","remarks","timestamp"],
                ts_col="timestamp", last_sync=state.get("inventory_transactions"))
            log(f"  inv_txns     → {n} rows synced")
            total += n
            if n > 0:
                state["inventory_transactions"] = now_str
        except Exception:
            pass  # table లేకపోతే skip

        # ── Notes (incremental) ───────────────────────────────────────────────
        n = sync_table(sc, nc, "notes",
            ["id","related_to","related_id","note_text","created_at","created_by"],
            ts_col="created_at", last_sync=state.get("notes"))
        log(f"  notes        → {n} rows synced")
        total += n
        if n > 0:
            state["notes"] = now_str

        # ── Notifications (incremental) ───────────────────────────────────────
        try:
            n = sync_table(sc, nc, "notifications",
                ["id","user_id","title","message","job_id","is_read","created_at"],
                ts_col="created_at", last_sync=state.get("notifications"))
            log(f"  notifications→ {n} rows synced")
            total += n
            if n > 0:
                state["notifications"] = now_str
        except Exception:
            pass

        # ── Settings ──────────────────────────────────────────────────────────
        n = sync_settings(sc, nc)
        log(f"  settings     → {n} rows synced")
        total += n

        # ── Activity Log (incremental) ────────────────────────────────────────
        try:
            n = sync_table(sc, nc, "activity_log",
                ["id","user_id","username","activity_type","description","timestamp"],
                ts_col="timestamp", last_sync=state.get("activity_log"))
            log(f"  activity_log → {n} rows synced")
            total += n
            if n > 0:
                state["activity_log"] = now_str
        except Exception:
            pass

        state["last_sync"] = now_str
        log(f"✅ Sync complete! Total {total} records pushed to Neon DB.")

    except Exception as e:
        log(f"Sync cycle error: {e}", "ERROR")
        import traceback
        traceback.print_exc()
    finally:
        try: sc.close()
        except Exception: pass
        try: nc.close()
        except Exception: pass

    return state


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="KPR Lab SQLite → Neon DB Sync Service")
    parser.add_argument("--once", action="store_true", help="ఒక్కసారి sync చేసి exit")
    args = parser.parse_args()

    # kprlab.db ఉన్న folder కి cd చేయండి
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    log("🚀 KPR Lab Sync Service Started")
    log(f"   SQLite  : {os.path.abspath(SQLITE_DB)}")
    log(f"   Neon DB : Neon Cloud (Singapore)")
    log(f"   Interval: {SYNC_INTERVAL_SEC} seconds")

    state = load_state()

    if args.once:
        state = run_sync_cycle(state)
        save_state(state)
        log("--once mode: exiting.")
        return

    # ── Continuous loop ────────────────────────────────────────────────────
    log(f"Background sync loop starting. Press Ctrl+C to stop.")
    while True:
        try:
            state = run_sync_cycle(state)
            save_state(state)
            log(f"Next sync in {SYNC_INTERVAL_SEC} seconds...")
            time.sleep(SYNC_INTERVAL_SEC)
        except KeyboardInterrupt:
            log("Sync service stopped by user.")
            break
        except Exception as e:
            log(f"Unexpected error: {e}. Retrying in 30s...", "ERROR")
            time.sleep(30)


if __name__ == "__main__":
    main()
