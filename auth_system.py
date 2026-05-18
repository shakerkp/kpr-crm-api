# auth_system_clean.py
# Cleaned and fixed Auth System with DatabaseManager, LoginManager and AuthSystem UI
import tkinter as tk
from tkinter import ttk, messagebox
import hashlib
import sqlite3
import os
from datetime import datetime, timedelta
from typing import Dict, Any
import traceback
import uuid

import sys as _sys

_AUTH_APP_DATA = os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")),
    "KPRLabCRM"
)
os.makedirs(_AUTH_APP_DATA, exist_ok=True)

DB_FILE = os.path.join(_AUTH_APP_DATA, "kprlab.db")
PASSWORD_SALT = ""  # No salt — matches db_manager.py hash_password()

# -------------------- DatabaseManager --------------------
class DatabaseManager:
    def __init__(self, db_file: str = DB_FILE):
        self.db_file = db_file
        self.init_database()

    def init_database(self):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.cursor()

        # users table is managed by db_manager.py — only add missing auth columns
        cursor.execute("PRAGMA table_info(users)")
        existing_cols = [row[1] for row in cursor.fetchall()]
        auth_columns = {
            "password_expires":   "ALTER TABLE users ADD COLUMN password_expires DATETIME",
            "last_login":         "ALTER TABLE users ADD COLUMN last_login DATETIME",
            "failed_login_count": "ALTER TABLE users ADD COLUMN failed_login_count INTEGER DEFAULT 0",
            "locked_until":       "ALTER TABLE users ADD COLUMN locked_until DATETIME",
        }
        for col, sql in auth_columns.items():
            if col not in existing_cols:
                cursor.execute(sql)
                print(f"[auth_system] Added column '{col}' to users table.")
        conn.commit()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS login_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                ip_address TEXT,
                attempt_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                success INTEGER NOT NULL,
                error_message TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_token TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL,
                ip_address TEXT,
                created_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                expires_time DATETIME NOT NULL,
                is_active INTEGER DEFAULT 1
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admin_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                admin_username TEXT NOT NULL,
                action_type TEXT NOT NULL,
                target_username TEXT,
                action_time DATETIME DEFAULT CURRENT_TIMESTAMP,
                details TEXT
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_username ON users (username)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_session_token ON user_sessions (session_token)')
        conn.commit()

        # Default users are created by db_manager.py — not here
        conn.close()

    def _hash_password(self, password: str) -> str:
        # Matches db_manager.py hash_password() — no salt
        return hashlib.sha256(password.encode()).hexdigest()

    def get_connection(self):
        return sqlite3.connect(self.db_file)

    def execute_query(self, query: str, params: tuple = ()) -> list:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return rows

    def execute_update(self, query: str, params: tuple = ()) -> int:
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute(query, params)
        affected = cursor.rowcount
        conn.commit()
        conn.close()
        return affected

# -------------------- LoginManager --------------------
class LoginManager:
    def __init__(self, db_file: str = DB_FILE):
        self.db = DatabaseManager(db_file)
        self.max_attempts = 3
        self.lockout_minutes = 30

    def _hash_password(self, password: str) -> str:
        # Matches db_manager.py hash_password() — no salt
        return hashlib.sha256(password.encode()).hexdigest()

    def _log_login_attempt(self, username: str, ip_address: str, success: bool, error_message: str = None):
        try:
            self.db.execute_update('''
                INSERT INTO login_attempts (username, ip_address, success, error_message)
                VALUES (?, ?, ?, ?)
            ''', (username, ip_address, 1 if success else 0, error_message))
        except Exception:
            traceback.print_exc()

    def _reset_failed_attempts(self, username: str):
        try:
            self.db.execute_update('UPDATE users SET failed_login_count = 0 WHERE username = ?', (username,))
        except Exception:
            traceback.print_exc()

    def _update_failed_attempts(self, username: str, count: int):
        try:
            self.db.execute_update('UPDATE users SET failed_login_count = ? WHERE username = ?', (count, username))
        except Exception:
            traceback.print_exc()

    def _update_last_login(self, username: str):
        try:
            self.db.execute_update('UPDATE users SET last_login = ? WHERE username = ?', (datetime.now().isoformat(), username))
        except Exception:
            traceback.print_exc()

    def _lock_account(self, username: str, lock_until: datetime):
        try:
            self.db.execute_update('UPDATE users SET locked_until = ? WHERE username = ?', (lock_until.isoformat(), username))
        except Exception:
            traceback.print_exc()

    def authenticate_user(self, username: str, password: str, ip_address: str = "127.0.0.1") -> Dict[str, Any]:
        if not username or not password:
            return {"success": False, "error": "Username and Password required"}
        try:
            rows = self.db.execute_query('''
                SELECT id, username, password_hash, email, full_name, role, is_active,
                       password_expires, last_login, failed_login_count, locked_until
                FROM users WHERE username = ?''', (username,))
            if not rows:
                self._log_login_attempt(username, ip_address, False, "User not found")
                return {"success": False, "error": "Invalid username or password"}

            # rows[0] is a tuple; unpack to variables
            (user_id, db_username, password_hash, email, full_name, role,
             is_active, password_expires, last_login, failed_count, locked_until) = rows[0]

            if not is_active:
                self._log_login_attempt(username, ip_address, False, "Account disabled")
                return {"success": False, "error": "Account disabled"}

            if locked_until:
                try:
                    if datetime.fromisoformat(locked_until) > datetime.now():
                        remaining = datetime.fromisoformat(locked_until) - datetime.now()
                        mins = int(remaining.total_seconds() / 60)
                        return {"success": False, "error": f"Account locked for {mins} minutes"}
                except Exception:
                    pass

            if password_hash == self._hash_password(password):
                if password_expires and datetime.fromisoformat(password_expires) < datetime.now():
                    return {"success": False, "error": "Password expired"}

                self._reset_failed_attempts(username)
                self._update_last_login(username)
                self._log_login_attempt(username, ip_address, True, None)

                token, expires_time = self._create_session(db_username, full_name, role, ip_address)

                return {
                    "success": True,
                    "user": {"id": user_id, "username": db_username, "full_name": full_name, "email": email, "role": role},
                    "session_token": token
                }
            else:
                new_failed = (failed_count or 0) + 1
                self._update_failed_attempts(username, new_failed)
                self._log_login_attempt(username, ip_address, False, "Invalid password")
                if new_failed >= self.max_attempts:
                    lock_until = datetime.now() + timedelta(minutes=self.lockout_minutes)
                    self._lock_account(username, lock_until)
                    return {"success": False, "error": f"Account locked for {self.lockout_minutes} minutes"}
                else:
                    remaining = self.max_attempts - new_failed
                    return {"success": False, "error": f"Invalid credentials ({remaining} attempts left)"}
        except Exception as e:
            traceback.print_exc()
            return {"success": False, "error": f"Database error: {e}"}

    def _create_session(self, username, full_name, role, ip_address="127.0.0.1", duration_minutes=60):
        session_token = str(uuid.uuid4())
        expires_time = datetime.now() + timedelta(minutes=duration_minutes)
        # Store session in DB (include ip_address)
        try:
            self.db.execute_update('''
                INSERT INTO user_sessions (session_token, username, ip_address, expires_time, is_active)
                VALUES (?, ?, ?, ?, 1)
            ''', (session_token, username, ip_address, expires_time.isoformat()))
        except Exception:
            traceback.print_exc()
        return session_token, expires_time

    def get_active_users(self):
        query = '''
            SELECT u.username, u.full_name, u.role, s.session_token, s.expires_time, s.ip_address
            FROM user_sessions s
            JOIN users u ON s.username = u.username
            WHERE s.is_active = 1 AND s.expires_time > ?
        '''
        results = self.db.execute_query(query, (datetime.now().isoformat(),))
        active_users = []
        for username, full_name, role, token, exp_time, ip in results:
            active_users.append({
                "username": username,
                "full_name": full_name,
                "role": role,
                "ip_address": ip or "N/A",
                "session_token": token,
                "expires_time": exp_time
            })
        return active_users

# -------------------- AuthSystem (UI) --------------------
class AuthSystem:
    def __init__(self, root, on_login_success):
        self.root = root
        self.on_login_success = on_login_success
        self._enter_binding = None
        self.login_manager = LoginManager()
        self.create_login_ui()

    def create_login_ui(self):
        for w in self.root.winfo_children():
            w.destroy()
        self.root.title("KPR Lab CRM - Login")
        self.root.geometry("420x520")
        self.root.resizable(False, False)
        frame = ttk.Frame(self.root, padding=20)
        frame.pack(expand=True)

        # Logo
        logo_path = "Visiting Card KPR copy.png"
        if os.path.exists(logo_path):
            try:
                from PIL import Image, ImageTk
                img = Image.open(logo_path)
                w, h = img.size
                nw = 220
                nh = int(nw * h / w)
                img = img.resize((nw, nh), Image.Resampling.LANCZOS)
                self.logo_img = ImageTk.PhotoImage(img)
                ttk.Label(frame, image=self.logo_img).pack(pady=10)
            except Exception:
                ttk.Label(frame, text="KPR Lab CRM", font=("Arial", 20, "bold")).pack(pady=10)
        else:
            ttk.Label(frame, text="KPR Lab CRM", font=("Arial", 20, "bold")).pack(pady=10)

        ttk.Label(frame, text="Username:", font=("Arial", 10)).pack(pady=5)
        self.username_entry = ttk.Entry(frame, width=30)
        self.username_entry.pack(pady=5)
        self.username_entry.focus_set()

        ttk.Label(frame, text="Password:", font=("Arial", 10)).pack(pady=5)
        self.password_entry = ttk.Entry(frame, show="*", width=30)
        self.password_entry.pack(pady=5)

        ttk.Button(frame, text="Login", command=self.login).pack(pady=10)

        # bind enter
        if self._enter_binding:
            self.root.unbind('<Return>', self._enter_binding)
        self._enter_binding = self.root.bind('<Return>', self._on_enter_key)

    def _on_enter_key(self, event=None):
        if hasattr(self, "username_entry") and self.username_entry.winfo_exists():
            self.login()

    def login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if not username or not password:
            messagebox.showerror("Login Error", "Please enter both username and password.")
            return
        result = self.login_manager.authenticate_user(username, password)
        if result.get("success"):
            user = result.get("user")
            messagebox.showinfo("Login Success", f"Welcome, {user.get('full_name') or user.get('username')}!")
            # unbind enter after login success
            if self._enter_binding:
                self.root.unbind('<Return>', self._enter_binding)
                self._enter_binding = None
            # Console print active users
            print("=== Active Users ===")
            for u in self.login_manager.get_active_users():
                print(f"{u['username']} ({u['role']}) - Expires at {u['expires_time']} - IP: {u.get('ip_address')}")

            # Show Admin Dashboard for admins
            if user["role"] == "admin":
                self.show_admin_panel()
            try:
                self.on_login_success(user["id"], user["username"], user["role"])
            except Exception as e:
                print("on_login_success callback failed:", e)
        else:
            err = result.get("error", "Login failed")
            messagebox.showerror("Login Failed", err)

    # -------- New: Simple Admin Panel with Active Users Tab --------
    def show_admin_panel(self):
        dashboard = tk.Toplevel(self.root)
        dashboard.title("Admin Dashboard")
        dashboard.geometry("700x500")

        notebook = ttk.Notebook(dashboard)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Active Users Tab
        active_users_frame = ttk.Frame(notebook, padding="10")
        notebook.add(active_users_frame, text="🟢 Active Users")

        columns = ("Username", "Full Name", "Role", "IP", "Token", "Expires")
        self.active_tree = ttk.Treeview(active_users_frame, columns=columns, show="headings", height=12)
        for col in columns:
            self.active_tree.heading(col, text=col)
            self.active_tree.column(col, width=120)
        self.active_tree.pack(fill=tk.BOTH, expand=True, pady=10)

        def refresh_active_users():
            for item in self.active_tree.get_children():
                self.active_tree.delete(item)
            users = self.login_manager.get_active_users()
            for u in users:
                self.active_tree.insert("", tk.END, values=(u["username"], u["full_name"], u["role"], u.get("ip_address","N/A"), u.get("session_token","N/A"), u.get("expires_time")))

        ttk.Button(active_users_frame, text="🔄 Refresh", command=refresh_active_users).pack(pady=5)
        refresh_active_users()

# -------------------- Demo Main (for standalone testing) --------------------
def demo_on_login_success(user_id, username, role):
    print(f"Demo: logged in -> id: {user_id}, username: {username}, role: {role}")

def main():
    root = tk.Tk()
    app = AuthSystem(root, demo_on_login_success)
    root.mainloop()

if __name__ == "__main__":
    main()
