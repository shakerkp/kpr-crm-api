"""
dashboard_module.py  —  KPR Lab CRM
Modern card-based dashboard:
  Admin  : 6 KPI cards, material overview bar, low stock table,
           recent jobs, notifications, activity log, active users
  Staff  : 2 KPI cards, assigned jobs, my material entries,
           Log Material quick-action, notifications
"""

import tkinter as tk
from tkinter import ttk, messagebox
import datetime

from db_manager import (
    get_app_settings,
    get_db_connection,
    get_assigned_jobs_for_user,
    log_activity,
    get_notifications_for_user,
    mark_notification_read,
    mark_all_notifications_read,
    get_unread_notification_count,
    get_dashboard_material_stats,
    process_inventory_transaction,
    get_active_jobs_for_selection,
    get_my_material_entries,
)
from app_logger import get_logger
logger = get_logger("DashboardModule")

# ── Palette ──────────────────────────────────────────────────────────────────
BG       = "#F0F2F5"
CARD     = "#FFFFFF"
BORDER   = "#E5E7EB"
TEXT     = "#111827"
SUB      = "#6B7280"
BLUE     = "#2563EB";  BLUE_LT   = "#DBEAFE"
GREEN    = "#059669";  GREEN_LT  = "#D1FAE5"
AMBER    = "#D97706";  AMBER_LT  = "#FEF3C7"
RED      = "#DC2626";  RED_LT    = "#FEE2E2"
PURPLE   = "#7C3AED";  PURPLE_LT = "#EDE9FE"
TEAL     = "#0D9488";  TEAL_LT   = "#CCFBF1"

FH1  = ("Segoe UI", 20, "bold")
FH2  = ("Segoe UI", 13, "bold")
FH3  = ("Segoe UI", 11, "bold")
FBOD = ("Segoe UI", 10)
FSM  = ("Segoe UI", 9)
FNUM = ("Segoe UI", 26, "bold")


class DashboardModule:
    POLL_MS = 30_000

    def __init__(self, parent_frame, current_user_info,
                 login_manager=None, on_unread_count_changed=None):
        self.parent_frame            = parent_frame
        self.current_user_info       = current_user_info
        self.login_manager           = login_manager
        self.on_unread_count_changed = on_unread_count_changed
        self._last_unread            = 0
        self._poll_job               = None

        role = str(current_user_info.get("role", "")).lower()
        self.is_admin = role == "admin"
        self.is_staff = role in ("staff", "sub_staff")

        s = get_app_settings()
        self.cur = s.get("currency_symbol", "₹")

        self.create_ui()
        self.load_all()
        self._start_poll()
        self.parent_frame.bind("<Destroy>", self._stop_poll)

    # ─────────────────────────────────────────────────────────────────
    # UI BUILD
    # ─────────────────────────────────────────────────────────────────

    def create_ui(self):
        for w in self.parent_frame.winfo_children():
            w.destroy()

        # Scrollable canvas
        self._canvas = tk.Canvas(self.parent_frame, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(self.parent_frame, orient="vertical",
                             command=self._canvas.yview)
        self._scroll = tk.Frame(self._canvas, bg=BG)
        self._scroll.bind("<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))
        self._wid = self._canvas.create_window((0, 0), window=self._scroll, anchor="nw")
        self.parent_frame.bind("<Configure>", self._on_resize)
        self._canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._canvas.configure(yscrollcommand=vsb.set)
        # Smart scroll: bind to canvas widget directly, NOT bind_all
        # This prevents stealing scroll from Treeviews in the same window
        def _canvas_scroll(event):
            try:
                self._canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        def _bind_scroll(e=None):
            self._canvas.bind_all("<MouseWheel>", _canvas_scroll)

        def _unbind_scroll(e=None):
            try:
                self._canvas.unbind_all("<MouseWheel>")
            except Exception:
                pass

        # Bind scroll only when mouse is inside the canvas area
        self._canvas.bind("<Enter>", _bind_scroll)
        self._canvas.bind("<Leave>", _unbind_scroll)
        self._scroll.bind("<Enter>", _bind_scroll)
        self._scroll.bind("<Leave>", _unbind_scroll)

        # Force correct width after window is drawn
        def _set_initial_width(event=None):
            try:
                if not self.parent_frame.winfo_exists():
                    return
                w = self.parent_frame.winfo_width()
                if w > 1:
                    self._canvas.itemconfig(self._wid, width=w)
                    self._canvas.configure(scrollregion=self._canvas.bbox("all"))
                    self._canvas.yview_moveto(0)
            except Exception:
                pass
        self._init_after = self.parent_frame.after(50, _set_initial_width)

        root = self._scroll

        # ── Welcome header ─────────────────────────────────────────────
        hdr = tk.Frame(root, bg=BG)
        hdr.pack(fill=tk.X, padx=24, pady=(22, 4))
        uname = (self.current_user_info.get("full_name")
                 or self.current_user_info.get("username", "User")).split()[0].capitalize()
        tk.Label(hdr, text=f"Welcome back, {uname} 👋",
                 font=FH1, bg=BG, fg=TEXT).pack(side=tk.LEFT)
        tk.Label(hdr, text=datetime.datetime.now().strftime("%A, %d %B %Y"),
                 font=FBOD, bg=BG, fg=SUB).pack(side=tk.RIGHT, pady=6)

        # ── KPI cards row ──────────────────────────────────────────────
        kpi_frame = tk.Frame(root, bg=BG)
        kpi_frame.pack(fill=tk.X, padx=16, pady=(8, 4))
        self.kpi_vals = {}

        if self.is_admin:
            kpi_defs = [
                ("👥 Customers",      "customers",   BLUE,   BLUE_LT),
                ("⏳ Pending Jobs",   "pending",     AMBER,  AMBER_LT),
                ("💰 Today Revenue",  "revenue",     GREEN,  GREEN_LT),
                ("⚠️ Unpaid Amount",  "unpaid",      RED,    RED_LT),
                ("📦 Low Stock",      "low_stock",   PURPLE, PURPLE_LT),
                ("🗑 30d Wastage %",  "wastage_pct", TEAL,   TEAL_LT),
            ]
            cols = 6
        else:
            kpi_defs = [
                ("⏳ My Pending Jobs", "pending",   AMBER, AMBER_LT),
                ("✅ My Completed",    "completed", GREEN, GREEN_LT),
            ]
            cols = 2

        for i, (title, key, accent, bg_lt) in enumerate(kpi_defs):
            self._kpi_card(kpi_frame, title, key, accent, i, cols)

        # ── Admin material overview bar ────────────────────────────────
        if self.is_admin:
            self._build_mat_bar(root)

        # Thin divider
        tk.Frame(root, bg=BORDER, height=1).pack(fill=tk.X, padx=24, pady=8)

        # ── Two-column lower section ───────────────────────────────────
        lower = tk.Frame(root, bg=BG)
        lower.pack(fill=tk.BOTH, expand=True, padx=16, pady=4)
        lower.columnconfigure(0, weight=6)
        lower.columnconfigure(1, weight=4)

        # Left: Jobs
        jobs_card = self._card(lower, "📋 Assigned Tasks / Recent Jobs", 0, 0)
        self.jobs_tree = self._tree(jobs_card,
            ("ID","Customer","Type","Status","Due Date"),
            (45, 155, 110, 90, 85))
        self.jobs_tree.tag_configure("Pending",     background="#FFFBEB")
        self.jobs_tree.tag_configure("In Progress", background="#EFF6FF")
        self.jobs_tree.tag_configure("Completed",   background="#ECFDF5")
        self.jobs_tree.tag_configure("overdue",     foreground=RED)

        if self.is_staff:
            bf = tk.Frame(jobs_card, bg=CARD)
            bf.pack(fill=tk.X, padx=12, pady=(0, 8))
            ttk.Button(bf, text="📦 Log Material for Selected Job",
                       command=self._open_material_entry).pack(side=tk.LEFT, padx=3)
            ttk.Button(bf, text="🔄 Refresh",
                       command=self.load_all).pack(side=tk.LEFT, padx=3)

        # Right: Low stock (admin) or notifications (staff)
        if self.is_admin:
            stk_card = self._card(lower, "📦 Low Stock Alerts", 0, 1, bg=RED_LT)
            self.stock_tree = self._tree(stk_card,
                ("Material","Stock","Reorder"), (160, 75, 75), height=9)
            self.stock_tree.tag_configure("critical", foreground=RED)
        else:
            ntf_card = self._card(lower, "🔔 My Notifications", 0, 1)
            self.notif_tree = self._tree(ntf_card,
                ("Title","Message","Time"), (110, 180, 90), height=9)
            self.notif_tree.tag_configure("unread", background="#FFFBEB")
            nb = tk.Frame(ntf_card, bg=CARD)
            nb.pack(fill=tk.X, padx=12, pady=(0,8))
            ttk.Button(nb, text="✅ Mark All Read",
                       command=self._mark_all_read).pack(side=tk.LEFT, padx=3)

        # ── Staff: My Entries ──────────────────────────────────────────
        if self.is_staff:
            me_card = self._standalone_card(root,
                "📋 My Material Entries — Last 30 Days")
            self.my_entries_tree = self._tree(me_card,
                ("Date/Time","Material","UoM","Type","Qty","Job#","Customer","Remarks"),
                (125, 145, 48, 68, 58, 52, 110, 175), height=7)
            self.my_entries_tree.tag_configure("wastage", foreground=RED)

        # ── Admin: Full notifications panel ───────────────────────────
        if self.is_admin:
            ntf2 = self._standalone_card(root, "🔔 Notifications")
            self.notif_tree = self._tree(ntf2,
                ("ID","Title","Message","Status","Time"),
                (38, 140, 330, 58, 130), height=7)
            self.notif_tree.tag_configure("unread", background="#FFFBEB")
            nb2 = tk.Frame(ntf2, bg=CARD)
            nb2.pack(fill=tk.X, padx=12, pady=(0,8))
            ttk.Button(nb2, text="✅ Mark Selected Read",
                       command=self._mark_selected_read).pack(side=tk.LEFT, padx=3)
            ttk.Button(nb2, text="✅✅ Mark All Read",
                       command=self._mark_all_read).pack(side=tk.LEFT, padx=3)

            # Activity log
            act_card = self._standalone_card(root, "🕐 Recent Activity Log")
            self.activity_tree = self._tree(act_card,
                ("Time","User","Action","Description"),
                (145, 95, 115, 380), height=7)

            # Active users (if login_manager provided)
            if self.login_manager:
                usr_card = self._standalone_card(root, "🟢 Active Users")
                self.active_tree = self._tree(usr_card,
                    ("Username","Full Name","Role","IP","Expires"),
                    (110, 140, 70, 120, 130), height=5)
                ub = tk.Frame(usr_card, bg=CARD)
                ub.pack(fill=tk.X, padx=12, pady=(0,8))
                ttk.Button(ub, text="🔄 Refresh",
                           command=self._load_active_users).pack(side=tk.LEFT, padx=3)
                ttk.Button(ub, text="🚪 Logout Selected",
                           command=self._logout_selected_user).pack(side=tk.LEFT, padx=3)

        # Refresh button
        rf = tk.Frame(root, bg=BG)
        rf.pack(fill=tk.X, padx=24, pady=(4, 20))
        ttk.Button(rf, text="🔄 Refresh Dashboard",
                   command=self.load_all).pack(side=tk.LEFT)

    # ── Admin material overview bar ────────────────────────────────────
    def _build_mat_bar(self, root):
        bar = tk.Frame(root, bg=CARD,
                       highlightbackground=BORDER, highlightthickness=1)
        bar.pack(fill=tk.X, padx=24, pady=(0, 8))
        inner = tk.Frame(bar, bg=CARD)
        inner.pack(fill=tk.X, padx=14, pady=10)

        tk.Label(inner, text="📦 Material Overview — Last 30 Days",
                 font=FH3, bg=CARD, fg=TEXT).pack(side=tk.LEFT, padx=(0,18))

        self.mat_stat_labels = {}
        for key, lbl_txt, colour in [
            ("today_usage",   "Today Usage:",   BLUE),
            ("today_wastage", "Today Wastage:", AMBER),
            ("wastage_pct",   "Wastage %:",     RED),
        ]:
            tk.Label(inner, text=lbl_txt, font=FSM, bg=CARD, fg=SUB
                     ).pack(side=tk.LEFT, padx=(10, 2))
            v = tk.Label(inner, text="—", font=("Segoe UI",10,"bold"),
                         bg=CARD, fg=colour)
            v.pack(side=tk.LEFT, padx=(0, 10))
            self.mat_stat_labels[key] = v

        tk.Label(inner, text="Top Wasted:", font=FSM, bg=CARD, fg=SUB
                 ).pack(side=tk.LEFT, padx=(10, 2))
        self.top_wasted_lbl = tk.Label(inner, text="—", font=FSM, bg=CARD, fg=RED)
        self.top_wasted_lbl.pack(side=tk.LEFT)

    # ─────────────────────────────────────────────────────────────────
    # WIDGET HELPERS
    # ─────────────────────────────────────────────────────────────────

    def _on_resize(self, event=None):
        try:
            w = self.parent_frame.winfo_width()
            if w > 1:
                self._canvas.itemconfig(self._wid, width=w)
                self._canvas.configure(scrollregion=self._canvas.bbox("all"))
        except Exception:
            pass

    def _kpi_card(self, parent, title, key, accent, col_idx, total_cols):
        card = tk.Frame(parent, bg=CARD,
                        highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=0, column=col_idx, padx=8, pady=6, sticky="nsew")
        parent.columnconfigure(col_idx, weight=1)
        # Colour stripe
        tk.Frame(card, bg=accent, height=4).pack(fill=tk.X)
        inner = tk.Frame(card, bg=CARD)
        inner.pack(fill=tk.BOTH, expand=True, padx=14, pady=12)
        tk.Label(inner, text=title, font=FSM, bg=CARD, fg=SUB).pack(anchor="w")
        lbl = tk.Label(inner, text="—", font=FNUM, bg=CARD, fg=accent)
        lbl.pack(anchor="w", pady=(2, 0))
        self.kpi_vals[key] = lbl

    def _card(self, parent, title, row, col, bg=CARD):
        card = tk.Frame(parent, bg=bg,
                        highlightbackground=BORDER, highlightthickness=1)
        card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
        tk.Label(card, text=title, font=FH2, bg=bg, fg=TEXT
                 ).pack(anchor="w", padx=14, pady=(12, 4))
        return card

    def _standalone_card(self, parent, title, bg=CARD):
        card = tk.Frame(parent, bg=bg,
                        highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=24, pady=(0, 12))
        tk.Label(card, text=title, font=FH2, bg=bg, fg=TEXT
                 ).pack(anchor="w", padx=14, pady=(12, 4))
        return card

    def _tree(self, parent, columns, widths=(), height=10):
        sty = ttk.Style()
        sty.configure("DB.Treeview", rowheight=26, font=FBOD,
                       background=CARD, fieldbackground=CARD, foreground=TEXT)
        sty.configure("DB.Treeview.Heading", font=("Segoe UI",9,"bold"),
                       background=BG, foreground=SUB)
        sty.layout("DB.Treeview",
                   [("DB.Treeview.treearea", {"sticky": "nswe"})])

        wrap = tk.Frame(parent, bg=CARD)
        wrap.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        tree = ttk.Treeview(wrap, columns=columns, show="headings",
                             height=height, style="DB.Treeview")
        for i, col in enumerate(columns):
            tree.heading(col, text=col)
            w = widths[i] if i < len(widths) else 100
            tree.column(col, width=w, minwidth=30,
                        anchor=tk.CENTER if col in
                        ("ID","Stock","Reorder","Qty","Job#","UoM","Status") else tk.W)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        return tree

    # ─────────────────────────────────────────────────────────────────
    # DATA LOAD
    # ─────────────────────────────────────────────────────────────────

    def load_all(self):
        try:
            conn = get_db_connection()
            cur  = conn.cursor()
            uid  = self.current_user_info["id"]

            if self.is_admin:
                # KPI values
                cur.execute("SELECT COUNT(*) FROM customers")
                self.kpi_vals["customers"].config(text=str(cur.fetchone()[0]))

                cur.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('Pending','In Progress')")
                self.kpi_vals["pending"].config(text=str(cur.fetchone()[0]))

                cur.execute("SELECT SUM(amount) FROM payments WHERE DATE(payment_date)=DATE('now')")
                rev = cur.fetchone()[0] or 0
                self.kpi_vals["revenue"].config(text=f"{self.cur} {rev:,.0f}")

                cur.execute("SELECT SUM(balance) FROM jobs WHERE payment_status NOT IN ('Paid','Cancelled')")
                unp = cur.fetchone()[0] or 0
                self.kpi_vals["unpaid"].config(
                    text=f"{self.cur} {unp:,.0f}",
                    fg=RED if unp > 0 else GREEN)

                # Material stats
                stats = get_dashboard_material_stats()
                ls = stats.get("low_stock_count", 0)
                self.kpi_vals["low_stock"].config(
                    text=str(ls), fg=RED if ls > 0 else GREEN)
                wp = stats.get("month_wastage_pct", 0)
                self.kpi_vals["wastage_pct"].config(
                    text=f"{wp}%",
                    fg=RED if wp >= 30 else (AMBER if wp >= 15 else GREEN))

                # Material bar
                self.mat_stat_labels["today_usage"].config(
                    text=str(stats.get("today_usage", 0)))
                tw = stats.get("today_wastage", 0)
                self.mat_stat_labels["today_wastage"].config(
                    text=str(tw), fg=RED if tw > 0 else SUB)
                self.mat_stat_labels["wastage_pct"].config(
                    text=f"{wp}%",
                    fg=RED if wp >= 30 else (AMBER if wp >= 15 else GREEN))
                top = stats.get("top_wasted", [])
                if hasattr(self, 'top_wasted_lbl'):
                    self.top_wasted_lbl.config(
                        text="  ·  ".join(
                            f"{r['material']}: {round(r['wasted'],1)}" for r in top)
                        if top else "None ✅")

                self._load_low_stock(cur)
                self._load_jobs(cur, admin=True)
                self._load_notifications()
                self._load_activity(cur)
                if self.login_manager and hasattr(self, "active_tree"):
                    self._load_active_users()

            else:
                cur.execute(
                    "SELECT COUNT(*) FROM jobs WHERE assigned_staff_id=? "
                    "AND status IN ('Pending','In Progress')", (uid,))
                self.kpi_vals["pending"].config(text=str(cur.fetchone()[0]))

                cur.execute(
                    "SELECT COUNT(*) FROM jobs WHERE assigned_staff_id=? "
                    "AND status IN ('Completed','Delivered')", (uid,))
                self.kpi_vals["completed"].config(text=str(cur.fetchone()[0]))

                self._load_jobs(cur, admin=False, uid=uid)
                self._load_my_entries()
                self._load_notifications()

            log_activity(uid, self.current_user_info.get("username",""),
                         "Dashboard View", "Opened dashboard.")
            conn.close()
            # Always scroll to top so Welcome header + KPI cards are visible
            def _scroll_top():
                try:
                    if self.parent_frame.winfo_exists():
                        self._canvas.yview_moveto(0)
                except Exception:
                    pass
            self.parent_frame.after(10, _scroll_top)
        except Exception as e:
            logger.error(f"load_all error: {e}")

    # ── Individual loaders ─────────────────────────────────────────────

    def _load_jobs(self, cur, admin=True, uid=None):
        for r in self.jobs_tree.get_children():
            self.jobs_tree.delete(r)
        today = datetime.date.today().isoformat()
        if admin:
            cur.execute("""
                SELECT j.id, c.name, j.job_type, j.status, j.due_date
                FROM jobs j JOIN customers c ON j.customer_id=c.id
                ORDER BY j.id DESC LIMIT 20
            """)
        else:
            cur.execute("""
                SELECT j.id, c.name, j.job_type, j.status, j.due_date
                FROM jobs j JOIN customers c ON j.customer_id=c.id
                WHERE j.assigned_staff_id=? AND j.status NOT IN ('Delivered')
                ORDER BY j.due_date ASC LIMIT 20
            """, (uid,))
        rows = cur.fetchall()
        if not rows:
            self.jobs_tree.insert("", tk.END, values=("-","No jobs found.","","",""))
            return
        for r in rows:
            name = r[1][:18]+"…" if len(r[1]) > 18 else r[1]
            due  = r[4] or "-"
            tag  = (r[3],)
            if (due != "-" and due < today
                    and r[3] not in ("Completed","Delivered","Cancelled")):
                tag = ("overdue",)
            self.jobs_tree.insert("", tk.END,
                values=(r[0], name, r[2] or "", r[3] or "", due), tags=tag)

    def _load_low_stock(self, cur):
        for r in self.stock_tree.get_children():
            self.stock_tree.delete(r)
        try:
            cur.execute("PRAGMA table_info(inventory_items)")
            inv_cols = [c[1] for c in cur.fetchall()]
            active_f = "AND is_active=1" if "is_active" in inv_cols else ""
            cur.execute(f"""
                SELECT name, current_stock, reorder_level
                FROM inventory_items
                WHERE current_stock <= reorder_level AND reorder_level > 0 {active_f}
                ORDER BY (reorder_level - current_stock) DESC
            """)
            rows = cur.fetchall()
            if not rows:
                self.stock_tree.insert("", tk.END, values=("✅ All stocked","",""))
                return
            for r in rows:
                tag = ("critical",) if r[1] <= 0 else ()
                self.stock_tree.insert("", tk.END,
                    values=(r[0], f"{r[1]:.1f}", f"{r[2]:.1f}"), tags=tag)
        except Exception as e:
            logger.error(f"_load_low_stock: {e}")

    def _load_notifications(self):
        if not hasattr(self, "notif_tree"):
            return
        for r in self.notif_tree.get_children():
            self.notif_tree.delete(r)
        uid    = self.current_user_info["id"]
        notifs = get_notifications_for_user(uid)
        for n in notifs:
            unread = n["is_read"] == 0
            tag    = ("unread",) if unread else ()
            if self.is_admin:
                self.notif_tree.insert("", tk.END, iid=str(n["id"]),
                    values=(n["id"], n["title"], n["message"],
                            "Unread" if unread else "Read",
                            str(n["created_at"])[:16]), tags=tag)
            else:
                self.notif_tree.insert("", tk.END, iid=str(n["id"]),
                    values=(n["title"], n["message"],
                            str(n["created_at"])[:16]), tags=tag)
        count = get_unread_notification_count(uid)
        if count != self._last_unread:
            self._last_unread = count
            if self.on_unread_count_changed:
                self.on_unread_count_changed(count)

    def _load_activity(self, cur):
        if not hasattr(self, "activity_tree"):
            return
        for r in self.activity_tree.get_children():
            self.activity_tree.delete(r)
        try:
            cur.execute("""
                SELECT timestamp, username, activity_type, description
                FROM activity_log ORDER BY timestamp DESC LIMIT 50
            """)
            for row in cur.fetchall():
                self.activity_tree.insert("", tk.END, values=(
                    str(row[0])[:16], row[1] or "—",
                    row[2] or "—", row[3] or ""))
        except Exception as e:
            logger.warning(f"_load_activity: {e}")

    def _load_active_users(self):
        if not hasattr(self, "active_tree") or not self.login_manager:
            return
        for r in self.active_tree.get_children():
            self.active_tree.delete(r)
        try:
            for u in self.login_manager.get_active_users():
                self.active_tree.insert("", tk.END, values=(
                    u["username"], u.get("full_name",""),
                    u["role"], u.get("ip_address",""),
                    u.get("expires_time","")))
        except Exception as e:
            logger.error(f"_load_active_users: {e}")

    def _load_my_entries(self):
        if not hasattr(self, "my_entries_tree"):
            return
        for r in self.my_entries_tree.get_children():
            self.my_entries_tree.delete(r)
        try:
            entries = get_my_material_entries(self.current_user_info["id"], days=30)
            if not entries:
                self.my_entries_tree.insert("", tk.END,
                    values=("No entries yet.","","","","","","",""))
                return
            for e in entries:
                tag  = ("wastage",) if e.get("transaction_type") == "Wastage" else ()
                jobd = f"#{e['job_id']}" if e.get("job_id") else "-"
                self.my_entries_tree.insert("", tk.END, values=(
                    str(e.get("timestamp",""))[:16],
                    e.get("material_name",""),
                    e.get("uom","Pcs"),
                    e.get("transaction_type",""),
                    round(e.get("quantity",0), 3),
                    jobd,
                    e.get("customer_name","-"),
                    e.get("remarks","")
                ), tags=tag)
        except Exception as ex:
            logger.error(f"_load_my_entries: {ex}")

    # ─────────────────────────────────────────────────────────────────
    # ACTIONS
    # ─────────────────────────────────────────────────────────────────

    def _mark_selected_read(self):
        for iid in self.notif_tree.selection():
            try:
                mark_notification_read(int(iid))
            except Exception:
                pass
        self._load_notifications()

    def _mark_all_read(self):
        mark_all_notifications_read(self.current_user_info["id"])
        self._load_notifications()

    def _logout_selected_user(self):
        if not hasattr(self, "active_tree"):
            return
        sel = self.active_tree.selection()
        if not sel:
            messagebox.showwarning("Select User", "Please select a user.")
            return
        vals = self.active_tree.item(sel[0], "values")
        try:
            for s in self.login_manager.get_active_users():
                if s["username"] == vals[0]:
                    self.login_manager.logout_user(s["session_token"])
                    break
            messagebox.showinfo("Done", f"'{vals[0]}' logged out.")
            self._load_active_users()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _open_material_entry(self):
        uid  = self.current_user_info.get("id")
        role = self.current_user_info.get("role","")
        sel  = self.jobs_tree.selection()
        pre_id, pre_label = None, None
        if sel:
            v = self.jobs_tree.item(sel[0], "values")
            try:
                pre_id    = int(v[0])
                pre_label = f"Job#{v[0]} | {v[2]} | {v[1]}"
            except Exception:
                pass

        active = get_active_jobs_for_selection(user_id=uid, role=role)
        jlist  = ["-- No Job / General --"]
        jmap   = {}
        for j in active:
            lbl = f"Job#{j['id']} | {j['job_type']} | {j['customer_name']}"
            if j.get("description"):
                lbl += f" | {str(j['description'])[:28]}"
            jlist.append(lbl)
            jmap[lbl] = j["id"]

        win = tk.Toplevel(self.parent_frame)
        win.title("📦 Log Material Usage / Wastage")
        win.geometry("540x370")
        win.resizable(False, False)
        win.grab_set()
        win.attributes("-topmost", True)   # Always on top of main window
        win.lift()                          # Bring to front immediately
        win.focus_force()                   # Force focus to this window

        bann = tk.Frame(win, bg="#E8F5E9", padx=12, pady=8)
        bann.pack(fill=tk.X)
        uname = self.current_user_info.get("full_name") or self.current_user_info.get("username","")
        tk.Label(bann, text=f"✍  {uname}   |   {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
                 bg="#E8F5E9", font=("Segoe UI",9), fg="#1B5E20").pack(anchor="w")

        frm = ttk.Frame(win, padding=14)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="Linked Job:").grid(row=0,column=0,sticky="w",pady=7,padx=(0,10))
        jvar = tk.StringVar(value=pre_label if pre_label and pre_label in jlist else jlist[0])
        ttk.Combobox(frm, textvariable=jvar, values=jlist,
                     state="readonly", width=44).grid(row=0,column=1,sticky="ew",pady=7)

        ttk.Label(frm, text="Material *:").grid(row=1,column=0,sticky="w",pady=7,padx=(0,10))
        mvar = tk.StringVar()
        mmap = {}
        try:
            _c  = get_db_connection()
            _cr = _c.cursor()
            _cr.execute("SELECT id,name,uom FROM inventory_items ORDER BY name")
            for m in _cr.fetchall():
                lbl = f"{m['name']} ({m['uom'] or 'Pcs'})"
                mmap[lbl] = m["id"]
            _c.close()
        except Exception:
            pass
        ttk.Combobox(frm, textvariable=mvar, values=list(mmap.keys()),
                     state="readonly", width=44).grid(row=1,column=1,sticky="ew",pady=7)

        ttk.Label(frm, text="Type *:").grid(row=2,column=0,sticky="w",pady=7,padx=(0,10))
        tvar = tk.StringVar(value="Usage (-)")
        ttk.Combobox(frm, textvariable=tvar, values=["Usage (-)", "Wastage (-)"],
                     state="readonly", width=18).grid(row=2,column=1,sticky="w",pady=7)

        ttk.Label(frm, text="Quantity *:").grid(row=3,column=0,sticky="w",pady=7,padx=(0,10))
        qvar = tk.DoubleVar(value=1.0)
        ttk.Entry(frm, textvariable=qvar, width=14).grid(row=3,column=1,sticky="w",pady=7)

        ttk.Label(frm, text="Remarks:").grid(row=4,column=0,sticky="w",pady=7,padx=(0,10))
        rvar = tk.StringVar()
        ttk.Entry(frm, textvariable=rvar, width=44).grid(row=4,column=1,sticky="ew",pady=7)

        def _save():
            mat = mvar.get()
            if not mat or mat not in mmap:
                messagebox.showerror("Error","Please select a material.", parent=win); return
            if qvar.get() <= 0:
                messagebox.showerror("Error","Quantity must be > 0.", parent=win); return
            tt  = "Usage" if "Usage" in tvar.get() else "Wastage"
            jid = jmap.get(jvar.get(), None)
            ok  = process_inventory_transaction(
                item_id=mmap[mat], user_id=uid,
                trans_type=tt, qty=qvar.get(),
                remarks=rvar.get(), job_id=jid)
            if ok:
                messagebox.showinfo("Saved",
                    f"✅ {tt} of {qvar.get()} recorded!"
                    + (f"\nLinked to Job#{jid}" if jid else ""), parent=win)
                self._load_my_entries()
                win.destroy()
            else:
                messagebox.showerror("Error","Save failed.", parent=win)

        bf = ttk.Frame(win, padding=(14,4,14,12))
        bf.pack(fill=tk.X)
        ttk.Button(bf, text="💾 Save Entry", command=_save).pack(side=tk.LEFT, padx=4)
        ttk.Button(bf, text="Cancel", command=win.destroy).pack(side=tk.LEFT, padx=4)

    # ─────────────────────────────────────────────────────────────────
    # NOTIFICATION POLLING
    # ─────────────────────────────────────────────────────────────────

    def _start_poll(self):
        self._poll_job = self.parent_frame.after(self.POLL_MS, self._poll)

    def _stop_poll(self, event=None):
        for attr in ('_poll_job', '_init_after'):
            job = getattr(self, attr, None)
            if job:
                try:
                    self.parent_frame.after_cancel(job)
                except Exception:
                    pass
                setattr(self, attr, None)

    def _poll(self):
        try:
            if not self.parent_frame.winfo_exists():
                return
            count = get_unread_notification_count(self.current_user_info["id"])
            if count != self._last_unread:
                self._load_notifications()
                if self.on_unread_count_changed:
                    self.on_unread_count_changed(count)
                self._last_unread = count
        except Exception as e:
            logger.error(f"_poll: {e}")
        finally:
            try:
                if self.parent_frame.winfo_exists():
                    self._poll_job = self.parent_frame.after(self.POLL_MS, self._poll)
            except Exception:
                pass

    # Legacy compat
    def load_dashboard_data(self): self.load_all()
    def load_assigned_jobs(self):
        try:
            c = get_db_connection(); cur = c.cursor()
            self._load_jobs(cur, admin=self.is_admin,
                            uid=self.current_user_info["id"])
            c.close()
        except Exception: pass
    def _start_notification_poll(self): self._start_poll()
