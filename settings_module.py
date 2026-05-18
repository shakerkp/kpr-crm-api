import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from db_manager import get_db_connection, log_activity, get_app_settings, update_app_settings
import os
import datetime
import sqlite3

from app_logger import get_logger
logger = get_logger("SettingsModule")

class SettingsModule:
    def __init__(self, parent_frame, current_user_info, refresh_main_ui_callback=None):
        self.parent_frame = parent_frame
        self.current_user_id = current_user_info.get('user_id')
        self.current_username = current_user_info.get('username')
        self.current_user_role = current_user_info.get('role')
        self.refresh_main_ui_callback = refresh_main_ui_callback # Callback to refresh main app UI
        self.create_settings_ui()
        self.load_settings() # Load settings when UI is created

    def create_settings_ui(self):
        # Clear existing widgets
        for widget in self.parent_frame.winfo_children():
            widget.destroy()

        # Title
        tk.Label(self.parent_frame, text="Application Settings", font=("Arial", 20, "bold"), bg="#FFFFFF", fg="#333333").pack(pady=15)

        # Notebook for different settings categories
        self.settings_notebook = ttk.Notebook(self.parent_frame)
        self.settings_notebook.pack(pady=10, fill=tk.BOTH, expand=True, padx=10)

        # --- Tab 1: General Settings ---
        general_frame = ttk.Frame(self.settings_notebook)
        self.settings_notebook.add(general_frame, text="General")

        tk.Label(general_frame, text="Lab Information & Branding", font=("Arial", 16, "bold"), bg="#FFFFFF").pack(pady=10)

        form_frame_general = tk.Frame(general_frame, bg="#FFFFFF")
        form_frame_general.pack(pady=10, padx=20, fill=tk.X)

        tk.Label(form_frame_general, text="Lab Name:", bg="#FFFFFF").grid(row=0, column=0, sticky="w", pady=5, padx=5)
        self.lab_name_entry = tk.Entry(form_frame_general, width=40)
        self.lab_name_entry.grid(row=0, column=1, sticky="ew", pady=5, padx=5)

        tk.Label(form_frame_general, text="Logo Path:", bg="#FFFFFF").grid(row=1, column=0, sticky="w", pady=5, padx=5)
        self.logo_path_entry = tk.Entry(form_frame_general, width=40)
        self.logo_path_entry.grid(row=1, column=1, sticky="ew", pady=5, padx=5)
        tk.Button(form_frame_general, text="Browse", command=self.browse_logo_path).grid(row=1, column=2, padx=5)

        tk.Label(form_frame_general, text="Invoice Footer:", bg="#FFFFFF").grid(row=2, column=0, sticky="w", pady=5, padx=5)
        self.invoice_footer_entry = tk.Entry(form_frame_general, width=40)
        self.invoice_footer_entry.grid(row=2, column=1, sticky="ew", pady=5, padx=5)
        
        # Configure column weight for entries to expand
        form_frame_general.columnconfigure(1, weight=1)

        tk.Button(general_frame, text="Save General Settings", command=self.save_general_settings, bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(pady=15)


        # --- Tab 2: Database Management ---
        db_frame = ttk.Frame(self.settings_notebook)
        self.settings_notebook.add(db_frame, text="Database & Logs")

        tk.Label(db_frame, text="Database Management", font=("Arial", 16, "bold"), bg="#FFFFFF").pack(pady=10)

        if self.current_user_role == 'admin':
            tk.Button(db_frame, text="Manual Database Backup", command=self.backup_database, bg="#FFC107", fg="black", font=("Arial", 10, "bold")).pack(pady=5)
            tk.Label(db_frame, text="Creates a copy of the database. An automatic backup is performed on exit.", bg="#FFFFFF").pack(pady=2)
            self.last_backup_label = tk.Label(db_frame, text="Last backup: N/A", bg="#FFFFFF", fg="gray")
            self.last_backup_label.pack(pady=2)


            tk.Button(db_frame, text="View Activity Log", command=self.view_activity_log, bg="#007ACC", fg="white", font=("Arial", 10, "bold")).pack(pady=10)
            tk.Label(db_frame, text="View system activity and user actions.", bg="#FFFFFF").pack(pady=2)

            tk.Button(db_frame, text="Clear Activity Log (Admin Only)", command=self.clear_activity_log, bg="#DC3545", fg="white", font=("Arial", 10, "bold")).pack(pady=10)
            tk.Label(db_frame, text="Warning: This action is irreversible.", bg="#FFFFFF").pack(pady=2)
        else:
            tk.Label(db_frame, text="Database management options are available for administrators only.", bg="#FFFFFF").pack(pady=20)
            tk.Button(db_frame, text="View Activity Log", command=self.view_activity_log, bg="#007ACC", fg="white", font=("Arial", 10, "bold")).pack(pady=10)

        # --- Tab 3: About ---
        about_frame = ttk.Frame(self.settings_notebook)
        self.settings_notebook.add(about_frame, text="About")

        tk.Label(about_frame, text="KPR Lab Manager CRM", font=("Arial", 18, "bold"), bg="#FFFFFF").pack(pady=20)
        tk.Label(about_frame, text="Version: 1.0.0", bg="#FFFFFF").pack(pady=5)
        tk.Label(about_frame, text="Developed by SEKHAR KAMMAMPATI", bg="#FFFFFF").pack(pady=5)
        tk.Label(about_frame, text="© 2023-2025 KPR Colour Lab. All rights reserved.", bg="#FFFFFF").pack(pady=5)

        tk.Label(about_frame, text="\nThis application helps manage customers, jobs, payments, and reporting for KPR Lab.",
                 bg="#FFFFFF", wraplength=400, justify=tk.CENTER).pack(pady=10)

    def load_settings(self):
        settings = get_app_settings()
        self.lab_name_entry.delete(0, tk.END)
        self.lab_name_entry.insert(0, settings.get('lab_name', ''))

        self.logo_path_entry.delete(0, tk.END)
        self.logo_path_entry.insert(0, settings.get('logo_path', ''))

        self.invoice_footer_entry.delete(0, tk.END)
        self.invoice_footer_entry.insert(0, settings.get('invoice_footer', ''))

        last_backup_date = settings.get('last_backup_date')
        if last_backup_date:
            self.last_backup_label.config(text=f"Last backup: {last_backup_date}")
        else:
            self.last_backup_label.config(text="Last backup: Never")

    def save_general_settings(self):
        lab_name = self.lab_name_entry.get().strip()
        logo_path = self.logo_path_entry.get().strip()
        invoice_footer = self.invoice_footer_entry.get().strip()

        if not lab_name:
            messagebox.showwarning("Input Error", "Lab Name cannot be empty.")
            return
        
        # Check if logo path exists if provided
        if logo_path and not os.path.exists(logo_path):
            if not messagebox.askyesno("Warning", "The specified logo path does not exist. Do you want to save anyway?"):
                return

        try:
            update_app_settings(lab_name=lab_name, logo_path=logo_path, invoice_footer=invoice_footer)
            messagebox.showinfo("Success", "General settings saved successfully!")
            log_activity(self.current_user_id, self.current_username, "Save Settings", "General settings updated")
            
            # Callback to main UI to refresh header/logo etc.
            if self.refresh_main_ui_callback:
                self.refresh_main_ui_callback()

        except Exception as e:
            messagebox.showerror("Error", f"Failed to save settings: {e}")
            log_activity(self.current_user_id, self.current_username, "Save Settings", f"Failed to save: {e}")

    def browse_logo_path(self):
        file_path = filedialog.askopenfilename(
            title="Select Logo Image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.gif *.bmp"), ("All files", "*.*")]
        )
        if file_path:
            self.logo_path_entry.delete(0, tk.END)
            self.logo_path_entry.insert(0, file_path)

    def backup_database(self):
        if self.current_user_role != 'admin':
            messagebox.showerror("Permission Denied", "Only administrators can backup the database.")
            log_activity(self.current_user_id, self.current_username, "Backup Database", "Attempted backup without admin role")
            return

        backup_dir = "backups"
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = os.path.join(backup_dir, f"kprlab_backup_{timestamp}.db")

        # It's crucial to ensure the main connection is not active during backup using backup_iter()
        # For simplicity in this structure, we'll try to ensure it's closed (though main.py handles it on exit)
        # The sqlite3.connect().backup() method handles its own connections internally
        try:
            source_conn = sqlite3.connect("kprlab.db") # Connect to the main database
            dest_conn = sqlite3.connect(backup_filename) # Connect to the backup file
            
            # Use the backup_iter method for safe backup
            # This method works even if other connections are open, but it's best practice
            # for the application to be idle or briefly pause writes during backup.
            # In our Tkinter app, it's generally okay since it's single-threaded.
            source_conn.backup(dest_conn)
            
            source_conn.close()
            dest_conn.close()
            
            messagebox.showinfo("Backup Success", f"Database backed up successfully to:\n{backup_filename}")
            log_activity(self.current_user_id, self.current_username, "Backup Database", f"Manual backup to {backup_filename}")
            update_app_settings(last_backup_date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            self.load_settings() # Refresh last backup date display
        except Exception as e:
            messagebox.showerror("Backup Error", f"Failed to backup database: {e}")
            log_activity(self.current_user_id, self.current_username, "Backup Database", f"Failed manual backup: {e}")
        finally:
            # Ensure connections are closed even if an error occurs
            if 'source_conn' in locals() and source_conn:
                source_conn.close()
            if 'dest_conn' in locals() and dest_conn:
                dest_conn.close()


    def view_activity_log(self):
        # We're logging to the DB, not a file. Let's retrieve from DB and show in a new window.
        log_activity(self.current_user_id, self.current_username, "View Log", "Accessed activity log module")
        
        log_window = tk.Toplevel(self.parent_frame)
        log_window.title("Activity Log")
        log_window.geometry("800x500")
        log_window.transient(self.parent_frame.winfo_toplevel()) # Make it appear on top of main window
        log_window.grab_set() # Disable interaction with the main window

        tk.Label(log_window, text="System Activity Log", font=("Arial", 16, "bold")).pack(pady=10)

        log_tree = ttk.Treeview(log_window, columns=("ID", "Timestamp", "User", "Activity Type", "Description"), show="headings")
        log_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        log_tree.heading("ID", text="ID")
        log_tree.heading("Timestamp", text="Timestamp")
        log_tree.heading("User", text="User")
        log_tree.heading("Activity Type", text="Activity Type")
        log_tree.heading("Description", text="Description")

        log_tree.column("ID", width=40, anchor="center")
        log_tree.column("Timestamp", width=150)
        log_tree.column("User", width=100)
        log_tree.column("Activity Type", width=120)
        log_tree.column("Description", width=300)

        scrollbar = ttk.Scrollbar(log_tree, orient="vertical", command=log_tree.yview)
        log_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")

        conn = get_db_connection()
        cursor = conn.cursor()
        # MODIFIED: Changed 'activity' to 'activity_type'
        cursor.execute("SELECT id, timestamp, username, activity_type, description FROM activity_log ORDER BY timestamp DESC")
        logs = cursor.fetchall()
        conn.close()

        for log_entry in logs:
            log_tree.insert("", "end", values=(
                log_entry['id'],
                log_entry['timestamp'],
                log_entry['username'],
                log_entry['activity_type'],
                log_entry['description']
            ))
        
        # Add a button to close the log window
        tk.Button(log_window, text="Close", command=log_window.destroy, font=("Arial", 10)).pack(pady=10)

    def clear_activity_log(self):
        if self.current_user_role != 'admin':
            messagebox.showerror("Permission Denied", "Only administrators can clear the activity log.")
            log_activity(self.current_user_id, self.current_username, "Clear Log", "Attempted clear log without admin role")
            return
        
        if messagebox.askyesno("Confirm Clear Log", "Are you sure you want to clear ALL activity log entries? This action is irreversible!"):
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("DELETE FROM activity_log")
                conn.commit()
                messagebox.showinfo("Success", "Activity log cleared successfully!")
                log_activity(self.current_user_id, self.current_username, "Clear Log", "Activity log cleared by admin")
                # If the log view is open, it won't auto-refresh, but next open will be clear.
            except Exception as e:
                conn.rollback()
                messagebox.showerror("Error", f"Failed to clear activity log: {e}")
                log_activity(self.current_user_id, self.current_username, "Clear Log", f"Failed to clear log: {e}")
            finally:
                conn.close()
