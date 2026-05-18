import tkinter as tk
from tkinter import messagebox, ttk
import os
import ctypes

# Only import what is actually used in main.py
# ── Network mode auto-detection ──────────────────────────────────────────────
# api_client.py exists + server reachable → network mode (multi-PC)
# Otherwise → local db_manager mode (single PC)
import os as _os
def _use_network_mode():
    if not _os.path.exists("api_client.py"):
        return False
    try:
        import api_client as _ac
        return _ac.test_connection()
    except Exception:
        return False

if _use_network_mode():
    from api_client import (
        authenticate_user, get_app_settings, update_app_settings,
        log_activity, get_notifications_for_user, mark_notification_read,
        mark_all_notifications_read, get_unread_notification_count,
        get_assigned_jobs_for_user, get_low_stock_items,
        get_pending_jobs_count, get_total_unpaid_amount,
        get_unpaid_customer_details, get_dashboard_material_stats,
        process_inventory_transaction, get_active_jobs_for_selection,
        get_my_material_entries, get_all_users, change_user_password,
        admin_reset_password, get_db_connection,
    )
    print("[Network Mode] Connected to server — using api_client")
else:
    print("[Local Mode] Using local db_manager")

from db_manager import (
    create_tables, create_default_admin, log_activity,
    get_app_settings, perform_automatic_backup,
    get_unread_notification_count,
)

from auth_system import AuthSystem
from customer_module import CustomerModule
from job_module import JobModule
from job_payment_module import JobPaymentModule
from reports_module import ReportsModule
from settings_module import SettingsModule
from user_management_module import UserManagementModule
from inventory_module import InventoryModule
from dashboard_module import DashboardModule
from invoice_module import InvoiceModule
from job_type_module import JobTypeModule
from order_slip_module import PasswordChangeDialog, AdminPasswordResetDialog
from app_logger import get_logger

logger = get_logger("Main")


class KPRLabCRM:
    def __init__(self, root):
        logger.info("KPRLabCRM __init__ started.")
        self.root = root

        icon_path = os.path.join("assets", "CRM Icon.ico")
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
                if os.name == 'nt':
                    myappid = 'KPRLab.CRM.App'
                    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
            except Exception as e:
                logger.warning(f"Icon error: {e}")

        self.current_user_id = None
        self.current_username = None
        self.current_user_role = None
        self.current_module = None
        self._last_selected_customer_info = None
        self.active_button = None

        create_tables()
        create_default_admin()

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.auth_system = AuthSystem(self.root, self.on_login_success)
        logger.info("KPRLabCRM __init__ finished.")

    def on_login_success(self, user_id, username, role):
        self.current_user_id = user_id
        self.current_username = username
        self.current_user_role = role
        log_activity(self.current_user_id, self.current_username, "User Login", f"User {username} logged in.")

        for widget in self.root.winfo_children():
            widget.destroy()

        self.root.title("KPR Lab CRM - Dashboard")
        self.root.resizable(True, True)
        self.root.state("zoomed")  # Login తర్వాత కూడా full screen

        self.create_main_ui()
        self.apply_theme_styles()

        self.settings = get_app_settings()
        self.apply_settings()

        # Set initial notification badge after UI is built
        count = get_unread_notification_count(self.current_user_id)
        self._update_notification_badge(count)

    def apply_settings(self):
        self.currency_symbol = self.settings.get('currency_symbol', '₹')

    def apply_theme_styles(self):
        style = ttk.Style()
        style.theme_use('clam')

        bg_color = "#FFFFFF"
        fg_color = "#212121"
        field_bg_color = "#FFFFFF"
        select_bg_color = "#BBDEFB"
        button_bg = "#E3F2FD"
        button_fg = "#0D47A1"
        sidebar_bg = "#F5F5F5"
        active_button_bg = "#90CAF9"
        header_bg = "#E3F2FD"

        style.configure("TFrame", background=bg_color)
        style.configure("TLabel", background=bg_color, foreground=fg_color)
        style.configure("TEntry", fieldbackground=field_bg_color, foreground=fg_color)
        style.configure("TCombobox", fieldbackground=field_bg_color, foreground=fg_color)

        style.configure("TButton", background=button_bg, foreground=button_fg, font=("Arial", 10, "bold"))
        style.map("TButton", background=[('active', active_button_bg)], foreground=[('active', button_fg)])
        style.configure("Active.TButton", background=active_button_bg, foreground=button_fg, font=("Arial", 10, "bold"))
        style.configure("White.TButton", background="#FFFFFF", foreground=button_fg, font=("Arial", 10, "bold"), relief="ridge")
        style.map("White.TButton", background=[('active', '#E3F2FD')], foreground=[('active', button_fg)])

        style.configure("Sidebar.TFrame", background=sidebar_bg)
        style.configure("Header.TFrame", background=header_bg)
        style.configure("Custom.TLabelframe", background=bg_color, foreground=fg_color, relief="ridge")
        style.configure("Custom.TLabelframe.Label", background=bg_color, foreground=fg_color, font=("Arial", 10, "bold"))

        style.configure("Treeview", background=field_bg_color, foreground=fg_color,
                        fieldbackground=field_bg_color, rowheight=25)
        style.map("Treeview", background=[('selected', select_bg_color)])
        style.configure("Treeview.Heading", background=header_bg, foreground=fg_color, font=("Arial", 10, "bold"))

    def create_main_ui(self):
        if hasattr(self, 'sidebar_frame') and self.sidebar_frame.winfo_exists():
            self.sidebar_frame.destroy()
        if hasattr(self, 'header_frame') and self.header_frame.winfo_exists():
            self.header_frame.destroy()
        if hasattr(self, 'content_frame') and self.content_frame.winfo_exists():
            self.content_frame.destroy()

        main_container = ttk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True)
        main_container.grid_rowconfigure(1, weight=1)
        main_container.grid_columnconfigure(1, weight=1)

        self.sidebar_frame = ttk.Frame(main_container, width=200, relief=tk.RAISED, borderwidth=1, style="Sidebar.TFrame")
        self.sidebar_frame.grid(row=0, column=0, rowspan=2, sticky="nswe")
        self.sidebar_frame.pack_propagate(False)

        sidebar_header_frame = ttk.Frame(self.sidebar_frame, padding="10", style="Sidebar.TFrame")
        sidebar_header_frame.pack(fill=tk.X, pady=10)
        ttk.Label(sidebar_header_frame, text="KPR CRM", font=("Arial", 14, "bold"), style="Sidebar.TFrame").pack()
        ttk.Separator(self.sidebar_frame, orient='horizontal').pack(fill='x', pady=5)

        nav_buttons_frame = ttk.Frame(self.sidebar_frame, style="Sidebar.TFrame")
        nav_buttons_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        self._dashboard_btn_text = tk.StringVar(value="🏠 Dashboard")
        self.dashboard_btn = ttk.Button(nav_buttons_frame, textvariable=self._dashboard_btn_text, command=lambda: self.show_module("dashboard"))
        self.dashboard_btn.pack(fill=tk.X, pady=2, padx=10)
        # Customers — hidden for sub_staff
        if self.current_user_role != 'sub_staff':
            self.customers_btn = ttk.Button(nav_buttons_frame, text="Customers", command=lambda: self.show_module("customers"))
            self.customers_btn.pack(fill=tk.X, pady=2, padx=10)
        else:
            self.customers_btn = None

        # Jobs & Payments — hidden for sub_staff
        if self.current_user_role != 'sub_staff':
            self.jobs_payments_btn = ttk.Button(nav_buttons_frame, text="Jobs & Payments", command=lambda: self.show_module("jobs_payments"))
            self.jobs_payments_btn.pack(fill=tk.X, pady=2, padx=10)
        else:
            self.jobs_payments_btn = None

        self.all_jobs_btn = ttk.Button(nav_buttons_frame, text="All Jobs", command=lambda: self.show_module("job"))
        self.all_jobs_btn.pack(fill=tk.X, pady=2, padx=10)

        # Invoice button — hidden for sub_staff
        if self.current_user_role != 'sub_staff':
            self.invoices_btn = ttk.Button(nav_buttons_frame, text="Invoices", command=lambda: self.show_module("invoices"))
            self.invoices_btn.pack(fill=tk.X, pady=2, padx=10)
        else:
            self.invoices_btn = None

        if self.current_user_role == 'admin':
            self.job_type_btn = ttk.Button(nav_buttons_frame, text="Job Types", command=lambda: self.show_module("job_types"))
            self.job_type_btn.pack(fill=tk.X, pady=2, padx=10)
            self.inventory_btn = ttk.Button(nav_buttons_frame, text="Inventory", command=lambda: self.show_module("inventory"))
            self.inventory_btn.pack(fill=tk.X, pady=2, padx=10)
            self.reports_btn = ttk.Button(nav_buttons_frame, text="Reports", command=lambda: self.show_module("reports"))
            self.reports_btn.pack(fill=tk.X, pady=2, padx=10)
            self.user_management_btn = ttk.Button(nav_buttons_frame, text="User Management", command=lambda: self.show_module("user_management"))
            self.user_management_btn.pack(fill=tk.X, pady=2, padx=10)
            self.settings_btn = ttk.Button(nav_buttons_frame, text="Settings", command=lambda: self.show_module("settings"))
            self.settings_btn.pack(fill=tk.X, pady=2, padx=10)
        else:
            self.inventory_btn = None
            self.reports_btn = None
            self.user_management_btn = None
            self.settings_btn = None

        bottom_sidebar_frame = ttk.Frame(self.sidebar_frame, style="Sidebar.TFrame")
        bottom_sidebar_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10, padx=10)
        self.welcome_label_text = tk.StringVar(value=f"Welcome, {self.current_username}\n({self.current_user_role})")
        ttk.Label(bottom_sidebar_frame, textvariable=self.welcome_label_text, font=("Arial", 10), style="Sidebar.TFrame").pack(pady=5)
        ttk.Button(bottom_sidebar_frame, text="🔒 Change Password", command=self._open_change_password).pack(fill=tk.X, pady=2)
        if self.current_user_role == 'admin':
            ttk.Button(bottom_sidebar_frame, text="🔑 Reset User Password", command=self._open_admin_reset_password).pack(fill=tk.X, pady=2)
        ttk.Button(bottom_sidebar_frame, text="Logout", command=self.logout).pack(fill=tk.X, pady=5)

        self.header_frame = ttk.Frame(main_container, padding="10", relief=tk.RAISED, borderwidth=1, style="Header.TFrame")
        self.header_frame.grid(row=0, column=1, sticky="nswe")
        self.header_frame.grid_columnconfigure(0, weight=1)
        self.current_module_title = tk.StringVar(value="Dashboard")
        ttk.Label(self.header_frame, textvariable=self.current_module_title, font=("Arial", 14, "bold"), style="Header.TFrame").pack(side=tk.LEFT, padx=10)

        self.content_frame = ttk.Frame(main_container, padding="10")
        self.content_frame.grid(row=1, column=1, sticky="nswe")

        self.module_button_map = {
            "dashboard": self.dashboard_btn,
            "customers": self.customers_btn,
            "jobs_payments": self.jobs_payments_btn,
            "job": self.all_jobs_btn,
            "invoices": self.invoices_btn,
            "inventory": self.inventory_btn,
            "reports": self.reports_btn,
            "user_management": self.user_management_btn,
            "settings": self.settings_btn
        }

        self.show_module("dashboard")

    def show_module(self, module_name):
        if self.active_button and self.active_button.winfo_exists():
            self.active_button.config(style="TButton")

        if self.current_module:
            for widget in self.content_frame.winfo_children():
                widget.destroy()
            self.current_module = None

        try:
            user_info = {
                'id': self.current_user_id,
                'username': self.current_username or "",
                'role': self.current_user_role or ""
            }
            if module_name == "dashboard":
                self.current_module = DashboardModule(
                    self.content_frame, user_info,
                    on_unread_count_changed=self._update_notification_badge
                )
                self.current_module_title.set("Dashboard Overview")
            elif module_name == "customers":
                if self.current_user_role == 'sub_staff':
                    messagebox.showwarning("Permission Denied", "Customers module is not available for your role.")
                    self.show_module("dashboard")
                    return
                self.current_module = CustomerModule(self.content_frame, user_info, self.set_last_selected_customer_info)
                self.current_module_title.set("Customer Management")
            elif module_name == "jobs_payments":
                if self.current_user_role == 'sub_staff':
                    messagebox.showwarning("Permission Denied", "Jobs & Payments module is not available for your role.")
                    self.show_module("dashboard")
                    return
                self.job_payment_module_instance = JobPaymentModule(self.content_frame, user_info)
                self.current_module = self.job_payment_module_instance
                self.current_module_title.set("Jobs & Payments")
                if self._last_selected_customer_info:
                    self.job_payment_module_instance.set_customer_context(
                        self._last_selected_customer_info['id'],
                        self._last_selected_customer_info['name'],
                        self._last_selected_customer_info['mobile']
                    )
            elif module_name == "job":
                self.current_module = JobModule(self.content_frame, user_info)
                self.current_module_title.set("All Jobs")
            elif module_name == "invoices":
                if self.current_user_role == 'sub_staff':
                    messagebox.showwarning("Permission Denied", "Invoices module is not available for your role.")
                    self.show_module("dashboard")
                    return
                self.current_module = InvoiceModule(self.content_frame, user_info)
                self.current_module_title.set("Invoice Management")
            elif module_name == "reports":
                if self.current_user_role == 'admin':
                    self.current_module = ReportsModule(self.content_frame, user_info)
                    self.current_module_title.set("Comprehensive Reports")
                else:
                    messagebox.showwarning("Permission Denied", "No access.")
                    self.show_module("dashboard")
                    return
            elif module_name == "settings":
                if self.current_user_role == 'admin':
                    self.current_module = SettingsModule(self.content_frame, user_info)
                    self.current_module_title.set("Application Settings")
                else:
                    messagebox.showwarning("Permission Denied", "No access.")
                    self.show_module("dashboard")
                    return
            elif module_name == "user_management":
                if self.current_user_role == 'admin':
                    self.current_module = UserManagementModule(self.content_frame, user_info)
                    self.current_module_title.set("User Management")
                else:
                    messagebox.showwarning("Permission Denied", "No access.")
                    self.show_module("dashboard")
                    return
            elif module_name == "job_types":
                if self.current_user_role == 'admin':
                    callback = None
                    if hasattr(self, "job_payment_module_instance") and self.job_payment_module_instance:
                        callback = self.job_payment_module_instance.refresh_job_types
                    self.current_module = JobTypeModule(self.content_frame, user_info, on_job_types_changed=callback)
                    self.current_module_title.set("Job Type Management")
                else:
                    messagebox.showwarning("Permission Denied", "No access.")
                    self.show_module("dashboard")
                    return
            elif module_name == "inventory":
                if self.current_user_role == 'admin':
                    self.current_module = InventoryModule(self.content_frame, user_info)
                    self.current_module_title.set("Inventory Management")
                else:
                    messagebox.showwarning("Permission Denied", "No access.")
                    self.show_module("dashboard")
                    return

        except Exception as e:
            messagebox.showerror("Module Load Error", f"Failed: {e}")
            import traceback; traceback.print_exc()
            self.current_module = None
            return

        new_active_button = self.module_button_map.get(module_name)
        if new_active_button and new_active_button.winfo_exists():
            new_active_button.config(style="Active.TButton")
            self.active_button = new_active_button

    def _update_notification_badge(self, unread_count):
        """Update the Dashboard sidebar button text with unread notification count."""
        if not hasattr(self, '_dashboard_btn_text'):
            return
        if unread_count > 0:
            self._dashboard_btn_text.set(f"🏠 Dashboard 🔔{unread_count}")
        else:
            self._dashboard_btn_text.set("🏠 Dashboard")

    def set_last_selected_customer_info(self, customer_id, customer_name, customer_mobile):
        if customer_id:
            self._last_selected_customer_info = {'id': customer_id, 'name': customer_name, 'mobile': customer_mobile}
        else:
            self._last_selected_customer_info = None

    def auto_backup_db(self):
        if os.path.exists("kprlab.db"):
            try:
                perform_automatic_backup()
            except Exception as e:
                log_activity(self.current_user_id, self.current_username, "DB Backup Failed", str(e))

    def on_closing(self):
        if messagebox.askokcancel("Quit", "Quit and create backup?"):
            self.auto_backup_db()
            self.logout(silent=True)
            self.root.destroy()

    def _open_change_password(self):
        """Any logged-in user can change their own password."""
        user_info = {
            'id':        self.current_user_id,
            'username':  self.current_username,
            'full_name': getattr(self, 'current_full_name', self.current_username),
        }
        PasswordChangeDialog(self.root, user_info)

    def _open_admin_reset_password(self):
        """Admin-only: reset any user's password."""
        admin_info = {
            'id':       self.current_user_id,
            'username': self.current_username,
            'role':     self.current_user_role,
        }
        AdminPasswordResetDialog(self.root, admin_info)

    def logout(self, silent=False):
        if not silent:
            log_activity(self.current_user_id, self.current_username, "User Logout", "Logged out")
            messagebox.showinfo("Logout", "You have been logged out.")
        for widget in self.root.winfo_children():
            widget.destroy()
        self.root.update_idletasks()
        self.current_user_id = None
        self.current_username = None
        self.current_user_role = None
        self.current_module = None
        self.active_button = None
        self._last_selected_customer_info = None
        for attr in ('sidebar_frame', 'header_frame', 'content_frame'):
            if hasattr(self, attr):
                delattr(self, attr)
        self.auth_system.create_login_ui()
        self.root.state('normal')
        self.root.geometry("400x500")
        self.root.resizable(False, False)


if __name__ == "__main__":
    root = tk.Tk()
    app = KPRLabCRM(root)
    root.mainloop()
