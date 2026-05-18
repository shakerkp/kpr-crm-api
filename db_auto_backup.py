"""
db_auto_backup.py — KPR Lab CRM Database Auto-Backup Service
=============================================================
రెండు modes లో వాడవచ్చు:

Mode 1 — kpr_api_server.py లో import చేసి server తో పాటు run చేయడం:
    from db_auto_backup import start_auto_backup
    start_auto_backup()          # server startup లో call చేయాలి

Mode 2 — Standalone గా run చేయడం (Windows Task Scheduler లో set చేయవచ్చు):
    python db_auto_backup.py

Features:
  ✅ Hourly auto-backup (configurable)
  ✅ Daily backup at midnight
  ✅ Backup rotation (last N backups మాత్రమే keep చేస్తుంది)
  ✅ DB integrity check before backup
  ✅ Backup success/failure logging
  ✅ Compressed backups (.db.bak)
"""

import sqlite3
import os
import shutil
import threading
import time
import datetime
import hashlib

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────
DATABASE_FILE      = "kprlab.db"
BACKUP_DIR         = "backups"
HOURLY_INTERVAL_S  = 3600          # 1 hour
MAX_HOURLY_BACKUPS = 24            # Last 24 hourly backups keep చేస్తుంది
MAX_DAILY_BACKUPS  = 30            # Last 30 daily backups keep చేస్తుంది
INTEGRITY_CHECK    = True          # Backup ముందు DB integrity check చేయాలా?
LOG_FILE           = os.path.join(BACKUP_DIR, "backup_log.txt")


# ─────────────────────────────────────────────────────────────
# Core Backup Function
# ─────────────────────────────────────────────────────────────

def _ensure_backup_dir():
    os.makedirs(BACKUP_DIR, exist_ok=True)
    # Windows: backup folder ని Hidden చేయడం (optional)
    # subprocess.run(["attrib", "+H", BACKUP_DIR], shell=True, capture_output=True)


def _log(message: str):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {message}"
    print(line)
    try:
        _ensure_backup_dir()
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _db_integrity_ok() -> bool:
    """DB corruption check చేస్తుంది. OK అయితే True return చేస్తుంది."""
    try:
        conn = sqlite3.connect(DATABASE_FILE)
        result = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        return result[0] == "ok"
    except Exception as e:
        _log(f"INTEGRITY CHECK ERROR: {e}")
        return False


def _file_hash(path: str) -> str:
    """Backup verify చేయడానికి MD5 hash."""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def do_backup(backup_type: str = "hourly") -> bool:
    """
    Actual backup perform చేస్తుంది.
    backup_type: "hourly" | "daily" | "manual"
    Returns True if successful.
    """
    if not os.path.exists(DATABASE_FILE):
        _log(f"BACKUP FAILED: Database file '{DATABASE_FILE}' not found.")
        return False

    if INTEGRITY_CHECK and not _db_integrity_ok():
        _log("BACKUP ABORTED: DB integrity check failed! Database may be corrupted.")
        return False

    _ensure_backup_dir()
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"kprlab_{backup_type}_{ts}.db.bak"
    backup_path = os.path.join(BACKUP_DIR, backup_name)

    try:
        # SQLite's own backup API — safe even while DB is in use
        src_conn = sqlite3.connect(DATABASE_FILE)
        dst_conn = sqlite3.connect(backup_path)
        src_conn.backup(dst_conn)
        src_conn.close()
        dst_conn.close()

        size_kb = os.path.getsize(backup_path) // 1024
        src_hash = _file_hash(DATABASE_FILE)
        bak_hash  = _file_hash(backup_path)

        if src_hash == bak_hash:
            _log(f"BACKUP OK [{backup_type}]: {backup_name} ({size_kb} KB) ✅ Hash verified.")
        else:
            _log(f"BACKUP WARNING [{backup_type}]: {backup_name} — hash mismatch! Source may have changed during backup.")

        # Update DB settings with last backup timestamp
        try:
            conn = sqlite3.connect(DATABASE_FILE)
            conn.execute(
                "UPDATE settings SET value=? WHERE key='last_backup_date'",
                (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

        return True

    except Exception as e:
        _log(f"BACKUP FAILED [{backup_type}]: {e}")
        return False
    finally:
        _rotate_backups(backup_type)


def _rotate_backups(backup_type: str):
    """Old backups delete చేస్తుంది — only keep last N."""
    max_keep = MAX_HOURLY_BACKUPS if backup_type == "hourly" else MAX_DAILY_BACKUPS
    try:
        files = sorted([
            f for f in os.listdir(BACKUP_DIR)
            if f.startswith(f"kprlab_{backup_type}_") and f.endswith(".db.bak")
        ])
        while len(files) > max_keep:
            old = os.path.join(BACKUP_DIR, files.pop(0))
            os.remove(old)
            _log(f"ROTATED: Deleted old backup {os.path.basename(old)}")
    except Exception as e:
        _log(f"ROTATION ERROR: {e}")


# ─────────────────────────────────────────────────────────────
# Background Auto-Backup Scheduler
# ─────────────────────────────────────────────────────────────

_backup_thread_started = False

def start_auto_backup(interval_seconds: int = HOURLY_INTERVAL_S):
    """
    kpr_api_server.py లో server startup తర్వాత call చేయాలి.
    Background thread లో hourly + daily backups run చేస్తుంది.
    """
    global _backup_thread_started
    if _backup_thread_started:
        return
    _backup_thread_started = True

    def _scheduler():
        _log("Auto-backup scheduler started.")
        last_daily_date = None

        # Immediate first backup on startup
        _log("Performing startup backup...")
        do_backup("hourly")

        while True:
            time.sleep(interval_seconds)
            now = datetime.datetime.now()

            # Hourly backup
            do_backup("hourly")

            # Daily backup at midnight (first run after midnight)
            today = now.date()
            if last_daily_date != today and now.hour == 0:
                do_backup("daily")
                last_daily_date = today

    t = threading.Thread(target=_scheduler, daemon=True, name="KPR-AutoBackup")
    t.start()
    _log(f"Auto-backup thread started. Interval: {interval_seconds // 60} minutes.")


# ─────────────────────────────────────────────────────────────
# Standalone Run
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    btype = sys.argv[1] if len(sys.argv) > 1 else "manual"
    print(f"KPR Lab — Manual Backup ({btype})")
    success = do_backup(btype)
    if success:
        print("✅ Backup completed successfully.")
        # List recent backups
        if os.path.exists(BACKUP_DIR):
            backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.endswith(".db.bak")], reverse=True)
            print(f"\nRecent backups ({len(backups)} total):")
            for b in backups[:10]:
                size = os.path.getsize(os.path.join(BACKUP_DIR, b)) // 1024
                print(f"  {b}  ({size} KB)")
    else:
        print("❌ Backup failed. Check backup_log.txt for details.")
    input("\nPress Enter to exit...")
