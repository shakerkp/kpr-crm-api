import sqlite3
import tkinter as tk
from psycopg2.extras import RealDictCursor
from tkinter import ttk, messagebox, Toplevel, filedialog
import datetime
import os
try:
    import openpyxl
except ImportError:
    openpyxl = None

from db_manager import get_db_connection, log_activity, process_inventory_transaction, get_active_jobs_for_selection
from app_logger import get_logger

logger = get_logger("InventoryModule")

class InventoryModule:
    def __init__(self, parent_frame, current_user_info):
        logger.info("InventoryModule: __init__ started.")
        self.parent_frame = parent_frame
        self.current_user_info = current_user_info
        # Role check for Admin vs Staff
        self.is_admin = str(self.current_user_info.get('role', '')).lower() == 'admin'
        self.selected_item_id = None

        self.item_sku = tk.StringVar()
        self.item_name = tk.StringVar()
        self.item_category_name = tk.StringVar()
        self.item_type = tk.StringVar()
        self.item_size = tk.StringVar()
        self.item_uom = tk.StringVar(value="Pcs")
        self.item_current_stock = tk.DoubleVar(value=0.0)
        self.item_unit_price = tk.DoubleVar(value=0.0)
        self.item_reorder_level = tk.DoubleVar(value=0.0)
        self.item_vendor_name = tk.StringVar()
        
        self.search_query = tk.StringVar()
        self.search_category = tk.StringVar()

        self.categories_map = {}
        self.vendors_map = {}
        self.uom_options = ["Pcs", "Sq.Ft", "Meters", "Rolls", "Kgs", "Ltrs", "Packets", "Boxes", "Sets"]

        self.create_ui()
        self.load_categories_and_vendors()
        self.load_inventory_items()
        logger.info("InventoryModule: __init__ finished.")

    def create_ui(self):
        for widget in self.parent_frame.winfo_children():
            widget.destroy()

        main_frame = ttk.Frame(self.parent_frame, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Inventory & Material Management", font=("Arial", 16, "bold")).pack(anchor=tk.W, pady=(0, 10))
        
        # --- Search Bar ---
        search_frame = ttk.LabelFrame(main_frame, text="Search & Filter", padding="10")
        search_frame.pack(fill=tk.X, padx=10, pady=5)
        
        ttk.Label(search_frame, text="Search (Name/SKU/Size):").pack(side=tk.LEFT, padx=5)
        ttk.Entry(search_frame, textvariable=self.search_query, width=25).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(search_frame, text="Category:").pack(side=tk.LEFT, padx=5)
        self.search_category_cb = ttk.Combobox(search_frame, textvariable=self.search_category, state="readonly", width=20)
        self.search_category_cb.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(search_frame, text="Search", command=self.load_inventory_items).pack(side=tk.LEFT, padx=5)
        ttk.Button(search_frame, text="Clear", command=self.clear_search).pack(side=tk.LEFT, padx=5)

        # --- Admin Only Form Frame ---
        if self.is_admin:
            form_frame = ttk.LabelFrame(main_frame, text="Item Details (Admin Only)", padding="10")
            form_frame.pack(fill=tk.X, padx=10, pady=5)

            form_frame.columnconfigure(1, weight=1)
            form_frame.columnconfigure(3, weight=1)
            form_frame.columnconfigure(5, weight=1)

            # ROW 0
            ttk.Label(form_frame, text="SKU/Code:").grid(row=0, column=0, padx=5, pady=5, sticky="w")
            ttk.Entry(form_frame, textvariable=self.item_sku).grid(row=0, column=1, padx=5, pady=5, sticky="ew")

            ttk.Label(form_frame, text="Item Name * :").grid(row=0, column=2, padx=5, pady=5, sticky="w")
            ttk.Entry(form_frame, textvariable=self.item_name).grid(row=0, column=3, padx=5, pady=5, sticky="ew")

            ttk.Label(form_frame, text="Category * :").grid(row=0, column=4, padx=5, pady=5, sticky="w")
            cat_frame = ttk.Frame(form_frame)
            cat_frame.grid(row=0, column=5, padx=5, pady=5, sticky="ew")
            self.category_combobox = ttk.Combobox(cat_frame, textvariable=self.item_category_name, state="readonly")
            self.category_combobox.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Button(cat_frame, text="+", width=3, command=self.manage_categories).pack(side=tk.LEFT, padx=(2,0))

            # ROW 1
            ttk.Label(form_frame, text="Type (e.g. Glossy):").grid(row=1, column=0, padx=5, pady=5, sticky="w")
            ttk.Entry(form_frame, textvariable=self.item_type).grid(row=1, column=1, padx=5, pady=5, sticky="ew")

            ttk.Label(form_frame, text="Size (e.g. 8x4):").grid(row=1, column=2, padx=5, pady=5, sticky="w")
            ttk.Entry(form_frame, textvariable=self.item_size).grid(row=1, column=3, padx=5, pady=5, sticky="ew")

            ttk.Label(form_frame, text="Unit (UoM):").grid(row=1, column=4, padx=5, pady=5, sticky="w")
            ttk.Combobox(form_frame, textvariable=self.item_uom, values=self.uom_options, state="readonly").grid(row=1, column=5, padx=5, pady=5, sticky="ew")

            # ROW 2
            ttk.Label(form_frame, text="Current Stock:").grid(row=2, column=0, padx=5, pady=5, sticky="w")
            ttk.Entry(form_frame, textvariable=self.item_current_stock).grid(row=2, column=1, padx=5, pady=5, sticky="ew")

            ttk.Label(form_frame, text="Reorder Level:").grid(row=2, column=2, padx=5, pady=5, sticky="w")
            ttk.Entry(form_frame, textvariable=self.item_reorder_level).grid(row=2, column=3, padx=5, pady=5, sticky="ew")

            ttk.Label(form_frame, text="Unit Price:").grid(row=2, column=4, padx=5, pady=5, sticky="w")
            ttk.Entry(form_frame, textvariable=self.item_unit_price).grid(row=2, column=5, padx=5, pady=5, sticky="ew")

            # ROW 3
            ttk.Label(form_frame, text="Vendor:").grid(row=3, column=0, padx=5, pady=5, sticky="w")
            ven_frame = ttk.Frame(form_frame)
            ven_frame.grid(row=3, column=1, padx=5, pady=5, sticky="ew")
            self.vendor_combobox = ttk.Combobox(ven_frame, textvariable=self.item_vendor_name, state="readonly")
            self.vendor_combobox.pack(side=tk.LEFT, fill=tk.X, expand=True)
            ttk.Button(ven_frame, text="+", width=3, command=self.manage_vendors).pack(side=tk.LEFT, padx=(2,0))

        # --- Buttons Frame ---
        button_frame = ttk.Frame(main_frame, padding="10")
        button_frame.pack(fill=tk.X, padx=10, pady=5)

        if self.is_admin:
            ttk.Button(button_frame, text="Add Item", command=self.add_item).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="Update Item", command=self.update_item).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="Delete Item", command=self.delete_item).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="Clear Form", command=self.clear_form).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="📊 Export Excel", command=self.export_to_excel).pack(side=tk.RIGHT, padx=5)
            ttk.Button(button_frame, text="📦 Stock In/Out", command=lambda: self.open_usage_entry(is_admin_mode=True)).pack(side=tk.RIGHT, padx=5)
        else:
            # Staff Only Button
            ttk.Button(button_frame, text="🛠️ ENTER MATERIAL USAGE / WASTAGE", command=lambda: self.open_usage_entry(is_admin_mode=False)).pack(side=tk.LEFT, padx=5)

        # --- Treeview ---
        tree_frame = ttk.Frame(main_frame, padding="10")
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        if self.is_admin:
            columns = ("ID", "SKU", "Name", "Category", "Type", "Size", "Stock", "UoM", "Price", "Reorder", "Vendor")
        else:
            columns = ("ID", "SKU", "Name", "Category", "Type", "Size", "UoM") 

        self.inventory_tree = ttk.Treeview(tree_frame, columns=columns, show="headings", selectmode="browse")

        for col in columns:
            self.inventory_tree.heading(col, text=col)
            width = 120 if col == "Name" else (50 if col in ("ID", "UoM") else 80)
            self.inventory_tree.column(col, width=width, anchor=tk.CENTER if col in ("ID", "Stock", "UoM") else tk.W)

        if self.is_admin:
            self.inventory_tree.tag_configure('low_stock', background='#ffcccc', foreground='red')

        self.inventory_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.inventory_tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.inventory_tree.config(yscrollcommand=scrollbar.set)
        self.inventory_tree.bind("<<TreeviewSelect>>", self.on_item_select)

    def load_categories_and_vendors(self):
        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("SELECT id, name FROM inventory_categories ORDER BY name")
            categories = cursor.fetchall()
            self.categories_map = {cat['name']: cat['id'] for cat in categories}
            cat_names = list(self.categories_map.keys())
            
            if self.is_admin:
                self.category_combobox['values'] = cat_names

            self.search_category_cb['values'] = ["All Categories"] + cat_names
            if not self.search_category.get():
                self.search_category.set("All Categories")

            if self.is_admin:
                cursor.execute("SELECT id, name FROM vendors ORDER BY name")
                vendors = cursor.fetchall()
                self.vendors_map = {vendor['name']: vendor['id'] for vendor in vendors}
                self.vendor_combobox['values'] = list(self.vendors_map.keys())
        except Exception as e:
            logger.error(f"Error loading filters: {e}")
        finally:
            conn.close()

    def load_inventory_items(self):
        for i in self.inventory_tree.get_children():
            self.inventory_tree.delete(i)

        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            query = """
                SELECT ii.id, ii.sku, ii.name, ic.name as category_name, 
                       ii.item_type, ii.item_size, ii.current_stock, ii.uom,
                       ii.unit_price, ii.reorder_level, v.name as vendor_name
                FROM inventory_items ii
                LEFT JOIN inventory_categories ic ON ii.category_id = ic.id
                LEFT JOIN vendors v ON ii.vendor_id = v.id
                WHERE 1=1
            """
            params = []
            search_text = self.search_query.get().strip()
            if search_text:
                query += " AND (ii.name LIKE ? OR ii.sku LIKE ? OR ii.item_size LIKE ? OR ii.item_type LIKE ?)"
                params.extend([f"%{search_text}%", f"%{search_text}%", f"%{search_text}%", f"%{search_text}%"])
                
            cat_filter = self.search_category.get()
            if cat_filter and cat_filter != "All Categories":
                query += " AND ic.name = ?"
                params.append(cat_filter)
                
            query += " ORDER BY ii.name"
            
            cursor.execute(query, tuple(params))
            for item in cursor.fetchall():
                if self.is_admin:
                    stock = float(item['current_stock']) if item['current_stock'] is not None else 0.0
                    reorder = float(item['reorder_level']) if item['reorder_level'] is not None else 0.0
                    tag = ('low_stock',) if (stock <= reorder and reorder > 0) else ()
                    self.inventory_tree.insert("", "end", values=(
                        item['id'], item['sku'] or "", item['name'], item['category_name'] or "Unknown",
                        item['item_type'] or "", item['item_size'] or "", stock, item['uom'] or "Pcs", 
                        f"{item['unit_price']:.2f}", reorder, item['vendor_name'] or ""
                    ), tags=tag)
                else:
                    self.inventory_tree.insert("", "end", values=(
                        item['id'], item['sku'] or "", item['name'], item['category_name'] or "Unknown",
                        item['item_type'] or "", item['item_size'] or "", item['uom'] or "Pcs"
                    ))
        finally:
            conn.close()

    def clear_search(self):
        self.search_query.set("")
        self.search_category.set("All Categories")
        self.load_inventory_items()

    def on_item_select(self, event):
        selected = self.inventory_tree.selection()
        if selected:
            vals = self.inventory_tree.item(selected[0], 'values')
            self.selected_item_id = vals[0]
            if self.is_admin:
                self.item_sku.set(vals[1] if vals[1] != 'None' else "")
                self.item_name.set(vals[2])
                self.item_category_name.set(vals[3])
                self.item_type.set(vals[4] if vals[4] != 'None' else "")
                self.item_size.set(vals[5] if vals[5] != 'None' else "")
                self.item_current_stock.set(vals[6])
                self.item_uom.set(vals[7])
                self.item_unit_price.set(vals[8])
                self.item_reorder_level.set(vals[9])
                self.item_vendor_name.set(vals[10] if vals[10] != 'None' else "")
            else:
                self.item_name.set(vals[2])
                self.item_uom.set(vals[6])

    def clear_form(self):
        self.selected_item_id = None
        if self.is_admin:
            self.item_sku.set("")
            self.item_name.set("")
            self.item_category_name.set("")
            self.item_type.set("")
            self.item_size.set("")
            self.item_uom.set("Pcs")
            self.item_current_stock.set(0.0)
            self.item_unit_price.set(0.0)
            self.item_reorder_level.set(0.0)
            self.item_vendor_name.set("")

    def add_item(self):
        name = self.item_name.get().strip()
        sku = self.item_sku.get().strip()
        category_name = self.item_category_name.get().strip()
        itype = self.item_type.get().strip()
        isize = self.item_size.get().strip()
        
        if not name or not category_name:
            messagebox.showerror("Input Error", "Item Name and Category are required.")
            return
        if category_name not in self.categories_map:
            messagebox.showerror("Input Error", "Selected Category is not valid.")
            return

        category_id = self.categories_map[category_name]
        vendor_id = None
        vendor_name = self.item_vendor_name.get().strip()
        if vendor_name:
            if vendor_name not in self.vendors_map:
                messagebox.showerror("Input Error", "Selected Vendor is not valid.")
                return
            vendor_id = self.vendors_map[vendor_name]

        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                INSERT INTO inventory_items (sku, name, category_id, item_type, item_size, current_stock, uom, unit_price, reorder_level, vendor_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (sku, name, category_id, itype, isize, self.item_current_stock.get(), self.item_uom.get(),
                  self.item_unit_price.get(), self.item_reorder_level.get(), vendor_id))
            conn.commit()
            messagebox.showinfo("Success", "Item added successfully!")
            log_activity(self.current_user_info['id'], self.current_user_info['username'], "Inventory Add", f"Added item: {name}")
            self.clear_form()
            self.load_inventory_items()
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Failed to add item: {e}")
        finally:
            conn.close()

    def update_item(self):
        if not self.selected_item_id:
            messagebox.showwarning("Selection Error", "Please select an item to update.")
            return

        name = self.item_name.get().strip()
        sku = self.item_sku.get().strip()
        category_name = self.item_category_name.get().strip()
        itype = self.item_type.get().strip()
        isize = self.item_size.get().strip()
        
        if not name or not category_name:
            messagebox.showerror("Input Error", "Item Name and Category are required.")
            return
        if category_name not in self.categories_map:
            messagebox.showerror("Input Error", "Selected Category is not valid.")
            return

        category_id = self.categories_map[category_name]
        vendor_id = None
        vendor_name = self.item_vendor_name.get().strip()
        if vendor_name:
            if vendor_name not in self.vendors_map:
                messagebox.showerror("Input Error", "Selected Vendor is not valid.")
                return
            vendor_id = self.vendors_map[vendor_name]

        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute("""
                UPDATE inventory_items 
                SET sku=?, name=?, category_id=?, item_type=?, item_size=?, current_stock=?, uom=?,
                    unit_price=?, reorder_level=?, vendor_id=?, last_updated=CURRENT_TIMESTAMP
                WHERE id=?
            """, (sku, name, category_id, itype, isize, self.item_current_stock.get(), self.item_uom.get(),
                  self.item_unit_price.get(), self.item_reorder_level.get(), vendor_id, self.selected_item_id))
            conn.commit()
            messagebox.showinfo("Success", "Item updated successfully!")
            log_activity(self.current_user_info['id'], self.current_user_info['username'], "Inventory Update", f"Updated ID: {self.selected_item_id}")
            self.clear_form()
            self.load_inventory_items()
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Failed to update item: {e}")
        finally:
            conn.close()

    def delete_item(self):
        if not self.selected_item_id:
            messagebox.showwarning("Selection Error", "Please select an item to delete.")
            return
        if messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this item?"):
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute("DELETE FROM inventory_items WHERE id=%s", (self.selected_item_id,))
                conn.commit()
                messagebox.showinfo("Success", "Item deleted successfully!")
                log_activity(self.current_user_info['id'], self.current_user_info['username'], "Inventory Delete", f"Deleted ID: {self.selected_item_id}")
                self.clear_form()
                self.load_inventory_items()
            except Exception as e:
                conn.rollback()
                messagebox.showerror("Error", f"Failed to delete item: {e}")
            finally:
                conn.close()

    def open_usage_entry(self, is_admin_mode=False):
        if not self.selected_item_id:
            messagebox.showwarning("Action required", "Please select a material from the list first.")
            return

        # ── Role guard: Staff/Sub-Staff can NEVER open admin mode ──────────────
        role = str(self.current_user_info.get('role', '')).lower()
        if role in ('staff', 'sub_staff') and is_admin_mode:
            messagebox.showerror("Access Denied", "You don't have permission to perform stock adjustments.")
            return
        # Force non-admin mode for staff/sub_staff regardless of how this was called
        if role in ('staff', 'sub_staff'):
            is_admin_mode = False

        # ── Load active jobs for the dropdown ──────────────────────────────────
        active_jobs = get_active_jobs_for_selection()
        # Build display strings: "Job#ID - Type: Description (Customer)"
        job_display_list = ["-- No Job / General --"]
        job_id_map = {}   # display_str -> job_id
        for j in active_jobs:
            desc = j.get('description') or ''
            label = f"Job#{j['id']} | {j['job_type']} | {j['customer_name']}"
            if desc:
                label += f" | {desc[:30]}"
            job_display_list.append(label)
            job_id_map[label] = j['id']

        # ── Window setup ────────────────────────────────────────────────────────
        adj_win = Toplevel(self.parent_frame)
        adj_win.title("Material Usage / Wastage Entry" if not is_admin_mode else "Stock Adjustment")
        adj_win.geometry("560x420")
        adj_win.resizable(False, False)
        adj_win.grab_set()
        adj_win.attributes("-topmost", True)
        adj_win.lift()
        adj_win.focus_force()

        # Header
        header_frame = ttk.Frame(adj_win, padding=(10, 10, 10, 5))
        header_frame.pack(fill=tk.X)
        ttk.Label(header_frame, text="Material Entry", font=("Arial", 14, "bold")).pack(side=tk.LEFT)

        # Material info banner
        banner = tk.Frame(adj_win, bg="#E3F2FD", padx=10, pady=8)
        banner.pack(fill=tk.X, padx=10)
        uom_val = self.item_uom.get() if hasattr(self, 'item_uom') else "Pcs"
        mat_text = f"📦  {self.item_name.get()}   |   UoM: {uom_val}"
        if is_admin_mode:
            mat_text += f"   |   Current Stock: {self.item_current_stock.get()} {uom_val}"
        tk.Label(banner, text=mat_text, bg="#E3F2FD", font=("Arial", 10, "bold"), fg="#0D47A1").pack(anchor="w")

        # ── Form ────────────────────────────────────────────────────────────────
        frame = ttk.Frame(adj_win, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        # Row 0 – Action Type
        ttk.Label(frame, text="Action Type *:").grid(row=0, column=0, sticky="w", pady=6, padx=(0, 10))
        action_var = tk.StringVar(value="Usage (-)")
        options = ["Stock In (+)", "Usage (-)", "Wastage (-)"] if is_admin_mode else ["Usage (-)", "Wastage (-)"]
        action_cb = ttk.Combobox(frame, textvariable=action_var, values=options, state="readonly", width=20)
        action_cb.grid(row=0, column=1, sticky="ew", pady=6)

        # Row 1 – Quantity
        ttk.Label(frame, text=f"Quantity ({uom_val}) *:").grid(row=1, column=0, sticky="w", pady=6, padx=(0, 10))
        qty_var = tk.DoubleVar(value=1.0)
        ttk.Entry(frame, textvariable=qty_var, width=20).grid(row=1, column=1, sticky="ew", pady=6)

        # Row 2 – Job Selection (mandatory for Usage/Wastage by staff)
        ttk.Label(frame, text="Linked Job:").grid(row=2, column=0, sticky="w", pady=6, padx=(0, 10))
        job_sel_var = tk.StringVar(value=job_display_list[0])
        job_cb = ttk.Combobox(frame, textvariable=job_sel_var, values=job_display_list, state="readonly", width=50)
        job_cb.grid(row=2, column=1, sticky="ew", pady=6)
        ttk.Label(frame, text="(Select the job this material was used for)", foreground="gray",
                  font=("Arial", 8)).grid(row=3, column=1, sticky="w")

        # Row 4 – Remarks
        ttk.Label(frame, text="Remarks:").grid(row=4, column=0, sticky="w", pady=6, padx=(0, 10))
        remarks_var = tk.StringVar()
        ttk.Entry(frame, textvariable=remarks_var).grid(row=4, column=1, sticky="ew", pady=6)

        # ── Entered-by info (non-admin) ─────────────────────────────────────────
        if not is_admin_mode:
            user_frame = tk.Frame(adj_win, bg="#FFF9C4", padx=10, pady=6)
            user_frame.pack(fill=tk.X, padx=10)
            entered_by = self.current_user_info.get('username', 'Unknown')
            tk.Label(user_frame, text=f"✍  Entry by: {entered_by}  |  Time: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
                     bg="#FFF9C4", font=("Arial", 9), fg="#555").pack(anchor="w")

        # ── Save ────────────────────────────────────────────────────────────────
        def save_entry():
            qty = qty_var.get()
            if qty <= 0:
                messagebox.showerror("Error", "Quantity must be greater than zero.")
                return

            action_sel = action_var.get()
            trans_type = "Stock In" if "In" in action_sel else ("Usage" if "Usage" in action_sel else "Wastage")

            # Resolve selected job id
            selected_job_label = job_sel_var.get()
            linked_job_id = job_id_map.get(selected_job_label, None)

            # For staff: Usage/Wastage must be linked to a job (warn, but allow)
            if not is_admin_mode and trans_type in ("Usage", "Wastage") and linked_job_id is None:
                if not messagebox.askyesno("No Job Selected",
                        "No job is selected.\nDo you want to save this entry without linking to a job?"):
                    return

            success = process_inventory_transaction(
                item_id=self.selected_item_id,
                user_id=self.current_user_info['id'],
                trans_type=trans_type,
                qty=qty,
                remarks=remarks_var.get(),
                job_id=linked_job_id
            )

            if success:
                log_activity(
                    self.current_user_info['id'],
                    self.current_user_info.get('username', ''),
                    f"Inventory {trans_type}",
                    f"{trans_type} of {qty} {uom_val} for '{self.item_name.get()}'"
                    + (f" | Job#{linked_job_id}" if linked_job_id else "")
                    + (f" | Remarks: {remarks_var.get()}" if remarks_var.get() else "")
                )
                messagebox.showinfo("Success",
                    f"✅ {trans_type} of {qty} {uom_val} recorded successfully!"
                    + (f"\nLinked to Job#{linked_job_id}" if linked_job_id else ""))
                self.load_inventory_items()
                adj_win.destroy()
            else:
                messagebox.showerror("Error", "Database error. Please try again.")

        btn_frame = ttk.Frame(adj_win, padding=(10, 5, 10, 12))
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="💾  Save Entry", command=save_entry).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Cancel", command=adj_win.destroy).pack(side=tk.LEFT, padx=5)

    def export_to_excel(self):
        if openpyxl is None:
            messagebox.showerror("Dependency Missing", "Please install 'openpyxl' to export to Excel.\nRun: pip install openpyxl")
            return
            
        items = self.inventory_tree.get_children()
        if not items:
            messagebox.showinfo("Empty", "No data to export.")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx", 
            filetypes=[("Excel Files", "*.xlsx")],
            title="Save Inventory Report",
            initialfile=f"Inventory_Report_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx"
        )
        if not file_path:
            return

        try:
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "Inventory Status"
            
            headers = ["ID", "SKU", "Item Name", "Category", "Type", "Size", "Current Stock", "UoM", "Unit Price", "Reorder Level", "Vendor"]
            ws.append(headers)
            
            for item in items:
                row_data = self.inventory_tree.item(item, 'values')
                ws.append(row_data)
                
            wb.save(file_path)
            messagebox.showinfo("Success", f"Inventory exported successfully to:\n{file_path}")
            log_activity(self.current_user_info['id'], self.current_user_info['username'], "Export Excel", "Exported inventory data")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to create Excel file: {e}")

    def manage_categories(self):
        ManageEntitiesDialog(self.parent_frame, "Manage Categories", "inventory_categories", self.load_categories_and_vendors)

    def manage_vendors(self):
        ManageEntitiesDialog(self.parent_frame, "Manage Vendors", "vendors", self.load_categories_and_vendors)

class ManageEntitiesDialog(Toplevel):
    def __init__(self, parent, title, table_name, refresh_callback):
        super().__init__(parent)
        self.title(title)
        self.geometry("450x400")
        self.transient(parent)
        self.grab_set()
        self.table_name = table_name
        self.refresh_callback = refresh_callback
        self.name_var = tk.StringVar()
        self.selected_id = None 
        self.create_dialog_ui()
        self.load_entities()

    def create_dialog_ui(self):
        form_frame = ttk.Frame(self, padding="10")
        form_frame.pack(fill=tk.X, pady=5)
        ttk.Label(form_frame, text="Name:").pack(side=tk.LEFT, padx=5)
        ttk.Entry(form_frame, textvariable=self.name_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        ttk.Button(form_frame, text="Add", command=self.add_entity).pack(side=tk.LEFT, padx=2)
        ttk.Button(form_frame, text="Update", command=self.update_entity).pack(side=tk.LEFT, padx=2)

        tree_frame = ttk.Frame(self, padding="10")
        tree_frame.pack(fill=tk.BOTH, expand=True)

        self.tree = ttk.Treeview(tree_frame, columns=("ID", "Name"), show="headings")
        self.tree.heading("ID", text="ID")
        self.tree.heading("Name", text="Name")
        self.tree.column("ID", width=50, anchor=tk.CENTER)
        self.tree.column("Name", width=350, anchor=tk.W)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.config(yscrollcommand=scrollbar.set)
        
        self.tree.bind("<<TreeviewSelect>>", self.on_select)

        button_frame = ttk.Frame(self, padding="10")
        button_frame.pack(fill=tk.X, pady=5)
        ttk.Button(button_frame, text="Delete Selected", command=self.delete_entity).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Close", command=self.destroy).pack(side=tk.RIGHT, padx=5)

    def load_entities(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(f"SELECT id, name FROM {self.table_name} ORDER BY name")
            for entity in cursor.fetchall():
                self.tree.insert("", "end", values=(entity['id'], entity['name']))
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to load {self.table_name}: {e}")
        finally:
            conn.close()

    def on_select(self, event):
        selected = self.tree.selection()
        if selected:
            item = self.tree.item(selected[0], 'values')
            self.selected_id = item[0]
            self.name_var.set(item[1])

    def add_entity(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Input Error", "Name cannot be empty.")
            return
        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(f"INSERT INTO {self.table_name} (name) VALUES (%s)", (name,))
            conn.commit()
            messagebox.showinfo("Success", f"{name} added successfully!")
            self.name_var.set("")
            self.selected_id = None
            self.load_entities()
            self.refresh_callback()
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", f"{name} already exists.")
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Failed to add: {e}")
        finally:
            conn.close()

    def update_entity(self):
        if not self.selected_id:
            messagebox.showwarning("Selection Error", "Please select an item from the list to update.")
            return
        new_name = self.name_var.get().strip()
        if not new_name:
            messagebox.showerror("Input Error", "Name cannot be empty.")
            return
        conn = get_db_connection()
        try:
            cursor = conn.cursor(cursor_factory=RealDictCursor)
            cursor.execute(f"UPDATE {self.table_name} SET name=%s WHERE id=%s", (new_name, self.selected_id))
            conn.commit()
            messagebox.showinfo("Success", f"Updated to '{new_name}' successfully!")
            self.name_var.set("")
            self.selected_id = None
            self.load_entities()
            self.refresh_callback()
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", f"'{new_name}' already exists.")
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Failed to update: {e}")
        finally:
            conn.close()

    def delete_entity(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showwarning("Selection Error", "Please select an item to delete.")
            return
        entity_id = self.tree.item(selected_item[0], 'values')[0]
        entity_name = self.tree.item(selected_item[0], 'values')[1]
        if messagebox.askyesno("Confirm Delete", f"Delete '{entity_name}'? This cannot be undone."):
            conn = get_db_connection()
            try:
                cursor = conn.cursor(cursor_factory=RealDictCursor)
                cursor.execute(f"DELETE FROM {self.table_name} WHERE id=%s", (entity_id,))
                conn.commit()
                messagebox.showinfo("Success", f"'{entity_name}' deleted successfully!")
                self.name_var.set("")
                self.selected_id = None
                self.load_entities()
                self.refresh_callback()
            except Exception as e:
                conn.rollback()
                messagebox.showerror("Error", f"Failed to delete: {e}")
            finally:
                conn.close()
