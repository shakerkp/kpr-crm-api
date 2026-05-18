import tkinter as tk
from tkinter import ttk, messagebox
import datetime
import re # Import regular expression module for mobile validation

# Import functions from db_manager
from db_manager import get_db_connection, log_activity

class CustomerModule:
    """
    Manages the customer module UI and logic, including adding, updating,
    deleting, and viewing customer records.
    """
    def __init__(self, parent_frame, current_user_info, set_last_selected_customer_info_callback):
        print(f"[{datetime.datetime.now()}] CustomerModule: __init__ started.")
        self.parent_frame = parent_frame
        self.current_user_info = current_user_info
        self.set_last_selected_customer_info_callback = set_last_selected_customer_info_callback # Store the callback

        self.selected_customer_id = None # To store the ID of the selected customer for editing/deleting

        self.create_ui()
        self.load_customers()
        print(f"[{datetime.datetime.now()}] CustomerModule: __init__ finished.")

    def create_ui(self):
        """Builds the graphical user interface for the customer module."""
        print(f"[{datetime.datetime.now()}] CustomerModule: create_ui started.")
        for widget in self.parent_frame.winfo_children():
            widget.destroy()

        main_frame = ttk.Frame(self.parent_frame, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Input Frame ---
        input_frame = ttk.LabelFrame(main_frame, text="Customer Details", padding="10")
        input_frame.pack(fill=tk.X, pady=10)
        input_frame.columnconfigure(1, weight=1) # Allow entry widgets to expand

        ttk.Label(input_frame, text="Name:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.name_entry = ttk.Entry(input_frame)
        self.name_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=2)

        ttk.Label(input_frame, text="Mobile:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.mobile_entry = ttk.Entry(input_frame)
        self.mobile_entry.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=2)

        ttk.Label(input_frame, text="Alternate Mobile:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.alt_mobile_entry = ttk.Entry(input_frame)
        self.alt_mobile_entry.grid(row=2, column=1, sticky=tk.EW, padx=5, pady=2)
        
        # FIX: Correctly place the Email entry widget using .grid()
        ttk.Label(input_frame, text="Email:").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.email_entry = ttk.Entry(input_frame)
        self.email_entry.grid(row=3, column=1, sticky=tk.EW, padx=5, pady=2)

        ttk.Label(input_frame, text="GST No:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
        self.gst_entry = ttk.Entry(input_frame)
        self.gst_entry.grid(row=4, column=1, sticky=tk.EW, padx=5, pady=2)

        ttk.Label(input_frame, text="PAN No:").grid(row=5, column=0, sticky=tk.W, padx=5, pady=2)
        self.pan_entry = ttk.Entry(input_frame)
        self.pan_entry.grid(row=5, column=1, sticky=tk.EW, padx=5, pady=2)

        ttk.Label(input_frame, text="Address:").grid(row=6, column=0, sticky=tk.W, padx=5, pady=2)
        self.address_entry = ttk.Entry(input_frame)
        self.address_entry.grid(row=6, column=1, sticky=tk.EW, padx=5, pady=2)

        ttk.Label(input_frame, text="Tags (comma-separated):").grid(row=7, column=0, sticky=tk.W, padx=5, pady=2)
        self.tags_entry = ttk.Entry(input_frame)
        self.tags_entry.grid(row=7, column=1, sticky=tk.EW, padx=5, pady=2)

        # --- Buttons Frame ---
        button_frame = ttk.Frame(main_frame, padding="10")
        button_frame.pack(fill=tk.X, pady=5)

        self.is_admin = self.current_user_info.get('role') == 'admin'

        self.add_button = ttk.Button(button_frame, text="Add Customer", command=self.add_customer)
        self.add_button.pack(side=tk.LEFT, padx=5)

        # Update & Delete: only visible to admin
        if self.is_admin:
            self.update_button = ttk.Button(button_frame, text="Update Customer", command=self.update_customer, state=tk.DISABLED)
            self.update_button.pack(side=tk.LEFT, padx=5)

            self.delete_button = ttk.Button(button_frame, text="Delete Customer", command=self.delete_customer, state=tk.DISABLED)
            self.delete_button.pack(side=tk.LEFT, padx=5)
        else:
            self.update_button = None
            self.delete_button = None

        self.clear_button = ttk.Button(button_frame, text="Clear Fields", command=self.clear_fields)
        self.clear_button.pack(side=tk.LEFT, padx=5)
        
        # Removed the "View Jobs/Payments" button as per user request
        # self.view_jobs_button = ttk.Button(button_frame, text="View Jobs/Payments", command=self.view_customer_jobs, state=tk.DISABLED)
        # self.view_jobs_button.pack(side=tk.RIGHT, padx=5)


        # --- Search Frame ---
        search_frame = ttk.Frame(main_frame, padding="10")
        search_frame.pack(fill=tk.X, pady=5)

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=5)
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=5)
        self.search_entry.bind("<KeyRelease>", self.search_customers)

        # --- Customer List Treeview ---
        tree_frame = ttk.Frame(main_frame, padding="10")
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=10)

        # Updated columns to match the database and input fields
        columns = ("ID", "Name", "Mobile", "Alternate Mobile", "GST No", "PAN No", "Address", "Email", "Tags")
        self.customer_tree = ttk.Treeview(tree_frame, columns=columns, show="headings")
        self.customer_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        for col in columns:
            self.customer_tree.heading(col, text=col)
            self.customer_tree.column(col, width=100, anchor=tk.W)
        
        self.customer_tree.column("ID", width=50, stretch=tk.NO)
        self.customer_tree.column("Name", width=150)
        self.customer_tree.column("Mobile", width=120)
        self.customer_tree.column("Alternate Mobile", width=120)
        self.customer_tree.column("GST No", width=100)
        self.customer_tree.column("PAN No", width=100)
        self.customer_tree.column("Address", width=200)
        self.customer_tree.column("Email", width=150)
        self.customer_tree.column("Tags", width=100)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.customer_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.customer_tree.config(yscrollcommand=scrollbar.set)

        self.customer_tree.bind("<<TreeviewSelect>>", self.on_customer_select)
        print(f"[{datetime.datetime.now()}] CustomerModule: create_ui finished.")

    def load_customers(self):
        """
        Loads customer data from the database into the Treeview.
        Filters based on the search input.
        """
        print(f"[{datetime.datetime.now()}] CustomerModule: Loading customers.")
        for item in self.customer_tree.get_children():
            self.customer_tree.delete(item)

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            search_term = self.search_entry.get().strip()
            # Updated the SELECT statement to include all new columns
            select_query = "SELECT id, name, mobile, alternate_mobile, gst_no, pan_no, address, email, tags FROM customers"
            
            if search_term:
                search_like = f"%{search_term}%"
                cursor.execute(f"{select_query} WHERE name LIKE ? OR mobile LIKE ? ORDER BY name", (search_like, search_like))
            else:
                cursor.execute(f"{select_query} ORDER BY name")
            
            customers = cursor.fetchall()
            for customer in customers:
                # Updated the values tuple to include all data from the database
                self.customer_tree.insert("", tk.END, values=(
                    customer['id'],
                    customer['name'],
                    customer['mobile'],
                    customer['alternate_mobile'] if customer['alternate_mobile'] is not None else "",
                    customer['gst_no'] if customer['gst_no'] is not None else "",
                    customer['pan_no'] if customer['pan_no'] is not None else "",
                    customer['address'] if customer['address'] is not None else "",
                    customer['email'] if customer['email'] is not None else "",
                    customer['tags'] if customer['tags'] is not None else ""
                ))
            print(f"[{datetime.datetime.now()}] CustomerModule: Loaded {len(customers)} customers.")
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to load customers: {e}")
            print(f"[{datetime.datetime.now()}] CustomerModule: Error loading customers: {e}")
        finally:
            conn.close()

    def search_customers(self, event=None):
        """Triggers customer loading based on search input."""
        self.load_customers()

    def on_customer_select(self, event):
        """Handles a customer selection in the Treeview, populating the input fields."""
        print(f"[{datetime.datetime.now()}] CustomerModule: Customer selected.")
        selected_items = self.customer_tree.selection()
        if not selected_items:
            self.clear_fields()
            self.selected_customer_id = None
            if self.update_button:
                self.update_button.config(state=tk.DISABLED)
            if self.delete_button:
                self.delete_button.config(state=tk.DISABLED)
            # self.view_jobs_button.config(state=tk.DISABLED) # Removed
            self.set_last_selected_customer_info_callback(None, None, None) # Clear selected customer info in main app
            return

        item = selected_items[0]
        values = self.customer_tree.item(item, 'values')
        
        self.selected_customer_id = values[0]
        self.name_entry.delete(0, tk.END)
        self.name_entry.insert(0, values[1])
        self.mobile_entry.delete(0, tk.END)
        self.mobile_entry.insert(0, values[2])
        # FIX: Added new fields to be populated on selection
        self.alt_mobile_entry.delete(0, tk.END)
        self.alt_mobile_entry.insert(0, values[3])
        self.gst_entry.delete(0, tk.END)
        self.gst_entry.insert(0, values[4])
        self.pan_entry.delete(0, tk.END)
        self.pan_entry.insert(0, values[5])
        
        self.address_entry.delete(0, tk.END)
        self.address_entry.insert(0, values[6])
        self.email_entry.delete(0, tk.END)
        self.email_entry.insert(0, values[7])
        self.tags_entry.delete(0, tk.END)
        self.tags_entry.insert(0, values[8])

        if self.is_admin:
            self.update_button.config(state=tk.NORMAL)
            self.delete_button.config(state=tk.NORMAL)
        self.add_button.config(state=tk.DISABLED)

        # Call the callback to update the main app's last selected customer info
        self.set_last_selected_customer_info_callback(values[0], values[1], values[2])
        print(f"[{datetime.datetime.now()}] CustomerModule: Customer ID {self.selected_customer_id} selected for editing.")

    def clear_fields(self):
        """Clears all input fields and resets the UI state."""
        print(f"[{datetime.datetime.now()}] CustomerModule: Entering clear_fields function.")
        self.name_entry.delete(0, tk.END)
        self.mobile_entry.delete(0, tk.END)
        self.alt_mobile_entry.delete(0, tk.END) # Added
        self.gst_entry.delete(0, tk.END)       # Added
        self.pan_entry.delete(0, tk.END)       # Added
        self.address_entry.delete(0, tk.END)
        self.email_entry.delete(0, tk.END)
        self.tags_entry.delete(0, tk.END)
        
        self.selected_customer_id = None
        print(f"[{datetime.datetime.now()}] CustomerModule: selected_customer_id set to None.")
        
        if self.update_button:
            self.update_button.config(state=tk.DISABLED)
        if self.delete_button:
            self.delete_button.config(state=tk.DISABLED)
        self.add_button.config(state=tk.NORMAL) # Enable add when fields are cleared
        
        # Deselect any selected item in the Treeview
        current_selection = self.customer_tree.selection()
        if current_selection:
            self.customer_tree.selection_remove(current_selection) 
            print(f"[{datetime.datetime.now()}] CustomerModule: Treeview selection removed.")
        
        self.set_last_selected_customer_info_callback(None, None, None) # Clear selected customer info in main app
        print(f"[{datetime.datetime.now()}] CustomerModule: Last selected customer info cleared in main app.")
        print(f"[{datetime.datetime.now()}] CustomerModule: Exiting clear_fields function.")

    def validate_inputs(self, is_new_customer=True):
        """Validates customer input fields."""
        print(f"[{datetime.datetime.now()}] CustomerModule: Starting input validation (is_new_customer={is_new_customer}).")
        name = self.name_entry.get().strip()
        mobile = self.mobile_entry.get().strip()
        email = self.email_entry.get().strip()

        if not name:
            messagebox.showwarning("Input Error", "Customer Name cannot be empty.")
            print(f"[{datetime.datetime.now()}] CustomerModule: Validation failed - Name empty.")
            return False
        if not mobile:
            messagebox.showwarning("Input Error", "Mobile Number cannot be empty.")
            print(f"[{datetime.datetime.now()}] CustomerModule: Validation failed - Mobile empty.")
            return False
        if not re.fullmatch(r'\d{10}', mobile):
            messagebox.showwarning("Input Error", "Mobile Number must be 10 digits.")
            print(f"[{datetime.datetime.now()}] CustomerModule: Validation failed - Invalid mobile format: {mobile}.")
            return False
        if email and not re.fullmatch(r'[^@]+@[^@]+\.[^@]+', email):
            messagebox.showwarning("Input Error", "Invalid Email Address format.")
            print(f"[{datetime.datetime.now()}] CustomerModule: Validation failed - Invalid email format: {email}.")
            return False
        
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Check for duplicate mobile number
            if is_new_customer:
                cursor.execute("SELECT COUNT(*) FROM customers WHERE mobile = ?", (mobile,))
                print(f"[{datetime.datetime.now()}] CustomerModule: Checking for duplicate mobile (add mode) for {mobile}.")
            else: # For update, allow the current customer's mobile to be the same
                cursor.execute("SELECT COUNT(*) FROM customers WHERE mobile = ? AND id != ?", (mobile, self.selected_customer_id))
                print(f"[{datetime.datetime.now()}] CustomerModule: Checking for duplicate mobile (update mode) for {mobile}, excluding ID {self.selected_customer_id}.")
            
            if cursor.fetchone()[0] > 0:
                messagebox.showwarning("Duplicate Entry", "Mobile Number already exists for another customer.")
                print(f"[{datetime.datetime.now()}] CustomerModule: Validation failed - Duplicate mobile: {mobile}.")
                return False
        except Exception as e:
            messagebox.showerror("Database Error", f"Error checking for duplicate mobile: {e}")
            print(f"[{datetime.datetime.now()}] CustomerModule: Error during duplicate mobile check: {e}")
            return False
        finally:
            conn.close()
        
        print(f"[{datetime.datetime.now()}] CustomerModule: Input validation successful.")
        return True

    def add_customer(self):
        """Adds a new customer to the database."""
        print(f"[{datetime.datetime.now()}] CustomerModule: Attempting to add customer.")
        if not self.validate_inputs(is_new_customer=True):
            print(f"[{datetime.datetime.now()}] CustomerModule: Add customer aborted due to validation failure.")
            return

        name = self.name_entry.get().strip()
        mobile = self.mobile_entry.get().strip()
        alt_mobile = self.alt_mobile_entry.get().strip() # Added
        gst_no = self.gst_entry.get().strip()           # Added
        pan_no = self.pan_entry.get().strip()           # Added
        address = self.address_entry.get().strip()
        email = self.email_entry.get().strip()
        tags = self.tags_entry.get().strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            print(f"[{datetime.datetime.now()}] CustomerModule: Inserting new customer: {name}, {mobile}.")
            # FIX: Corrected the SQL statement to match all columns and values
            cursor.execute("INSERT INTO customers (name, mobile, alternate_mobile, gst_no, pan_no, address, email, tags) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (name, mobile, alt_mobile, gst_no, pan_no, address, email, tags))
            conn.commit()
            messagebox.showinfo("Success", "Customer added successfully!")
            log_activity(self.current_user_info['id'], self.current_user_info['username'], "Customer Add", f"Added customer: {name} ({mobile})")
            self.clear_fields()
            self.load_customers()
            print(f"[{datetime.datetime.now()}] CustomerModule: Customer '{name}' added and committed.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add customer: {e}")
            print(f"[{datetime.datetime.now()}] CustomerModule: Error adding customer: {e}")
            conn.rollback()
        finally:
            conn.close()

    def update_customer(self):
        """Updates an existing customer record in the database."""
        if not self.is_admin:
            messagebox.showerror("Permission Denied", "Only admins can update customers.")
            return
        print(f"[{datetime.datetime.now()}] CustomerModule: Attempting to update customer ID: {self.selected_customer_id}.")
        if self.selected_customer_id is None:
            messagebox.showwarning("Selection Error", "Please select a customer to update.")
            print(f"[{datetime.datetime.now()}] CustomerModule: Update customer aborted - no customer selected.")
            return
        
        if not self.validate_inputs(is_new_customer=False):
            print(f"[{datetime.datetime.now()}] CustomerModule: Update customer aborted due to validation failure.")
            return

        name = self.name_entry.get().strip()
        mobile = self.mobile_entry.get().strip()
        alt_mobile = self.alt_mobile_entry.get().strip() # Added
        gst_no = self.gst_entry.get().strip()           # Added
        pan_no = self.pan_entry.get().strip()           # Added
        address = self.address_entry.get().strip()
        email = self.email_entry.get().strip()
        tags = self.tags_entry.get().strip()

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            print(f"[{datetime.datetime.now()}] CustomerModule: Updating customer ID {self.selected_customer_id}: {name}, {mobile}.")
            # FIX: Corrected the SQL statement to match all columns
            cursor.execute("""
                UPDATE customers SET name=?, mobile=?, alternate_mobile=?, gst_no=?, pan_no=?, address=?, email=?, tags=? WHERE id=?
            """, (name, mobile, alt_mobile, gst_no, pan_no, address, email, tags, self.selected_customer_id))
            conn.commit()
            messagebox.showinfo("Success", "Customer updated successfully!")
            log_activity(self.current_user_info['id'], self.current_user_info['username'], "Customer Update", f"Updated customer ID: {self.selected_customer_id} ({name})")
            self.clear_fields()
            self.load_customers()
            print(f"[{datetime.datetime.now()}] CustomerModule: Customer ID {self.selected_customer_id} updated and committed.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update customer: {e}")
            print(f"[{datetime.datetime.now()}] CustomerModule: Error updating customer: {e}")
            conn.rollback()
        finally:
            conn.close()

    def delete_customer(self):
        """Deletes a customer and all their associated data from the database."""
        if not self.is_admin:
            messagebox.showerror("Permission Denied", "Only admins can delete customers.")
            return
        print(f"[{datetime.datetime.now()}] CustomerModule: Attempting to delete customer ID: {self.selected_customer_id}.")
        if self.selected_customer_id is None:
            messagebox.showwarning("Selection Error", "Please select a customer to delete.")
            return

        if not messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this customer? All associated jobs and payments will also be deleted."):
            print(f"[{datetime.datetime.now()}] CustomerModule: Delete cancelled by user.")
            return

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            # Start a transaction for atomicity
            conn.execute("BEGIN TRANSACTION")

            # Get customer details for logging
            cursor.execute("SELECT name, mobile FROM customers WHERE id=?", (self.selected_customer_id,))
            customer_info = cursor.fetchone()
            customer_name_log = customer_info['name']
            customer_mobile_log = customer_info['mobile']

            # Delete associated payments first
            cursor.execute("DELETE FROM payments WHERE customer_id=?", (self.selected_customer_id,))
            payments_deleted = cursor.rowcount
            print(f"[{datetime.datetime.now()}] CustomerModule: Deleted {payments_deleted} payments for customer ID {self.selected_customer_id}.")

            # Delete associated jobs
            cursor.execute("DELETE FROM jobs WHERE customer_id=?", (self.selected_customer_id,))
            jobs_deleted = cursor.rowcount
            print(f"[{datetime.datetime.now()}] CustomerModule: Deleted {jobs_deleted} jobs for customer ID {self.selected_customer_id}.")

            # Finally, delete the customer
            cursor.execute("DELETE FROM customers WHERE id=?", (self.selected_customer_id,))
            customers_deleted = cursor.rowcount
            print(f"[{datetime.datetime.now()}] CustomerModule: Deleted {customers_deleted} customer record for ID {self.selected_customer_id}.")

            conn.commit()
            messagebox.showinfo("Success", "Customer and all associated data deleted successfully!")
            log_activity(self.current_user_info['id'], self.current_user_info['username'], "Customer Delete", f"Deleted customer: {customer_name_log} ({customer_mobile_log}) and their {jobs_deleted} jobs and {payments_deleted} payments.")
            self.clear_fields()
            self.load_customers()
            print(f"[{datetime.datetime.now()}] CustomerModule: Customer ID {self.selected_customer_id} deleted.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to delete customer: {e}")
            print(f"[{datetime.datetime.now()}] CustomerModule: Error deleting customer: {e}")
            conn.rollback() # Rollback all changes if any error occurs
        finally:
            conn.close()

    # Removed the view_customer_jobs function as per user request
    # def view_customer_jobs(self):
    #     print(f"[{datetime.datetime.now()}] CustomerModule: Attempting to view jobs for customer ID: {self.selected_customer_id}.")
    #     if self.selected_customer_id is None:
    #         messagebox.showwarning("Selection Error", "Please select a customer to view their jobs.")
    #         return
    #     self.parent_frame.winfo_toplevel().show_module("jobs_payments")
    #     print(f"[{datetime.datetime.now()}] CustomerModule: Signaled main app to show Job/Payment module for customer ID {self.selected_customer_id}.")
