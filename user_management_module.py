import tkinter as tk
from tkinter import ttk, messagebox
import datetime

from db_manager import get_db_connection, log_activity, get_all_users, delete_user, hash_password # Import hash_password

class UserManagementModule:
    def __init__(self, content_frame, user_info):
        print(f"[{datetime.datetime.now()}] UserManagementModule: Initializing.")
        self.content_frame = content_frame
        self.current_user_info = user_info
        self.selected_user_id = None # To store the ID of the user selected in the treeview
        self.create_ui()
        print(f"[{datetime.datetime.now()}] UserManagementModule: Initialization complete.")

    def create_ui(self):
        print(f"[{datetime.datetime.now()}] UserManagementModule: Creating UI.")
        # Clear existing widgets in the content frame
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        self.main_frame = ttk.Frame(self.content_frame, padding="10")
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(self.main_frame, text="User Management", font=("Arial", 16, "bold")).pack(pady=10)

        # --- User List Treeview ---
        columns = ("ID", "Username", "Role", "Active")
        self.user_tree = ttk.Treeview(self.main_frame, columns=columns, show="headings")
        for col in columns:
            self.user_tree.heading(col, text=col)
            self.user_tree.column(col, width=100, anchor=tk.CENTER)
        self.user_tree.pack(fill=tk.BOTH, expand=True, pady=10)

        self.user_tree.bind("<<TreeviewSelect>>", self.on_user_select)

        # --- User Details and Actions Frame ---
        details_frame = ttk.LabelFrame(self.main_frame, text="User Details & Actions", padding="10")
        details_frame.pack(fill=tk.X, pady=10)

        # Labels and Entries for user details
        ttk.Label(details_frame, text="User ID:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.user_id_var = tk.StringVar()
        ttk.Label(details_frame, textvariable=self.user_id_var, font=("Arial", 10, "bold")).grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(details_frame, text="Username:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.username_var = tk.StringVar()
        self.username_entry = ttk.Entry(details_frame, textvariable=self.username_var, width=30)
        self.username_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(details_frame, text="Password:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.password_var = tk.StringVar()
        self.password_entry = ttk.Entry(details_frame, textvariable=self.password_var, show="*", width=30)
        self.password_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        ttk.Label(details_frame, text="(Leave blank to keep current password)").grid(row=2, column=2, padx=5, pady=5, sticky="w")


        ttk.Label(details_frame, text="Role:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
        self.role_var = tk.StringVar(value="staff")
        self.role_combobox = ttk.Combobox(details_frame, textvariable=self.role_var, values=["admin", "staff", "sub_staff"], state="readonly", width=28)
        self.role_combobox.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        ttk.Label(details_frame, text="Active:").grid(row=4, column=0, padx=5, pady=5, sticky="w")
        self.is_active_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(details_frame, text="Is Active", variable=self.is_active_var).grid(row=4, column=1, padx=5, pady=5, sticky="w")

        # Buttons for actions
        button_frame = ttk.Frame(details_frame)
        button_frame.grid(row=5, column=0, columnspan=3, pady=10)
        
        ttk.Button(button_frame, text="Add New User", command=self.add_new_user).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Update Selected User", command=self.update_selected_user).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Delete Selected User", command=self.delete_selected_user).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear Form", command=self.clear_form).pack(side=tk.LEFT, padx=5)

        self.load_users()
        print(f"[{datetime.datetime.now()}] UserManagementModule: UI created.")

    def load_users(self):
        print(f"[{datetime.datetime.now()}] UserManagementModule: Loading users.")
        for item in self.user_tree.get_children():
            self.user_tree.delete(item)
        
        users = get_all_users()
        for user in users:
            active_status = "Yes" if user['is_active'] == 1 else "No"
            # When inserting, the iid is set to user['id'].
            self.user_tree.insert("", tk.END, iid=user['id'], values=(user['id'], user['username'], user['role'], active_status))
        print(f"[{datetime.datetime.now()}] UserManagementModule: Users loaded.")

    def on_user_select(self, event):
        selected_item = self.user_tree.selection()
        if selected_item:
            # FIX: The selected_item[0] already IS the iid. No need to call .item(..., 'iid')
            user_id = selected_item[0] 
            self.selected_user_id = user_id
            
            conn = get_db_connection()
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT id, username, role, is_active FROM users WHERE id = ?", (user_id,))
                user = cursor.fetchone()
                if user:
                    self.user_id_var.set(user['id'])
                    self.username_var.set(user['username'])
                    self.role_var.set(user['role'])
                    self.is_active_var.set(bool(user['is_active']))
                    self.password_var.set("") # Clear password field for security
                    self.username_entry.config(state='readonly') # Prevent changing username of existing user
                print(f"[{datetime.datetime.now()}] UserManagementModule: User {user_id} selected.")
            except Exception as e:
                messagebox.showerror("Database Error", f"Error fetching user details: {e}")
                print(f"[{datetime.datetime.now()}] UserManagementModule: Error fetching user details: {e}")
            finally:
                conn.close()
        else:
            # This 'else' block is the problematic part.
            # When selection is cleared by clear_form, it re-triggers on_user_select.
            # We need to prevent recursive calls.
            # Check if self.selected_user_id is already None to avoid redundant clearing.
            if self.selected_user_id is not None: # Only clear if something was previously selected
                self.clear_form()
                print(f"[{datetime.datetime.now()}] UserManagementModule: User selection cleared (via on_user_select).")
            else:
                print(f"[{datetime.datetime.now()}] UserManagementModule: No user selected, form already cleared or no prior selection.")


    def clear_form(self):
        print(f"[{datetime.datetime.now()}] UserManagementModule: Clearing form.")
        # Temporarily unbind the TreeviewSelect event
        self.user_tree.unbind("<<TreeviewSelect>>")

        self.selected_user_id = None
        self.user_id_var.set("")
        self.username_var.set("")
        self.password_var.set("")
        self.role_var.set("user")
        self.is_active_var.set(True)
        self.username_entry.config(state='normal') # Allow editing username for new user
        
        # Clear treeview selection
        for item in self.user_tree.selection():
            self.user_tree.selection_remove(item)

        # Rebind the TreeviewSelect event
        self.user_tree.bind("<<TreeviewSelect>>", self.on_user_select)

        print(f"[{datetime.datetime.now()}] UserManagementModule: Form cleared.")

    def add_new_user(self):
        print(f"[{datetime.datetime.now()}] UserManagementModule: Attempting to add new user.")
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        role = self.role_var.get()
        is_active = self.is_active_var.get()

        if not username or not password:
            messagebox.showwarning("Input Error", "Username and password are required for new users.")
            print(f"[{datetime.datetime.now()}] UserManagementModule: Add user failed - missing username/password.")
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Check if username already exists
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                messagebox.showerror("Error", "Username already exists. Please choose a different username.")
                print(f"[{datetime.datetime.now()}] UserManagementModule: Add user failed - username exists.")
                return

            hashed_password = hash_password(password) # Use hash_password from db_manager
            cursor.execute(
                "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
                (username, hashed_password, role, int(is_active))
            )
            conn.commit()
            messagebox.showinfo("Success", f"User '{username}' added successfully.")
            log_activity(self.current_user_info['id'], self.current_user_info['username'], "User Add", f"Added new user: {username}.")
            self.load_users()
            self.clear_form()
            print(f"[{datetime.datetime.now()}] UserManagementModule: User '{username}' added successfully.")
        except Exception as e:
            messagebox.showerror("Database Error", f"Error adding user: {e}")
            print(f"[{datetime.datetime.now()}] UserManagementModule: Error adding user: {e}")
        finally:
            conn.close()

    def update_selected_user(self):
        print(f"[{datetime.datetime.now()}] UserManagementModule: Attempting to update selected user.")
        if self.selected_user_id is None:
            messagebox.showwarning("Selection Error", "Please select a user to update.")
            print(f"[{datetime.datetime.now()}] UserManagementModule: Update user failed - no user selected.")
            return

        user_id = self.selected_user_id
        username = self.username_var.get().strip() # Username is readonly, so it's the original
        new_password = self.password_var.get().strip()
        new_role = self.role_var.get()
        new_is_active = self.is_active_var.get()

        if int(user_id) == self.current_user_info['id'] and new_is_active == False:
            messagebox.showwarning("Action Forbidden", "You cannot deactivate your own account.")
            print(f"[{datetime.datetime.now()}] UserManagementModule: Update user failed - cannot deactivate self.")
            return
        
        if int(user_id) == self.current_user_info['id'] and new_role != self.current_user_info['role']:
            messagebox.showwarning("Action Forbidden", "You cannot change your own role.")
            print(f"[{datetime.datetime.now()}] UserManagementModule: Update user failed - cannot change own role.")
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Fetch current user details to get existing password hash
            cursor.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
            current_password_hash = cursor.fetchone()['password_hash']

            if new_password: # If a new password is provided, hash it
                updated_password_hash = hash_password(new_password)
            else: # Otherwise, keep the existing hash
                updated_password_hash = current_password_hash

            cursor.execute(
                "UPDATE users SET password_hash = ?, role = ?, is_active = ? WHERE id = ?",
                (updated_password_hash, new_role, int(new_is_active), user_id)
            )
            conn.commit()
            messagebox.showinfo("Success", f"User '{username}' updated successfully.")
            log_activity(self.current_user_info['id'], self.current_user_info['username'], "User Update", f"Updated user: {username}.")
            self.load_users()
            self.clear_form()
            print(f"[{datetime.datetime.now()}] UserManagementModule: User '{username}' updated successfully.")
        except Exception as e:
            messagebox.showerror("Database Error", f"Error updating user: {e}")
            print(f"[{datetime.datetime.now()}] UserManagementModule: Error updating user: {e}")
        finally:
            conn.close()

    def delete_selected_user(self):
        print(f"[{datetime.datetime.now()}] UserManagementModule: Attempting to delete selected user.")
        if self.selected_user_id is None:
            messagebox.showwarning("Selection Error", "Please select a user to delete.")
            print(f"[{datetime.datetime.now()}] UserManagementModule: Delete user failed - no user selected.")
            return

        user_id = self.selected_user_id
        username = self.username_var.get().strip() # Get username for logging/message

        if int(user_id) == self.current_user_info['id']:
            messagebox.showwarning("Action Forbidden", "You cannot delete your own account.")
            print(f"[{datetime.datetime.now()}] UserManagementModule: Delete user failed - cannot delete self.")
            return

        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete user '{username}'? This action cannot be undone."):
            if delete_user(user_id): # Use delete_user from db_manager
                messagebox.showinfo("Success", f"User '{username}' deleted successfully.")
                log_activity(self.current_user_info['id'], self.current_user_info['username'], "User Delete", f"Deleted user: {username}.")
                self.load_users()
                self.clear_form()
                print(f"[{datetime.datetime.now()}] UserManagementModule: User '{username}' deleted successfully.")
            else:
                messagebox.showerror("Error", "Failed to delete user.")
                print(f"[{datetime.datetime.now()}] UserManagementModule: Error deleting user: {username}.")

