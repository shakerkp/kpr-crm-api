# -*- coding: utf-8 -*-
# Patched & consolidated on 2025-08-30 (IST)
# Notes:
# - Ensures advance payments are recorded into `payments` at job creation.
# - Ensures balance/status update via `update_job_payment_status` after any payment.
# - Keeps your original structure and methods intact.

import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont # Import for custom fonts
# Import necessary functions from db_manager, including the new one for job types
from db_manager import get_db_connection, log_activity, get_payments_for_customer, get_all_job_types_structured, get_staff_users, add_notification
import datetime
from decimal import Decimal # Decimal ఇంపోర్ట్ చేయండి

class JobPaymentModule:
    def __init__(self, parent_frame, current_user_info):
        print(f"[{datetime.datetime.now()}] JobPaymentModule: __init__ started.")
        self.parent_frame = parent_frame
        self.current_user_info = current_user_info
        self.selected_customer_id = None # This will be set internally now
        self.selected_customer_name = ""
        self.selected_customer_mobile = ""
        self.selected_job_id = None
        self.delete_job_btn = None # Initialize to None, will be set in create_ui if admin

        # Job type definitions - NOW LOADED DYNAMICALLY FROM DB
        self.job_types = self._load_job_types_from_db()
        self.all_job_type_options = self._get_flat_job_type_list()

        # Job variables
        self.job_type_var = tk.StringVar(value="Other")
        self.job_desc = tk.StringVar()

        # Financial variables - these will be displayed and editable for NEW jobs, read-only for existing jobs
        self.initial_price = tk.DoubleVar(value=0.0)
        self.discount_amount = tk.DoubleVar(value=0.0)
        self.final_price = tk.DoubleVar(value=0.0)
        self.before_gst = tk.DoubleVar(value=0.0)  # NEW: Before GST (treated as final_price)
        self.after_gst = tk.DoubleVar(value=0.0)   # NEW: After GST / Grand Total
        self.adv1 = tk.DoubleVar(value=0.0)
        self.balance = tk.DoubleVar(value=0.0)
        self.payment_mode = tk.StringVar(value="Cash") # For job form
        self.job_status_var = tk.StringVar(value="Pending")
        self.payment_status_var = tk.StringVar(value="Unpaid")
        self.start_date_var = tk.StringVar(value=datetime.date.today().isoformat())
        self.due_date_var = tk.StringVar() # New for due date
        self.completion_date_var = tk.StringVar() # New for completion date
        self.delivery_date_var = tk.StringVar()
        self.remarks_var = tk.StringVar() # New for remarks
        self.assigned_staff_var = tk.StringVar() # NEW: For assigned staff

        # GST variables
        self.gst_type_var = tk.StringVar(value="None") # Default to None
        self.gst_category_var = tk.StringVar(value="")
        self.gst_percentage_var = tk.DoubleVar(value=0.0)
        self.gst_amount_var = tk.DoubleVar(value=0.0) # To store calculated GST amount
        self.customer_gst_no_display_var = tk.StringVar(value="N/A") # To display selected customer's GSTN

        # Dictionaries to map staff names to IDs and vice versa
        self.staff_map = {} # name -> id
        self.staff_id_to_name = {} # id -> name

        # Payment variables (for the integrated payment form)
        self.payment_amount_var = tk.DoubleVar(value=0.0)
        self.payment_mode_for_new_payment_var = tk.StringVar(value="Cash") # For new payment form
        self.payment_notes_var = tk.StringVar()
        self.payment_job_id_var = tk.StringVar() # To link payment to a specific job from dropdown

        # Search variable for customer selection within this module
        self.customer_search_term_var = tk.StringVar()
        self.customer_search_results = [] # To store customer search results

        self.create_ui()

        # Trace changes to financial and GST variables for auto-calculation
        self.initial_price.trace_add("write", self._calculate_financials)
        self.discount_amount.trace_add("write", self._calculate_financials)
        self.adv1.trace_add("write", self._calculate_financials)
        self.gst_type_var.trace_add("write", self._calculate_financials)
        self.gst_percentage_var.trace_add("write", self._calculate_financials)
        
        # Trace search term changes for customer search
        self.customer_search_term_var.trace_add("write", self._filter_customers_for_selection)

        print(f"[{datetime.datetime.now()}] JobPaymentModule: __init__ finished.")

    def _load_job_types_from_db(self):
        """Loads job categories and subtypes from the database."""
        print(f"[{datetime.datetime.now()}] JobPaymentModule: Loading job types from DB.")
        return get_all_job_types_structured()

    def _get_flat_job_type_list(self):
        print(f"[{datetime.datetime.now()}] JobPaymentModule: _get_flat_job_type_list called.")
        flat_list = []
        # Ensure "Other" is always at the end if it exists, otherwise add it.
        # Create a sorted list of categories, putting "Other" last if present.
        categories_sorted = sorted([cat for cat in self.job_types.keys() if cat != "Other"])
        if "Other" in self.job_types:
            categories_sorted.append("Other") # Ensure "Other" is always last

        for category in categories_sorted:
            flat_list.append(f"-- {category} --")
            # Sort subtypes alphabetically
            for item in sorted(self.job_types[category]):
                flat_list.append(item)
        return flat_list

    def create_ui(self):
        print(f"[{datetime.datetime.now()}] JobPaymentModule: create_ui started.")
        # REMOVED: for widget in self.parent_frame.winfo_children(): widget.destroy()
        # The responsibility of destroying/clearing the parent frame should be with the calling application.

        self.main_frame = ttk.Frame(self.parent_frame)
        self.main_frame.pack(fill=tk.BOTH, expand=True)

        # Changed font size for the headline and reduced pady
        ttk.Label(self.main_frame, text="Jobs & Payments Management", font=("Arial", 11, "bold")).pack(pady=5)

        # --- Customer Selection Section (New) ---
        customer_selection_frame = ttk.LabelFrame(self.main_frame, text="Select Customer", padding="5") # Reduced padding
        customer_selection_frame.pack(fill=tk.X, padx=10, pady=2) # Reduced pady

        # Customer Search Bar (now above the treeview)
        ttk.Label(customer_selection_frame, text="Search for Customer (Name/Mobile/Email/Tags):").pack(pady=1, padx=5, anchor=tk.W) # Reduced pady
        self.customer_search_entry = ttk.Entry(customer_selection_frame, textvariable=self.customer_search_term_var)
        self.customer_search_entry.pack(fill=tk.X, expand=True, padx=5, pady=1) # Reduced pady

        # Changed height from 3 to 2 to reduce vertical space further
        self.customer_selection_tree = ttk.Treeview(customer_selection_frame, columns=("ID", "Name", "Mobile", "Email", "GST No"), show="headings", height=2)
        self.customer_selection_tree.heading("ID", text="ID")
        self.customer_selection_tree.heading("Name", text="Name")
        self.customer_selection_tree.heading("Mobile", text="Mobile")
        self.customer_selection_tree.heading("Email", text="Email")
        self.customer_selection_tree.heading("GST No", text="GST No") # New column heading
        self.customer_selection_tree.column("ID", width=40, stretch=tk.NO)
        self.customer_selection_tree.column("Name", width=120, stretch=tk.YES)
        self.customer_selection_tree.column("Mobile", width=100, stretch=tk.NO)
        self.customer_selection_tree.column("Email", width=150, stretch=tk.YES)
        self.customer_selection_tree.column("GST No", width=100, stretch=tk.NO) # New column width
        self.customer_selection_tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=2) # Reduced pady
        # Bind double-click to select customer
        self.customer_selection_tree.bind("<<TreeviewSelect>>", self._on_customer_selection_in_tree)
        self.customer_selection_tree.bind("<Double-1>", self._on_customer_double_click_in_tree)


        customer_selection_buttons_frame = ttk.Frame(customer_selection_frame)
        customer_selection_buttons_frame.pack(pady=2) # Reduced pady
        self.select_customer_btn = ttk.Button(customer_selection_buttons_frame, text="Select Customer", command=self._select_customer_for_module, state=tk.DISABLED)
        self.select_customer_btn.pack(side=tk.LEFT, padx=5)
        self.clear_customer_selection_btn = ttk.Button(customer_selection_buttons_frame, text="Clear Customer Selection", command=self._clear_customer_selection, state=tk.DISABLED)
        self.clear_customer_selection_btn.pack(side=tk.LEFT, padx=5)

        # Display selected customer info at the top of the Jobs/Payments section
        selected_customer_info_frame = ttk.Frame(self.main_frame)
        selected_customer_info_frame.pack(pady=2, fill=tk.X, padx=10)

        self.selected_customer_display_label = ttk.Label(selected_customer_info_frame, text="No Customer Selected for Jobs/Payments", font=("Arial", 11, "bold"), foreground="blue") # Reduced font size
        self.selected_customer_display_label.pack(side=tk.LEFT, expand=True)

        # Customer GST No display
        ttk.Label(selected_customer_info_frame, text="Customer GSTIN:").pack(side=tk.LEFT, padx=(10, 5))
        self.customer_gst_no_label = ttk.Label(selected_customer_info_frame, textvariable=self.customer_gst_no_display_var, font=("Arial", 10, "italic"), foreground="darkgreen")
        self.customer_gst_no_label.pack(side=tk.LEFT, padx=5)


        # Create a Notebook (tabbed interface) for Jobs and Payments
        self.customer_history_notebook = ttk.Notebook(self.main_frame)
        self.customer_history_notebook.pack(fill=tk.BOTH, expand=True)

        # --- Tab 1: Jobs for Customer ---
        self.jobs_tab = ttk.Frame(self.customer_history_notebook, padding="5") # Reduced padding
        self.customer_history_notebook.add(self.jobs_tab, text="Jobs")

        # Job Buttons (moved to the top of the tab for visibility)
        add_job_button_container = ttk.Frame(self.jobs_tab)
        add_job_button_container.pack(pady=5, fill=tk.X, expand=True) # Reduced pady
        self.add_job_btn = ttk.Button(add_job_button_container, text="Add New Job", command=self.add_job, state=tk.DISABLED)
        self.add_job_btn.pack(side=tk.LEFT, expand=True, padx=5)

        self.update_job_btn = ttk.Button(add_job_button_container, text="Update Job", command=self.update_job, state=tk.DISABLED)
        self.update_job_btn.pack(side=tk.LEFT, expand=True, padx=5)
        
        # Only create and pack delete button for admin users
        if self.current_user_info and self.current_user_info.get('role') == 'admin':
            self.delete_job_btn = ttk.Button(add_job_button_container, text="Delete Job", command=self.delete_job, state=tk.DISABLED)
            self.delete_job_btn.pack(side=tk.LEFT, expand=True, padx=5)
        
        ttk.Button(add_job_button_container, text="Clear Job Form", command=self.clear_job_form).pack(side=tk.LEFT, expand=True, padx=5)

        # Job Input Fields (moved into jobs_tab)
        job_form_frame = ttk.LabelFrame(self.jobs_tab, text="Job Information", padding=(5, 2)) # Reduced padding
        job_form_frame.pack(fill=tk.X, padx=10, pady=2) # Reduced pady
        job_form_frame.columnconfigure(1, weight=1)
        job_form_frame.columnconfigure(3, weight=1)

        ttk.Label(job_form_frame, text="Job Type:").grid(row=1, column=0, sticky=tk.W, pady=1, padx=5) # Reduced pady
        self.job_type_combobox = ttk.Combobox(job_form_frame, textvariable=self.job_type_var, values=self.all_job_type_options, state="readonly")
        self.job_type_combobox.grid(row=1, column=1, columnspan=3, sticky=tk.EW, padx=5, pady=1) # Reduced pady

        ttk.Label(job_form_frame, text="Description:").grid(row=2, column=0, sticky=tk.W, pady=1, padx=5) # Reduced pady
        ttk.Entry(job_form_frame, textvariable=self.job_desc).grid(row=2, column=1, columnspan=3, sticky=tk.EW, padx=5, pady=1) # Reduced pady

        # Financial fields - state will be controlled by on_job_select and clear_job_form
        ttk.Label(job_form_frame, text="Initial Price (₹):").grid(row=3, column=0, sticky=tk.W, pady=1, padx=5) # Adjusted row
        self.initial_price_entry = ttk.Entry(job_form_frame, textvariable=self.initial_price, state='normal')
        self.initial_price_entry.grid(row=3, column=1, sticky=tk.EW, padx=5, pady=1) 
        # self.initial_price_entry.bind("<KeyRelease>", self._calculate_financials) # Bind KeyRelease - moved to __init__

        ttk.Label(job_form_frame, text="Discount (₹):").grid(row=3, column=2, sticky=tk.W, pady=1, padx=5) # Adjusted row
        self.discount_amount_entry = ttk.Entry(job_form_frame, textvariable=self.discount_amount, state='normal')
        self.discount_amount_entry.grid(row=3, column=3, sticky=tk.EW, padx=5, pady=1) 
        # self.discount_amount_entry.bind("<KeyRelease>", self._calculate_financials) # Bind KeyRelease - moved to __init__

        # Custom font for big and bold display
        big_bold_font = tkfont.Font(family="Arial", size=12, weight="bold")

        ttk.Label(job_form_frame, text="Before GST (₹):").grid(row=4, column=0, sticky=tk.W, pady=1, padx=5) # Adjusted row
        self.before_gst_label = ttk.Label(job_form_frame, textvariable=self.before_gst, font=big_bold_font, foreground="green")
        self.before_gst_label.grid(row=4, column=1, sticky=tk.EW, padx=5, pady=1)

        # AFTER GST (Grand Total) - big and colorful for easy identification
        ttk.Label(job_form_frame, text="After GST (Grand Total ₹):").grid(row=5, column=2, sticky=tk.W, pady=1, padx=5)
        self.after_gst_label = ttk.Label(job_form_frame, textvariable=self.after_gst, font=tkfont.Font(family="Arial", size=13, weight="bold"), foreground="darkblue")
        self.after_gst_label.grid(row=5, column=3, sticky=tk.EW, padx=5, pady=1)

        # Keep advance field on same rows (moved down)
        

        ttk.Label(job_form_frame, text="Advance 1 (₹):").grid(row=4, column=2, sticky=tk.W, pady=1, padx=5) # Adjusted row
        self.adv1_entry = ttk.Entry(job_form_frame, textvariable=self.adv1, state='normal')
        self.adv1_entry.grid(row=4, column=3, sticky=tk.EW, padx=5, pady=1) 
        # self.adv1_entry.bind("<KeyRelease>", self._calculate_financials) # Bind KeyRelease - moved to __init__
        
        ttk.Label(job_form_frame, text="Balance (₹):").grid(row=5, column=0, sticky=tk.W, pady=1, padx=5) # Adjusted row
        self.balance_label = ttk.Label(job_form_frame, textvariable=self.balance, font=big_bold_font, foreground="red")
        self.balance_label.grid(row=5, column=1, sticky=tk.EW, padx=5, pady=1) 

        # NEW: GST Details Frame (right side space)
        gst_details_frame = ttk.LabelFrame(job_form_frame, text="GST Details", padding=(5, 2))
        gst_details_frame.grid(row=6, column=0, columnspan=4, sticky=tk.EW, padx=5, pady=2)
        gst_details_frame.columnconfigure(1, weight=1)
        gst_details_frame.columnconfigure(3, weight=1)
        gst_details_frame.columnconfigure(5, weight=1) # For right side spacing

        ttk.Label(gst_details_frame, text="GST Type:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=1)
        gst_type_options = ["None", "Inclusive", "Exclusive"]
        self.gst_type_combobox = ttk.Combobox(gst_details_frame, textvariable=self.gst_type_var, values=gst_type_options, state="readonly", width=10)
        self.gst_type_combobox.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=1)
        # self.gst_type_combobox.bind("<<ComboboxSelected>>", self._calculate_financials) # Bind moved to __init__

        ttk.Label(gst_details_frame, text="Category:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=1)
        gst_category_options = ["CGST & SGST", "IGST"]
        self.gst_category_combobox = ttk.Combobox(gst_details_frame, textvariable=self.gst_category_var, values=gst_category_options, state="readonly", width=12)
        self.gst_category_combobox.grid(row=0, column=3, sticky=tk.EW, padx=5, pady=1)

        ttk.Label(gst_details_frame, text="GST %:").grid(row=0, column=4, sticky=tk.W, padx=5, pady=1)
        self.gst_percentage_entry = ttk.Entry(gst_details_frame, textvariable=self.gst_percentage_var, width=5)
        self.gst_percentage_entry.grid(row=0, column=5, sticky=tk.W, padx=5, pady=1)
        # self.gst_percentage_entry.bind("<KeyRelease>", self._calculate_financials) # Bind moved to __init__

        ttk.Label(gst_details_frame, text="GST Amount (₹):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=1)
        self.gst_amount_label = ttk.Label(gst_details_frame, textvariable=self.gst_amount_var, font=("Arial", 10, "italic"), foreground="blue")
        self.gst_amount_label.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=1)
        
        # Row for other job details (Status, Payment Mode, Dates, Remarks, Assigned To)
        current_row = 7 # Adjusted row for subsequent elements after GST frame

        ttk.Label(job_form_frame, text="Payment Mode:").grid(row=current_row, column=0, sticky=tk.W, pady=1, padx=5)
        self.payment_mode_option_menu_job_form = ttk.OptionMenu(job_form_frame, self.payment_mode, "Cash", "Cash", "Card", "UPI", "Bank Transfer")
        self.payment_mode_option_menu_job_form.grid(row=current_row, column=1, sticky=tk.EW, padx=5, pady=1)
        self.payment_mode_option_menu_job_form.config(state='normal') # Set to normal for new job

        ttk.Label(job_form_frame, text="Job Status:").grid(row=current_row, column=2, sticky=tk.W, pady=1, padx=5)
        job_status_options = ["Pending", "In Progress", "Completed", "Cancelled", "Delivered"] # Corrected order based on common flow
        self.job_status_option_menu = ttk.OptionMenu(job_form_frame, self.job_status_var, "Pending", *job_status_options)
        self.job_status_option_menu.grid(row=current_row, column=3, sticky=tk.EW, padx=5, pady=1)
        
        current_row += 1
        ttk.Label(job_form_frame, text="Payment Status:").grid(row=current_row, column=0, sticky=tk.W, pady=1, padx=5)
        self.payment_status_display_label = ttk.Entry(job_form_frame, textvariable=self.payment_status_var, state='readonly')
        self.payment_status_display_label.grid(row=current_row, column=1, sticky=tk.EW, padx=5, pady=1)

        # NEW: Assigned To Staff (visible only for admin)
        if self.current_user_info and self.current_user_info.get('role') in ('admin', 'staff', 'sub_staff', 'user'):
            ttk.Label(job_form_frame, text="Assigned To:").grid(row=current_row, column=2, sticky=tk.W, pady=1, padx=5)
            self.assigned_staff_combobox = ttk.Combobox(job_form_frame, textvariable=self.assigned_staff_var, state="readonly")
            self.assigned_staff_combobox.grid(row=current_row, column=3, sticky=tk.EW, padx=5, pady=1)
            current_row_for_dates = current_row + 1 # Adjust row for subsequent elements
        else:
            self.assigned_staff_combobox = None # Explicitly set to None if not admin
            current_row_for_dates = current_row + 1 # If no assigned to, dates remain at next row

        ttk.Label(job_form_frame, text="Start Date:").grid(row=current_row_for_dates, column=0, sticky=tk.W, pady=1, padx=5)
        ttk.Entry(job_form_frame, textvariable=self.start_date_var).grid(row=current_row_for_dates, column=1, sticky=tk.EW, padx=5, pady=1)

        ttk.Label(job_form_frame, text="Due Date:").grid(row=current_row_for_dates, column=2, sticky=tk.W, pady=1, padx=5)
        ttk.Entry(job_form_frame, textvariable=self.due_date_var).grid(row=current_row_for_dates, column=3, sticky=tk.EW, padx=5, pady=1)

        current_row_for_dates += 1
        ttk.Label(job_form_frame, text="Completion Date:").grid(row=current_row_for_dates, column=0, sticky=tk.W, pady=1, padx=5)
        ttk.Entry(job_form_frame, textvariable=self.completion_date_var).grid(row=current_row_for_dates, column=1, sticky=tk.EW, padx=5, pady=1)

        ttk.Label(job_form_frame, text="Delivery Date:").grid(row=current_row_for_dates, column=2, sticky=tk.W, pady=1, padx=5)
        ttk.Entry(job_form_frame, textvariable=self.delivery_date_var).grid(row=current_row_for_dates, column=3, sticky=tk.EW, padx=5, pady=1)

        current_row_for_dates += 1
        ttk.Label(job_form_frame, text="Remarks:").grid(row=current_row_for_dates, column=0, sticky=tk.W, pady=1, padx=5)
        ttk.Entry(job_form_frame, textvariable=self.remarks_var).grid(row=current_row_for_dates, column=1, columnspan=3, sticky=tk.EW, padx=5, pady=1)

        # Updated job_tree columns - 'Size' column removed, added GST columns
        self.job_tree = ttk.Treeview(self.jobs_tab, columns=("ID", "Job Type", "Description", "Start Date", "Due Date", "Completion Date", "Delivery Date", "Status", "Before GST", "After GST (Grand Total)", "Balance", "Payment Status", "Assigned To", "Remarks", "GST Type", "GST Category", "GST %", "GST Amount"), show="headings")

        self.job_tree.heading("ID", text="ID")
        self.job_tree.heading("Job Type", text="Job Type")
        self.job_tree.heading("Description", text="Description")
        self.job_tree.heading("Start Date", text="Start Date")
        self.job_tree.heading("Due Date", text="Due Date")
        self.job_tree.heading("Completion Date", text="Completion Date")
        self.job_tree.heading("Delivery Date", text="Delivery Date")
        self.job_tree.heading("Status", text="Status")
        self.job_tree.heading("Before GST", text="Before GST")
        self.job_tree.heading("After GST (Grand Total)", text="After GST (Grand Total)")
        self.job_tree.heading("Balance", text="Balance")
        self.job_tree.heading("Payment Status", text="Payment Status")
        self.job_tree.heading("Assigned To", text="Assigned To")
        self.job_tree.heading("Remarks", text="Remarks")
        self.job_tree.heading("GST Type", text="GST Type") # New heading
        self.job_tree.heading("GST Category", text="GST Category") # New heading
        self.job_tree.heading("GST %", text="GST %") # New heading
        self.job_tree.heading("GST Amount", text="GST Amount") # New heading

        self.job_tree.column("ID", width=30, stretch=tk.NO)
        self.job_tree.column("Job Type", width=80, stretch=tk.YES)
        self.job_tree.column("Description", width=150, stretch=tk.YES)
        self.job_tree.column("Start Date", width=90, stretch=tk.NO)
        self.job_tree.column("Due Date", width=90, stretch=tk.NO)
        self.job_tree.column("Completion Date", width=90, stretch=tk.NO)
        self.job_tree.column("Delivery Date", width=90, stretch=tk.NO)
        self.job_tree.column("Status", width=70, stretch=tk.NO)
        self.job_tree.column("Before GST", width=70, stretch=tk.NO, anchor=tk.E)
        self.job_tree.column("After GST (Grand Total)", width=90, stretch=tk.NO, anchor=tk.E)
        self.job_tree.column("Balance", width=70, stretch=tk.NO, anchor=tk.E)
        self.job_tree.column("Payment Status", width=80, stretch=tk.NO)
        self.job_tree.column("Assigned To", width=80, stretch=tk.NO)
        self.job_tree.column("Remarks", width=100, stretch=tk.YES)
        self.job_tree.column("GST Type", width=60, stretch=tk.NO) # New column width
        self.job_tree.column("GST Category", width=80, stretch=tk.NO) # New column width
        self.job_tree.column("GST %", width=50, stretch=tk.NO, anchor=tk.E) # New column width
        self.job_tree.column("GST Amount", width=70, stretch=tk.NO, anchor=tk.E) # New column width

        self.job_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=2)
        # We will bind this after loading data to prevent initial unwanted triggers
        # self.job_tree.bind("<<TreeviewSelect>>", self.on_job_select) 
        self.job_tree.bind("<Double-1>", self._on_job_double_click)


        # --- Tab 2: Payments for Customer ---
        self.payments_tab = ttk.Frame(self.customer_history_notebook, padding="5")
        self.customer_history_notebook.add(self.payments_tab, text="Payments")

        ttk.Label(self.payments_tab, text="Record Payment", font=("Arial", 12, "bold")).pack(pady=5)

        # Integrated Payment Form
        payment_form_frame = ttk.LabelFrame(self.payments_tab, text="Payment Information", padding="5")
        payment_form_frame.pack(fill=tk.X, padx=10, pady=2)
        payment_form_frame.columnconfigure(1, weight=1)
        payment_form_frame.columnconfigure(3, weight=1)

        ttk.Label(payment_form_frame, text="Payment Amount (₹):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=1)
        self.payment_amount_entry = ttk.Entry(payment_form_frame, textvariable=self.payment_amount_var)
        self.payment_amount_entry.grid(row=0, column=1, sticky=tk.EW, padx=5, pady=1)
        self.payment_amount_entry.bind("<KeyRelease>", self._validate_payment_amount)

        ttk.Label(payment_form_frame, text="Payment Mode:").grid(row=0, column=2, sticky=tk.W, padx=5, pady=1)
        ttk.OptionMenu(payment_form_frame, self.payment_mode_for_new_payment_var, "Cash", "Cash", "Card", "UPI", "Bank Transfer").grid(row=0, column=3, sticky=tk.EW, padx=5, pady=1)

        ttk.Label(payment_form_frame, text="Link to Job ID (Optional):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=1)
        self.payment_job_id_combobox = ttk.Combobox(payment_form_frame, textvariable=self.payment_job_id_var, state="readonly")
        self.payment_job_id_combobox.grid(row=1, column=1, sticky=tk.EW, padx=5, pady=1)
        self.payment_job_id_combobox.bind("<<ComboboxSelected>>", self._on_payment_job_select)

        ttk.Label(payment_form_frame, text="Notes:").grid(row=1, column=2, sticky=tk.W, padx=5, pady=1)
        ttk.Entry(payment_form_frame, textvariable=self.payment_notes_var).grid(row=1, column=3, sticky=tk.EW, padx=5, pady=1)

        self.add_payment_btn = ttk.Button(payment_form_frame, text="Record Payment", command=self.add_payment, state=tk.DISABLED)
        self.add_payment_btn.grid(row=2, column=0, columnspan=4, pady=2)

        ttk.Label(self.payments_tab, text="Payment History for Selected Customer", font=("Arial", 11, "bold")).pack(pady=2)
        # UPDATED: Added 'Invoice ID' column
        self.payment_history_tree = ttk.Treeview(self.payments_tab, columns=("ID", "Job ID", "Invoice ID", "Amount", "Date", "Mode", "Notes"), show="headings", height=10)
        self.payment_history_tree.heading("ID", text="ID")
        self.payment_history_tree.heading("Job ID", text="జాబ్ ID") # Telugu translation
        self.payment_history_tree.heading("Invoice ID", text="ఇన్వాయిస్ ID") # Telugu translation
        self.payment_history_tree.heading("Amount", text="మొత్తం") # Telugu translation
        self.payment_history_tree.heading("Date", text="తేదీ") # Telugu translation
        self.payment_history_tree.heading("Mode", text="విధానం") # Telugu translation
        self.payment_history_tree.heading("Notes", text="గమనికలు") # Telugu translation
        self.payment_history_tree.column("ID", width=30, stretch=tk.NO)
        self.payment_history_tree.column("Job ID", width=60, stretch=tk.NO, anchor=tk.CENTER) # Adjusted width
        self.payment_history_tree.column("Invoice ID", width=70, stretch=tk.NO, anchor=tk.CENTER) # New column width
        self.payment_history_tree.column("Amount", width=80, stretch=tk.NO, anchor=tk.E)
        self.payment_history_tree.column("Date", width=120, stretch=tk.NO)
        self.payment_history_tree.column("Mode", width=80, stretch=tk.NO)
        self.payment_history_tree.column("Notes", width=150, stretch=tk.YES)
        self.payment_history_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=2)
        
        self._load_all_customers_for_selection()
        self.set_customer_context(None, None, None, None) # Pass None for GST No initially
        self._load_staff_members()
        print(f"[{datetime.datetime.now()}] JobPaymentModule: create_ui finished.")


    def _load_staff_members(self):
        """Loads staff members into the combobox and internal maps."""
        print(f"[{datetime.datetime.now()}] JobPaymentModule: _load_staff_members started.")
        self.staff_map = {}
        self.staff_id_to_name = {}
        staff_users = get_staff_users() # Call the function from db_manager
        staff_names = ["-- Select Staff --"] # Default option
        for user in staff_users:
            self.staff_map[user['username']] = user['id']
            self.staff_id_to_name[user['id']] = user['username']
            staff_names.append(user['username'])

        if self.assigned_staff_combobox: # Only update if the widget exists (i.e., if admin)
            self.assigned_staff_combobox['values'] = staff_names
            self.assigned_staff_var.set(staff_names[0]) # Set default selection
        print(f"[{datetime.datetime.now()}] JobPaymentModule: Loaded staff members: {staff_names}.")


    def _load_all_customers_for_selection(self):
        """Loads all customers into the customer_selection_tree."""
        print(f"[{datetime.datetime.now()}] JobPaymentModule: _load_all_customers_for_selection started.")
        for item in self.customer_selection_tree.get_children():
            self.customer_selection_tree.delete(item)
        self.customer_search_results = [] # Clear previous results
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            # Assuming 'gst_no' column exists in 'customers' table
            cur.execute("SELECT id, name, mobile, email, tags, gst_no FROM customers ORDER BY name")
            for row in cur.fetchall():
                self.customer_search_results.append(row) # Store full rows for filtering
                self.customer_selection_tree.insert("", tk.END, values=(
                    row['id'],
                    row['name'] if row['name'] is not None else "",
                    row['mobile'] if row['mobile'] is not None else "",
                    row['email'] if row['email'] is not None else "",
                    row['gst_no'] if row['gst_no'] is not None else "" # New: GST No
                ))
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to select customers: {e}")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Error loading customers for selection: {e}")
        finally:
            if conn:
                conn.close()
        print(f"[{datetime.datetime.now()}] JobPaymentModule: _load_all_customers_for_selection finished.")

    def _filter_customers_for_selection(self, *args):
        """Filters customers in the customer_selection_tree based on search term."""
        print(f"[{datetime.datetime.now()}] JobPaymentModule: _filter_customers_for_selection called with term: {self.customer_search_term_var.get()}.")
        search_term = self.customer_search_term_var.get().lower()
        for item in self.customer_selection_tree.get_children():
            self.customer_selection_tree.delete(item)
        
        filtered_customers = []
        for customer in self.customer_search_results:
            name = customer['name'].lower() if customer['name'] else ""
            mobile = customer['mobile'].lower() if customer['mobile'] else ""
            email = customer['email'].lower() if customer['email'] else ""
            tags = customer['tags'].lower() if customer['tags'] else ""
            gst_no = customer['gst_no'].lower() if customer['gst_no'] else "" # New: GST No

            if search_term in name or search_term in mobile or search_term in email or search_term in tags or search_term in gst_no:
                filtered_customers.append(customer)
        
        for row in filtered_customers:
            self.customer_selection_tree.insert("", tk.END, values=(
                row['id'],
                row['name'] if row['name'] is not None else "",
                row['mobile'] if row['mobile'] is not None else "",
                row['email'] if row['email'] is not None else "",
                row['gst_no'] if row['gst_no'] is not None else "" # New: GST No
            ))
        
        # Disable select button if no item is selected or no results
        self.select_customer_btn.config(state=tk.DISABLED)
        self.clear_customer_selection_btn.config(state=tk.DISABLED)


    def _on_customer_selection_in_tree(self, event):
        """Enables/disables select button when a customer is selected in the customer_selection_tree."""
        selected_item = self.customer_selection_tree.selection()
        if selected_item:
            self.select_customer_btn.config(state=tk.NORMAL)
            self.clear_customer_selection_btn.config(state=tk.NORMAL)
        else:
            self.select_customer_btn.config(state=tk.DISABLED)
            self.clear_customer_selection_btn.config(state=tk.DISABLED)

    def _on_customer_double_click_in_tree(self, event):
        """Handles double-click on a customer in the selection tree."""
        selected_item = self.customer_selection_tree.selection()
        if selected_item:
            self._select_customer_for_module()

    def _select_customer_for_module(self):
        """Sets the selected customer from the customer_selection_tree as the active customer for the module."""
        selected_item = self.customer_selection_tree.selection()
        if selected_item:
            values = self.customer_selection_tree.item(selected_item, 'values')
            customer_id = values[0]
            customer_name = values[1]
            customer_mobile = values[2]
            customer_gst_no = values[4] # Get GST No from treeview values
            self.set_customer_context(customer_id, customer_name, customer_mobile, customer_gst_no)
            messagebox.showinfo("Customer Selected", f"Customer '{customer_name}' selected for jobs and payments.")
        else:
            messagebox.showwarning("No Customer Selected", "Please select a customer from the list.")

    def _clear_customer_selection(self):
        """Clears the customer selection and resets the module context."""
        self.customer_selection_tree.selection_remove(self.customer_selection_tree.selection())
        self.customer_search_term_var.set("") # Clear search bar
        self._load_all_customers_for_selection() # Reload all customers
        self.set_customer_context(None, None, None, None) # Pass None for GST No
        messagebox.showinfo("Selection Cleared", "Customer selection cleared. Please select a new customer.")


    def set_customer_context(self, customer_id, customer_name, customer_mobile, customer_gst_no=None):
        """
        Sets the context for which customer's jobs/payments are displayed.
        Controls the state of job and payment related input fields and buttons.
        """
        print(f"[{datetime.datetime.now()}] JobPaymentModule: Setting customer context to ID: {customer_id}, Name: {customer_name}.")
        self.selected_customer_id = customer_id
        self.selected_customer_name = customer_name
        self.selected_customer_mobile = customer_mobile
        self.customer_gst_no_display_var.set(customer_gst_no if customer_gst_no else "N/A")
        
        if customer_id:
            self.selected_customer_display_label.config(text=f"Selected Customer: {customer_name} (Mobile: {customer_mobile})")
            # Load data without a search term
            self.load_jobs_for_customer(customer_id)
            self.load_payments_for_customer(customer_id)
            self.populate_payment_job_id_combobox(customer_id)
            
            # Enable Add Job button when a customer is selected and no specific job is being edited
            self.add_job_btn.config(state=tk.NORMAL) 
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Add New Job button state set to NORMAL.")
            
            # The add_payment_btn state is also controlled by _validate_payment_amount based on amount > 0
            self.add_payment_btn.config(state=tk.NORMAL) 
        else:
            self.selected_customer_display_label.config(text="No Customer Selected for Jobs/Payments")
            self.customer_gst_no_display_var.set("N/A")
            # Temporarily unbind to prevent recursive calls when clearing
            self.job_tree.unbind("<<TreeviewSelect>>")
            self.job_tree.delete(*self.job_tree.get_children())
            self.job_tree.bind("<<TreeviewSelect>>", self.on_job_select) # Rebind

            self.payment_history_tree.delete(*self.payment_history_tree.get_children())
            self.populate_payment_job_id_combobox(None) # Clear job IDs for payment

            # Disable Add Job button when no customer is selected
            self.add_job_btn.config(state=tk.DISABLED) 
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Add New Job button state set to DISABLED.")

            self.clear_job_form()
            self.clear_payment_form()
            self.add_payment_btn.config(state=tk.DISABLED) # Disable add payment button


    def _get_numeric_value(self, tk_var):
        """Safely gets a float value from a Tkinter DoubleVar/StringVar, defaulting to 0.0 if invalid."""
        try:
            return Decimal(str(tk_var.get()))
        except (ValueError, tk.TclError):
            return Decimal('0.0')

    def _calculate_financials(self, *args):
        # This function is used for new job creation, where financial fields are editable.
        print(f"[{datetime.datetime.now()}] JobPaymentModule: _calculate_financials called.")
        try:
            initial_price = self._get_numeric_value(self.initial_price)
            discount = self._get_numeric_value(self.discount_amount)
            gst_percentage = self._get_numeric_value(self.gst_percentage_var)
            gst_type = self.gst_type_var.get()
            pass

            subtotal_before_gst = initial_price - discount
            gst_amount = Decimal('0.0')
            final_price_calculated = Decimal('0.0')

            if gst_type == "Exclusive":
                gst_amount = subtotal_before_gst * gst_percentage / Decimal('100.0')
                final_price_calculated = subtotal_before_gst + gst_amount
            elif gst_type == "Inclusive":
                # If initial price is inclusive, then final price is initial_price - discount
                # And GST amount is derived from this final price.
                final_price_calculated = subtotal_before_gst
                if gst_percentage > 0:
                    gst_amount = final_price_calculated - (final_price_calculated * Decimal('100.0') / (Decimal('100.0') + gst_percentage))
                else:
                    gst_amount = Decimal('0.0')
            else: # "None"
                final_price_calculated = subtotal_before_gst
                gst_amount = Decimal('0.0')
            
            adv1 = self._get_numeric_value(self.adv1)
            balance = final_price_calculated - adv1

            # Per request: treat BEFORE GST as the stored final_price (so set final_price = subtotal_before_gst)
            self.before_gst.set(f"{subtotal_before_gst:.2f}")
            self.final_price.set(f"{subtotal_before_gst:.2f}")  # stored value used in DB
            self.after_gst.set(f"{final_price_calculated:.2f}")  # grand total (before + gst)
            self.gst_amount_var.set(f"{gst_amount:.2f}")

            # Display balance relative to GRAND TOTAL (after gst)
            balance_display = final_price_calculated - adv1
            self.balance.set(f"{balance_display:.2f}")

            # Determine payment status based on calculated values
            if adv1 == Decimal('0.00'):
                self.payment_status_var.set("Unpaid")
            elif abs(balance) < Decimal('0.01'):  # Use a small tolerance for Decimal comparison
                self.payment_status_var.set("Paid")
            else:
                self.payment_status_var.set("Partially Paid")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Financials calculated. Payment Status: {self.payment_status_var.get()}")
        except Exception as e:
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Error in _calculate_financials: {e}")


    def _validate_payment_amount(self, *args):
        """Validates payment amount and enables/disables add payment button."""
        try:
            amount = float(self.payment_amount_var.get())
            if amount <= 0 or not self.selected_customer_id:
                self.add_payment_btn.config(state=tk.DISABLED)
                return
            # If a job is linked, ensure amount <= job due
            selected_job_text = self.payment_job_id_var.get().strip()
            job_id_for_payment = None
            if selected_job_text and " - " in selected_job_text:
                try:
                    job_id_for_payment = int(selected_job_text.split(" - ")[0])
                except ValueError:
                    job_id_for_payment = None
            conn = None
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                if job_id_for_payment:
                    cur.execute("SELECT COALESCE(final_price,0) + COALESCE(gst_amount,0) - COALESCE((SELECT SUM(amount) FROM payments p WHERE p.job_id = jobs.id),0) AS due FROM jobs WHERE id = ?", (job_id_for_payment,))
                    res = cur.fetchone()
                    due = float(res['due']) if res and res['due'] is not None else 0.0
                    if amount > due + 0.0001:
                        self.add_payment_btn.config(state=tk.DISABLED)
                        return
                else:
                    cur.execute("SELECT COALESCE(SUM(COALESCE(j.final_price,0) + COALESCE(j.gst_amount,0) - COALESCE((SELECT SUM(amount) FROM payments p WHERE p.job_id = j.id),0)),0) as total_due FROM jobs j WHERE j.customer_id = ?", (self.selected_customer_id,))
                    res = cur.fetchone()
                    total_due = float(res['total_due']) if res and res['total_due'] is not None else 0.0
                    if amount > total_due + 0.0001:
                        self.add_payment_btn.config(state=tk.DISABLED)
                        return
                # passed checks
                self.add_payment_btn.config(state=tk.NORMAL)
            except Exception:
                # if DB check fails, fall back to enabling based on amount > 0
                self.add_payment_btn.config(state=tk.NORMAL if amount > 0 else tk.DISABLED)
            finally:
                if conn: conn.close()
        except ValueError:
            self.add_payment_btn.config(state=tk.DISABLED)

    def _on_payment_job_select(self, event):
        """Called when a job ID is selected in the payment form combobox."""
        print(f"[{datetime.datetime.now()}] JobPaymentModule: Payment Job ID selected: {self.payment_job_id_var.get()}")
        # You can add logic here if you want to pre-fill amount based on job balance, etc.
        # For now, just a print statement.


    # --- Job Management Methods ---
    def load_jobs_for_customer(self, customer_id): # Removed search_term parameter
        print(f"[{datetime.datetime.now()}] JobPaymentModule: load_jobs_for_customer started for ID: {customer_id}.")
        
        # Temporarily unbind the TreeviewSelect event
        self.job_tree.unbind("<<TreeviewSelect>>")

        # Clear any existing selection BEFORE deleting items
        self.job_tree.selection_remove(self.job_tree.selection())

        for item in self.job_tree.get_children():
            self.job_tree.delete(item)
        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            # Fetch assigned_staff_id user's username
            # IMPORTANT: Ensure your 'jobs' table has 'gst_type', 'gst_category', 'gst_percentage', 'gst_amount' columns.
            query = """
                SELECT j.id, j.job_type, j.description, j.start_date, j.due_date, j.completion_date, j.delivery_date, j.status, j.final_price, 
                       -- compute dynamic balance from payments to avoid artificial zeroing when invoice flags change
                       (COALESCE(j.final_price,0) + COALESCE(j.gst_amount,0) - COALESCE((SELECT SUM(amount) FROM payments p WHERE p.job_id = j.id),0)) AS computed_after_gst_balance,
                       j.payment_status, u.username as assigned_staff_name, j.notes AS remarks, j.initial_price, j.discount_amount, j.advance1, j.payment_mode,
                       j.gst_type, j.gst_category, j.gst_percentage, j.gst_amount
                FROM jobs j
                LEFT JOIN users u ON j.assigned_staff_id = u.id
                WHERE j.customer_id=?
                ORDER BY j.start_date DESC
            """
            params = [customer_id]
            pass

            cur.execute(query, params)

            for row in cur.fetchall():
                # calculate before and after gst display values
                before_gst_val = Decimal(str(row['final_price'])) if row['final_price'] is not None else Decimal('0.00')
                after_gst_val = before_gst_val + (Decimal(str(row['gst_amount'])) if row['gst_amount'] is not None else Decimal('0.00'))
                balance_to_show = Decimal(str(row['computed_after_gst_balance'])) if row['computed_after_gst_balance'] is not None else (after_gst_val - (Decimal(str(row['advance1'])) if row['advance1'] is not None else Decimal('0.00')))

                self.job_tree.insert("", tk.END, values=(
                    row['id'],
                    row['job_type'] if row['job_type'] is not None else "",
                    row['description'] if row['description'] is not None else "",
                    row['start_date'] if row['start_date'] is not None else "",
                    row['due_date'] if row['due_date'] is not None else "",
                    row['completion_date'] if row['completion_date'] is not None else "",
                    row['delivery_date'] if row['delivery_date'] is not None else "",
                    row['status'] if row['status'] is not None else "",
                    f"{before_gst_val:.2f}",  # Before GST (stored final_price)
                    f"{after_gst_val:.2f}",   # After GST (Grand Total)
                    f"{balance_to_show:.2f}",  # Computed outstanding (after GST - payments)
                    row['payment_status'] if row['payment_status'] is not None else "",
                    row['assigned_staff_name'] if row['assigned_staff_name'] is not None else "N/A", # Display assigned staff username
                    row['remarks'] if row['remarks'] is not None else "",
                    row['gst_type'] if row['gst_type'] is not None else "None", # New: GST Type
                    row['gst_category'] if row['gst_category'] is not None else "", # New: GST Category
                    f"{Decimal(str(row['gst_percentage'])):.2f}" if row['gst_percentage'] is not None else "0.00", # New: GST %
                    f"{Decimal(str(row['gst_amount'])):.2f}" if row['gst_amount'] is not None else "0.00" # New: GST Amount
                ))
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to load jobs for customer {customer_id}: {e}")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Error loading jobs: {e}")
        finally:
            if conn:
                conn.close()
            # Rebind the TreeviewSelect event
            self.job_tree.bind("<<TreeviewSelect>>", self.on_job_select)
        
        # Call clear_job_form AFTER loading and rebinding
        self.clear_job_form() 
        print(f"[{datetime.datetime.now()}] JobPaymentModule: load_jobs_for_customer finished.")

    def on_job_select(self, event):
        print(f"[{datetime.datetime.now()}] JobPaymentModule: on_job_select started.")
        selected_item = self.job_tree.selection()
        if selected_item:
            # Access the first item in the selection tuple
            values = self.job_tree.item(selected_item[0], 'values')
            self.selected_job_id = values[0]
            
            conn = None
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                # Fetch all job details including new GST fields
                # IMPORTANT: Ensure your 'jobs' table has 'gst_type', 'gst_category', 'gst_percentage', 'gst_amount' columns.
                query = """
                    SELECT j.job_type, j.description, j.initial_price, j.discount_amount, j.final_price,
                           j.advance1, j.balance, j.payment_mode, j.status, j.start_date, j.delivery_date, j.payment_status, j.assigned_staff_id,
                           j.due_date, j.completion_date, j.notes AS remarks,
                           j.gst_type, j.gst_category, j.gst_percentage, j.gst_amount
                    FROM jobs j
                    WHERE j.id=? AND j.customer_id=?
                """
                cur.execute(query, (self.selected_job_id, self.selected_customer_id)) # Ensure job belongs to selected customer
                job_details = cur.fetchone()
                pass

                if job_details:
                    job_type_db = job_details['job_type'] if job_details['job_type'] is not None else ""
                    # Check if the job_type_db is a valid option in the dynamically loaded list
                    if job_type_db in self.all_job_type_options:
                        self.job_type_var.set(job_type_db)
                    else:
                        self.job_type_var.set("Other") # Fallback to "Other" if not found

                    self.job_desc.set(job_details['description'] if job_details['description'] is not None else "")
                    
                    # Set financial fields and make them read-only
                    self.initial_price.set(job_details['initial_price'] if job_details['initial_price'] is not None else 0.0)
                    self.initial_price_entry.config(state='readonly')

                    self.discount_amount.set(job_details['discount_amount'] if job_details['discount_amount'] is not None else 0.0)
                    self.discount_amount_entry.config(state='readonly')

                    self.final_price.set(job_details['final_price'] if job_details['final_price'] is not None else 0.0)
                    # self.final_price_entry.config(state='readonly') # Now a Label

                    self.adv1.set(job_details['advance1'] if job_details['advance1'] is not None else 0.0)
                    self.adv1_entry.config(state='readonly')

                    self.balance.set(job_details['balance'] if job_details['balance'] is not None else 0.0)
                    # self.balance_entry.config(state='readonly') # Now a Label

                    self.payment_mode.set(job_details['payment_mode'] if job_details['payment_mode'] is not None else "Cash")
                    self.payment_mode_option_menu_job_form.config(state='disabled') # Ensure it's disabled

                    self.payment_status_var.set(job_details['payment_status'] if job_details['payment_status'] is not None else "Unpaid")
                    self.payment_status_display_label.config(state='readonly') # Ensure it's disabled


                    self.job_status_var.set(job_details['status'] if job_details['status'] is not None else "Pending")
                    self.job_status_option_menu.config(state='normal') # Job Status can be updated
                    
                    self.start_date_var.set(job_details['start_date'] if job_details['start_date'] is not None else "")
                    self.due_date_var.set(job_details['due_date'] if job_details['due_date'] is not None else "")
                    self.completion_date_var.set(job_details['completion_date'] if job_details['completion_date'] is not None else "")
                    self.delivery_date_var.set(job_details['delivery_date'] if job_details['delivery_date'] is not None else "")
                    self.remarks_var.set(job_details['remarks'] if job_details['remarks'] is not None else "")
                    
                    # Set assigned staff combobox
                    assigned_staff_id = job_details['assigned_staff_id']
                    if self.assigned_staff_combobox: # Check if widget exists
                        if assigned_staff_id and assigned_staff_id in self.staff_id_to_name:
                            self.assigned_staff_var.set(self.staff_id_to_name[assigned_staff_id])
                        else:
                            self.assigned_staff_var.set("-- Select Staff --")

                    # Set GST fields and make them read-only
                    self.gst_type_var.set(job_details['gst_type'] if job_details['gst_type'] is not None else "None")
                    self.gst_type_combobox.config(state='readonly')
                    self.gst_category_var.set(job_details['gst_category'] if job_details['gst_category'] is not None else "")
                    self.gst_category_combobox.config(state='readonly')
                    self.gst_percentage_var.set(job_details['gst_percentage'] if job_details['gst_percentage'] is not None else 0.0)
                    self.gst_percentage_entry.config(state='readonly')
                    self.gst_amount_var.set(job_details['gst_amount'] if job_details['gst_amount'] is not None else 0.0) # Display calculated GST amount


                    # When a job is selected, disable "Add Job"
                    self.add_job_btn.config(state=tk.DISABLED)
                    print(f"[{datetime.datetime.now()}] JobPaymentModule: Add New Job button state set to DISABLED (job selected).")
                    self.update_job_btn.config(state=tk.NORMAL)
                    
                    # Only enable delete button if it exists and user is admin
                    if self.delete_job_btn:
                        delete_btn_state = tk.NORMAL if self.current_user_info and self.current_user_info.get('role') == 'admin' else tk.DISABLED
                        self.delete_job_btn.config(state=delete_btn_state)
                    
                else:
                    print(f"[{datetime.datetime.now()}] JobPaymentModule: No job details found for ID {self.selected_job_id} for selected customer.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to select job: {e}")
                print(f"[{datetime.datetime.now()}] JobPaymentModule: Error in on_job_select: {e}")
            finally:
                if conn:
                    conn.close()
        else: # No item selected in the treeview
            self.selected_job_id = None
            self.add_job_btn.config(state=tk.NORMAL if self.selected_customer_id else tk.DISABLED)
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Add New Job button state set to {'NORMAL' if self.selected_customer_id else 'DISABLED'} (no job selected).")
            self.update_job_btn.config(state=tk.DISABLED)
            
            # Disable delete button if no job is selected and it exists
            if self.delete_job_btn:
                self.delete_job_btn.config(state=tk.DISABLED)
            self.payment_job_id_var.set("") # Clear job ID in payment form - Keep this here
            
        print(f"[{datetime.datetime.now()}] JobPaymentModule: on_job_select finished.")

    def _on_job_double_click(self, event):
        """Handles double-click on a job in the job treeview."""
        selected_item = self.job_tree.selection()
        if selected_item:
            values = self.job_tree.item(selected_item[0], 'values')
            job_id = values[0]
            # After column changes, balance is now at index 10 (0-indexed)
            job_balance = values[10]

            # Set the selected job ID for the payment form
            # "ID - Description"
            self.payment_job_id_var.set(f"{job_id} - {values[2]}") 

            # Pre-fill the payment amount with the job's balance
            try:
                # Remove currency symbol and convert to float
                balance_numeric = float(job_balance.replace('₹', '').strip())
                self.payment_amount_var.set(balance_numeric)
            except ValueError:
                self.payment_amount_var.set(0.0) # Default if balance is not a valid number

            # Switch to the Payments tab
            self.customer_history_notebook.select(self.payments_tab)
            self._validate_payment_amount() # Re-evaluate the state of the add payment button


    def add_job(self):
        print(f"[{datetime.datetime.now()}] JobPaymentModule: add_job started.")
        if not self.selected_customer_id:
            messagebox.showerror("Error", "Please select a customer before adding a job.")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Add job prevented: No customer selected.")
            return
        
        job_type = self.job_type_var.get().strip()
        if not job_type or job_type.startswith("--"):
            messagebox.showwarning("Input Error", "Please select a specific job type, not a category header.")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Add job input error: Invalid job type.")
            return

        description = self.job_desc.get().strip()
        initial_price = self._get_numeric_value(self.initial_price)
        discount = self._get_numeric_value(self.discount_amount)
        final_price = self._get_numeric_value(self.final_price) # This is already calculated
        adv1 = self._get_numeric_value(self.adv1)
        balance = self._get_numeric_value(self.balance) # This is already calculated
        payment_mode = self.payment_mode.get().strip()
        job_status = self.job_status_var.get().strip()
        payment_status = self.payment_status_var.get().strip() # Use the calculated payment status
        start_date = self.start_date_var.get().strip()
        due_date = self.due_date_var.get().strip() # Get due_date
        completion_date = self.completion_date_var.get().strip() # Get completion_date
        delivery_date = self.delivery_date_var.get().strip()
        remarks = self.remarks_var.get().strip() # Get remarks
        
        assigned_staff_name = self.assigned_staff_var.get().strip()
        # Ensure that if "-- Select Staff --" is chosen, assigned_staff_id is None
        assigned_staff_id = self.staff_map.get(assigned_staff_name) if assigned_staff_name != "-- Select Staff --" else None

        # Get GST details
        gst_type = self.gst_type_var.get().strip()
        gst_category = self.gst_category_var.get().strip()
        gst_percentage = self._get_numeric_value(self.gst_percentage_var)
        gst_amount = self._get_numeric_value(self.gst_amount_var) # The calculated GST amount

        if not description or final_price <= 0:
            messagebox.showerror("Input Error", "Description and Final Price (must be greater than 0) are required.")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Add job input error: Description or Final Price invalid.")
            return

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            # IMPORTANT: Ensure your 'jobs' table has 'gst_type', 'gst_category', 'gst_percentage', 'gst_amount' columns.
            cur.execute("""
                INSERT INTO jobs (customer_id, job_type, description, initial_price, discount_amount, final_price,
                                  advance1, balance,
                                  payment_mode, status, payment_status, start_date, delivery_date,
                                  due_date, completion_date, notes, assigned_staff_id,
                                  gst_type, gst_category, gst_percentage, gst_amount)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.selected_customer_id, job_type, description,
                float(initial_price), float(discount), float(final_price), float(adv1), float(balance),
                payment_mode, job_status, payment_status, start_date, delivery_date,
                due_date, completion_date, remarks, assigned_staff_id,
                gst_type, gst_category, float(gst_percentage), float(gst_amount)
            ))
            pass
            
            job_id = cur.lastrowid # Get the ID of the newly inserted job

            total_advance_paid = adv1
            if total_advance_paid > 0:
                payment_notes = f"Initial payment for Job ID: {job_id} - {description}"
                # Explicitly pass payment_date
                cur.execute("""
                    INSERT INTO payments (customer_id, job_id, amount, payment_mode, notes, payment_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (self.selected_customer_id, job_id, float(total_advance_paid), payment_mode, payment_notes, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
                print(f"[{datetime.datetime.now()}] JobPaymentModule: Recorded initial payment for new job {job_id}.")

            conn.commit() # Commit both job and payment (if any)
            log_activity(self.current_user_info.get('id'), self.current_user_info.get('username'),
                         "Job Added", f"New job (ID: {job_id}, Type: {job_type}) added for Customer ID: {self.selected_customer_id}")

            # Send notification to assigned staff
            if assigned_staff_id:
                add_notification(
                    user_id=assigned_staff_id,
                    title="New Job Assigned",
                    message=f"Job #{job_id} ({job_type}) assigned to you by {self.current_user_info.get('username', 'Admin')} for customer {self.selected_customer_name}.",
                    job_id=job_id
                )

            messagebox.showinfo("Success", "Job added successfully!")
            # Reload data
            self.load_jobs_for_customer(self.selected_customer_id)
            self.load_payments_for_customer(self.selected_customer_id) # NEW: Refresh payments history
            self.populate_payment_job_id_combobox(self.selected_customer_id) # Refresh job IDs for payment form
            self.clear_job_form()
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Job added successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add job: {e}")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Unhandled error adding job: {e}")
            if conn: conn.rollback()
        finally:
            if conn: conn.close()
        print(f"[{datetime.datetime.now()}] JobPaymentModule: add_job finished.")

    def update_job(self):
        print(f"[{datetime.datetime.now()}] JobPaymentModule: update_job started.")
        if not self.selected_job_id:
            messagebox.showerror("Error", "Please select a job to update.")
            return

        job_type = self.job_type_var.get().strip()
        if not job_type or job_type.startswith("--"):
            messagebox.showwarning("Input Error", "Please select a specific job type, not a category header.")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Update job input error: Invalid job type.")
            return

        description = self.job_desc.get().strip()
        
        # Financial variables are not updated here as they are read-only in UI
        job_status = self.job_status_var.get().strip() # Job Status can still be updated
        start_date = self.start_date_var.get().strip()
        due_date = self.due_date_var.get().strip() 
        completion_date = self.completion_date_var.get().strip() 
        delivery_date = self.delivery_date_var.get().strip()
        remarks = self.remarks_var.get().strip() 
        
        assigned_staff_name = self.assigned_staff_var.get().strip()
        assigned_staff_id = self.staff_map.get(assigned_staff_name) if assigned_staff_name != "-- Select Staff --" else None

        # Get GST details (these are read-only from UI, so fetch from DB if needed, but for update, use current values)
        # For update, we only update fields that are editable in the UI.
        # GST fields are read-only when a job is selected, so they are not directly updated via this method.
        # If they need to be updated, it would require making them editable or a separate process.
        # For now, we will just pass the existing values from the DB.

        if not description: # Only description is directly editable here
            messagebox.showerror("Input Error", "Description is required.")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Update job input error: Description invalid.")
            return

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            pass
            
            # Fetch current financial and GST values from DB as they are not directly editable in UI
            # IMPORTANT: Ensure your 'jobs' table has 'gst_type', 'gst_category', 'gst_percentage', 'gst_amount' columns.
            cur.execute("SELECT initial_price, discount_amount, advance1, final_price, balance, payment_status, payment_mode, gst_type, gst_category, gst_percentage, gst_amount FROM jobs WHERE id = ?", (self.selected_job_id,))
            current_job_details = cur.fetchone()
            
            if not current_job_details:
                messagebox.showerror("Error", "Could not retrieve current job details for update.")
                print(f"[{datetime.datetime.now()}] JobPaymentModule: Update job failed: Could not fetch details for job {self.selected_job_id}.")
                return

            # Use existing financial and GST values from DB
# initial_price = current_job_details['initial_price']
# discount = current_job_details['discount_amount']
# advance1 = current_job_details['advance1']
# final_price = current_job_details['final_price']
# balance = current_job_details['balance']
# payment_status = current_job_details['payment_status']
# payment_mode = current_job_details['payment_mode']
            gst_type = current_job_details['gst_type']
            gst_category = current_job_details['gst_category']
            gst_percentage = current_job_details['gst_percentage']
            gst_amount = current_job_details['gst_amount']


            cur.execute("""
                UPDATE jobs SET
                    job_type = ?, description = ?,
                    status = ?, start_date = ?, delivery_date = ?,
                    due_date = ?, completion_date = ?, notes = ?, assigned_staff_id = ?,
                    gst_type = ?, gst_category = ?, gst_percentage = ?, gst_amount = ?
                WHERE id = ?
            """, (
                job_type, description,
                job_status, start_date, delivery_date,
                due_date, completion_date, remarks, assigned_staff_id,
                gst_type, gst_category, gst_percentage, gst_amount, # Pass existing GST values
                self.selected_job_id
            ))
            conn.commit()
            log_activity(self.current_user_info.get('id'), self.current_user_info.get('username'),
                         "Job Updated", f"Job (ID: {self.selected_job_id}, Type: {job_type}) updated for Customer ID: {self.selected_customer_id}")

            # Send notification to assigned staff on update
            if assigned_staff_id:
                add_notification(
                    user_id=assigned_staff_id,
                    title="Job Updated & Assigned",
                    message=f"Job #{self.selected_job_id} ({job_type}) has been updated and assigned to you by {self.current_user_info.get('username', 'Admin')} for customer {self.selected_customer_name}.",
                    job_id=self.selected_job_id
                )

            messagebox.showinfo("Success", "Job updated successfully!")
            self.load_jobs_for_customer(self.selected_customer_id)
            self.clear_job_form()
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Job updated successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update job: {e}")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Unhandled error updating job: {e}")
            if conn: conn.rollback()
        finally:
            if conn: conn.close()
        print(f"[{datetime.datetime.now()}] JobPaymentModule: update_job finished.")

    def delete_job(self):
        print(f"[{datetime.datetime.now()}] JobPaymentModule: delete_job started.")
        if not self.selected_job_id:
            messagebox.showerror("Error", "Please select a job to delete.")
            return
        
        # Admin check
        if not (self.current_user_info and self.current_user_info.get('role') == 'admin'):
            messagebox.showerror("Permission Denied", "Only administrators can delete jobs.")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Delete job prevented: User is not admin.")
            return

        # Check if job is linked to an invoice before attempting to delete
        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute("SELECT invoice_id FROM jobs WHERE id = ?", (self.selected_job_id,))
            invoice_id = cursor.fetchone()['invoice_id']
            if invoice_id:
                messagebox.showerror("Error", f"Cannot delete job: It is linked to Invoice ID {invoice_id}. Please delete the invoice first.")
                print(f"[{datetime.datetime.now()}] JobPaymentModule: Deletion of job {self.selected_job_id} prevented: Linked to invoice {invoice_id}.")
                return
        except Exception as e:
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Error checking invoice linkage for job {self.selected_job_id}: {e}")
            # Continue with delete attempt if error checking linkage, but log it.
        finally:
            if conn: conn.close()


        confirm = messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this job? This action cannot be undone.")
        if confirm:
            conn = None
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                # Delete associated payments first to avoid foreign key constraint issues
                cur.execute("DELETE FROM payments WHERE job_id = ?", (self.selected_job_id,))
                print(f"[{datetime.datetime.now()}] JobPaymentModule: Deleted payments for job {self.selected_job_id}.")
                pass

                # Delete associated notes
                cur.execute("DELETE FROM notes WHERE related_to = 'job' AND related_id = ?", (self.selected_job_id,))
                print(f"[{datetime.datetime.now()}] JobPaymentModule: Deleted notes for job {self.selected_job_id}.")

                cur.execute("DELETE FROM jobs WHERE id = ?", (self.selected_job_id,))
                conn.commit()
                log_activity(self.current_user_info.get('id'), self.current_user_info.get('username'),
                             "Job Deleted", f"Job (ID: {self.selected_job_id}) deleted for Customer ID: {self.selected_customer_id}")
                messagebox.showinfo("Success", "Job deleted successfully!")
                self.load_jobs_for_customer(self.selected_customer_id)
                self.load_payments_for_customer(self.selected_customer_id) # Refresh payments history
                self.populate_payment_job_id_combobox(self.selected_customer_id) # Refresh job IDs for payment form
                self.clear_job_form()
                print(f"[{datetime.datetime.now()}] JobPaymentModule: Job deleted successfully.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete job: {e}")
                print(f"[{datetime.datetime.now()}] JobPaymentModule: Error deleting job: {e}")
                if conn: conn.rollback()
            finally:
                if conn: conn.close()
        print(f"[{datetime.datetime.now()}] JobPaymentModule: delete_job finished.")

    def clear_job_form(self):
        print(f"[{datetime.datetime.now()}] JobPaymentModule: clear_job_form called.")
        self.selected_job_id = None
        self.job_type_var.set("Other") # Reset to default
        self.job_desc.set("")
        self.initial_price.set(0.0)
        self.initial_price_entry.config(state='normal')
        self.discount_amount.set(0.0)
        self.discount_amount_entry.config(state='normal')
        self.final_price.set(0.0)
        self.adv1.set(0.0)
        self.adv1_entry.config(state='normal')
        self.balance.set(0.0)
        self.payment_mode.set("Cash")
        self.payment_mode_option_menu_job_form.config(state='normal')
        self.job_status_var.set("Pending")
        self.payment_status_var.set("Unpaid")
        self.payment_status_display_label.config(state='readonly')
        self.start_date_var.set(datetime.date.today().isoformat())
        self.due_date_var.set("")
        self.completion_date_var.set("")
        self.delivery_date_var.set("")
        self.remarks_var.set("")
        if self.assigned_staff_combobox:
            self.assigned_staff_var.set("-- Select Staff --")

        # Reset GST fields and set to normal state
        self.gst_type_var.set("None")
        self.gst_type_combobox.config(state='normal') # Should be normal for new job entry
        self.gst_category_var.set("")
        self.gst_category_combobox.config(state='normal') # Should be normal for new job entry
        self.gst_percentage_var.set(0.0)
        self.gst_percentage_entry.config(state='normal')
        self.gst_amount_var.set(0.0) # Clear calculated GST amount

        # Re-enable "Add Job" button and disable "Update Job"
        self.add_job_btn.config(state=tk.NORMAL if self.selected_customer_id else tk.DISABLED)
        print(f"[{datetime.datetime.now()}] JobPaymentModule: Add New Job button state set to {'NORMAL' if self.selected_customer_id else 'DISABLED'} (form cleared).")
        self.update_job_btn.config(state=tk.DISABLED)
        if self.delete_job_btn:
            self.delete_job_btn.config(state=tk.DISABLED)
        
        # Temporarily unbind the TreeviewSelect event
        self.job_tree.unbind("<<TreeviewSelect>>")
        # Clear selected item in treeview if any
        self.job_tree.selection_remove(self.job_tree.selection())
        # Rebind the TreeviewSelect event
        self.job_tree.bind("<<TreeviewSelect>>", self.on_job_select)

        self.payment_job_id_var.set("") # Clear selected job ID in payment form
        self.add_payment_btn.config(state=tk.DISABLED) # Disable button after clearing form


    # --- Payment Management Methods ---
    
    def add_payment(self):
        print(f"[{datetime.datetime.now()}] JobPaymentModule: add_payment started.")
        if not self.selected_customer_id:
            messagebox.showerror("Error", "Please select a customer before recording a payment.")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Add payment prevented: No customer selected.")
            return

        amount = self._get_numeric_value(self.payment_amount_var)
        payment_mode = self.payment_mode_for_new_payment_var.get().strip()
        notes = self.payment_notes_var.get().strip()

        # Extract job_id from the combobox selection (e.g., "123 - Description")
        selected_job_text = self.payment_job_id_var.get().strip()
        job_id_for_payment = None
        if selected_job_text and " - " in selected_job_text:
            try:
                job_id_for_payment = int(selected_job_text.split(" - ")[0])
            except ValueError:
                job_id_for_payment = None # Not a valid job ID format

        if amount <= 0:
            messagebox.showerror("Input Error", "Payment amount must be positive.")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Add payment input error: Amount invalid.")
            return
        if not payment_mode:
            messagebox.showerror("Input Error", "Payment mode cannot be empty.")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Add payment input error: Payment mode empty.")
            return

        conn = None
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            payment_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            # Check outstanding before allowing this payment
            if job_id_for_payment:
                cur.execute("SELECT COALESCE(final_price,0) + COALESCE(gst_amount,0) - COALESCE((SELECT SUM(amount) FROM payments p WHERE p.job_id = jobs.id),0) AS due FROM jobs WHERE id = ?", (job_id_for_payment,))
                res = cur.fetchone()
                due = float(res['due']) if res and res['due'] is not None else 0.0
                if float(amount) > due + 0.0001:  # small tolerance
                    messagebox.showerror("Input Error", f"Payment exceeds job outstanding amount (Due: {due:.2f}).")
                    print(f"[{datetime.datetime.now()}] Add payment prevented: amount {amount} > job due {due}")
                    return
            else:
                # No job linked: ensure payment does not exceed customer's total outstanding
                cur.execute("SELECT COALESCE(SUM(COALESCE(j.final_price,0) + COALESCE(j.gst_amount,0) - COALESCE((SELECT SUM(amount) FROM payments p WHERE p.job_id = j.id),0)),0) as total_due FROM jobs j WHERE j.customer_id = ?", (self.selected_customer_id,))
                res = cur.fetchone()
                total_due = float(res['total_due']) if res and res['total_due'] is not None else 0.0
                if float(amount) > total_due + 0.0001:
                    messagebox.showerror("Input Error", f"Payment exceeds customer's total outstanding (Due: {total_due:.2f}).")
                    print(f"[{datetime.datetime.now()}] Add payment prevented: amount {amount} > customer total due {total_due}")
                    return

            # Insert into payments table
            cur.execute("""
                INSERT INTO payments (customer_id, job_id, amount, payment_date, payment_mode, notes)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (self.selected_customer_id, job_id_for_payment, float(amount), payment_date, payment_mode, notes))

            # If payment is linked to a job, update job's advance1 and payment_status atomically
            if job_id_for_payment:
                try:
                    cur.execute("""
                        UPDATE jobs
                        SET advance1 = COALESCE(advance1,0) + ?,
                            payment_status = CASE
                                WHEN COALESCE((SELECT COALESCE(j.final_price,0) + COALESCE(j.gst_amount,0) - COALESCE((SELECT SUM(amount) FROM payments p WHERE p.job_id = j.id),0) FROM jobs j WHERE j.id = ?),0) - ? <= 0 THEN 'Paid'
                                ELSE 'Partially Paid'
                            END
                        WHERE id = ?
                    """, (float(amount), int(job_id_for_payment), float(amount), int(job_id_for_payment)))
                    print(f"[{datetime.datetime.now()}] DB: Updated job {job_id_for_payment} within add_payment transaction.")
                except Exception as e:
                    print(f"[{datetime.datetime.now()}] DB: Error updating job payment status for job {job_id_for_payment}: {e}")

            conn.commit()
            log_activity(self.current_user_info.get('id'), self.current_user_info.get('username'),
                         "Payment Recorded", f"Recorded payment of {amount} for Customer ID: {self.selected_customer_id} (Job ID: {job_id_for_payment if job_id_for_payment else 'N/A'})")
            messagebox.showinfo("Success", "Payment recorded successfully!")
            self.load_payments_for_customer(self.selected_customer_id) # Refresh payment history
            self.load_jobs_for_customer(self.selected_customer_id) # Refresh job list to reflect payment status changes
            self.clear_payment_form()
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Payment added successfully.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to record payment: {e}")
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Error adding payment: {e}")
            if conn: conn.rollback()
        finally:
            if conn: conn.close()
        print(f"[{datetime.datetime.now()}] JobPaymentModule: add_payment finished.")

    def load_payments_for_customer(self, customer_id):
        print(f"[{datetime.datetime.now()}] JobPaymentModule: load_payments_for_customer started for ID: {customer_id}.")
        for item in self.payment_history_tree.get_children():
            self.payment_history_tree.delete(item)
        
        if customer_id:
            payments = get_payments_for_customer(customer_id) # This function now returns invoice_id too
            if payments:
                for payment in payments:
                    # UPDATED: Added Invoice ID to values
                    self.payment_history_tree.insert("", tk.END, values=(
                        payment['id'],
                        payment['job_id'] if payment['job_id'] is not None else "N/A",
                        payment['invoice_id'] if payment['invoice_id'] is not None else "N/A", # New column
                        f"{Decimal(str(payment['amount'])):.2f}",
                        payment['payment_date'],
                        payment['payment_mode'] if payment['payment_mode'] is not None else "N/A",
                        payment['notes'] if payment['notes'] is not None else ""
                    ))
                print(f"[{datetime.datetime.now()}] JobPaymentModule: Loaded {len(payments)} payments for customer {customer_id}.")
            else:
                self.payment_history_tree.insert("", tk.END, values=("", "No payments recorded for this customer.", "", "", "", "", ""))
                print(f"[{datetime.datetime.now()}] JobPaymentModule: No payments found for customer {customer_id}.")
        else:
            self.payment_history_tree.insert("", tk.END, values=("", "Select a customer to view payment history.", "", "", "", "", ""))
            print(f"[{datetime.datetime.now()}] JobPaymentModule: No customer selected for payment history.")
        print(f"[{datetime.datetime.now()}] JobPaymentModule: load_payments_for_customer finished.")


    def clear_payment_form(self):
        print(f"[{datetime.datetime.now()}] JobPaymentModule: clear_payment_form called.")
        self.payment_amount_var.set(0.0)
        self.payment_mode_for_new_payment_var.set("Cash")
        self.payment_notes_var.set("")
        self.payment_job_id_var.set("") # Clear selected job ID
        self.add_payment_btn.config(state=tk.DISABLED) # Disable button after clearing form

    def populate_payment_job_id_combobox(self, customer_id):
        print(f"[{datetime.datetime.now()}] JobPaymentModule: Populating payment job ID combobox for customer: {customer_id}.")
        job_ids = []
        if customer_id:
            conn = None
            try:
                conn = get_db_connection()
                cur = conn.cursor()
                # Fetch only jobs that are not fully paid and not invoiced
                cur.execute("SELECT id, description FROM jobs WHERE customer_id=? AND payment_status != 'Paid' AND invoice_id IS NULL ORDER BY id DESC", (customer_id,))
                # Format as "ID - Description" for better readability
                job_ids = [f"{row['id']} - {row['description']}" for row in cur.fetchall()]
            except Exception as e:
                print(f"[{datetime.datetime.now()}] JobPaymentModule: Error fetching job IDs for combobox: {e}")
            finally:
                if conn:
                    conn.close()
        self.payment_job_id_combobox['values'] = job_ids
        if job_ids:
            self.payment_job_id_combobox.set(job_ids[0]) # Optionally pre-select the latest job
        else:
            self.payment_job_id_combobox.set("") # Clear if no jobs
        print(f"[{datetime.datetime.now()}] JobPaymentModule: Payment job ID combobox populated with {len(job_ids)} jobs.")

    def refresh_job_types(self):
        """డేటాబేస్ నుంచి కొత్త job types మళ్లీ load చేసి combobox refresh చేస్తుంది"""
        try:
            print(f"[{datetime.datetime.now()}] JobPaymentModule: refresh_job_types called.")
            self.job_types = self._load_job_types_from_db()
            self.all_job_type_options = self._get_flat_job_type_list()
            # update combobox if widget exists
            try:
                self.job_type_combobox['values'] = self.all_job_type_options
            except Exception:
                pass
            current = self.job_type_var.get() if hasattr(self, "job_type_var") else None
            if current and current in self.all_job_type_options:
                try:
                    self.job_type_combobox.set(current)
                except Exception:
                    self.job_type_var.set(current)
            else:
                if hasattr(self, "job_type_var"):
                    self.job_type_var.set("Other")
        except Exception as e:
            print(f"[{datetime.datetime.now()}] JobPaymentModule: Error in refresh_job_types: {e}")


