import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
# Import necessary functions from db_manager
from db_manager import get_db_connection, log_activity, add_job_note, get_job_notes
from order_slip_module import open_order_slip, WhatsAppSMSDialog
import datetime

class JobModule:
    def __init__(self, parent_frame, current_user_info):
        print(f"[{datetime.datetime.now()}] JobModule: __init__ started.")
        self.parent_frame = parent_frame
        self.current_user_info = current_user_info # {id, username, role}
        self.selected_job_id = None
        self.is_sub_staff = (current_user_info.get('role') == 'sub_staff')

        # Variables for job input fields (same as CustomerJobModule for consistency)
        self.job_types = {
            "Albums": ["Wedding Album", "Birthday Album", "Custom Album"],
            "Photo Frames": ["Acrylic Frame", "Glass Photo Frame", "LED Frame", "Canvas Print", "Collage Frame", "Moulding Frame"],
            "Mugs": ["Custom Mug", "Magic Mug", "Beer Mug"],
            "T-Shirts": ["Custom T-Shirt (Cotton)", "Custom T-Shirt (Polyester)", "Couple T-Shirt"],
            "Caps": ["Custom Cap"],
            "Banners": ["Flex Banner", "Vinyl Banner", "Standee Banner"],
            "Posters": ["Glossy Poster", "Matte Poster"],
            "Other": ["Lamination", "Passport Photos", "ID Cards", "Photo Restoration"]
        }
        self.all_job_type_options = self._get_flat_job_type_list()

        self.job_type_var = tk.StringVar(value="Other")
        self.job_desc = tk.StringVar()
        self.job_size = tk.StringVar() # Added for size field
        # Removed financial variables as per screenshot
        # self.initial_price = tk.DoubleVar(value=0.0)
        # self.discount_amount = tk.DoubleVar(value=0.0)
        # self.final_price = tk.DoubleVar(value=0.0)
        # self.adv1 = tk.DoubleVar(value=0.0)
        # self.balance = tk.DoubleVar(value=0.0)
        # self.rounded_off_amount = tk.DoubleVar(value=0.0)
        # self.payment_mode = tk.StringVar(value="Cash")
        self.job_status_var = tk.StringVar(value="Pending") # This will be the dropdown
        self.payment_status_var = tk.StringVar(value="Unpaid") # New for payment status
        self.start_date_var = tk.StringVar(value=datetime.date.today().isoformat())
        self.due_date_var = tk.StringVar() # New for due date
        self.completion_date_var = tk.StringVar() # New for completion date
        self.delivery_date_var = tk.StringVar()
        self.remarks_var = tk.StringVar() # New for remarks
        self.assigned_staff_var = tk.StringVar(value="Unassigned") # New for assigned staff

        # Fetch staff for assignment dropdown
        self.staff_members = self._get_staff_members()
        self.staff_options = ["Unassigned"] + [staff['username'] for staff in self.staff_members]

        self.create_job_ui()

        # Removed trace changes to financial variables
        # self.initial_price.trace_add("write", self._calculate_financials)
        # self.discount_amount.trace_add("write", self._calculate_financials)
        # self.adv1.trace_add("write", self._calculate_financials)
        # self.rounded_off_amount.trace_add("write", self._calculate_financials)
        print(f"[{datetime.datetime.now()}] JobModule: __init__ finished.")

    def _get_flat_job_type_list(self):
        """Helper to get a flat list of all job types for the combobox."""
        flat_list = []
        for category, items in self.job_types.items():
            flat_list.append(f"-- {category} --") # Add category header for visual grouping
            for item in items:
                flat_list.append(item)
        return flat_list

    def _get_staff_members(self):
        """Fetches list of active users who can be assigned as staff."""
        print(f"[{datetime.datetime.now()}] JobModule: Fetching staff members.")
        conn = None
        staff_list = []
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id, username FROM users WHERE is_active = 1") # Only active users
            staff_list = cur.fetchall()
            print(f"[{datetime.datetime.now()}] JobModule: Fetched {len(staff_list)} staff members.")
        except Exception as e:
            print(f"[{datetime.datetime.now()}] JobModule: Error fetching staff members: {e}")
            messagebox.showerror("Database Error", f"Failed to load staff members: {e}")
        finally:
            if conn:
                conn.close()
        return staff_list

    def _get_staff_id_from_username(self, username):
        """Returns staff ID given a username, or None if not found."""
        if username == "Unassigned":
            return None
        for staff in self.staff_members:
            if staff['username'] == username:
                return staff['id']
        return None

    def _get_username_from_staff_id(self, staff_id):
        """Returns username given a staff ID, or 'Unassigned' if not found or None."""
        if staff_id is None:
            return "Unassigned"
        for staff in self.staff_members:
            if staff['id'] == staff_id:
                return staff['username']
        return "Unassigned"

    # Removed _calculate_financials as financial columns are removed
    # def _calculate_financials(self, *args):
    #     """Calculates final price and balance based on inputs."""
    #     initial_price = self._get_numeric_value(self.initial_price)
    #     discount = self._get_numeric_value(self.discount_amount)
    #     advance1 = self._get_numeric_value(self.adv1)
    #     rounded_off = self._get_numeric_value(self.rounded_off_amount)

    #     calculated_final_price = initial_price - discount
    #     self.final_price.set(f"{calculated_final_price:.2f}")

    #     balance = calculated_final_price - advance1 + rounded_off
    #     self.balance.set(f"{balance:.2f}")

    def _get_numeric_value(self, tk_var):
        """Safely gets a float value from a StringVar/DoubleVar, defaulting to 0.0 if invalid."""
        try:
            return float(tk_var.get())
        except (ValueError, tk.TclError):
            return 0.0

    def create_job_ui(self):
        print(f"[{datetime.datetime.now()}] JobModule: create_job_ui started.")
        for widget in self.parent_frame.winfo_children():
            widget.destroy()

        main_frame = ttk.Frame(self.parent_frame, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Search and Filter Frame
        # Further reduced pady for the frame itself
        search_frame = ttk.LabelFrame(main_frame, text="Search & Filter Jobs", padding=(10, 1)) 
        search_frame.pack(fill=tk.X, pady=1) # Further reduced pady

        # Further reduced pady for internal widgets
        ttk.Label(search_frame, text="Search (Customer Name/Mobile/Job Desc):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=0)
        self.search_entry = ttk.Entry(search_frame, width=40)
        self.search_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=0) 
        self.search_entry.bind("<KeyRelease>", self.filter_jobs)

        ttk.Label(search_frame, text="Status Filter:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=0)
        self.filter_status_var = tk.StringVar(value="All")
        status_options = ["All", "Pending", "In Progress", "Completed", "Delivered", "Cancelled"]
        ttk.OptionMenu(search_frame, self.filter_status_var, "All", *status_options, command=self.filter_jobs).grid(row=0, column=3, sticky=(tk.W, tk.E), padx=5, pady=0)

        search_frame.columnconfigure(1, weight=1) # Allow search entry to expand

        # Jobs Treeview
        self.job_tree = ttk.Treeview(main_frame, columns=(
            "ID", "Customer Name", "Customer Mobile", "Job Type", "Description", "Size", # Added Size
            "Status", "Payment Status",
            "Start Date", "Due Date", "Completion Date", "Delivery Date", "Remarks", "Assigned Staff" # Added Due Date, Completion Date, Remarks, Assigned Staff
        ), show="headings")

        # Define headings and column widths
        self.job_tree.heading("ID", text="ID")
        self.job_tree.heading("Customer Name", text="Customer Name")
        self.job_tree.heading("Customer Mobile", text="Mobile")
        self.job_tree.heading("Job Type", text="Job Type")
        self.job_tree.heading("Description", text="Description")
        self.job_tree.heading("Size", text="Size") # New heading
        # Removed financial headings
        # self.job_tree.heading("Initial Price", text="Init Price")
        # self.job_tree.heading("Discount", text="Disc")
        # self.job_tree.heading("Final Price", text="Final Price")
        # self.job_tree.heading("Advance1", text="Adv1")
        # self.job_tree.heading("Balance", text="Balance")
        # self.job_tree.heading("Rounded Off", text="Rnd Off")
        # self.job_tree.heading("Payment Mode", text="Pay Mode")
        self.job_tree.heading("Status", text="Status")
        self.job_tree.heading("Payment Status", text="Pay Status")
        self.job_tree.heading("Start Date", text="Start Date")
        self.job_tree.heading("Due Date", text="Due Date") # New heading
        self.job_tree.heading("Completion Date", text="Comp. Date") # New heading
        self.job_tree.heading("Delivery Date", text="Delivery Date")
        self.job_tree.heading("Remarks", text="Remarks") # New heading
        self.job_tree.heading("Assigned Staff", text="Assigned To")

        self.job_tree.column("ID", width=40, stretch=tk.NO)
        self.job_tree.column("Customer Name", width=120, stretch=tk.YES)
        # Mobile column — hidden for sub_staff (width=0, minwidth=0)
        if self.is_sub_staff:
            self.job_tree.column("Customer Mobile", width=0, minwidth=0, stretch=tk.NO)
            self.job_tree.heading("Customer Mobile", text="")
        else:
            self.job_tree.column("Customer Mobile", width=90, stretch=tk.NO)
        self.job_tree.column("Job Type", width=100, stretch=tk.YES)
        self.job_tree.column("Description", width=150, stretch=tk.YES)
        self.job_tree.column("Size", width=60, stretch=tk.NO) # New column width
        # Removed financial column widths
        # self.job_tree.column("Initial Price", width=70, stretch=tk.NO, anchor=tk.E)
        # self.job_tree.column("Discount", width=50, stretch=tk.NO, anchor=tk.E)
        # self.job_tree.column("Final Price", width=70, stretch=tk.NO, anchor=tk.E)
        # self.job_tree.column("Advance1", width=60, stretch=tk.NO, anchor=tk.E)
        # self.job_tree.column("Balance", width=70, stretch=tk.NO, anchor=tk.E)
        # self.job_tree.column("Rounded Off", width=60, stretch=tk.NO, anchor=tk.E)
        # self.job_tree.column("Payment Mode", width=80, stretch=tk.NO)
        self.job_tree.column("Status", width=80, stretch=tk.NO)
        self.job_tree.column("Payment Status", width=80, stretch=tk.NO)
        self.job_tree.column("Start Date", width=80, stretch=tk.NO)
        self.job_tree.column("Due Date", width=80, stretch=tk.NO) # New column width
        self.job_tree.column("Completion Date", width=80, stretch=tk.NO) # New column width
        self.job_tree.column("Delivery Date", width=80, stretch=tk.NO)
        self.job_tree.column("Remarks", width=100, stretch=tk.YES) # New column width
        self.job_tree.column("Assigned Staff", width=80, stretch=tk.NO)

        self.job_tree.pack(fill=tk.BOTH, expand=True, pady=5)
        self.job_tree.bind("<<TreeviewSelect>>", self.on_job_select)

        # Job Details Form (for viewing/editing selected job)
        # Further reduced vertical padding for the frame itself
        job_form_frame = ttk.LabelFrame(main_frame, text="Selected Job Details", padding=(10, 0)) 
        job_form_frame.pack(fill=tk.X, pady=0) # Further reduced vertical pady
        job_form_frame.columnconfigure(1, weight=1)
        job_form_frame.columnconfigure(3, weight=1)

        # Further reduced pady for internal widgets
        ttk.Label(job_form_frame, text="Job ID:").grid(row=0, column=0, sticky=tk.W, pady=0, padx=5) 
        self.job_id_display = ttk.Label(job_form_frame, text="N/A", font=("Arial", 10, "bold"))
        self.job_id_display.grid(row=0, column=1, sticky=tk.W, pady=0, padx=5) 
        
        ttk.Label(job_form_frame, text="Customer:").grid(row=0, column=2, sticky=tk.W, pady=0, padx=5) 
        self.customer_display = ttk.Label(job_form_frame, text="N/A", font=("Arial", 10, "bold"), foreground="blue")
        self.customer_display.grid(row=0, column=3, sticky=tk.W, pady=0, padx=5) 

        #ttk.Label(job_form_frame, text="Job Type:").grid(row=1, column=0, sticky=tk.W, pady=0, padx=5) 
        #self.job_type_combobox = ttk.Combobox(job_form_frame, textvariable=self.job_type_var, values=self.all_job_type_options, state="readonly")
        #self.job_type_combobox.grid(row=1, column=1, columnspan=3, sticky=tk.EW, padx=5, pady=0) 

        #ttk.Label(job_form_frame, text="Description:").grid(row=1, column=0, sticky=tk.W, pady=0, padx=5) 
        #ttk.Entry(job_form_frame, textvariable=self.job_desc).grid(row=1, column=1, columnspan=3, sticky=tk.EW, padx=5, pady=0) 
        
        #ttk.Label(job_form_frame, text="Size (Optional):").grid(row=2, column=0, sticky=tk.W, pady=0, padx=5) # Adjusted row
        #ttk.Entry(job_form_frame, textvariable=self.job_size).grid(row=2, column=1, sticky=tk.EW, padx=5, pady=0) # Adjusted row

        # Removed financial input fields
        # ttk.Label(job_form_frame, text="Initial Price (₹):").grid(row=4, column=0, sticky=tk.W, pady=0, padx=5) # Adjusted row
        # ttk.Entry(job_form_frame, textvariable=self.initial_price).grid(row=4, column=1, sticky=tk.EW, padx=5, pady=0) # Adjusted row

        # ttk.Label(job_form_frame, text="Discount (₹):").grid(row=4, column=2, sticky=tk.W, pady=0, padx=5) # Adjusted row
        # ttk.Entry(job_form_frame, textvariable=self.discount_amount).grid(row=4, column=3, sticky=tk.EW, padx=5, pady=0) # Adjusted row

        # ttk.Label(job_form_frame, text="Final Price (₹):").grid(row=5, column=0, sticky=tk.W, pady=0, padx=5) # Adjusted row
        # ttk.Entry(job_form_frame, textvariable=self.final_price, state='readonly').grid(row=5, column=1, sticky=tk.EW, padx=5, pady=0) # Adjusted row

        # ttk.Label(job_form_frame, text="Advance 1 (₹):").grid(row=5, column=2, sticky=tk.W, pady=0, padx=5) # Adjusted row
        # ttk.Entry(job_form_frame, textvariable=self.adv1).grid(row=5, column=3, sticky=tk.EW, padx=5, pady=0) # Adjusted row

        # ttk.Label(job_form_frame, text="Rounded Off (₹):").grid(row=6, column=2, sticky=tk.W, pady=0, padx=5) # Adjusted row
        # ttk.Entry(job_form_frame, textvariable=self.rounded_off_amount).grid(row=6, column=3, sticky=tk.EW, padx=5, pady=0) # Adjusted row
        
        # ttk.Label(job_form_frame, text="Balance (₹):").grid(row=7, column=0, sticky=tk.W, pady=0, padx=5) # Adjusted row
        # ttk.Entry(job_form_frame, textvariable=self.balance, state='readonly').grid(row=7, column=1, sticky=tk.EW, padx=5, pady=0) # Adjusted row

        # ttk.Label(job_form_frame, text="Payment Mode:").grid(row=7, column=2, sticky=tk.W, pady=0, padx=5) # Adjusted row
        # ttk.OptionMenu(job_form_frame, self.payment_mode, "Cash", "Cash", "Card", "UPI", "Bank Transfer").grid(row=7, column=3, sticky=tk.EW, padx=5, pady=0) # Adjusted row

        # Adjusted row numbers for remaining fields
        ttk.Label(job_form_frame, text="Job Status:").grid(row=3, column=0, sticky=tk.W, pady=0, padx=5)
        job_status_options = ["Pending", "In Progress", "Completed", "Delivered", "Cancelled"] # User's requested statuses
        self.job_status_combobox = ttk.Combobox(job_form_frame, textvariable=self.job_status_var, values=job_status_options, state="readonly")
        self.job_status_combobox.grid(row=3, column=1, sticky=tk.EW, padx=5, pady=0)
        self.job_status_combobox.set("Pending") # Default value

        #ttk.Label(job_form_frame, text="Payment Status:").grid(row=4, column=2, sticky=tk.W, pady=0, padx=5)
        #payment_status_options = ["Unpaid", "Partially Paid", "Paid"]
        #ttk.OptionMenu(job_form_frame, self.payment_status_var, "Unpaid", *payment_status_options).grid(row=4, column=3, sticky=tk.EW, padx=5, pady=0)

        ttk.Label(job_form_frame, text="Start Date:").grid(row=5, column=0, sticky=tk.W, pady=0, padx=5)
        ttk.Entry(job_form_frame, textvariable=self.start_date_var).grid(row=5, column=1, sticky=tk.EW, padx=5, pady=0)

        ttk.Label(job_form_frame, text="Due Date:").grid(row=5, column=2, sticky=tk.W, pady=0, padx=5)
        ttk.Entry(job_form_frame, textvariable=self.due_date_var).grid(row=5, column=3, sticky=tk.EW, padx=5, pady=0)

        ttk.Label(job_form_frame, text="Completion Date:").grid(row=6, column=0, sticky=tk.W, pady=0, padx=5)
        ttk.Entry(job_form_frame, textvariable=self.completion_date_var).grid(row=6, column=1, sticky=tk.EW, padx=5, pady=0)

        ttk.Label(job_form_frame, text="Delivery Date:").grid(row=6, column=2, sticky=tk.W, pady=0, padx=5)
        ttk.Entry(job_form_frame, textvariable=self.delivery_date_var).grid(row=6, column=3, sticky=tk.EW, padx=5, pady=0)

        ttk.Label(job_form_frame, text="Remarks:").grid(row=7, column=0, sticky=tk.W, pady=0, padx=5)
        ttk.Entry(job_form_frame, textvariable=self.remarks_var).grid(row=7, column=1, columnspan=3, sticky=tk.EW, padx=5, pady=0)

        # Only show Assigned Staff for admin users
        if self.current_user_info and self.current_user_info.get('role') == 'admin':
            ttk.Label(job_form_frame, text="Assigned Staff:").grid(row=8, column=0, sticky=tk.W, pady=0, padx=5)
            self.assigned_staff_combobox = ttk.OptionMenu(job_form_frame, self.assigned_staff_var, "Unassigned", *self.staff_options)
            self.assigned_staff_combobox.grid(row=8, column=1, sticky=tk.EW, padx=5, pady=0)
        else:
            self.assigned_staff_combobox = None # Ensure it's None if not created


        # Job Action Buttons
        job_btn_frame = ttk.Frame(main_frame, padding=(10, 0))
        job_btn_frame.pack(fill=tk.X, pady=5)
        self.update_job_btn = ttk.Button(job_btn_frame, text="Update Job", command=self.update_job, state=tk.DISABLED)
        self.update_job_btn.pack(side=tk.LEFT, padx=5)

        # Only create delete button if user is admin
        if self.current_user_info and self.current_user_info.get('role') == 'admin':
            self.delete_job_btn = ttk.Button(job_btn_frame, text="Delete Job", command=self.delete_job, state=tk.DISABLED)
            self.delete_job_btn.pack(side=tk.LEFT, padx=5)
        else:
            self.delete_job_btn = None

        ttk.Button(job_btn_frame, text="Clear Form", command=self.clear_job_form).pack(side=tk.LEFT, padx=5)
        self.add_note_btn = ttk.Button(job_btn_frame, text="Add Note", command=self.add_job_note, state=tk.DISABLED)
        self.add_note_btn.pack(side=tk.LEFT, padx=5)

        # 🖨 Print Order Slip — available to all roles
        self.print_slip_btn = ttk.Button(job_btn_frame, text="🖨 Print Slip",
                                         command=self._print_order_slip, state=tk.DISABLED)
        self.print_slip_btn.pack(side=tk.LEFT, padx=5)

        # 📲 Notify Customer (WhatsApp/SMS) — available to all roles
        self.notify_btn = ttk.Button(job_btn_frame, text="📲 Notify Customer",
                                     command=self._notify_customer, state=tk.DISABLED)
        self.notify_btn.pack(side=tk.LEFT, padx=5)


        # Notes Section
        notes_frame = ttk.LabelFrame(main_frame, text="Job Notes", padding=(10,5))
        notes_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.notes_tree = ttk.Treeview(notes_frame, columns=("Timestamp", "User", "Note"), show="headings")
        self.notes_tree.heading("Timestamp", text="Timestamp")
        self.notes_tree.heading("User", text="User")
        self.notes_tree.heading("Note", text="Note")
        self.notes_tree.column("Timestamp", width=120, stretch=tk.NO)
        self.notes_tree.column("User", width=80, stretch=tk.NO)
        self.notes_tree.column("Note", width=300, stretch=tk.YES)
        self.notes_tree.pack(fill=tk.BOTH, expand=True)

        self.load_all_jobs() # Initial load of all jobs
        print(f"[{datetime.datetime.now()}] JobModule: create_job_ui finished.")

    def load_all_jobs(self):
        print(f"[{datetime.datetime.now()}] JobModule: load_all_jobs started.")
        for item in self.job_tree.get_children():
            self.job_tree.delete(item)
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            query = """
                SELECT j.id, c.name AS customer_name, c.mobile AS customer_mobile,
                        j.job_type, j.description, j.size, 
                        j.status, j.payment_status, j.start_date, j.delivery_date,
                        j.due_date, j.completion_date, j.notes AS remarks,
                        u.username AS assigned_staff_name
                FROM jobs j
                JOIN customers c ON j.customer_id = c.id
                LEFT JOIN users u ON j.assigned_staff_id = u.id
                ORDER BY j.start_date DESC
            """
            cur.execute(query)
            for row in cur.fetchall():
                self.job_tree.insert("", tk.END, values=(
                    row['id'],
                    row['customer_name'] or "",
                    row['customer_mobile'] or "",
                    row['job_type'] or "",
                    row['description'] or "",
                    row['size'] or "",
                    row['status'] or "",
                    row['payment_status'] or "",
                    row['start_date'] or "",
                    row['due_date'] or "",
                    row['completion_date'] or "",
                    row['delivery_date'] or "",
                    row['remarks'] or "",
                    row['assigned_staff_name'] or "Unassigned"
                ))
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to load all jobs: {e}")
            print(f"[{datetime.datetime.now()}] JobModule: Error loading all jobs: {e}")
        finally:
            if conn:
                conn.close()
        self.clear_job_form()
        print(f"[{datetime.datetime.now()}] JobModule: load_all_jobs finished.")

    def filter_jobs(self, event=None):
        print(f"[{datetime.datetime.now()}] JobModule: filter_jobs started.")
        search_term = self.search_entry.get().lower()
        status_filter = self.filter_status_var.get()

        for item in self.job_tree.get_children():
            self.job_tree.delete(item)
        
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            
            # Base query
            query = """
                SELECT j.id, c.name AS customer_name, c.mobile AS customer_mobile,
                        j.job_type, j.description, j.size, 
                        j.status, j.payment_status, j.start_date, j.delivery_date,
                        j.due_date, j.completion_date, j.notes AS remarks,
                        u.username AS assigned_staff_name
                FROM jobs j
                JOIN customers c ON j.customer_id = c.id
                LEFT JOIN users u ON j.assigned_staff_id = u.id
                WHERE (LOWER(c.name) LIKE ? OR c.mobile LIKE ? OR LOWER(j.description) LIKE ?)
            """
            params = (f"%{search_term}%", f"%{search_term}%", f"%{search_term}%")

            if status_filter != "All":
                query += " AND j.status = ?"
                params += (status_filter,)
            
            query += " ORDER BY j.start_date DESC"
            
            cur.execute(query, params)

            for row in cur.fetchall():
                self.job_tree.insert("", tk.END, values=(
                    row['id'],
                    row['customer_name'] or "",
                    row['customer_mobile'] or "",
                    row['job_type'] or "",
                    row['description'] or "",
                    row['size'] or "",
                    row['status'] or "",
                    row['payment_status'] or "",
                    row['start_date'] or "",
                    row['due_date'] or "",
                    row['completion_date'] or "",
                    row['delivery_date'] or "",
                    row['remarks'] or "",
                    row['assigned_staff_name'] or "Unassigned"
                ))
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to filter jobs: {e}")
            print(f"[{datetime.datetime.now()}] JobModule: Error filtering jobs: {e}")
        finally:
            if conn:
                conn.close()
        print(f"[{datetime.datetime.now()}] JobModule: filter_jobs finished.")

    def on_job_select(self, event):
        print(f"[{datetime.datetime.now()}] JobModule: on_job_select started.")
        selected_item = self.job_tree.selection()
        if selected_item:
            values = self.job_tree.item(selected_item, 'values')
            self.selected_job_id = values[0]
            
            conn = None
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                query = """
                    SELECT j.*, c.name AS customer_name, c.mobile AS customer_mobile, u.username AS assigned_staff_name
                    FROM jobs j
                    JOIN customers c ON j.customer_id = c.id
                    LEFT JOIN users u ON j.assigned_staff_id = u.id
                    WHERE j.id=?
                """
                cur.execute(query, (self.selected_job_id,))
                job_details = cur.fetchone()

                if job_details:
                    self.job_id_display.config(text=str(job_details['id']))
                    customer_name = job_details['customer_name'] if job_details['customer_name'] is not None else ""
                    customer_mobile = job_details['customer_mobile'] if job_details['customer_mobile'] is not None else ""
                    # Hide mobile number for sub_staff
                    if self.is_sub_staff:
                        self.customer_display.config(text=f"{customer_name}")
                    else:
                        self.customer_display.config(text=f"{customer_name} (Mob: {customer_mobile})")
                    
                    job_type_db = job_details['job_type'] if job_details['job_type'] is not None else ""
                    if job_type_db in self.all_job_type_options:
                        self.job_type_var.set(job_type_db)
                    else:
                        self.job_type_var.set("Other")

                    self.job_desc.set(job_details['description'] if job_details['description'] is not None else "")
                    self.job_size.set(job_details['size'] if job_details['size'] is not None else "") # Set size
                    # Removed financial variable setting
                    # self.initial_price.set(job_details['initial_price'] if job_details['initial_price'] is not None else 0.0)
                    # self.discount_amount.set(job_details['discount_amount'] if job_details['discount_amount'] is not None else 0.0)
                    # self.final_price.set(job_details['final_price'] if job_details['final_price'] is not None else 0.0)
                    # self.adv1.set(job_details['advance1'] if job_details['advance1'] is not None else 0.0)
                    # self.balance.set(job_details['balance'] if job_details['balance'] is not None else 0.0)
                    # self.rounded_off_amount.set(job_details['rounded_off_amount'] if job_details['rounded_off_amount'] is not None else 0.0)
                    # self.payment_mode.set(job_details['payment_mode'] if job_details['payment_mode'] is not None else "Cash")
                    self.job_status_var.set(job_details['status'] if job_details['status'] is not None else "Pending")
                    self.payment_status_var.set(job_details['payment_status'] if job_details['payment_status'] is not None else "Unpaid")
                    self.start_date_var.set(job_details['start_date'] if job_details['start_date'] is not None else "")
                    self.due_date_var.set(job_details['due_date'] if job_details['due_date'] is not None else "") # Set due_date
                    self.completion_date_var.set(job_details['completion_date'] if job_details['completion_date'] is not None else "") # Set completion_date
                    self.delivery_date_var.set(job_details['delivery_date'] if job_details['delivery_date'] is not None else "")
                    self.remarks_var.set(job_details['notes'] if job_details['notes'] is not None else "") # Set remarks from 'notes' column
                    self.assigned_staff_var.set(job_details['assigned_staff_name'] if job_details['assigned_staff_name'] is not None else "Unassigned")

                    self.update_job_btn.config(state=tk.NORMAL)
                    if self.delete_job_btn:
                        self.delete_job_btn.config(state=tk.NORMAL)
                    self.add_note_btn.config(state=tk.NORMAL)
                    self.print_slip_btn.config(state=tk.NORMAL)
                    self.notify_btn.config(state=tk.NORMAL)

                    self.load_job_notes(self.selected_job_id) # Load notes for the selected job
                else:
                    print(f"[{datetime.datetime.now()}] JobModule: No job details found for ID {self.selected_job_id}.")
                    self.clear_job_form()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to select job: {e}")
                print(f"[{datetime.datetime.now()}] JobModule: Error in on_job_select: {e}")
                self.clear_job_form()
            finally:
                if conn:
                    conn.close()
        else:
            self.selected_job_id = None
            self.clear_job_form()
            self.update_job_btn.config(state=tk.DISABLED)
            if self.delete_job_btn:
                self.delete_job_btn.config(state=tk.DISABLED)
            self.add_note_btn.config(state=tk.DISABLED)
            self.print_slip_btn.config(state=tk.DISABLED)
            self.notify_btn.config(state=tk.DISABLED)
        print(f"[{datetime.datetime.now()}] JobModule: on_job_select finished.")

    def update_job(self):
        print(f"[{datetime.datetime.now()}] JobModule: update_job started.")
        if not self.selected_job_id:
            messagebox.showerror("Error", "No job selected to update.")
            return

        job_type = self.job_type_var.get().strip()
        if not job_type or job_type.startswith("--"):
            messagebox.showwarning("Input Error", "Please select a specific job type, not a category header.")
            return

        description = self.job_desc.get().strip()
        job_size = self.job_size.get().strip()
        # Removed financial variables
        # initial_price = self._get_numeric_value(self.initial_price)
        # discount = self._get_numeric_value(self.discount_amount)
        # final_price = self._get_numeric_value(self.final_price)
        # adv1 = self._get_numeric_value(self.adv1)
        # balance = self._get_numeric_value(self.balance)
        # rounded_off = self._get_numeric_value(self.rounded_off_amount)
        # payment_mode = self.payment_mode.get().strip()
        status = self.job_status_var.get().strip()
        payment_status = self.payment_status_var.get().strip()
        start_date = self.start_date_var.get().strip()
        due_date = self.due_date_var.get().strip()
        completion_date = self.completion_date_var.get().strip()
        delivery_date = self.delivery_date_var.get().strip()
        remarks = self.remarks_var.get().strip()
        assigned_staff_id = self._get_staff_id_from_username(self.assigned_staff_var.get())

        # Adjusted validation since final_price is removed
        if not description:
            messagebox.showerror("Input Error", "Description is required.")
            return

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("""
                UPDATE jobs SET
                    job_type=?, description=?, size=?, 
                    status=?, payment_status=?, start_date=?, delivery_date=?,
                    due_date=?, completion_date=?, notes=?, assigned_staff_id=?
                WHERE id=?
            """, (
                job_type, description, job_size, 
                status, payment_status, start_date, delivery_date,
                due_date, completion_date, remarks, assigned_staff_id, # remarks maps to 'notes' column
                self.selected_job_id
            ))
            conn.commit()
            log_activity(self.current_user_info.get('id'), self.current_user_info.get('username'),
                         "Job Updated", f"Updated job ID: {self.selected_job_id}")
            messagebox.showinfo("Success", "Job updated successfully!")
            self.load_all_jobs() # Reload all jobs to reflect changes
            self.clear_job_form()
            print(f"[{datetime.datetime.now()}] JobModule: Job updated successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update job: {e}")
            print(f"[{datetime.datetime.now()}] JobModule: Error updating job: {e}")
            if conn: conn.rollback()
        finally:
            if conn: conn.close()
        print(f"[{datetime.datetime.now()}] JobModule: update_job finished.")

    def delete_job(self):
        print(f"[{datetime.datetime.now()}] JobModule: delete_job started.")
        if not self.selected_job_id:
            messagebox.showerror("Error", "No job selected to delete.")
            return

        # Admin check (already handled by button visibility, but good to have server-side check too)
        if not (self.current_user_info and self.current_user_info.get('role') == 'admin'):
            messagebox.showerror("Permission Denied", "Only administrators can delete jobs.")
            print(f"[{datetime.datetime.now()}] JobModule: Delete job prevented: User is not admin.")
            return

        confirm = messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this job and all its associated payments and notes? This action cannot be undone.")
        if confirm:
            conn = None
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                
                # Delete associated notes first
                cur.execute("DELETE FROM notes WHERE related_id=? AND related_to='job'", (self.selected_job_id,)) # Corrected to use related_to and related_id
                print(f"[{datetime.datetime.now()}] JobModule: Deleted notes for job {self.selected_job_id}.")

                # Delete associated payments
                cur.execute("DELETE FROM payments WHERE job_id=?", (self.selected_job_id,))
                print(f"[{datetime.datetime.now()}] JobModule: Deleted payments for job {self.selected_job_id}.")

                # Delete the job itself
                cur.execute("DELETE FROM jobs WHERE id=?", (self.selected_job_id,))
                conn.commit()
                log_activity(self.current_user_info.get('id'), self.current_user_info.get('username'),
                             "Job Deleted", f"Deleted job ID: {self.selected_job_id}")
                messagebox.showinfo("Success", "Job and all associated data deleted successfully.")
                self.load_all_jobs() # Reload jobs
                self.clear_job_form()
                print(f"[{datetime.datetime.now()}] JobModule: Job deleted successfully.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete job: {e}")
                print(f"[{datetime.datetime.now()}] JobModule: Error deleting job: {e}")
                if conn: conn.rollback()
            finally:
                if conn: conn.close()
        else:
            print(f"[{datetime.datetime.now()}] JobModule: Job deletion cancelled.")
        print(f"[{datetime.datetime.now()}] JobModule: delete_job finished.")


    def clear_job_form(self):
        print(f"[{datetime.datetime.now()}] JobModule: clear_job_form called.")
        self.selected_job_id = None
        self.job_id_display.config(text="N/A")
        self.customer_display.config(text="N/A")
        self.job_type_var.set("Other")
        self.job_desc.set("")
        self.job_size.set("") # Clear size
        # Removed financial variable clearing
        # self.initial_price.set(0.0)
        # self.discount_amount.set(0.0)
        # self.final_price.set(0.0)
        # self.adv1.set(0.0)
        # self.balance.set(0.0)
        # self.rounded_off_amount.set(0.0)
        # self.payment_mode.set("Cash")
        self.job_status_var.set("Pending")
        self.payment_status_var.set("Unpaid")
        self.start_date_var.set(datetime.date.today().isoformat())
        self.due_date_var.set("") # Clear due_date
        self.completion_date_var.set("") # Clear completion_date
        self.delivery_date_var.set("")
        self.remarks_var.set("") # Clear remarks
        self.assigned_staff_var.set("Unassigned") # Clear assigned staff

        self.update_job_btn.config(state=tk.DISABLED)
        if self.delete_job_btn:
            self.delete_job_btn.config(state=tk.DISABLED)
        self.add_note_btn.config(state=tk.DISABLED)
        self.print_slip_btn.config(state=tk.DISABLED)
        self.notify_btn.config(state=tk.DISABLED)
        
        # Clear notes treeview
        for item in self.notes_tree.get_children():
            self.notes_tree.delete(item)
        print(f"[{datetime.datetime.now()}] JobModule: clear_job_form finished.")

    def _print_order_slip(self):
        """Generate and open the PDF order slip for the selected job."""
        if not self.selected_job_id:
            messagebox.showwarning("No Job", "Please select a job first.")
            return
        open_order_slip(int(self.selected_job_id), parent_window=self.parent_frame)

    def _notify_customer(self):
        """Open WhatsApp/SMS notification dialog for the selected job."""
        if not self.selected_job_id:
            messagebox.showwarning("No Job", "Please select a job first.")
            return
        WhatsAppSMSDialog(self.parent_frame, int(self.selected_job_id), self.current_user_info)

    def add_job_note(self):
        print(f"[{datetime.datetime.now()}] JobModule: add_job_note started.")
        if not self.selected_job_id:
            messagebox.showwarning("Error", "Please select a job to add a note.")
            return

        note_text = simpledialog.askstring("Add Job Note", "Enter your note for this job:")
        if note_text:
            user_id = self.current_user_info.get('id')
# username = self.current_user_info.get('username')
            # The add_job_note in db_manager expects (job_id, note_text, user_id)
            # You were passing username as the 3rd argument, but db_manager expects user_id
            if add_job_note(self.selected_job_id, note_text, user_id): # Corrected arguments
                messagebox.showinfo("Success", "Note added successfully!")
                self.load_job_notes(self.selected_job_id) # Reload notes for the current job
            else:
                messagebox.showerror("Error", "Failed to add note.")
        print(f"[{datetime.datetime.now()}] JobModule: add_job_note finished.")

    def load_job_notes(self, job_id):
        print(f"[{datetime.datetime.now()}] JobModule: load_job_notes started for job ID: {job_id}.")
        for item in self.notes_tree.get_children():
            self.notes_tree.delete(item)
        
        notes = get_job_notes(job_id) # Call the function from db_manager
        if notes:
            for note in notes:
                self.notes_tree.insert("", tk.END, values=(
                    note['timestamp'],
                    note['username'],
                    note['note_text']
                ))
            print(f"[{datetime.datetime.now()}] JobModule: Loaded {len(notes)} notes for job {job_id}.")
        else:
            self.notes_tree.insert("", tk.END, values=("No notes recorded for this job.", "", ""))
            print(f"[{datetime.datetime.now()}] JobModule: No notes found for job {job_id}.")
        print(f"[{datetime.datetime.now()}] JobModule: load_job_notes finished.")

