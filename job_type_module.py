# job_type_module.py
# FIX: Replaced all sqlite3.connect('kprlab.db') with get_db_connection()
# FIX: Added try/finally for safe connection handling
# FIX: Row objects now support column-name access (via db_manager row_factory)
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from db_manager import get_db_connection
from app_logger import get_logger

logger = get_logger("JobTypeModule")

class JobTypeModule:
    def __init__(self, parent, user_info, on_job_types_changed=None):
        self.parent = parent
        self.user_info = user_info
        self.on_job_types_changed = on_job_types_changed
        self.create_ui()

    def create_ui(self):
        frame = ttk.Frame(self.parent, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        category_frame = ttk.Frame(frame)
        category_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(category_frame, text="Select Category:").pack(side=tk.LEFT, padx=5)
        self.category_dropdown = ttk.Combobox(category_frame, state="readonly")
        self.category_dropdown.pack(side=tk.LEFT, padx=5)
        self.category_dropdown.bind("<<ComboboxSelected>>", self.on_category_selected)

        ttk.Button(category_frame, text="Add Category", command=self.add_category).pack(side=tk.LEFT, padx=5)
        ttk.Button(category_frame, text="Update Category", command=self.update_category).pack(side=tk.LEFT, padx=5)
        ttk.Button(category_frame, text="Delete Category", command=self.delete_category).pack(side=tk.LEFT, padx=5)

        entry_frame = ttk.Frame(frame)
        entry_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(entry_frame, text="Job Type Name:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.name_entry = ttk.Entry(entry_frame)
        self.name_entry.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(button_frame, text="Add Job Type", command=self.add_job_type).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Update Job Type", command=self.update_job_type).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Delete Job Type", command=self.delete_job_type).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Clear Fields", command=self.clear_fields).pack(side=tk.LEFT, padx=5)

        self.tree = ttk.Treeview(frame, columns=("ID", "Name"), show="headings")
        self.tree.heading("ID", text="ID")
        self.tree.heading("Name", text="Name")
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        self.load_categories()

    def load_categories(self):
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT category FROM job_types ORDER BY category")
            categories = [row[0] for row in cursor.fetchall()]
            self.category_dropdown['values'] = categories
            if categories:
                self.category_dropdown.set(categories[0])
                self.load_job_types()
        except Exception as e:
            logger.error(f"JobTypeModule: Error loading categories: {e}")
        finally:
            conn.close()

    def add_category(self):
        new_category = simpledialog.askstring("Add Category", "Enter new category name:")
        if not new_category:
            return
        new_category = new_category.strip()
        if not new_category:
            messagebox.showerror("Error", "Category name cannot be empty.")
            return
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO job_types (category, name) VALUES (?, ?)", (new_category, 'Default Job Type'))
            conn.commit()
            messagebox.showinfo("Success", f"Category '{new_category}' added.")
            self.load_categories()
            if self.on_job_types_changed:
                self.on_job_types_changed()
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Failed to add category: {e}")
            logger.error(f"JobTypeModule: Error adding category: {e}")
        finally:
            conn.close()

    def update_category(self):
        old_category = self.category_dropdown.get()
        if not old_category:
            messagebox.showerror("Error", "Select a category to update.")
            return
        new_category = simpledialog.askstring("Update Category", "Enter new category name:", initialvalue=old_category)
        if not new_category:
            return
        new_category = new_category.strip()
        if not new_category:
            messagebox.showerror("Error", "Category name cannot be empty.")
            return
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE job_types SET category=? WHERE category=?", (new_category, old_category))
            conn.commit()
            messagebox.showinfo("Success", f"Category updated to '{new_category}'.")
            self.load_categories()
            if self.on_job_types_changed:
                self.on_job_types_changed()
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Failed to update category: {e}")
            logger.error(f"JobTypeModule: Error updating category: {e}")
        finally:
            conn.close()

    def delete_category(self):
        category = self.category_dropdown.get()
        if not category:
            messagebox.showerror("Error", "Select a category to delete.")
            return
        if not messagebox.askyesno("Confirm Delete", f"Delete category '{category}' and all its job types?"):
            return
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM job_types WHERE category=?", (category,))
            conn.commit()
            messagebox.showinfo("Deleted", f"Category '{category}' deleted.")
            self.load_categories()
            if self.on_job_types_changed:
                self.on_job_types_changed()
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Failed to delete category: {e}")
            logger.error(f"JobTypeModule: Error deleting category: {e}")
        finally:
            conn.close()

    def load_job_types(self):
        category = self.category_dropdown.get()
        if not category:
            return
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM job_types WHERE category=? ORDER BY name", (category,))
            rows = cursor.fetchall()
            self.tree.delete(*self.tree.get_children())
            for row in rows:
                self.tree.insert("", tk.END, values=(row['id'], row['name']))
        except Exception as e:
            logger.error(f"JobTypeModule: Error loading job types: {e}")
        finally:
            conn.close()

    def on_category_selected(self, event):
        self.load_job_types()
        self.clear_fields()

    def add_job_type(self):
        category = self.category_dropdown.get()
        name = self.name_entry.get().strip()
        if not category or not name:
            messagebox.showerror("Error", "Please fill all fields.")
            return
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO job_types (category, name) VALUES (?, ?)", (category, name))
            conn.commit()
            self.load_job_types()
            self.clear_fields()
            if self.on_job_types_changed:
                self.on_job_types_changed()
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Failed to add job type: {e}")
            logger.error(f"JobTypeModule: Error adding job type: {e}")
        finally:
            conn.close()

    def update_job_type(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror("Error", "Please select a job type to update.")
            return
        job_id = self.tree.item(selected[0])['values'][0]
        name = self.name_entry.get().strip()
        if not name:
            messagebox.showerror("Error", "Please enter job type name.")
            return
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE job_types SET name=? WHERE id=?", (name, job_id))
            conn.commit()
            self.load_job_types()
            self.clear_fields()
            if self.on_job_types_changed:
                self.on_job_types_changed()
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Failed to update job type: {e}")
            logger.error(f"JobTypeModule: Error updating job type: {e}")
        finally:
            conn.close()

    def delete_job_type(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror("Error", "Please select a job type to delete.")
            return
        job_id = self.tree.item(selected[0])['values'][0]
        if not messagebox.askyesno("Confirm Delete", "Delete this job type?"):
            return
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM job_types WHERE id=?", (job_id,))
            conn.commit()
            self.load_job_types()
            self.clear_fields()
            if self.on_job_types_changed:
                self.on_job_types_changed()
        except Exception as e:
            conn.rollback()
            messagebox.showerror("Error", f"Failed to delete job type: {e}")
            logger.error(f"JobTypeModule: Error deleting job type: {e}")
        finally:
            conn.close()

    def on_tree_select(self, event):
        selected = self.tree.selection()
        if selected:
            self.name_entry.delete(0, tk.END)
            self.name_entry.insert(0, self.tree.item(selected[0])['values'][1])

    def clear_fields(self):
        self.name_entry.delete(0, tk.END)
        self.tree.selection_remove(self.tree.selection())
