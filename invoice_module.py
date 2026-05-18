import tkinter as tk
from psycopg2.extras import RealDictCursor
from tkinter import ttk, messagebox, filedialog
import datetime
import os
import subprocess 

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

DEFAULT_FONT = 'Helvetica'
DEFAULT_BOLD_FONT = 'Helvetica-Bold'

if 'DejaVuSans' not in pdfmetrics.getRegisteredFontNames():
    print(f"[{datetime.datetime.now()}] InvoiceModule: Starting font registration process (first time).")
    print(f"[{datetime.datetime.now()}] InvoiceModule: Initially registered fonts: {pdfmetrics.getRegisteredFontNames()}")
    try:
        dejavu_sans_path = 'DejaVuSans.ttf'
        if os.path.exists(dejavu_sans_path):
            pdfmetrics.registerFont(TTFont('DejaVuSans', dejavu_sans_path))
            print(f"[{datetime.datetime.now()}] InvoiceModule: DejaVuSans font registered successfully from {dejavu_sans_path}.")
            DEFAULT_FONT = 'DejaVuSans'
        else:
            print(f"[{datetime.datetime.now()}] InvoiceModule: DejaVuSans.ttf not found at {dejavu_sans_path}. Falling back to Helvetica for normal text.")

        dejavu_sans_bold_path = 'DejaVuSansBold.ttf'
        if DEFAULT_FONT == 'DejaVuSans' and os.path.exists(dejavu_sans_bold_path):
            pdfmetrics.registerFont(TTFont('DejaVuSans-Bold', dejavu_sans_bold_path))
            print(f"[{datetime.datetime.now()}] InvoiceModule: DejaVuSans-Bold font registered successfully from {dejavu_sans_bold_path}.")
            DEFAULT_BOLD_FONT = 'DejaVuSans-Bold'
        elif DEFAULT_FONT == 'DejaVuSans':
            print(f"[{datetime.datetime.now()}] InvoiceModule: DejaVuSansBold.ttf not found at {dejavu_sans_bold_path}. Bold font will fall back to Helvetica-Bold.")

    except Exception as e:
        print(f"[{datetime.datetime.now()}] InvoiceModule: Critical error during font registration: {e}. Ensuring fallback to Helvetica for all text.")
        DEFAULT_FONT = 'Helvetica'
        DEFAULT_BOLD_FONT = 'Helvetica-Bold'
    
    print(f"[{datetime.datetime.now()}] InvoiceModule: Registered fonts after initial setup: {pdfmetrics.getRegisteredFontNames()}")
    print(f"[{datetime.datetime.now()}] InvoiceModule: Final font settings after initial setup: DEFAULT_FONT='{DEFAULT_FONT}', DEFAULT_BOLD_FONT='{DEFAULT_BOLD_FONT}'.")
else:
    print(f"[{datetime.datetime.now()}] InvoiceModule: Fonts already registered. Skipping re-registration.")
    if 'DejaVuSans' in pdfmetrics.getRegisteredFontNames():
        DEFAULT_FONT = 'DejaVuSans'
    if 'DejaVuSans-Bold' in pdfmetrics.getRegisteredFontNames():
        DEFAULT_BOLD_FONT = 'DejaVuSans-Bold'

from db_manager import (
    get_db_connection, log_activity, get_all_customers_for_filter, create_invoice, get_all_invoices,
    get_invoice_details, delete_invoice, get_app_settings
)

# --- Main InvoiceModule Class ---
class InvoiceModule:
    def __init__(self, content_frame, user_info):
        print(f"[{datetime.datetime.now()}] InvoiceModule: Initializing.")
        self.content_frame = content_frame
        self.user_info = user_info
        self.currency_symbol = get_app_settings().get('currency_symbol', '₹')
        print(f"[{datetime.datetime.now()}] InvoiceModule: Currency symbol from settings: '{self.currency_symbol}'.")
        self.selected_customer_id = None
        self.selected_job_ids = []
        self.selected_invoice_id = None
        self.all_invoices_data = [] # To store all invoices for local filtering
        self.invoice_search_term_var = tk.StringVar() # New: Variable for search term for View Invoices
        self.customer_search_term_create_invoice_var = tk.StringVar() # New: Variable for customer search in Create Invoice
        self.all_customers_data = [] # To store all customer data for local filtering in Create Invoice
        
        # Store a reference to the root Tkinter window
        self.root_window = self.content_frame.winfo_toplevel() 

        self.create_ui()
        print(f"[{datetime.datetime.now()}] InvoiceModule: Initialization complete.")

    def create_ui(self, *args):
        print(f"[{datetime.datetime.now()}] InvoiceModule: Creating UI.")
        for widget in self.content_frame.winfo_children():
            widget.destroy()

        self.main_notebook = ttk.Notebook(self.content_frame)
        self.main_notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.create_invoice_tab = ttk.Frame(self.main_notebook, padding="10")
        self.main_notebook.add(self.create_invoice_tab, text="Create Invoice")
        self.create_create_invoice_tab_ui(self.create_invoice_tab) 

        self.view_invoices_tab = ttk.Frame(self.main_notebook, padding="10")
        self.main_notebook.add(self.view_invoices_tab, text="View Invoices")
        self.create_view_invoices_tab_ui(self.view_invoices_tab)

        self.main_notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)
        
        # Initial load for create invoice tab
        self.load_customers_for_combobox() 
        # Initial load for view invoices tab (handled in create_view_invoices_tab_ui)
        print(f"[{datetime.datetime.now()}] InvoiceModule: UI created.")

    def create_create_invoice_tab_ui(self, parent_frame):
        print(f"[{datetime.datetime.now()}] InvoiceModule: Creating Create Invoice UI.")
        customer_frame = ttk.LabelFrame(parent_frame, text="Select Customer", padding="10")
        customer_frame.pack(fill=tk.X, pady=5)

        # New: Customer Search Entry for Create Invoice tab
        ttk.Label(customer_frame, text="Search Customer (Name/Mobile):").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.customer_search_entry_create_invoice = ttk.Entry(customer_frame, textvariable=self.customer_search_term_create_invoice_var)
        self.customer_search_entry_create_invoice.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.customer_search_entry_create_invoice.bind("<KeyRelease>", self._filter_customers_for_invoice_creation)
        customer_frame.grid_columnconfigure(1, weight=1) # Make search entry expandable

        ttk.Label(customer_frame, text="Selected Customer:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.customer_combobox_var = tk.StringVar()
        self.customer_combobox = ttk.Combobox(customer_frame, textvariable=self.customer_combobox_var, state="readonly", width=50)
        self.customer_combobox.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.customer_combobox.bind("<<ComboboxSelected>>", self.on_customer_selected)

        jobs_frame = ttk.LabelFrame(parent_frame, text="Unbilled Jobs for Selected Customer", padding="10")
        jobs_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ("Job ID", "Job Type", "Description", "Final Price", "Balance Due", "Start Date", "Status", "GST Type", "GST %", "GST Amount")
        self.unbilled_jobs_tree = ttk.Treeview(jobs_frame, columns=columns, show="headings", selectmode="extended")
        for col in columns:
            self.unbilled_jobs_tree.heading(col, text=col)
            if col in ["Final Price", "Balance Due", "GST Amount"]:
                self.unbilled_jobs_tree.column(col, width=100, anchor=tk.E)
            elif col in ["GST %"]:
                self.unbilled_jobs_tree.column(col, width=60, anchor=tk.E)
            else:
                self.unbilled_jobs_tree.column(col, width=100, anchor=tk.CENTER)
        self.unbilled_jobs_tree.pack(fill=tk.BOTH, expand=True, pady=5)
        self.unbilled_jobs_tree.bind("<<TreeviewSelect>>", self.calculate_total_for_invoicing)

        summary_frame = ttk.LabelFrame(parent_frame, text="Invoice Summary", padding="10")
        summary_frame.pack(fill=tk.X, pady=5)

        ttk.Label(summary_frame, text="Selected Jobs Total:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.selected_jobs_total_var = tk.StringVar(value=f"{self.currency_symbol} 0.00")
        ttk.Label(summary_frame, textvariable=self.selected_jobs_total_var, font=("Arial", 10, "bold")).grid(row=0, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(summary_frame, text="Total GST Amount:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.selected_jobs_gst_total_var = tk.StringVar(value=f"{self.currency_symbol} 0.00")
        ttk.Label(summary_frame, textvariable=self.selected_jobs_gst_total_var, font=("Arial", 10, "bold"), foreground="blue").grid(row=1, column=1, padx=5, pady=5, sticky="w")

        ttk.Label(summary_frame, text="Notes:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.invoice_notes_text = tk.Text(summary_frame, height=3, width=40)
        self.invoice_notes_text.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        ttk.Button(summary_frame, text="Create Invoice", command=self.create_new_invoice).grid(row=3, column=0, columnspan=2, pady=10)
        print(f"[{datetime.datetime.now()}] InvoiceModule: Create Invoice UI created.")

    def create_view_invoices_tab_ui(self, parent_frame):
        print(f"[{datetime.datetime.now()}] InvoiceModule: Creating View Invoices UI.")
        
        # Existing: Search Frame for View Invoices
        search_frame = ttk.LabelFrame(parent_frame, text="Search Invoices", padding="10")
        search_frame.pack(fill=tk.X, pady=5)

        ttk.Label(search_frame, text="Search by Invoice No., Customer Name, or Mobile:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.invoice_search_entry = ttk.Entry(search_frame, textvariable=self.invoice_search_term_var)
        self.invoice_search_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")
        self.invoice_search_entry.bind("<KeyRelease>", self._filter_invoices) # Live search
        
        ttk.Button(search_frame, text="Search", command=self._filter_invoices).grid(row=0, column=2, padx=5, pady=5)
        search_frame.grid_columnconfigure(1, weight=1) # Make search entry expandable

        invoice_list_frame = ttk.LabelFrame(parent_frame, text="All Invoices", padding="10")
        invoice_list_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        columns = ("Invoice No.", "Customer Name", "Invoice Date", "Total Amount", "Amount Paid", "Balance Due", "Status")
        self.invoice_tree = ttk.Treeview(invoice_list_frame, columns=columns, show="headings")
        for col in columns:
            self.invoice_tree.heading(col, text=col)
            self.invoice_tree.column(col, width=100, anchor=tk.CENTER)
        self.invoice_tree.pack(fill=tk.BOTH, expand=True, pady=5)
        self.invoice_tree.bind("<<TreeviewSelect>>", self.on_invoice_selected)

        invoice_details_frame = ttk.LabelFrame(parent_frame, text="Selected Invoice Details", padding="10")
        invoice_details_frame.pack(fill=tk.X, pady=5)

        ttk.Label(invoice_details_frame, text="Invoice No.:").grid(row=0, column=0, padx=5, pady=2, sticky="w")
        self.detail_invoice_id_var = tk.StringVar()
        ttk.Label(invoice_details_frame, textvariable=self.detail_invoice_id_var, font=("Arial", 10, "bold")).grid(row=0, column=1, padx=5, pady=2, sticky="w")

        ttk.Label(invoice_details_frame, text="Customer:").grid(row=1, column=0, padx=5, pady=2, sticky="w")
        self.detail_customer_name_var = tk.StringVar()
        ttk.Label(invoice_details_frame, textvariable=self.detail_customer_name_var).grid(row=1, column=1, padx=5, pady=2, sticky="w")

        ttk.Label(invoice_details_frame, text="Total Amount:").grid(row=2, column=0, padx=5, pady=2, sticky="w")
        self.detail_total_amount_var = tk.StringVar()
        ttk.Label(invoice_details_frame, textvariable=self.detail_total_amount_var).grid(row=2, column=1, padx=5, pady=2, sticky="w")

        ttk.Label(invoice_details_frame, text="Amount Paid:").grid(row=3, column=0, padx=5, pady=2, sticky="w")
        self.detail_amount_paid_var = tk.StringVar()
        ttk.Label(invoice_details_frame, textvariable=self.detail_amount_paid_var).grid(row=3, column=1, padx=5, pady=2, sticky="w")

        ttk.Label(invoice_details_frame, text="Balance Due:").grid(row=4, column=0, padx=5, pady=2, sticky="w")
        self.detail_balance_due_var = tk.StringVar()
        ttk.Label(invoice_details_frame, textvariable=self.detail_balance_due_var).grid(row=4, column=1, padx=5, pady=2, sticky="w")

        ttk.Label(invoice_details_frame, text="Status:").grid(row=5, column=0, padx=5, pady=2, sticky="w")
        self.detail_status_var = tk.StringVar()
        ttk.Label(invoice_details_frame, textvariable=self.detail_status_var).grid(row=5, column=1, padx=5, pady=2, sticky="w")

        ttk.Label(invoice_details_frame, text="Notes:").grid(row=6, column=0, padx=5, pady=2, sticky="w")
        self.detail_notes_text = tk.Text(invoice_details_frame, height=3, width=40, state="disabled")
        self.detail_notes_text.grid(row=6, column=1, padx=5, pady=2, sticky="ew")

        ttk.Label(invoice_details_frame, text="Invoice Line Items:").grid(row=7, column=0, columnspan=2, padx=5, pady=5, sticky="w")
        line_item_columns = ("Job ID", "Description", "Billed Amount", "GST Type", "GST %", "GST Amount") # Updated columns
        self.line_item_tree = ttk.Treeview(invoice_details_frame, columns=line_item_columns, show="headings")
        for col in line_item_columns:
            self.line_item_tree.heading(col, text=col)
            if col in ["Billed Amount", "GST Amount"]:
                self.line_item_tree.column(col, width=100, anchor=tk.E)
            elif col == "GST %":
                self.line_item_tree.column(col, width=60, anchor=tk.E)
            else:
                self.line_item_tree.column(col, width=80, anchor=tk.CENTER)
        self.line_item_tree.grid(row=8, column=0, columnspan=2, padx=5, pady=5, sticky="nsew") 
        invoice_details_frame.grid_rowconfigure(8, weight=1)
        invoice_details_frame.grid_columnconfigure(1, weight=1)

        action_buttons_frame = ttk.Frame(invoice_details_frame)
        action_buttons_frame.grid(row=9, column=0, columnspan=2, pady=10)
        # REMOVED: Record Payment button - payments handled in Job & Payments module
        ttk.Button(action_buttons_frame, text="Delete Invoice", command=self.delete_selected_invoice).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_buttons_frame, text="Print Invoice", command=self._print_invoice_to_pdf).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_buttons_frame, text="Revise Invoice", command=self.revise_selected_invoice).pack(side=tk.LEFT, padx=5)
        
        # Initial load of all invoices when the tab is created
        self.load_all_invoices() 
        print(f"[{datetime.datetime.now()}] InvoiceModule: View Invoices UI created.")

    def on_tab_change(self, event):
        """Called when the notebook tab changes."""
        selected_tab = self.main_notebook.tab(self.main_notebook.select(), "text")
        print(f"[{datetime.datetime.now()}] InvoiceModule: Tab changed to: {selected_tab}")
        if selected_tab == "View Invoices":
            self.invoice_search_term_var.set("") # Clear search on tab change
            self.load_all_invoices() # Reload all invoices
            if self.selected_invoice_id:
                self.display_invoice_details(self.selected_invoice_id)
        elif selected_tab == "Create Invoice":
            self.customer_search_term_create_invoice_var.set("") # Clear search on tab change
            self.load_customers_for_combobox() # Reload all customers for create invoice tab
            self.clear_create_invoice_form()

    def load_customers_for_combobox(self):
        """Loads all customers into self.all_customers_data for filtering and populates the combobox."""
        print(f"[{datetime.datetime.now()}] InvoiceModule: Loading customers for combobox.")
        try:
            self.all_customers_data = get_all_customers_for_filter() # Fetch all customers once
            print(f"[{datetime.datetime.now()}] InvoiceModule: Loaded {len(self.all_customers_data)} customers from database")
            self._filter_customers_for_invoice_creation() # Populate combobox with all (or filtered) customers
        except Exception as e:
            print(f"[{datetime.datetime.now()}] InvoiceModule: Error loading customers: {e}")
            messagebox.showerror("Database Error", f"Failed to load customers: {e}")
            self.all_customers_data = []

    def _filter_customers_for_invoice_creation(self, *args):
        """Filters the customer combobox in the Create Invoice tab based on the search term."""
        search_term = self.customer_search_term_create_invoice_var.get().lower().strip()
        print(f"[{datetime.datetime.now()}] InvoiceModule: Filtering customers with search term: '{search_term}'")

        filtered_customer_names = []
        self.customer_map = {} # Rebuild map based on filtered results

        if search_term:
            for customer in self.all_customers_data:
                customer_name = customer['name'].lower() if customer['name'] else ""
                customer_mobile = customer['mobile'].lower() if customer['mobile'] else ""
                if search_term in customer_name or search_term in customer_mobile:
                    display_name = f"{customer['name']} ({customer['mobile']})"
                    filtered_customer_names.append(display_name)
                    self.customer_map[display_name] = customer['id']
        else:
            for customer in self.all_customers_data:
                display_name = f"{customer['name']} ({customer['mobile']})"
                filtered_customer_names.append(display_name)
                self.customer_map[display_name] = customer['id']

        # Update combobox values
        self.customer_combobox['values'] = filtered_customer_names
        
        # If the currently selected customer is no longer in the filtered list, clear the selection
        current_selection = self.customer_combobox_var.get()
        if current_selection and current_selection not in filtered_customer_names:
            self.customer_combobox_var.set("")
            self.selected_customer_id = None
            self.clear_unbilled_jobs_tree() # Clear jobs if customer is deselected/filtered out
        
        # If no customers match the filter, ensure no customer is selected and job tree is cleared
        if not filtered_customer_names:
            self.customer_combobox_var.set("")
            self.selected_customer_id = None
            self.clear_unbilled_jobs_tree()
            
        print(f"[{datetime.datetime.now()}] InvoiceModule: Found {len(filtered_customer_names)} matching customers")


    def on_customer_selected(self, event):
        selected_customer_text = self.customer_combobox_var.get()
        self.selected_customer_id = self.customer_map.get(selected_customer_text)
        print(f"[{datetime.datetime.now()}] InvoiceModule: Customer selected: ID={self.selected_customer_id}.")
        self.load_unbilled_jobs()

    def clear_unbilled_jobs_tree(self):
        for item in self.unbilled_jobs_tree.get_children():
            self.unbilled_jobs_tree.delete(item)
        self.selected_job_ids = []
        self.selected_jobs_total_var.set(f"{self.currency_symbol} 0.00")
        self.selected_jobs_gst_total_var.set(f"{self.currency_symbol} 0.00")

    def load_unbilled_jobs(self):
        print(f"[{datetime.datetime.now()}] InvoiceModule: Loading unbilled jobs for customer ID: {self.selected_customer_id}.")
        self.clear_unbilled_jobs_tree()
        if self.selected_customer_id:
            # Updated to get GST details from jobs
            conn = get_db_connection()
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            try:
                cursor.execute("""
                    SELECT j.id, j.job_type, j.description, j.final_price, j.balance, j.start_date, j.status,
                           j.gst_type, j.gst_percentage, j.gst_amount
                    FROM jobs j 
                    WHERE j.customer_id = ? AND j.invoice_id IS NULL AND j.balance > 0 
                    ORDER BY j.start_date DESC
                """, (self.selected_customer_id,))
                
                unbilled_jobs = cursor.fetchall()
                self.jobs_for_invoice = {job['id']: job for job in unbilled_jobs}
                
                if unbilled_jobs:
                    for job in unbilled_jobs:
                        gst_type = job['gst_type'] if job['gst_type'] else 'None'
                        gst_percentage = job['gst_percentage'] if job['gst_percentage'] else 0.0
                        gst_amount = job['gst_amount'] if job['gst_amount'] else 0.0
                        
                        self.unbilled_jobs_tree.insert("", tk.END, iid=job['id'], values=(
                            job['id'],
                            job['job_type'],
                            job['description'],
                            f"{self.currency_symbol} {job['final_price']:.2f}",
                            f"{self.currency_symbol} {job['balance']:.2f}",
                            job['start_date'],
                            job['status'],
                            gst_type,
                            f"{gst_percentage:.1f}%" if gst_percentage > 0 else "0%",
                            f"{self.currency_symbol} {gst_amount:.2f}"
                        ))
                    print(f"[{datetime.datetime.now()}] InvoiceModule: {len(unbilled_jobs)} unbilled jobs loaded.")
                else:
                    print(f"[{datetime.datetime.now()}] InvoiceModule: No unbilled jobs found for this customer.")
                    messagebox.showinfo("No Jobs", "No unbilled jobs found for the selected customer.")
            except Exception as e:
                print(f"[{datetime.datetime.now()}] InvoiceModule: Error loading unbilled jobs: {e}")
                messagebox.showerror("Database Error", f"Failed to load unbilled jobs: {e}")
            finally:
                conn.close()
        else:
            print(f"[{datetime.datetime.now()}] InvoiceModule: No customer selected.")

    def calculate_total_for_invoicing(self, event):
        selected_items = self.unbilled_jobs_tree.selection()
        self.selected_job_ids = [self.unbilled_jobs_tree.item(item, "values")[0] for item in selected_items]
        total_amount = 0.0
        total_gst = 0.0

        for item in selected_items:
            try:
                values = self.unbilled_jobs_tree.item(item, "values")
                job_id = values[0]

                # Get job details to determine GST type
                if hasattr(self, 'jobs_for_invoice') and job_id in self.jobs_for_invoice:
                    job_data = self.jobs_for_invoice[job_id]
                    final_price = job_data['final_price']
                    gst_amount = job_data.get('gst_amount', 0.0)
                    gst_type = job_data.get('gst_type', 'None')

                    if gst_type and gst_type.lower() == 'inclusive':
                        # For inclusive GST, final_price already includes GST
                        total_amount += final_price
                        total_gst += gst_amount or 0.0
                    else:
                        # For exclusive or no GST
                        # For exclusive, final_price is base; add GST to total amount
                        if gst_type and gst_type.lower() == 'exclusive':
                            total_amount += final_price + (gst_amount or 0.0)
                        else:
                            total_amount += final_price
                        total_gst += gst_amount or 0.0
                else:
                    # Fallback to parsing from treeview
                    price_str = values[3].replace(self.currency_symbol, '').strip()
                    gst_str = values[9].replace(self.currency_symbol, '').strip()

                    price = float(price_str)
                    gst = float(gst_str)

                    total_amount += price
                    total_gst += gst

            except (ValueError, IndexError) as e:
                print(f"[{datetime.datetime.now()}] InvoiceModule: Error parsing values from treeview item: {e}")
                continue

        self.selected_jobs_total_var.set(f"{self.currency_symbol} {total_amount:.2f}")
        self.selected_jobs_gst_total_var.set(f"{self.currency_symbol} {total_gst:.2f}")
        print(f"[{datetime.datetime.now()}] InvoiceModule: Selected jobs total updated to {self.selected_jobs_total_var.get()}, GST: {self.selected_jobs_gst_total_var.get()}.")
    def create_new_invoice(self):
        print(f"[{datetime.datetime.now()}] InvoiceModule: Attempting to create new invoice.")
        if not self.selected_customer_id:
            messagebox.showerror("Error", "Please select a customer first.")
            return

        selected_jobs = self.unbilled_jobs_tree.selection()
        if not selected_jobs:
            messagebox.showerror("Error", "Please select at least one job to invoice.")
            return

        total_amount_str = self.selected_jobs_total_var.get().replace(self.currency_symbol, '').strip()
        if not total_amount_str or float(total_amount_str) <= 0:
            messagebox.showerror("Error", "Selected jobs total amount is zero or invalid.")
            return

        try:
            total_amount = float(total_amount_str)
# invoice_date = datetime.date.today().strftime("%Y-%m-%d")
# due_date = (datetime.date.today() + datetime.timedelta(days=30)).strftime("%Y-%m-%d") # 30 days due
            invoice_notes = self.invoice_notes_text.get("1.0", tk.END).strip()
            
            # Collect only job IDs for the create_invoice function
            job_ids_to_invoice = [int(self.unbilled_jobs_tree.item(item, "values")[0]) for item in selected_jobs]

            invoice_id = create_invoice(
                customer_id=self.selected_customer_id,
                job_ids=job_ids_to_invoice, # Pass list of job IDs
                total_amount=total_amount,
                notes=invoice_notes,
                created_by_user_id=self.user_info['id']
            )

            if invoice_id:
                messagebox.showinfo("Success", f"Invoice #{invoice_id} created successfully!")
                self.load_unbilled_jobs() # Refresh the list of unbilled jobs
                self.clear_create_invoice_form() # Clear the form
                self.load_all_invoices() # Refresh the view invoice tab
                self.main_notebook.select(self.view_invoices_tab)
            else:
                messagebox.showerror("Error", "Failed to create invoice. Please check the logs.")

        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")
            print(f"[{datetime.datetime.now()}] InvoiceModule: Error creating invoice: {e}")

    def clear_create_invoice_form(self):
        print(f"[{datetime.datetime.now()}] InvoiceModule: Clearing create invoice form.")
        self.customer_search_term_create_invoice_var.set("") # Clear search bar
        self.customer_combobox_var.set("")
        self.selected_customer_id = None
        self.clear_unbilled_jobs_tree()
        self.invoice_notes_text.delete("1.0", tk.END)
        self.selected_jobs_total_var.set(f"{self.currency_symbol} 0.00")
        self.selected_jobs_gst_total_var.set(f"{self.currency_symbol} 0.00")
        self.load_customers_for_combobox() # Reload all customers to reset combobox

    def load_all_invoices(self):
        """Loads all invoices into self.all_invoices_data and then filters them into the treeview."""
        print(f"[{datetime.datetime.now()}] InvoiceModule: Loading all invoices.")
        self.all_invoices_data = get_all_invoices() # Fetch all invoices once
        self._filter_invoices() # Populate treeview with all (or filtered) invoices
        print(f"[{datetime.datetime.now()}] InvoiceModule: All invoices loaded into memory.")

    def _filter_invoices(self, *args):
        """Filters invoices displayed in the treeview based on the search term."""
        print(f"[{datetime.datetime.now()}] InvoiceModule: Filtering invoices with term: {self.invoice_search_term_var.get()}.")
        search_term = self.invoice_search_term_var.get().lower().strip()

        # Clear current treeview contents
        for item in self.invoice_tree.get_children():
            self.invoice_tree.delete(item)

        filtered_invoices = []
        if search_term:
            for invoice in self.all_invoices_data:
                # Check invoice number, customer name, customer mobile
                if (search_term in invoice['invoice_number'].lower() or
                    search_term in invoice['customer_name'].lower() or
                    search_term in invoice['customer_mobile'].lower()):
                    filtered_invoices.append(invoice)
        else:
            filtered_invoices = self.all_invoices_data # If no search term, show all

        for invoice in filtered_invoices:
            self.invoice_tree.insert("", tk.END, iid=invoice['id'], values=(
                invoice['invoice_number'],
                invoice['customer_name'],
                invoice['invoice_date'],
                f"{self.currency_symbol} {invoice['total_amount']:.2f}",
                f"{self.currency_symbol} {invoice['amount_paid']:.2f}",
                f"{self.currency_symbol} {invoice['balance_due']:.2f}",
                invoice['status']
            ))
        print(f"[{datetime.datetime.now()}] InvoiceModule: Displayed {len(filtered_invoices)} filtered invoices.")


    def on_invoice_selected(self, event):
        selected_item = self.invoice_tree.selection()
        if selected_item:
            # Directly use the iid from the selection
            invoice_id = selected_item[0] 
            self.selected_invoice_id = invoice_id
            self.display_invoice_details(invoice_id)
        else:
            self.selected_invoice_id = None
            self.clear_invoice_details()

    def display_invoice_details(self, invoice_id):
        print(f"[{datetime.datetime.now()}] InvoiceModule: Displaying details for invoice ID: {invoice_id}.")
        invoice_header, line_items = get_invoice_details(invoice_id)

        if invoice_header:
            self.detail_invoice_id_var.set(invoice_header['invoice_number'])
            self.detail_customer_name_var.set(f"{invoice_header['customer_name']} (Mob: {invoice_header['customer_mobile']})")
            self.detail_total_amount_var.set(f"{self.currency_symbol} {invoice_header['total_amount']:.2f}")
            self.detail_amount_paid_var.set(f"{self.currency_symbol} {invoice_header['amount_paid']:.2f}")
            self.detail_balance_due_var.set(f"{self.currency_symbol} {invoice_header['balance_due']:.2f}")
            self.detail_status_var.set(invoice_header['status'])
            
            self.detail_notes_text.config(state="normal")
            self.detail_notes_text.delete("1.0", tk.END)
            self.detail_notes_text.insert(tk.END, invoice_header['notes'] if invoice_header['notes'] else "No notes.")
            self.detail_notes_text.config(state="disabled")

            # Populate line items treeview with job GST details
            for item in self.line_item_tree.get_children():
                self.line_item_tree.delete(item)
            
            if line_items:
                # Get GST details from jobs for each line item
                conn = None
                try:
                    conn = get_db_connection()
                    cursor = conn.cursor(cursor_factory=RealDictCursor)
                    
                    for item in line_items:
                        job_id = item.get('job_id')
                        gst_type = 'None'
                        gst_percentage = 0.0
                        gst_amount = 0.0
                        
                        if job_id:
                            try:
                                cursor.execute("""
                                    SELECT gst_type, gst_percentage, gst_amount 
                                    FROM jobs WHERE id = ?
                                """, (job_id,))
                                job_gst = cursor.fetchone()
                                if job_gst:
                                    gst_type = job_gst['gst_type'] or 'None'
                                    gst_percentage = job_gst['gst_percentage'] or 0.0
                                    gst_amount = job_gst['gst_amount'] or 0.0
                            except Exception as e:
                                print(f"[{datetime.datetime.now()}] InvoiceModule: Error fetching job GST details: {e}")
                        
                        self.line_item_tree.insert("", tk.END, iid=item['line_item_id'], values=(
                            item['job_id'] if item['job_id'] else "N/A",
                            item['item_description'],
                            f"{self.currency_symbol} {item['amount_billed_for_job']:.2f}",
                            gst_type,
                            f"{gst_percentage:.1f}%" if gst_percentage > 0 else "0%",
                            f"{self.currency_symbol} {gst_amount:.2f}"
                        ))
                        
                except Exception as e:
                    print(f"[{datetime.datetime.now()}] InvoiceModule: Error in display_invoice_details: {e}")
                finally:
                    if conn:
                        conn.close()
            else:
                self.line_item_tree.insert("", tk.END, values=("", "No line items found.", "", "", "", ""))
        else:
            self.clear_invoice_details()
        print(f"[{datetime.datetime.now()}] InvoiceModule: Invoice details displayed for ID: {invoice_id}.")

    def clear_invoice_details(self):
        print(f"[{datetime.datetime.now()}] InvoiceModule: Clearing invoice details.")
        self.detail_invoice_id_var.set("")
        self.detail_customer_name_var.set("")
        self.detail_total_amount_var.set("")
        self.detail_amount_paid_var.set("")
        self.detail_balance_due_var.set("")
        self.detail_status_var.set("")
        self.detail_notes_text.config(state="normal")
        self.detail_notes_text.delete("1.0", tk.END)
        self.detail_notes_text.config(state="disabled")
        for item in self.line_item_tree.get_children():
            self.line_item_tree.delete(item)

    def delete_selected_invoice(self):
        print(f"[{datetime.datetime.now()}] InvoiceModule: Attempting to delete invoice.")
        if not self.selected_invoice_id:
            messagebox.showerror("Error", "Please select an invoice to delete.")
            return
        
        if not (self.user_info and self.user_info.get('role') == 'admin'):
            messagebox.showerror("Permission Denied", "Only administrators can delete invoices.")
            print(f"[{datetime.datetime.now()}] InvoiceModule: Delete invoice prevented: User is not admin.")
            return

        confirm = messagebox.askyesno("Confirm Deletion", "Are you sure you want to delete this invoice? This action cannot be undone and will revert associated jobs to 'Unpaid' status.")
        if confirm:
            if delete_invoice(self.selected_invoice_id):
                messagebox.showinfo("Success", "Invoice deleted successfully!")
                self.load_all_invoices() # Refresh invoice list
                self.clear_invoice_details() # Clear details pane
                self.selected_invoice_id = None
            else:
                messagebox.showerror("Error", "Failed to delete invoice.")
        print(f"[{datetime.datetime.now()}] InvoiceModule: Delete invoice process finished.")

    def revise_selected_invoice(self):
        print(f"[{datetime.datetime.now()}] InvoiceModule: Revising invoice ID: {self.selected_invoice_id}")
        if not self.selected_invoice_id:
            messagebox.showerror("Error", "Please select an invoice to revise.")
            return

        # Invoice data DB నుండి
        invoice_header, line_items = get_invoice_details(self.selected_invoice_id)
        if not invoice_header:
            messagebox.showerror("Error", "Invoice data not found.")
            return

        # Customer తాజా details DB నుండి
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            cursor.execute(
                "SELECT name, mobile, email, address FROM customers WHERE id = ?",
                (invoice_header['customer_id'],)
            )
            customer = cursor.fetchone()
            if customer:
                invoice_header['customer_name'] = customer['name']
                invoice_header['customer_mobile'] = customer['mobile']
                invoice_header['customer_email'] = customer['email']
                invoice_header['customer_address'] = customer['address']
        finally:
            conn.close()

        # ✅ UI variables update చేయడం
        self.detail_customer_name_var.set(
            f"{invoice_header['customer_name']} (Mob: {invoice_header['customer_mobile']})"
        )
        self.detail_total_amount_var.set(f"{self.currency_symbol} {invoice_header['total_amount']:.2f}")
        self.detail_amount_paid_var.set(f"{self.currency_symbol} {invoice_header['amount_paid']:.2f}")
        self.detail_balance_due_var.set(f"{self.currency_symbol} {invoice_header['balance_due']:.2f}")
        self.detail_status_var.set(invoice_header['status'])

        # ✅ Notes కూడా refresh
        self.detail_notes_text.config(state="normal")
        self.detail_notes_text.delete("1.0", tk.END)
        self.detail_notes_text.insert(tk.END, invoice_header['notes'] if invoice_header['notes'] else "No notes.")
        self.detail_notes_text.config(state="disabled")

        # ✅ UI list refresh
        self.load_all_invoices()

        # ✅ Log చేసి, PDF కి కొత్త header పంపించడం
        log_activity(
            self.user_info['id'],
            None,
            "Invoice Revised",
            f"Revised invoice {invoice_header.get('invoice_number')}"
        )

        # IMPORTANT: Override చేసి PDFకి పంపడం
        self._print_invoice_to_pdf_with_header(invoice_header, line_items)

        messagebox.showinfo(
            "Invoice Revised",
            f"Invoice {invoice_header.get('invoice_number')} revised successfully with latest customer & invoice details."
        )


    def _print_invoice_to_pdf_with_header(self, invoice_header, line_items):
        """Generate PDF using overridden invoice header and line items"""
        try:
            # Reuse the same logic as _print_invoice_to_pdf but with injected header/line_items
            pdf_filename = f"Invoice_{invoice_header['invoice_number']}.pdf"
            doc = SimpleDocTemplate(pdf_filename, pagesize=letter)
            styles = getSampleStyleSheet()
            elements = []

            elements.append(Paragraph("Invoice", styles['Title']))
            elements.append(Spacer(1, 12))

            elements.append(Paragraph(f"Invoice No: {invoice_header['invoice_number']}", styles['Normal']))
            elements.append(Paragraph(f"Customer: {invoice_header['customer_name']}", styles['Normal']))
            elements.append(Paragraph(f"Mobile: {invoice_header['customer_mobile']}", styles['Normal']))
            elements.append(Paragraph(f"Email: {invoice_header['customer_email']}", styles['Normal']))
            elements.append(Paragraph(f"Address: {invoice_header['customer_address']}", styles['Normal']))
            elements.append(Paragraph(f"Total: {self.currency_symbol} {invoice_header['total_amount']:.2f}", styles['Normal']))
            elements.append(Paragraph(f"Paid: {self.currency_symbol} {invoice_header['amount_paid']:.2f}", styles['Normal']))
            elements.append(Paragraph(f"Balance: {self.currency_symbol} {invoice_header['balance_due']:.2f}", styles['Normal']))
            elements.append(Paragraph(f"Status: {invoice_header['status']}", styles['Normal']))

            doc.build(elements)

            os.startfile(pdf_filename)
        except Exception as e:
            print(f"Error printing revised invoice: {e}")
            messagebox.showerror("Error", f"Could not generate revised invoice PDF. {e}")
    def _print_invoice_to_pdf(self):
        print(f"[{datetime.datetime.now()}] InvoiceModule: Attempting to print invoice to PDF.")
        if not self.selected_invoice_id:
            messagebox.showerror("Error", "Please select an invoice to print.")
            return

        invoice_header, line_items = get_invoice_details(self.selected_invoice_id)
        if not invoice_header:
            messagebox.showerror("Error", "Could not retrieve invoice details for printing.")
            return

        # Get company settings
        app_settings = get_app_settings()
        company_name = app_settings.get('company_name', 'Your Company Name')
        company_address = app_settings.get('company_address', '123 Main St, City, State, PIN')
        company_phone = app_settings.get('company_phone', 'YOUR_COMPANY_PHONE')
        company_email = app_settings.get('company_email', 'YOUR_COMPANY_EMAIL')
        company_gstin = app_settings.get('company_gstin', 'YOUR_COMPANY_GSTIN')
        currency_symbol = app_settings.get('currency_symbol', '₹')

        # Prompt user to select save location
        initial_filename = f"Invoice_{invoice_header['invoice_number']}.pdf"
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            initialfile=initial_filename,
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
        )

        if not file_path:
            messagebox.showinfo("Cancelled", "Invoice PDF generation cancelled.")
            return # User cancelled the save dialog

        doc = SimpleDocTemplate(file_path, pagesize=letter)
        story = []
        styles = getSampleStyleSheet()
        
        # Custom styles for better control
        styles.add(ParagraphStyle(name='CompanyHeader', fontName=DEFAULT_BOLD_FONT, fontSize=18, alignment=TA_CENTER, spaceAfter=6))
        styles.add(ParagraphStyle(name='CompanyAddress', fontName=DEFAULT_FONT, fontSize=9, alignment=TA_CENTER, spaceAfter=2))
        styles.add(ParagraphStyle(name='CompanyContact', fontName=DEFAULT_FONT, fontSize=9, alignment=TA_CENTER, spaceAfter=12))
        styles.add(ParagraphStyle(name='InvoiceTitle', fontName=DEFAULT_BOLD_FONT, fontSize=14, alignment=TA_CENTER, spaceAfter=12))
        styles.add(ParagraphStyle(name='DetailLabel', fontName=DEFAULT_BOLD_FONT, fontSize=9, alignment=TA_LEFT))
        styles.add(ParagraphStyle(name='DetailValue', fontName=DEFAULT_FONT, fontSize=9, alignment=TA_LEFT))
        styles.add(ParagraphStyle(name='TableHeading', fontName=DEFAULT_BOLD_FONT, fontSize=9, alignment=TA_CENTER, spaceAfter=2))
        styles.add(ParagraphStyle(name='TableContent', fontName=DEFAULT_FONT, fontSize=8, alignment=TA_CENTER))
        styles.add(ParagraphStyle(name='TableContentLeft', fontName=DEFAULT_FONT, fontSize=8, alignment=TA_LEFT))
        styles.add(ParagraphStyle(name='TotalLabel', fontName=DEFAULT_BOLD_FONT, fontSize=10, alignment=TA_RIGHT))
        styles.add(ParagraphStyle(name='TotalValue', fontName=DEFAULT_BOLD_FONT, fontSize=10, alignment=TA_RIGHT))
        styles.add(ParagraphStyle(name='TermsHeading', fontName=DEFAULT_BOLD_FONT, fontSize=10, alignment=TA_LEFT, spaceAfter=6))
        styles.add(ParagraphStyle(name='TermsText', fontName=DEFAULT_FONT, fontSize=8, alignment=TA_LEFT))
        styles.add(ParagraphStyle(name='SignatureLine', fontName=DEFAULT_FONT, fontSize=9, alignment=TA_RIGHT, spaceBefore=20))
        styles.add(ParagraphStyle(name='ComputerGenerated', fontName=DEFAULT_FONT, fontSize=7, alignment=TA_CENTER, spaceBefore=10))

        # --- Logo and Company Info Section ---
        logo_path = r"D:\New folder (2)\crm\kpr_logo.png"
        if os.path.exists(logo_path):
            logo = Image(logo_path, width=1.8*inch, height=0.9*inch)
            logo_table = Table([[logo]], colWidths=[letter[0] - 2*inch])
            logo_table.setStyle(TableStyle([('ALIGN', (0,0), (-1,-1), 'CENTER'),
                                           ('VALIGN', (0,0), (-1,-1), 'MIDDLE')]))
            story.append(logo_table)
            story.append(Spacer(1, 0.1 * inch))
        else:
            print(f"[{datetime.datetime.now()}] InvoiceModule: KPR logo not found at {logo_path}. Skipping logo.")

        # Company Details (centered)
        story.append(Paragraph(company_address, styles['CompanyAddress']))
        story.append(Paragraph(f"GSTIN: {company_gstin} | Phone: {company_phone} | Email: {company_email}", styles['CompanyContact']))
        story.append(Spacer(1, 0.1 * inch))

        story.append(Paragraph("TAX INVOICE", styles['InvoiceTitle']))
        story.append(Spacer(1, 0.1 * inch))

        # --- Invoice Details and Customer Details (Side-by-Side) ---
        invoice_customer_data = [
            [Paragraph("Invoice No:", styles['DetailLabel']), Paragraph(invoice_header['invoice_number'], styles['DetailValue']),
             Paragraph("Customer Name:", styles['DetailLabel']), Paragraph(invoice_header['customer_name'], styles['DetailValue'])],
            [Paragraph("Invoice Date:", styles['DetailLabel']), Paragraph(invoice_header['invoice_date'], styles['DetailValue']),
             Paragraph("Mobile:", styles['DetailLabel']), Paragraph(invoice_header['customer_mobile'], styles['DetailValue'])],
            [Paragraph("Due Date:", styles['DetailLabel']), Paragraph(invoice_header['due_date'], styles['DetailValue']),
             Paragraph("Address:", styles['DetailLabel']), Paragraph(invoice_header['customer_address'] if invoice_header['customer_address'] else "N/A", styles['DetailValue'])],
            [Paragraph("Status:", styles['DetailLabel']), Paragraph(invoice_header['status'], styles['DetailValue']),
             Paragraph("Email:", styles['DetailLabel']), Paragraph(invoice_header['customer_email'] if invoice_header['customer_email'] else "N/A", styles['DetailValue'])]
        ]

        invoice_customer_table = Table(invoice_customer_data, colWidths=[1.2*inch, 2.5*inch, 1.2*inch, 2.5*inch])
        invoice_customer_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('LEFTPADDING', (0,0), (-1,-1), 5),
            ('RIGHTPADDING', (0,0), (-1,-1), 5),
            ('TOPPADDING', (0,0), (-1,-1), 3),
            ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ]))
        story.append(invoice_customer_table)
        story.append(Spacer(1, 0.2 * inch))

        # --- Line Items Table with GST from Jobs ---
        line_item_data_for_pdf = [[
            Paragraph("S.No.", styles['TableHeading']),
            Paragraph("Description", styles['TableHeading']),
            Paragraph("HSN/SAC", styles['TableHeading']),
            Paragraph("Qty", styles['TableHeading']),
            Paragraph("Unit Price", styles['TableHeading']),
            Paragraph("Taxable Amount", styles['TableHeading']), 
            Paragraph("CGST", styles['TableHeading']),
            Paragraph("SGST", styles['TableHeading']),
            Paragraph("IGST", styles['TableHeading']),
            Paragraph("Total", styles['TableHeading'])
        ]]

        total_cgst_amount = 0.0
        total_sgst_amount = 0.0
        total_igst_amount = 0.0
        grand_total_after_gst = 0.0
        total_taxable_amount_sum = 0.0

        # Get GST details from jobs for each line item
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Store actual GST rates from jobs for proper display
        actual_gst_rates = {'cgst': 0, 'sgst': 0, 'igst': 0}

        for i, item in enumerate(line_items):
            # Get job GST details
            job_id = item.get('job_id')
            gst_type = 'None'
            gst_percentage = 0.0
            gst_amount = 0.0
            gst_category = 'CGST & SGST'  # Default
            
            if job_id:
                try:
                    cursor.execute("""
                        SELECT gst_type, gst_percentage, gst_amount, gst_category 
                        FROM jobs WHERE id = ?
                    """, (job_id,))
                    job_gst = cursor.fetchone()
                    if job_gst:
                        gst_type = job_gst['gst_type'] or 'None'
                        gst_percentage = job_gst['gst_percentage'] or 0.0
                        gst_amount = job_gst['gst_amount'] or 0.0
                        gst_category = job_gst['gst_category'] or 'CGST & SGST'
                        
                        # Store actual rates for display
                        if gst_category == 'IGST':
                            actual_gst_rates['igst'] = gst_percentage
                        else:
                            actual_gst_rates['cgst'] = gst_percentage / 2
                            actual_gst_rates['sgst'] = gst_percentage / 2
                            
                except Exception as e:
                    print(f"[{datetime.datetime.now()}] InvoiceModule: Error fetching job GST for PDF: {e}")
            
            # Calculate line item values properly to avoid double GST
            qty = 1.0  # Default quantity
            amount = item.get('amount_billed_for_job', 0.0) or 0.0
            
            # Determine actual base amount and unit price based on GST type
            if gst_type.lower() == 'inclusive':
                # Amount already includes GST, so calculate base price
                item_taxable_amount = amount / (1 + gst_percentage / 100) if gst_percentage > 0 else amount
                unit_price = item_taxable_amount / qty if qty > 0 else item_taxable_amount
                item_final_total = amount  # Total already includes GST
                item_gst_amount = amount - item_taxable_amount
            elif gst_type.lower() == 'exclusive':
                # Amount is base price, GST needs to be added
                item_taxable_amount = amount
                unit_price = amount / qty if qty > 0 else amount  # Use base amount as unit price
                item_gst_amount = float(gst_amount)  # Use pre-calculated GST amount from job
                item_final_total = amount + item_gst_amount
            else:
                # No GST
                item_taxable_amount = amount
                unit_price = amount / qty if qty > 0 else amount
                item_final_total = amount
                item_gst_amount = 0.0

            # Split GST amount based on category or default logic
            if item_gst_amount > 0:
                # If gst_category is not available, determine based on company/customer state
                # For now, we'll use a simple rule: if percentage >= 18%, it's likely IGST
                # Otherwise, split into CGST/SGST
                if gst_category == 'IGST' or (not gst_category and gst_percentage >= 18):
                    item_cgst = 0.0
                    item_sgst = 0.0
                    item_igst = item_gst_amount
                else:  # CGST & SGST (default or explicitly set)
                    item_cgst = item_gst_amount / 2
                    item_sgst = item_gst_amount / 2
                    item_igst = 0.0
            else:
                item_cgst = 0.0
                item_sgst = 0.0
                item_igst = 0.0

            total_cgst_amount += item_cgst
            total_sgst_amount += item_sgst
            total_igst_amount += item_igst 
            
            # Important: Add only taxable amount to subtotal, final total includes GST
            total_taxable_amount_sum += item_taxable_amount
            grand_total_after_gst += item_final_total

            line_item_data_for_pdf.append([
                Paragraph(str(i + 1), styles['TableContent']),
                Paragraph(item['item_description'], styles['TableContentLeft']),
                Paragraph("N/A", styles['TableContent']),  # HSN/SAC not available
                Paragraph(f"{qty:.0f}", styles['TableContent']),
                Paragraph(f"{currency_symbol} {unit_price:.2f}", styles['TableContent']),
                Paragraph(f"{currency_symbol} {item_taxable_amount:.2f}", styles['TableContent']),
                Paragraph(f"{currency_symbol} {item_cgst:.2f}", styles['TableContent']),
                Paragraph(f"{currency_symbol} {item_sgst:.2f}", styles['TableContent']),
                Paragraph(f"{currency_symbol} {item_igst:.2f}", styles['TableContent']),
                Paragraph(f"{currency_symbol} {item_final_total:.2f}", styles['TableContent'])
            ])
        
        conn.close()  # Close the database connection
        
        # Table style for line items
        line_item_table_style = TableStyle([
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('FONTNAME', (0,0), (-1,0), DEFAULT_BOLD_FONT),
            ('FONTNAME', (0,1), (-1,-1), DEFAULT_FONT),
            ('FONTSIZE', (0,0), (-1,-1), 8),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('ALIGN', (1,0), (1,-1), 'LEFT'), # Description left-aligned
            ('LEFTPADDING', (0,0), (-1,-1), 2),
            ('RIGHTPADDING', (0,0), (-1,-1), 2),
            ('TOPPADDING', (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ])

        col_widths = [0.3*inch, 1.6*inch, 0.7*inch, 0.4*inch, 0.7*inch, 0.8*inch, 0.7*inch, 0.7*inch, 0.7*inch, 0.8*inch]
        line_item_table = Table(line_item_data_for_pdf, colWidths=col_widths)
        line_item_table.setStyle(line_item_table_style)
        story.append(line_item_table)
        story.append(Spacer(1, 0.2 * inch))

        # --- Terms & Conditions and Totals Section (Side-by-Side at Bottom) ---
        terms_and_conditions_text = invoice_header.get('terms_and_conditions', '') or \
                                    "1. All payments are due within 7 days of invoice date.\n" \
                                    "2. Goods once sold will not be taken back.\n" \
                                    "3. E. & O.E."

        notes_story = []
        notes_story.append(Paragraph("<b>Notes:</b>", styles['TermsHeading']))
        notes_story.append(Paragraph(invoice_header['notes'] if invoice_header['notes'] else "N/A", styles['TermsText']))
        notes_story.append(Spacer(1, 0.1 * inch))
        notes_story.append(Paragraph("<b>Terms & Conditions:</b>", styles['TermsHeading']))
        for line in terms_and_conditions_text.split('\n'):
            notes_story.append(Paragraph(line.strip(), styles['TermsText']))

        # Totals data for the right side - Show proper GST breakdown using actual job rates
        gst_breakdown_lines = []
        
        if total_cgst_amount > 0:
            display_cgst_rate = actual_gst_rates['cgst'] if actual_gst_rates['cgst'] > 0 else (total_cgst_amount / (total_taxable_amount_sum + 0.000001)) * 100
            gst_breakdown_lines.append([
                Paragraph(f"CGST ({display_cgst_rate:.1f}%):", styles['TotalLabel']), 
                Paragraph(f"{currency_symbol}{total_cgst_amount:.2f}", styles['TotalValue'])
            ])
        
        if total_sgst_amount > 0:
            display_sgst_rate = actual_gst_rates['sgst'] if actual_gst_rates['sgst'] > 0 else (total_sgst_amount / (total_taxable_amount_sum + 0.000001)) * 100
            gst_breakdown_lines.append([
                Paragraph(f"SGST ({display_sgst_rate:.1f}%):", styles['TotalLabel']), 
                Paragraph(f"{currency_symbol}{total_sgst_amount:.2f}", styles['TotalValue'])
            ])
        
        if total_igst_amount > 0:
            # Use actual GST rate from job data instead of calculated rate
            display_igst_rate = actual_gst_rates['igst'] if actual_gst_rates['igst'] > 0 else (total_igst_amount / (total_taxable_amount_sum + 0.000001)) * 100
            gst_breakdown_lines.append([
                Paragraph(f"IGST ({display_igst_rate:.1f}%):", styles['TotalLabel']), 
                Paragraph(f"{currency_symbol}{total_igst_amount:.2f}", styles['TotalValue'])
            ])

        # Build totals data
        totals_data = [
            [Paragraph("Sub Total:", styles['TotalLabel']), Paragraph(f"{currency_symbol}{total_taxable_amount_sum:.2f}", styles['TotalValue'])]
        ]
        
        # Add GST lines
        totals_data.extend(gst_breakdown_lines)
        
        # Add remaining totals
        totals_data.extend([
            [Paragraph("Total Tax:", styles['TotalLabel']), Paragraph(f"{currency_symbol}{total_cgst_amount + total_sgst_amount + total_igst_amount:.2f}", styles['TotalValue'])],
            [Paragraph("Grand Total:", styles['TotalLabel']), Paragraph(f"{currency_symbol}{grand_total_after_gst:.2f}", styles['TotalValue'])],
            [Paragraph("Amount Paid:", styles['TotalLabel']), Paragraph(f"{currency_symbol}{invoice_header['amount_paid']:.2f}", styles['TotalValue'])],
            [Paragraph("Balance Due:", styles['TotalLabel']), Paragraph(f"{currency_symbol}{(grand_total_after_gst - invoice_header['amount_paid']):.2f}", styles['TotalValue'])]
        ])
        totals_table = Table(totals_data, colWidths=[2.5*inch, 1.5*inch])
        totals_table.setStyle(TableStyle([
            ('ALIGN', (0,0), (-1,-1), 'RIGHT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 2),
            ('BOTTOMPADDING', (0,0), (-1,-1), 2),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ]))

        # Main table to hold notes/terms and totals side-by-side
        bottom_sections_table_data = [[notes_story, totals_table]]
        bottom_sections_table = Table(bottom_sections_table_data, colWidths=[4.0*inch, 3.5*inch]) 
        bottom_sections_table.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('ALIGN', (0,0), (0,0), 'LEFT'),
            ('ALIGN', (1,0), (1,0), 'RIGHT'),
            ('LEFTPADDING', (0,0), (-1,-1), 0),
            ('RIGHTPADDING', (0,0), (-1,-1), 0),
            ('TOPPADDING', (0,0), (-1,-1), 0),
            ('BOTTOMPADDING', (0,0), (-1,-1), 0),
        ]))
        story.append(bottom_sections_table)
        story.append(Spacer(1, 0.2 * inch))

        # --- Signature and Computer Generated Text ---
        story.append(Paragraph("For " + company_name, styles['SignatureLine']))
        story.append(Paragraph("Authorized Signatory", styles['SignatureLine']))
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph("Thank you for your business!", styles['ComputerGenerated']))
        story.append(Paragraph("This is a computer generated invoice and does not require a signature.", styles['ComputerGenerated']))
        
        try:
            doc.build(story)
            messagebox.showinfo("PDF Generated", f"Invoice saved as {os.path.basename(file_path)}")
            subprocess.Popen([file_path], shell=True) # Open the PDF
            print(f"[{datetime.datetime.now()}] InvoiceModule: PDF generated and opened: {file_path}.")
            log_activity(self.user_info['id'], None, "Invoice Printed", f"Printed invoice {invoice_header['invoice_number']}.")
        except Exception as e:
            messagebox.showerror("PDF Error", f"Failed to generate PDF: {e}")
            print(f"[{datetime.datetime.now()}] InvoiceModule: Error generating PDF: {e}")
        print(f"[{datetime.datetime.now()}] InvoiceModule: Print invoice to PDF process finished.")
