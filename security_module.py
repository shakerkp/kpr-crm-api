"""
security_module.py — KPR Lab CRM Security Enhancements
=======================================================
kpr_api_server.py లో ఈ module import చేయాలి:
    from security_module import RateLimiter, SessionManager, log_security_event

Features:
  ✅ Login rate limiting (brute-force protection)
  ✅ Session management (one session per user option)
  ✅ IP-based access logging
  ✅ Security event logging to DB
  ✅ Token expiry & cleanup
"""

import time
import datetime
import threading
import sqlite3
import os
from collections import defaultdict
from typing import Dict, Optional

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────
MAX_LOGIN_ATTEMPTS    = 5          # ఇన్ని failures తర్వాత lockout
LOCKOUT_SECONDS       = 300        # 5 minutes lockout
ONE_SESSION_PER_USER  = False      # True = ఒకే time లో ఒక్కడే login (role కాదు, user)
DATABASE_NAME         = "kprlab.db"


# ═══════════════════════════════════════════════════════════════
# Rate Limiter — Login Brute-Force Protection
# ═══════════════════════════════════════════════════════════════

class RateLimiter:
    """
    IP + username combination based login rate limiting.
    Server memory లో ఉంటుంది — restart అయితే reset అవుతుంది.
    """

    def __init__(self, max_attempts: int = MAX_LOGIN_ATTEMPTS,
                 lockout_seconds: int = LOCKOUT_SECONDS):
        self.max_attempts   = max_attempts
        self.lockout_seconds = lockout_seconds
        self._attempts: Dict[str, list] = defaultdict(list)  # key → [timestamp, ...]
        self._lock = threading.Lock()

    def _key(self, ip: str, username: str) -> str:
        return f"{ip}|{username.lower()}"

    def is_blocked(self, ip: str, username: str) -> tuple[bool, int]:
        """
        Returns (is_blocked, seconds_remaining).
        Blocked అయితే login reject చేయాలి.
        """
        key = self._key(ip, username)
        now = time.time()
        with self._lock:
            # Expired entries remove
            self._attempts[key] = [t for t in self._attempts[key]
                                    if now - t < self.lockout_seconds]
            count = len(self._attempts[key])
            if count >= self.max_attempts:
                oldest = self._attempts[key][0]
                remaining = int(self.lockout_seconds - (now - oldest))
                return True, max(0, remaining)
        return False, 0

    def record_failure(self, ip: str, username: str):
        """Failed login attempt record చేయాలి."""
        key = self._key(ip, username)
        with self._lock:
            self._attempts[key].append(time.time())

    def reset(self, ip: str, username: str):
        """Successful login తర్వాత reset చేయాలి."""
        key = self._key(ip, username)
        with self._lock:
            self._attempts.pop(key, None)

    def get_attempt_count(self, ip: str, username: str) -> int:
        key = self._key(ip, username)
        now = time.time()
        with self._lock:
            self._attempts[key] = [t for t in self._attempts[key]
                                    if now - t < self.lockout_seconds]
            return len(self._attempts[key])


# ═══════════════════════════════════════════════════════════════
# Session Manager — Token + User Tracking
# ═══════════════════════════════════════════════════════════════

class SessionManager:
    """
    Active sessions track చేస్తుంది.
    ONE_SESSION_PER_USER=True అయితే same user రెండు PCs లో login చేయలేరు.
    """

    def __init__(self, one_session_per_user: bool = ONE_SESSION_PER_USER):
        self.one_session_per_user = one_session_per_user
        # token → {user_id, username, role, ip, login_time, expires}
        self._sessions: Dict[str, dict] = {}
        self._user_tokens: Dict[int, str] = {}   # user_id → active token
        self._lock = threading.Lock()

    def create_session(self, token: str, user_id: int, username: str,
                       role: str, ip: str, expires: datetime.datetime):
        """New session create చేయాలి. ONE_SESSION_PER_USER=True అయితే old session kill చేస్తుంది."""
        with self._lock:
            if self.one_session_per_user and user_id in self._user_tokens:
                # Old token invalidate
                old_token = self._user_tokens[user_id]
                self._sessions.pop(old_token, None)

            self._sessions[token] = {
                "user_id":    user_id,
                "username":   username,
                "role":       role,
                "ip":         ip,
                "login_time": datetime.datetime.now().isoformat(),
                "expires":    expires,
            }
            self._user_tokens[user_id] = token

    def get_session(self, token: str) -> Optional[dict]:
        """Token valid అయితే session info return చేస్తుంది, లేదా None."""
        with self._lock:
            session = self._sessions.get(token)
            if not session:
                return None
            if datetime.datetime.utcnow() > session["expires"]:
                self._sessions.pop(token, None)
                self._user_tokens.pop(session["user_id"], None)
                return None
            return session

    def revoke_token(self, token: str):
        """Logout — token remove చేయాలి."""
        with self._lock:
            session = self._sessions.pop(token, None)
            if session:
                self._user_tokens.pop(session["user_id"], None)

    def revoke_user(self, user_id: int):
        """Admin — specific user అన్ని sessions force logout చేయాలి."""
        with self._lock:
            token = self._user_tokens.pop(user_id, None)
            if token:
                self._sessions.pop(token, None)

    def active_sessions(self) -> list:
        """Admin dashboard కోసం active sessions list."""
        now = datetime.datetime.utcnow()
        with self._lock:
            result = []
            for token, s in list(self._sessions.items()):
                if now <= s["expires"]:
                    result.append({
                        "username":   s["username"],
                        "role":       s["role"],
                        "ip":         s["ip"],
                        "login_time": s["login_time"],
                        "expires":    s["expires"].isoformat(),
                    })
                else:
                    # Expired cleanup
                    self._sessions.pop(token, None)
                    self._user_tokens.pop(s["user_id"], None)
            return result

    def cleanup_expired(self):
        """Background thread నుండి call చేయాలి."""
        now = datetime.datetime.utcnow()
        with self._lock:
            expired = [t for t, s in self._sessions.items() if now > s["expires"]]
            for t in expired:
                s = self._sessions.pop(t)
                self._user_tokens.pop(s["user_id"], None)


# ═══════════════════════════════════════════════════════════════
# Security Event Logger
# ═══════════════════════════════════════════════════════════════

def log_security_event(event_type: str, username: str, ip: str,
                        description: str, user_id: int = 0):
    """
    Security events DB లో log చేస్తుంది.
    Event types: LOGIN_SUCCESS, LOGIN_FAILED, LOCKED_OUT, LOGOUT,
                 FORCE_LOGOUT, SUSPICIOUS
    """
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Try security_log table first; fallback to activity_log
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS security_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT, event_type TEXT,
                    user_id INTEGER, username TEXT, ip TEXT, description TEXT
                )"""
            )
            conn.execute(
                "INSERT INTO security_log (timestamp,event_type,user_id,username,ip,description) VALUES (?,?,?,?,?,?)",
                (ts, event_type, user_id, username, ip, description)
            )
        except Exception:
            pass
        # Also write to activity_log for visibility
        conn.execute(
            "INSERT INTO activity_log (user_id,username,activity_type,description,timestamp) VALUES (?,?,?,?,?)",
            (user_id, username, f"SECURITY:{event_type}", f"[{ip}] {description}", ts)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[SECURITY LOG ERROR] {e}")


# ═══════════════════════════════════════════════════════════════
# Background Cleanup Thread
# ═══════════════════════════════════════════════════════════════

def start_session_cleanup(session_manager: SessionManager, interval_seconds: int = 300):
    """
    Every 5 minutes expired sessions cleanup చేస్తుంది.
    Server startup లో ఒకసారి call చేయాలి.
    """
    def _loop():
        while True:
            time.sleep(interval_seconds)
            try:
                session_manager.cleanup_expired()
            except Exception as e:
                print(f"[SESSION CLEANUP ERROR] {e}")

    t = threading.Thread(target=_loop, daemon=True)
    t.start()
    print(f"[Security] Session cleanup thread started (every {interval_seconds}s).")
