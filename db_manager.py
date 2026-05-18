# db_manager.py
import sqlite3
import datetime
import os
import hashlib
from decimal import Decimal, getcontext

# Set the precision for Decimal calculations to avoid floating-point issues
getcontext().prec = 28  # Set precision to 28 decimal places for financial accuracy

# --- Global Database Configuration ---
DATABASE_NAME = "kprlab.db"
ACTIVITY_LOG_TABLE = "activity_log"
SETTINGS_TABLE = "settings"
BACKUP_DIR = 'backups'


# --- Database Connection Management ---
def get_db_connection():
    """
    Establishes and returns a connection to the SQLite database.
    Sets row_factory to sqlite3.Row to allow accessing columns by name.
    """
    try:
        conn = sqlite3.connect(DATABASE_NAME)
        # Configure row_factory to return rows as dictionary-like objects
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error establishing database connection: {e}")
        raise  # Re-raise the exception to indicate a critical failure


# --- Password Hashing and Verification ---
def hash_password(password):
    """Hashes a password using SHA256 for secure storage."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(stored_password_hash, provided_password):
    """Verifies a provided password against a stored hash."""
    return stored_password_hash == hash_password(provided_password)


# --- User Management Functions ---
def get_user_by_id(user_id):
    """Fetches a single user by their ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    user = None
    try:
        # Dynamically check for columns to ensure compatibility with older schemas
        cursor.execute("PRAGMA table_info(users)")
        user_columns = [col[1] for col in cursor.fetchall()]

        select_columns = ["id", "username", "role", "is_active"]
        if "full_name" in user_columns:
            select_columns.append("full_name")
        if "email" in user_columns:
            select_columns.append("email")
        if "phone" in user_columns:
            select_columns.append("phone")

        cursor.execute(f"SELECT {', '.join(select_columns)} FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        if user:
            return dict(user)  # Convert Row object to dictionary
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching user by ID ({user_id}): {e}")
    finally:
        conn.close()
    return user


def log_activity(user_id, username_from_caller, activity_type, description):
    """
    Logs an activity into the activity_log table.
    Prioritizes username_from_caller if provided, otherwise fetches internally.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    username = username_from_caller if username_from_caller is not None else "System"
    # If user_id is provided and username is still "System", try to fetch the username
    if user_id and username == "System":
        user_info = get_user_by_id(user_id)
        if user_info:
            username = user_info.get('username', 'System')

    try:
        cursor.execute(f"INSERT INTO {ACTIVITY_LOG_TABLE} (user_id, username, activity_type, description, timestamp) VALUES (?, ?, ?, ?, ?)",
                       (user_id, username, activity_type, description, timestamp))
        conn.commit()
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error logging activity: {e}")
    finally:
        conn.close()


def create_tables():
    """
    Ensures all necessary tables exist in the database.
    Adds new columns if they don't exist without dropping existing data.
    This function is made robust to handle missing columns from previous versions.
    """
    print(f"[{datetime.datetime.now()}] DB: Ensuring tables are created. Checking for existing tables and adding new columns if necessary.")
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Users Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                is_active INTEGER DEFAULT 1,
                full_name TEXT,
                email TEXT,
                phone TEXT
            )
        """)
        # Add missing columns to users table
        cursor.execute("PRAGMA table_info(users)")
        user_cols = [col[1] for col in cursor.fetchall()]
        if 'full_name' not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'full_name' to 'users' table.")
        if 'email' not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'email' to 'users' table.")
        if 'phone' not in user_cols:
            cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'phone' to 'users' table.")
        print(f"[{datetime.datetime.now()}] DB: 'users' table ensured with all expected columns.")

        # Customers Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                mobile TEXT NOT NULL UNIQUE,
                email TEXT,
                address TEXT,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        print(f"[{datetime.datetime.now()}] DB: 'customers' table ensured.")
        # Add missing columns to customers table
        cursor.execute("PRAGMA table_info(customers)")
        cust_cols = [col[1] for col in cursor.fetchall()]

        if 'alternate_mobile' not in cust_cols:
            cursor.execute("ALTER TABLE customers ADD COLUMN alternate_mobile TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'alternate_mobile' to 'customers' table.")

        if 'gst_no' not in cust_cols:
            cursor.execute("ALTER TABLE customers ADD COLUMN gst_no TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'gst_no' to 'customers' table.")

        if 'pan_no' not in cust_cols:
            cursor.execute("ALTER TABLE customers ADD COLUMN pan_no TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'pan_no' to 'customers' table.")

        # Jobs Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                job_type TEXT NOT NULL,
                description TEXT,
                size TEXT,
                initial_price REAL NOT NULL,
                discount_amount REAL DEFAULT 0.0,
                advance1 REAL DEFAULT 0.0,
                final_price REAL,
                balance REAL,
                payment_status TEXT DEFAULT 'Unpaid',
                payment_mode TEXT,
                assigned_staff_id INTEGER,
                status TEXT NOT NULL DEFAULT 'Pending',
                start_date TEXT NOT NULL,
                due_date TEXT,
                completion_date TEXT,
                delivery_date TEXT,
                notes TEXT,
                invoice_id INTEGER,
                attachments TEXT,
                rounded_off_amount REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (assigned_staff_id) REFERENCES users(id),
                FOREIGN KEY (invoice_id) REFERENCES invoices(id)
            )
        """)
        # Add missing columns to jobs table
        cursor.execute("PRAGMA table_info(jobs)")
        job_cols = [col[1] for col in cursor.fetchall()]
        if 'size' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN size TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'size' to 'jobs' table.")
        if 'discount_amount' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN discount_amount REAL DEFAULT 0.0")
            print(f"[{datetime.datetime.now()}] DB: Added 'discount_amount' to 'jobs' table.")
        if 'advance1' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN advance1 REAL DEFAULT 0.0")
            print(f"[{datetime.datetime.now()}] DB: Added 'advance1' to 'jobs' table.")
        if 'final_price' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN final_price REAL")
            print(f"[{datetime.datetime.now()}] DB: Added 'final_price' to 'jobs' table.")
        if 'balance' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN balance REAL")
            print(f"[{datetime.datetime.now()}] DB: Added 'balance' to 'jobs' table.")
        if 'payment_status' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN payment_status TEXT DEFAULT 'Unpaid'")
            print(f"[{datetime.datetime.now()}] DB: Added 'payment_status' to 'jobs' table.")
        if 'payment_mode' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN payment_mode TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'payment_mode' to 'jobs' table.")
        if 'assigned_staff_id' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN assigned_staff_id INTEGER")
            print(f"[{datetime.datetime.now()}] DB: Added 'assigned_staff_id' to 'jobs' table.")
        if 'due_date' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN due_date TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'due_date' to 'jobs' table.")
        if 'completion_date' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN completion_date TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'completion_date' to 'jobs' table.")
        if 'invoice_id' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN invoice_id INTEGER")
            print(f"[{datetime.datetime.now()}] DB: Added 'invoice_id' to 'jobs' table.")
        if 'attachments' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN attachments TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'attachments' to 'jobs' table.")
        if 'rounded_off_amount' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN rounded_off_amount REAL DEFAULT 0.0")
            print(f"[{datetime.datetime.now()}] DB: Added 'rounded_off_amount' to 'jobs' table.")
        # Add missing GST-related columns to jobs table
        if 'gst_type' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN gst_type TEXT DEFAULT 'None'")
            print(f"[{datetime.datetime.now()}] DB: Added 'gst_type' to 'jobs' table.")
        if 'gst_category' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN gst_category TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'gst_category' to 'jobs' table.")
        if 'gst_percentage' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN gst_percentage REAL DEFAULT 0.0")
            print(f"[{datetime.datetime.now()}] DB: Added 'gst_percentage' to 'jobs' table.")
        if 'gst_amount' not in job_cols:
            cursor.execute("ALTER TABLE jobs ADD COLUMN gst_amount REAL DEFAULT 0.0")
            print(f"[{datetime.datetime.now()}] DB: Added 'gst_amount' to 'jobs' table.")

        print(f"[{datetime.datetime.now()}] DB: 'jobs' table ensured with all expected columns.")

        # Payments Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                job_id INTEGER,
                invoice_id INTEGER,
                amount REAL NOT NULL,
                payment_date TEXT NOT NULL,
                payment_mode TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (job_id) REFERENCES jobs(id),
                FOREIGN KEY (invoice_id) REFERENCES invoices(id)
            )
        """)
        # Add missing columns to payments table
        cursor.execute("PRAGMA table_info(payments)")
        payment_cols = [col[1] for col in cursor.fetchall()]
        if 'invoice_id' not in payment_cols:
            cursor.execute("ALTER TABLE payments ADD COLUMN invoice_id INTEGER")
            print(f"[{datetime.datetime.now()}] DB: Added 'invoice_id' to 'payments' table.")
        if 'payment_mode' not in payment_cols:
            cursor.execute("ALTER TABLE payments ADD COLUMN payment_mode TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'payment_mode' to 'payments' table.")
        print(f"[{datetime.datetime.now()}] DB: 'payments' table ensured.")

        # Packages Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS packages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                price REAL NOT NULL
            )
        """)
        print(f"[{datetime.datetime.now()}] DB: 'packages' table ensured.")

        # Activity Log Table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {ACTIVITY_LOG_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                activity_type TEXT NOT NULL,
                description TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        print(f"[{datetime.datetime.now()}] DB: 'activity_log' table ensured.")

        # Settings Table
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {SETTINGS_TABLE} (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        print(f"[{datetime.datetime.now()}] DB: 'settings' table ensured.")

        # Notes Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                related_to TEXT,
                related_id INTEGER,
                note_text TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by INTEGER,
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)
        print(f"[{datetime.datetime.now()}] DB: 'notes' table ensured.")

        # Inventory Categories Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """)
        print(f"[{datetime.datetime.now()}] DB: 'inventory_categories' table ensured.")

        # Vendors Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS vendors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                contact_person TEXT,
                phone TEXT,
                email TEXT,
                address TEXT
            )
        """)
        print(f"[{datetime.datetime.now()}] DB: 'vendors' table ensured.")

        # Inventory Items Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category_id INTEGER,
                vendor_id INTEGER,
                current_stock REAL NOT NULL DEFAULT 0.0,
                unit_price REAL NOT NULL,
                last_restocked TEXT,
                reorder_level INTEGER DEFAULT 10,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (category_id) REFERENCES inventory_categories(id),
                FOREIGN KEY (vendor_id) REFERENCES vendors(id)
            )
        """)
        # Add missing columns to inventory_items table
        cursor.execute("PRAGMA table_info(inventory_items)")
        inventory_cols = [col[1] for col in cursor.fetchall()]
        if 'current_stock' not in inventory_cols:
            cursor.execute("ALTER TABLE inventory_items ADD COLUMN current_stock REAL DEFAULT 0.0")
        if 'unit_price' not in inventory_cols:
            cursor.execute("ALTER TABLE inventory_items ADD COLUMN unit_price REAL NOT NULL DEFAULT 0.0")
        if 'last_updated' not in inventory_cols:
            cursor.execute("ALTER TABLE inventory_items ADD COLUMN last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        if 'sku' not in inventory_cols:
            cursor.execute("ALTER TABLE inventory_items ADD COLUMN sku TEXT")
        if 'uom' not in inventory_cols:
            cursor.execute("ALTER TABLE inventory_items ADD COLUMN uom TEXT DEFAULT 'Pcs'")
        if 'item_type' not in inventory_cols:
            cursor.execute("ALTER TABLE inventory_items ADD COLUMN item_type TEXT")
        if 'item_size' not in inventory_cols:
            cursor.execute("ALTER TABLE inventory_items ADD COLUMN item_size TEXT")
            
        # If 'stock_quantity' exists from a previous version and 'current_stock' doesn't, migrate
        if 'stock_quantity' in inventory_cols and 'current_stock' not in inventory_cols:
            cursor.execute("ALTER TABLE inventory_items ADD COLUMN current_stock REAL")
            cursor.execute("UPDATE inventory_items SET current_stock = stock_quantity WHERE current_stock IS NULL")
            # Recreate table to drop old column
            cursor.execute("CREATE TEMPORARY TABLE temp_inventory_items AS SELECT id, name, category_id, vendor_id, current_stock, unit_price, last_restocked, reorder_level FROM inventory_items")
            cursor.execute("DROP TABLE inventory_items")
            cursor.execute("""
                CREATE TABLE inventory_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    category_id INTEGER,
                    vendor_id INTEGER,
                    current_stock REAL NOT NULL DEFAULT 0.0,
                    unit_price REAL NOT NULL,
                    last_restocked TEXT,
                    reorder_level INTEGER DEFAULT 10,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                    sku TEXT,
                    uom TEXT DEFAULT 'Pcs',
                    item_type TEXT,
                    item_size TEXT,
                    FOREIGN KEY (category_id) REFERENCES inventory_categories(id),
                    FOREIGN KEY (vendor_id) REFERENCES vendors(id)
                )
            """)
            cursor.execute("INSERT INTO inventory_items (id, name, category_id, vendor_id, current_stock, unit_price, last_restocked, reorder_level) SELECT id, name, category_id, vendor_id, current_stock, unit_price, last_restocked, reorder_level FROM temp_inventory_items")
            cursor.execute("DROP TABLE temp_inventory_items")
            print(f"[{datetime.datetime.now()}] DB: Migrated 'stock_quantity' to 'current_stock' in 'inventory_items' table.")
        print(f"[{datetime.datetime.now()}] DB: 'inventory_items' table ensured with all properties including SKU, UOM, Type, Size.")

        # Invoices Table (moved up for FK constraint)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT NOT NULL UNIQUE,
                customer_id INTEGER NOT NULL,
                invoice_date TEXT NOT NULL,
                due_date TEXT,
                total_amount REAL NOT NULL,
                amount_paid REAL DEFAULT 0.0,
                balance_due REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'Pending',
                notes TEXT,
                terms_and_conditions TEXT,
                created_by INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id),
                FOREIGN KEY (created_by) REFERENCES users(id)
            )
        """)
        # Add missing columns to invoices table
        cursor.execute("PRAGMA table_info(invoices)")
        invoice_cols = [col[1] for col in cursor.fetchall()]
        if 'invoice_number' not in invoice_cols:
            cursor.execute("ALTER TABLE invoices ADD COLUMN invoice_number TEXT")
            cursor.execute("UPDATE invoices SET invoice_number = 'INV-' || id WHERE invoice_number IS NULL")
            print(f"[{datetime.datetime.now()}] DB: Added 'invoice_number' to 'invoices' table.")
        if 'terms_and_conditions' not in invoice_cols:
            cursor.execute("ALTER TABLE invoices ADD COLUMN terms_and_conditions TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'terms_and_conditions' to 'invoices' table.")
        if 'created_by' not in invoice_cols:
            cursor.execute("ALTER TABLE invoices ADD COLUMN created_by INTEGER")
            print(f"[{datetime.datetime.now()}] DB: Added 'created_by' to 'invoices' table.")
        print(f"[{datetime.datetime.now()}] DB: 'invoices' table ensured.")

        # Invoice Line Items Table (moved up for FK constraint)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS invoice_line_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_id INTEGER NOT NULL,
                job_id INTEGER,
                item_description TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit_price REAL NOT NULL,
                amount_billed_for_job REAL NOT NULL,
                hsn_sac_code TEXT,
                gst_rate REAL DEFAULT 0.0,
                gst_calculation_method TEXT DEFAULT 'Inclusive',
                FOREIGN KEY (invoice_id) REFERENCES invoices(id),
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        """)
        # Add missing columns to invoice_line_items table
        cursor.execute("PRAGMA table_info(invoice_line_items)")
        line_item_cols = [col[1] for col in cursor.fetchall()]
        if 'hsn_sac_code' not in line_item_cols:
            cursor.execute("ALTER TABLE invoice_line_items ADD COLUMN hsn_sac_code TEXT")
            print(f"[{datetime.datetime.now()}] DB: Added 'hsn_sac_code' to 'invoice_line_items' table.")
        if 'gst_rate' not in line_item_cols:
            cursor.execute("ALTER TABLE invoice_line_items ADD COLUMN gst_rate REAL DEFAULT 0.0")
            print(f"[{datetime.datetime.now()}] DB: Added 'gst_rate' column to 'invoice_line_items' table.")
        if 'gst_calculation_method' not in line_item_cols:
            cursor.execute("ALTER TABLE invoice_line_items ADD COLUMN gst_calculation_method TEXT DEFAULT 'Inclusive'")
            print(f"[{datetime.datetime.now()}] DB: Added 'gst_calculation_method' column to 'invoice_line_items' table.")
        print(f"[{datetime.datetime.now()}] DB: 'invoice_line_items' table ensured.")

        # Job Types Table (NEW) - store structured job categories and names
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS job_types (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                name TEXT NOT NULL,
                UNIQUE(category, name)
            )
        """)
        print(f"[{datetime.datetime.now()}] DB: 'job_types' table ensured.")

        # Notifications Table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                job_id INTEGER,
                is_read INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (job_id) REFERENCES jobs(id)
            )
        """)
        print(f"[{datetime.datetime.now()}] DB: 'notifications' table ensured.")

        conn.commit()
        print(f"[{datetime.datetime.now()}] DB: All tables and columns committed.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error ensuring tables: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


def create_default_admin():
    """Creates a default admin user if no users exist in the database."""
    print(f"[{datetime.datetime.now()}] DB: Attempting to create default admin.")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            admin_username = "admin"
            admin_password_hash = hash_password("adminpass")

            # Check for optional columns before inserting
            cursor.execute("PRAGMA table_info(users)")
            user_columns = [col[1] for col in cursor.fetchall()]

            if 'full_name' in user_columns and 'email' in user_columns and 'phone' in user_columns:
                cursor.execute(
                    "INSERT INTO users (username, password_hash, role, is_active, full_name, email, phone) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (admin_username, admin_password_hash, 'admin', 1, 'Admin User', 'admin@example.com', ''))
            else:
                cursor.execute(
                    "INSERT INTO users (username, password_hash, role, is_active) VALUES (?, ?, ?, ?)",
                    (admin_username, admin_password_hash, 'admin', 1))

            conn.commit()
            print(f"[{datetime.datetime.now()}] DB: Default admin user '{admin_username}' created.")
        else:
            print(f"[{datetime.datetime.now()}] DB: Default admin user already exists.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error creating default admin: {e}")
    finally:
        conn.close()


def authenticate_user(username, password):
    """Authenticates a user by checking username and hashed password."""
    conn = get_db_connection()
    cursor = conn.cursor()
    user_info = None
    try:
        cursor.execute("SELECT id, username, password_hash, role, is_active FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        if user:
            if verify_password(user['password_hash'], password) and user['is_active'] == 1:
                user_info = dict(user)
                print(f"[{datetime.datetime.now()}] DB: User '{username}' authenticated successfully.")
            else:
                print(f"[{datetime.datetime.now()}] DB: Authentication failed for '{username}': Invalid password or inactive account.")
        else:
            print(f"[{datetime.datetime.now()}] DB: Authentication failed: User '{username}' not found.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error during user authentication: {e}")
    finally:
        conn.close()
    return user_info


def get_all_users():
    """Fetches all users from the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    users = []
    try:
        cursor.execute("PRAGMA table_info(users)")
        user_columns = [col[1] for col in cursor.fetchall()]

        select_cols = ["id", "username", "role", "is_active"]
        if "full_name" in user_columns:
            select_cols.append("full_name")
        if "email" in user_columns:
            select_cols.append("email")
        if "phone" in user_columns:
            select_cols.append("phone")

        cursor.execute(f"SELECT {', '.join(select_cols)} FROM users ORDER BY username")
        users = cursor.fetchall()
        print(f"[{datetime.datetime.now()}] DB: Fetched {len(users)} users.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching all users: {e}")
    finally:
        conn.close()
    return [dict(row) for row in users]


def get_app_settings():
    """
    Retrieves all application settings from the settings table.
    Returns a dictionary of setting_name: setting_value.
    """
    print(f"[{datetime.datetime.now()}] DB: Getting app settings.")
    conn = get_db_connection()
    cursor = conn.cursor()
    settings = {}
    try:
        cursor.execute(f"SELECT key, value FROM {SETTINGS_TABLE}")
        for row in cursor.fetchall():
            settings[row['key']] = row['value']
        print(f"[{datetime.datetime.now()}] DB: App settings retrieved.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error getting app settings: {e}")
    finally:
        conn.close()
    return settings


def update_app_settings(**kwargs):
    """
    Updates or inserts application settings.
    Accepts keyword arguments where key is setting_name and value is setting_value.
    """
    print(f"[{datetime.datetime.now()}] DB: Updating app settings: {kwargs}")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        for key, value in kwargs.items():
            cursor.execute(f"INSERT OR REPLACE INTO {SETTINGS_TABLE} (key, value) VALUES (?, ?)",
                           (key, str(value)))
        conn.commit()
        print(f"[{datetime.datetime.now()}] DB: App settings updated successfully.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error updating app settings: {e}")
        conn.rollback()
        raise  # Re-raise for caller to handle if necessary
    finally:
        conn.close()


def perform_automatic_backup():
    """
    Performs a backup of the main database file to a 'backups' directory.
    """
    print(f"[{datetime.datetime.now()}] DB: Starting automatic backup.")
    backup_dir = BACKUP_DIR
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = os.path.join(backup_dir, f"kprlab_auto_backup_{timestamp}.db")

    source_conn = None
    dest_conn = None
    try:
        source_conn = sqlite3.connect(DATABASE_NAME)
        dest_conn = sqlite3.connect(backup_filename)
        source_conn.backup(dest_conn)
        print(f"[{datetime.datetime.now()}] DB: Automatic database backup successful to: {backup_filename}")
        update_app_settings(last_backup_date=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        log_activity(None, None, 'DB Backup', f"Automatic backup created: {backup_filename}")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Automatic database backup failed: {e}")
        log_activity(None, None, 'DB Backup Failed', f"Error: {e}")
    finally:
        if source_conn:
            source_conn.close()
        if dest_conn:
            dest_conn.close()


def print_all_users():
    """
    Prints all users currently in the database to the console. (For debugging/admin view).
    """
    print(f"[{datetime.datetime.now()}] DB: Printing all users.")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(users)")
        user_columns = [col[1] for col in cursor.fetchall()]

        select_cols = ["id", "username", "password_hash", "role", "is_active"]
        if "full_name" in user_columns:
            select_cols.append("full_name")
        if "email" in user_columns:
            select_cols.append("email")
        if "phone" in user_columns:
            select_cols.append("phone")

        cursor.execute(f"SELECT {', '.join(select_cols)} FROM users")
        users = cursor.fetchall()
        print("\n--- All Users ---")
        for user in users:
            user_info_str = f"ID: {user['id']}, Username: {user['username']}, Role: {user['role']}, Active: {bool(user['is_active'])}"
            if "full_name" in user_columns:
                user_info_str += f", Full Name: {user['full_name']}"
            if "email" in user_columns:
                user_info_str += f", Email: {user['email']}"
            if "phone" in user_columns:
                user_info_str += f", Phone: {user['phone']}"
            print(user_info_str)
        print("-----------------\n")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error printing users: {e}")
    finally:
        conn.close()


def get_low_stock_items():
    """
    Fetches inventory items whose current stock is at or below their reorder level.
    """
    print(f"[{datetime.datetime.now()}] DB: Fetching low stock items.")
    conn = get_db_connection()
    cursor = conn.cursor()
    low_stock_items = []
    try:
        cursor.execute("""
            SELECT
                ii.name,
                ii.current_stock,
                ii.reorder_level
            FROM inventory_items ii
            WHERE ii.current_stock <= ii.reorder_level AND ii.reorder_level > 0
            ORDER BY ii.name
        """)
        low_stock_items = cursor.fetchall()
        print(f"[{datetime.datetime.now()}] DB: Fetched {len(low_stock_items)} low stock items.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching low stock items: {e}")
    finally:
        conn.close()
    return low_stock_items


def get_pending_jobs_count():
    """
    Returns the count of jobs with 'Pending' or 'In Progress' status.
    """
    print(f"[{datetime.datetime.now()}] DB: Fetching pending jobs count.")
    conn = get_db_connection()
    cursor = conn.cursor()
    count = 0
    try:
        cursor.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('Pending', 'In Progress')")
        count = cursor.fetchone()[0]
        print(f"[{datetime.datetime.now()}] DB: Found {count} pending/in-progress jobs.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching pending jobs count: {e}")
    finally:
        conn.close()
    return count


def get_total_unpaid_amount():
    """
    Calculates the total outstanding balance from jobs that are not fully paid or cancelled.
    """
    print(f"[{datetime.datetime.now()}] DB: Fetching total unpaid amount.")
    conn = get_db_connection()
    cursor = conn.cursor()
    total_unpaid = Decimal('0.00')
    try:
        cursor.execute("SELECT SUM(balance) FROM jobs WHERE payment_status NOT IN ('Paid', 'Cancelled')")
        result = cursor.fetchone()[0]
        if result is not None:
            total_unpaid = Decimal(str(result))  # Convert to Decimal
        print(f"[{datetime.datetime.now()}] DB: Total unpaid amount: {total_unpaid:.2f}")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching total unpaid amount: {e}")
    finally:
        conn.close()
    return total_unpaid


def get_unpaid_customer_details():
    """
    Fetches details of customers with outstanding balances (Unpaid or Partially Paid jobs).
    Returns a list of dictionaries, each containing customer name, mobile, job ID, and outstanding balance.
    """
    print(f"[{datetime.datetime.now()}] DB: Fetching unpaid customer details.")
    conn = get_db_connection()
    cursor = conn.cursor()
    unpaid_customers = []
    try:
        cursor.execute("""
            SELECT
                c.id,
                c.name AS customer_name,
                c.mobile AS customer_mobile,
                j.id AS job_id,
                j.balance
            FROM jobs j
            JOIN customers c ON j.customer_id = c.id
            WHERE j.payment_status IN ('Unpaid', 'Partially Paid') AND j.balance > 0
            ORDER BY c.name, j.id
        """)
        unpaid_customers = cursor.fetchall()
        print(f"[{datetime.datetime.now()}] DB: Fetched {len(unpaid_customers)} unpaid customer job entries.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching unpaid customer details: {e}")
    finally:
        conn.close()
    return unpaid_customers


def update_job_payment_status(job_id, amount_paid):
    """
    Updates the payment status and balance for a specific job after a payment is made.
    Ensures status correctly reflects the total amount paid.
    """
    print(f"[{datetime.datetime.now()}] DB: Attempting to update job {job_id} payment status with {amount_paid} paid.")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT final_price, advance1 FROM jobs WHERE id=?", (job_id,))
        job = cursor.fetchone()

        if not job:
            print(f"[{datetime.datetime.now()}] DB: Job {job_id} not found.")
            return False

        final_price_decimal = Decimal(str(job['final_price'] or 0.0))
        current_advance1 = Decimal(str(job['advance1'] or 0.0))
        amount_paid_decimal = Decimal(str(amount_paid or 0.0))

        new_advance1 = current_advance1 + amount_paid_decimal
        new_balance = final_price_decimal - new_advance1

        if new_balance < Decimal('0.00'):
            new_balance = Decimal('0.00')

        if new_advance1 >= final_price_decimal:
            new_payment_status = "Paid"
        elif new_advance1 > Decimal('0.00'):
            new_payment_status = "Partially Paid"
        else:
            new_payment_status = "Unpaid"

        cursor.execute("""
            UPDATE jobs
            SET balance = ?, payment_status = ?, advance1 = ?
            WHERE id = ?
        """, (float(new_balance), new_payment_status, float(new_advance1), job_id))

        conn.commit()
        print(f"[{datetime.datetime.now()}] DB: Job {job_id} updated. New Balance: {new_balance:.2f}, New Status: {new_payment_status}.")
        return True

    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error updating job payment status for job {job_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def get_payments_for_job(job_id):
    """
    Fetches all payment records associated with a specific job ID.
    """
    print(f"[{datetime.datetime.now()}] DB: Fetching payments for job ID: {job_id}.")
    conn = get_db_connection()
    cursor = conn.cursor()
    payments = []
    try:
        cursor.execute("SELECT id, invoice_id, amount, payment_date, payment_mode, notes FROM payments WHERE job_id=? ORDER BY payment_date DESC", (job_id,))
        payments = cursor.fetchall()
        print(f"[{datetime.datetime.now()}] DB: Fetched {len(payments)} payments for job {job_id}.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching payments for job {job_id}: {e}")
    finally:
        conn.close()
    return payments


def get_all_job_types_structured():
    """
    Returns a mapping of job categories to a list of subtypes, read from the job_types table.
    Example return:
    {
        "Printing": ["Photo Print", "Canvas"],
        "Albums": ["Wedding Album"],
        "Other": ["Custom"]
    }
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    job_types = {}
    try:
        cursor.execute("SELECT category, name FROM job_types ORDER BY category, name")
        rows = cursor.fetchall()
        for row in rows:
            # row may be sqlite3.Row or tuple
            if isinstance(row, sqlite3.Row) or hasattr(row, 'keys'):
                category = row['category'] if row['category'] is not None else 'Other'
                name = row['name'] if row['name'] is not None else 'Custom'
            else:
                category = row[0] or 'Other'
                name = row[1] or 'Custom'
            category = category.strip() if isinstance(category, str) else 'Other'
            name = name.strip() if isinstance(name, str) else 'Custom'
            job_types.setdefault(category, [])
            if name not in job_types[category]:
                job_types[category].append(name)
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error loading job types from job_types table: {e}")
    finally:
        conn.close()

    # Ensure "Other" exists with at least one sensible default
    if 'Other' not in job_types or not job_types['Other']:
        job_types.setdefault('Other', [])
        if 'Custom' not in job_types['Other']:
            job_types['Other'].append('Custom')

    # Sort categories (Other last) and subtypes alphabetically for consistent UI
    ordered = {}
    for cat in sorted([c for c in job_types.keys() if c != 'Other']):
        ordered[cat] = sorted(job_types[cat])
    if 'Other' in job_types:
        ordered['Other'] = sorted(job_types['Other'])
    return ordered


def get_payments_for_customer(customer_id):
    """
    Fetches all payment records associated with a specific customer ID.
    """
    print(f"[{datetime.datetime.now()}] DB: Fetching all payments for customer ID: {customer_id}.")
    conn = get_db_connection()
    cursor = conn.cursor()
    payments = []
    try:
        cursor.execute("SELECT id, job_id, invoice_id, amount, payment_date, payment_mode, notes FROM payments WHERE customer_id=? ORDER BY payment_date DESC", (customer_id,))
        payments = cursor.fetchall()
        print(f"[{datetime.datetime.now()}] DB: Fetched {len(payments)} payments for customer {customer_id}.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching payments for customer {customer_id}: {e}")
    finally:
        conn.close()
    return payments


# --- NEW REPORTING FUNCTIONS (for ReportsModule) ---
def get_job_report_data(start_date_str, end_date_str, status_filter, customer_id_filter, search_term):
    """
    Fetches job data based on various filters for reporting.
    Filters include date range, job status, customer, and a general search term.
    """
    print(f"[{datetime.datetime.now()}] DB: Fetching job report data.")
    conn = get_db_connection()
    cur = conn.cursor()
    jobs = []
    try:
        query = """
            SELECT
                j.id, c.name AS customer_name, c.mobile AS customer_mobile,
                j.job_type, j.description, j.size, j.initial_price, j.discount_amount, j.final_price,
                j.advance1, j.balance, j.rounded_off_amount,
                j.payment_status, j.status, j.start_date, j.delivery_date, j.payment_mode,
                j.due_date, j.completion_date, j.notes AS remarks,
                u.username AS assigned_staff_name
            FROM jobs j
            JOIN customers c ON j.customer_id = c.id
            LEFT JOIN users u ON j.assigned_staff_id = u.id
            WHERE j.start_date BETWEEN ? AND ?
        """
        params = [start_date_str, end_date_str]

        if status_filter != "All":
            query += " AND j.status = ?"
            params.append(status_filter)

        if customer_id_filter is not None:
            query += " AND j.customer_id = ?"
            params.append(customer_id_filter)

        if search_term:
            search_like = f"%{search_term}%"
            query += " AND (LOWER(j.description) LIKE ? OR c.mobile LIKE ?)"
            params.extend([search_like, search_like])

        query += " ORDER BY j.start_date DESC, j.id DESC"

        cur.execute(query, tuple(params))
        jobs = cur.fetchall()
        print(f"[{datetime.datetime.now()}] DB: Fetched {len(jobs)} jobs for report.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching job report data: {e}")
    finally:
        conn.close()
    return jobs


def get_customer_report_data(start_date_str, end_date_str, search_term):
    """
    Fetches customer data with aggregated job and payment summaries.
    - Total Billed Amount, Total Advance Received are LIFETIME totals from jobs.
    - Total Balance Due is a LIFETIME total (sum of invoice balances + unbilled job balances).
    - Total Payments Received is for the specified DATE RANGE.
    """
    print(f"[{datetime.datetime.now()}] DB: Fetching customer report data with search term: '{search_term}'.")
    conn = get_db_connection()
    cur = conn.cursor()
    customers_data = []
    try:
        query = """
            SELECT
                c.id, c.name, c.mobile, c.email, c.address, c.tags,
                COUNT(DISTINCT j.id) AS total_jobs,
                SUM(j.final_price) AS total_billed_amount,
                SUM(j.advance1) AS total_advance_received,
                SUM(CASE WHEN p.payment_date BETWEEN ? AND ? THEN p.amount ELSE 0 END) AS total_payments_received
            FROM customers c
            LEFT JOIN jobs j ON c.id = j.customer_id
            LEFT JOIN payments p ON c.id = p.customer_id
            WHERE 1=1
        """
        params = [
            start_date_str + " 00:00:00", end_date_str + " 23:59:59"
        ]

        if search_term:
            search_like = f"%{search_term.lower()}%"
            query += " AND (LOWER(c.name) LIKE ? OR c.mobile LIKE ? OR LOWER(c.email) LIKE ?)"
            params.extend([search_like, search_like, search_like])
            
        query += """
            GROUP BY c.id, c.name, c.mobile, c.email, c.address, c.tags
            ORDER BY c.name
        """

        cur.execute(query, tuple(params))
        raw_customers_data = cur.fetchall()

        for row in raw_customers_data:
            customer_dict = dict(row)
            customer_id = customer_dict['id']

            cur.execute("SELECT SUM(balance_due) FROM invoices WHERE customer_id = ?", (customer_id,))
            invoice_balance_due = cur.fetchone()[0] or 0.0

            cur.execute("SELECT SUM(balance) FROM jobs WHERE customer_id = ? AND invoice_id IS NULL", (customer_id,))
            unbilled_job_balance_due = cur.fetchone()[0] or 0.0

            customer_dict['total_balance_due'] = Decimal(str(invoice_balance_due)) + Decimal(str(unbilled_job_balance_due))
            customers_data.append(customer_dict)

        print(f"[{datetime.datetime.now()}] DB: Fetched {len(customers_data)} customers for report.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching customer report data: {e}")
    finally:
        conn.close()
    return customers_data


def get_payment_report_data(start_date_str, end_date_str, customer_id_filter, search_term):
    """
    Fetches payment data based on date range, customer, and a general search term.
    Includes linked job description and customer details.
    """
    print(f"[{datetime.datetime.now()}] DB: Fetching payment report data.")
    conn = get_db_connection()
    cur = conn.cursor()
    payments_data = []
    try:
        query = """
            SELECT
                p.id, c.name AS customer_name, c.mobile AS customer_mobile,
                p.job_id, j.description AS job_description,
                p.amount, p.payment_date, p.payment_mode, p.notes
            FROM payments p
            JOIN customers c ON p.customer_id = c.id
            LEFT JOIN jobs j ON p.job_id = j.id
            WHERE p.payment_date BETWEEN ? AND ?
        """
        params = [start_date_str, end_date_str]

        if customer_id_filter is not None:
            query += " AND p.customer_id = ?"
            params.append(customer_id_filter)

        if search_term:
            search_like = f"%{search_term.lower()}%"
            query += " AND (LOWER(p.notes) LIKE ? OR LOWER(j.description) LIKE ? OR c.mobile LIKE ?)"
            params.extend([search_like, search_like, search_like])
            
        query += " ORDER BY p.payment_date DESC, p.id DESC"

        cur.execute(query, tuple(params))
        payments_data = cur.fetchall()
        print(f"[{datetime.datetime.now()}] DB: Fetched {len(payments_data)} payments for report.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching payment report data: {e}")
    finally:
        conn.close()
    return payments_data


def get_all_customers_for_filter():
    """
    Fetches all customer IDs, names, and mobiles for use in filter dropdowns.
    """
    print(f"[{datetime.datetime.now()}] DB: Fetching all customers for filter.")
    conn = get_db_connection()
    cursor = conn.cursor()
    customers = []
    try:
        cursor.execute("SELECT id, name, mobile FROM customers ORDER BY name")
        customers = cursor.fetchall()
        print(f"[{datetime.datetime.now()}] DB: Fetched {len(customers)} customers for filter.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching customers for filter: {e}")
    finally:
        conn.close()
    return [dict(row) for row in customers]


def get_staff_users():
    """Retrieves all active staff users (admin, staff, sub_staff) assignable to jobs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(users)")
    user_columns = [col[1] for col in cursor.fetchall()]

    select_cols = ["id", "username"]
    if "full_name" in user_columns:
        select_cols.append("full_name")

    # FIX: include both staff (user) and admin
    cursor.execute(f"""
        SELECT {', '.join(select_cols)}
        FROM users
        WHERE role IN ('user', 'admin', 'staff', 'sub_staff') AND is_active = 1
        ORDER BY username
    """)
    staff_users = cursor.fetchall()
    conn.close()
    return [dict(row) for row in staff_users]


def update_user_role(user_id, new_role):
    """Updates the role of a user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE users SET role = ? WHERE id = ?", (new_role, user_id))
        conn.commit()
        print(f"[{datetime.datetime.now()}] DB: User {user_id} role updated to '{new_role}'.")
        return True
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error updating user role: {e}")
        return False
    finally:
        conn.close()


def delete_user(user_id):
    """Deletes a user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        print(f"[{datetime.datetime.now()}] DB: User {user_id} deleted.")
        return True
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error deleting user: {e}")
        return False
    finally:
        conn.close()


# --- Job Notes Functions ---
def add_job_note(job_id, note_text, user_id):
    """Adds a new note to a job."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT INTO notes (related_to, related_id, note_text, created_by) VALUES (?, ?, ?, ?)",
            ('job', job_id, note_text, user_id)
        )
        conn.commit()
        print(f"[{datetime.datetime.now()}] DB: Note added to job {job_id}.")
        return True
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error adding job note: {e}")
        return False
    finally:
        conn.close()


def get_job_notes(job_id):
    """Retrieves all notes for a specific job."""
    conn = get_db_connection()
    cursor = conn.cursor()
    notes = []
    try:
        cursor.execute("""
            SELECT n.id, n.note_text, n.timestamp, u.username
            FROM notes n
            LEFT JOIN users u ON n.created_by = u.id
            WHERE n.related_id = ? AND n.related_to = 'job'
            ORDER BY n.timestamp DESC
        """, (job_id,))
        notes = cursor.fetchall()
        print(f"[{datetime.datetime.now()}] DB: Fetched {len(notes)} notes for job {job_id}.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching job notes: {e}")
    finally:
        conn.close()
    return [dict(row) for row in notes]


# --- Invoice Module Specific Functions ---
def get_customer_unbilled_jobs(customer_id):
    """
    Fetches jobs for a specific customer that are not yet associated with an invoice.
    """
    print(f"[{datetime.datetime.now()}] DB: Fetching unbilled jobs for customer ID: {customer_id}.")
    conn = get_db_connection()
    cursor = conn.cursor()
    unbilled_jobs = []
    try:
        cursor.execute("""
            SELECT
                j.id,
                j.job_type,
                j.description,
                j.final_price,
                j.balance,
                j.start_date,
                j.payment_status,
                j.advance1,
                j.status -- Added status column
            FROM jobs j
            WHERE j.customer_id = ?
              AND j.invoice_id IS NULL
            ORDER BY j.start_date DESC
        """, (customer_id,))
        unbilled_jobs = cursor.fetchall()
        print(f"[{datetime.datetime.now()}] DB: Fetched {len(unbilled_jobs)} unbilled jobs for customer {customer_id}.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching unbilled jobs: {e}")
    finally:
        conn.close()
    return [dict(row) for row in unbilled_jobs]


def get_latest_invoice_number_for_month(month_prefix, year_suffix):
    """
    Fetches the latest sequential invoice number for a given month and year prefix.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    latest_seq = 0
    try:
        search_pattern = f"{year_suffix}{month_prefix}%"
        cursor.execute("""
            SELECT invoice_number FROM invoices
            WHERE invoice_number LIKE ?
            ORDER BY invoice_number DESC
            LIMIT 1
        """, (search_pattern,))
        result = cursor.fetchone()
        if result:
            latest_num_str = result['invoice_number']
            try:
                # Extract the numeric part (last 3 digits)
                latest_seq = int(latest_num_str[-3:])
            except ValueError:
                print(f"[{datetime.datetime.now()}] DB: Could not parse sequence from invoice number: {latest_num_str}")
                latest_seq = 0
        print(f"[{datetime.datetime.now()}] DB: Latest sequence for {year_suffix}{month_prefix}: {latest_seq}")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error getting latest invoice number: {e}")
    finally:
        conn.close()
    return latest_seq


def create_invoice(customer_id, job_ids, total_amount, notes, created_by_user_id):
    """
    Creates a new invoice, generates an invoice number, and links jobs.
    Initial amount_paid will reflect the sum of advances from linked jobs.
    """
    print(f"[{datetime.datetime.now()}] DB: Creating invoice for customer {customer_id} with jobs {job_ids}.")
    conn = get_db_connection()
    cursor = conn.cursor()
    invoice_id = None
    try:
        conn.execute("BEGIN TRANSACTION")

        now = datetime.datetime.now()
        month_abbr_map = {
            1: 'JA', 2: 'FE', 3: 'MH', 4: 'AP', 5: 'MY', 6: 'JN',
            7: 'JL', 8: 'AU', 9: 'SE', 10: 'OC', 11: 'NV', 12: 'DE'
        }
        month_prefix = month_abbr_map.get(now.month, 'XX')
        year_suffix = now.strftime('%y')

        latest_seq = get_latest_invoice_number_for_month(month_prefix, year_suffix)
        new_seq = latest_seq + 1
        invoice_number = f"{year_suffix}{month_prefix}{new_seq:03d}"
        
        invoice_date = now.strftime('%Y-%m-%d')
        due_date = (now + datetime.timedelta(days=7)).strftime('%Y-%m-%d')

        total_advances_from_jobs = Decimal('0.00')
        jobs_data_for_invoice = []
        for job_id in job_ids:
            cursor.execute("SELECT id, final_price, description, job_type, advance1 FROM jobs WHERE id = ?", (job_id,))
            job_data = cursor.fetchone()
            if job_data:
                jobs_data_for_invoice.append(job_data)
                total_advances_from_jobs += Decimal(str(job_data['advance1'] if job_data['advance1'] is not None else 0.0))
            else:
                raise ValueError(f"No job found with ID: {job_id}")

        amount_paid_on_invoice_creation = total_advances_from_jobs
        balance_due = Decimal(str(total_amount)) - amount_paid_on_invoice_creation
        
        if balance_due < Decimal('0.00'):
            balance_due = Decimal('0.00')

        status_to_set = 'Pending'
        if balance_due <= Decimal('0.01'): # Use Decimal for comparison
            status_to_set = 'Paid'
        elif amount_paid_on_invoice_creation > Decimal('0.00'):
            status_to_set = 'Partially Paid'

        cursor.execute("""
            INSERT INTO invoices (invoice_number, customer_id, invoice_date, due_date, total_amount, amount_paid, balance_due, status, notes, terms_and_conditions, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (invoice_number, customer_id, invoice_date, due_date, float(total_amount), float(amount_paid_on_invoice_creation), float(balance_due), status_to_set, notes, "", created_by_user_id))
        invoice_id = cursor.lastrowid

        for job_data in jobs_data_for_invoice:
            job_id = job_data['id']
            job_final_price = Decimal(str(job_data['final_price']))
            job_description = job_data['description'] if job_data['description'] else job_data['job_type']
            
            # Ensure these fields are handled gracefully if not present in job_data directly
            # They are typically set on the line item itself or derived.
            default_hsn_sac = "" # Default to empty string
            default_gst_rate = Decimal('0.0')
            default_gst_calc_method = "Inclusive"

            cursor.execute("""
                INSERT INTO invoice_line_items (invoice_id, job_id, item_description, quantity, unit_price, amount_billed_for_job, hsn_sac_code, gst_rate, gst_calculation_method)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (invoice_id, job_id, job_description, 1, float(job_final_price), float(job_final_price), default_hsn_sac, float(default_gst_rate), default_gst_calc_method))
            
            # When a job is invoiced, its balance becomes 0 and payment_status becomes 'Invoiced'
            cursor.execute("UPDATE jobs SET payment_status = 'Invoiced', balance = 0.0, invoice_id = ? WHERE id = ?", (invoice_id, job_id))

        conn.commit()
        log_activity(created_by_user_id, None, "Invoice Created", f"Created invoice ID: {invoice_id} with number {invoice_number} for customer {customer_id}.") 
        print(f"[{datetime.datetime.now()}] DB: Invoice {invoice_id} ({invoice_number}) created successfully.")
        return invoice_id
    except (sqlite3.Error, ValueError) as e:
        conn.rollback()
        print(f"[{datetime.datetime.now()}] DB: Error creating invoice: {e}")
        return None
    finally:
        conn.close()


def get_all_invoices():
    """Fetches all invoices with customer names."""
    conn = get_db_connection()
    cursor = conn.cursor()
    invoices = []
    try:
        cursor.execute("""
            SELECT i.id, i.invoice_number, i.invoice_date, i.due_date,
                   i.total_amount, i.amount_paid, i.balance_due, i.status, i.notes,
                   c.name AS customer_name, c.mobile AS customer_mobile
            FROM invoices i
            JOIN customers c ON i.customer_id = c.id
            ORDER BY i.invoice_date DESC, i.id DESC
        """)
        invoices = cursor.fetchall()
        print(f"[{datetime.datetime.now()}] DB: Fetched {len(invoices)} invoices.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching all invoices: {e}")
    finally:
        conn.close()
    return [dict(row) for row in invoices]


def get_invoices_for_customer(customer_id):
    """Fetches all invoices for a specific customer."""
    conn = get_db_connection()
    cursor = conn.cursor()
    invoices = []
    try:
        cursor.execute("""
            SELECT id, invoice_number, invoice_date, total_amount, amount_paid, balance_due, status
            FROM invoices
            WHERE customer_id = ?
            ORDER BY invoice_date DESC
        """, (customer_id,))
        invoices = cursor.fetchall()
        print(f"[{datetime.datetime.now()}] DB: Fetched {len(invoices)} invoices for customer {customer_id}.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching invoices for customer {customer_id}: {e}")
    finally:
        conn.close()
    return [dict(row) for row in invoices]


def get_invoice_details(invoice_id):
    """
    Fetches details for a single invoice and its line items.
    Returns (invoice_header_dict, list_of_line_item_dicts).
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    invoice_header = None
    line_items = []
    try:
        cursor.execute("""
            SELECT i.id, i.invoice_number, i.invoice_date, i.due_date,
                   i.total_amount, i.amount_paid, i.balance_due, i.status, i.notes, i.terms_and_conditions,
                   c.id AS customer_id, c.name AS customer_name, c.mobile AS customer_mobile, c.email AS customer_email, c.address AS customer_address
            FROM invoices i
            JOIN customers c ON i.customer_id = c.id
            WHERE i.id = ?
        """, (invoice_id,))
        invoice_header = cursor.fetchone()
        if invoice_header:
            invoice_header = dict(invoice_header)
            
            cursor.execute("""
                SELECT ili.id AS line_item_id, ili.job_id, ili.item_description, ili.quantity, ili.unit_price, ili.amount_billed_for_job,
                       ili.hsn_sac_code, ili.gst_rate, ili.gst_calculation_method,
                       j.job_type, j.description AS job_description_from_job_table
                FROM invoice_line_items ili
                LEFT JOIN jobs j ON ili.job_id = j.id
                WHERE ili.invoice_id = ?
                ORDER BY ili.id ASC
            """, (invoice_id,))
            raw_line_items = cursor.fetchall()
            
            for item in raw_line_items:
                item_dict = dict(item)
                # Prioritize job_description from job table if item_description is just job_type
                if item_dict.get('item_description') == item_dict.get('job_type') and item_dict.get('job_description_from_job_table'):
                    item_dict['item_description'] = item_dict['job_description_from_job_table']
                line_items.append(item_dict)

            print(f"[{datetime.datetime.now()}] DB: Fetched details for invoice {invoice_id} with {len(line_items)} line items.")
        else:
            print(f"[{datetime.datetime.now()}] DB: Invoice {invoice_id} not found.")

    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching invoice details: {e}")
    finally:
        conn.close()
    return invoice_header, line_items


def record_invoice_payment_db(invoice_id, amount, payment_mode, user_id):
    """
    Records a payment for an invoice and updates the invoice's amount_paid and balance_due.
    Also inserts a record into the payments table.
    """
    print(f"[{datetime.datetime.now()}] DB: Recording payment for invoice {invoice_id}: Amount={amount}, Mode={payment_mode}.")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN TRANSACTION")

        cursor.execute("SELECT total_amount, amount_paid FROM invoices WHERE id = ?", (invoice_id,))
        invoice_data = cursor.fetchone()
        if not invoice_data:
            print(f"[{datetime.datetime.now()}] DB: Invoice {invoice_id} not found for payment recording.")
            conn.rollback()
            return False

        current_total_amount = Decimal(str(invoice_data['total_amount']))
        current_amount_paid = Decimal(str(invoice_data['amount_paid']))
        
        amount_decimal = Decimal(str(amount))
        updated_amount_paid = current_amount_paid + amount_decimal
        updated_balance_due = current_total_amount - updated_amount_paid
        
        if updated_balance_due < Decimal('0.00'):
            updated_balance_due = Decimal('0.00')

        status_to_set = 'Pending'
        if updated_balance_due <= Decimal('0.01'): # Use Decimal for comparison
            status_to_set = 'Paid'
        elif updated_amount_paid > Decimal('0.00'):
            status_to_set = 'Partially Paid'

        cursor.execute("""
            UPDATE invoices SET amount_paid = ?, balance_due = ?, status = ? WHERE id = ?
        """, (float(updated_amount_paid), float(updated_balance_due), status_to_set, invoice_id))
        print(f"[{datetime.datetime.now()}] DB: Invoice {invoice_id} updated. New amount_paid: {updated_amount_paid}, New balance_due: {updated_balance_due}, Status: {status_to_set}.")

        payment_date = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("SELECT customer_id FROM invoices WHERE id = ?", (invoice_id,))
        customer_id = cursor.fetchone()['customer_id']

        cursor.execute("""
            INSERT INTO payments (customer_id, invoice_id, amount, payment_date, payment_mode, notes)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (customer_id, invoice_id, float(amount_decimal), payment_date, payment_mode, f"Payment for Invoice {invoice_id}"))
        print(f"[{datetime.datetime.now()}] DB: Payment recorded in payments table for invoice {invoice_id}.")

        if status_to_set == 'Paid':
            cursor.execute("SELECT job_id FROM invoice_line_items WHERE invoice_id = ?", (invoice_id,))
            job_ids_in_invoice = cursor.fetchall()
            for job_item in job_ids_in_invoice:
                job_id = job_item['job_id']
                if job_id:
                    cursor.execute("UPDATE jobs SET payment_status = 'Paid', balance = 0.0 WHERE id = ?", (job_id,))
                    print(f"[{datetime.datetime.now()}] DB: Associated job {job_id} marked as 'Paid'.")

        conn.commit()
        log_activity(user_id, None, "Invoice Payment Recorded", f"Payment of {amount} recorded for Invoice {invoice_id} via {payment_mode}.")
        print(f"[{datetime.datetime.now()}] DB: Payment recording for invoice {invoice_id} successful.")
        return True
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error recording payment for invoice {invoice_id}: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def update_invoice_status(invoice_id, new_status):
    """
    Updates the status of an invoice directly.
    This function is now primarily for 'Cancelled' or similar direct status changes
    that are NOT related to recording a payment.
    """
    print(f"[{datetime.datetime.now()}] DB: Directly updating invoice {invoice_id} to status '{new_status}'.")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN TRANSACTION")

        cursor.execute("SELECT total_amount, amount_paid, balance_due FROM invoices WHERE id = ?", (invoice_id,))
        invoice_data = cursor.fetchone()
        if not invoice_data:
            print(f"[{datetime.datetime.now()}] DB: Invoice {invoice_id} not found for status update.")
            return False

        current_total_amount = Decimal(str(invoice_data['total_amount']))
        updated_amount_paid = Decimal(str(invoice_data['amount_paid']))
        updated_balance_due = Decimal(str(invoice_data['balance_due']))

        if new_status == 'Cancelled':
            updated_amount_paid = Decimal('0.00')
            updated_balance_due = current_total_amount
            print(f"[{datetime.datetime.now()}] DB: Invoice {invoice_id} cancelled. Resetting amounts.")
        elif new_status == 'Paid' and updated_balance_due > Decimal('0.01'):
            updated_amount_paid = current_total_amount
            updated_balance_due = Decimal('0.00')
            print(f"[{datetime.datetime.now()}] DB: Invoice {invoice_id} manually marked as Paid. Setting amounts to full paid.")
        elif new_status == 'Pending' and updated_amount_paid > Decimal('0.01'):
            updated_amount_paid = Decimal('0.00')
            updated_balance_due = current_total_amount
            print(f"[{datetime.datetime.now()}] DB: Invoice {invoice_id} manually reverted to Pending. Resetting amounts.")


        cursor.execute("""
            UPDATE invoices SET amount_paid = ?, balance_due = ?, status = ? WHERE id = ?
        """, (float(updated_amount_paid), float(updated_balance_due), new_status, invoice_id))
        print(f"[{datetime.datetime.now()}] DB: Invoice {invoice_id} status updated to '{new_status}'.")

        cursor.execute("SELECT job_id FROM invoice_line_items WHERE invoice_id = ?", (invoice_id,))
        invoice_line_items = cursor.fetchall()

        for line_item in invoice_line_items:
            job_id = line_item['job_id']
            if job_id:
                if new_status == 'Paid':
                    cursor.execute("UPDATE jobs SET payment_status = 'Paid', balance = 0.0 WHERE id = ?", (job_id,))
                    print(f"[{datetime.datetime.now()}] DB: Associated job {job_id} marked as 'Paid'.")
                elif new_status == 'Cancelled' or new_status == 'Pending':
                    cursor.execute("SELECT final_price FROM jobs WHERE id = ?", (job_id,))
                    job_final_price = cursor.fetchone()['final_price']
                    cursor.execute("UPDATE jobs SET payment_status = 'Unpaid', balance = ?, invoice_id = NULL WHERE id = ?", (job_final_price, job_id))
                    print(f"[{datetime.datetime.now()}] DB: Associated job {job_id} reverted to 'Unpaid' and unlinked from invoice.")
                elif new_status == 'Partially Paid':
                    pass 

        conn.commit()
        return True
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error updating invoice status: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def delete_invoice(invoice_id):
    """Deletes an invoice and its associated line items.
    Also reverts the linked jobs' payment_status to 'Unpaid' and restores their balance.
    """
    print(f"[{datetime.datetime.now()}] DB: Deleting invoice ID: {invoice_id}.")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        conn.execute("BEGIN TRANSACTION")
        
        cursor.execute("""
            SELECT ili.job_id, j.final_price
            FROM invoice_line_items ili
            JOIN jobs j ON ili.job_id = j.id
            WHERE ili.invoice_id = ?
        """, (invoice_id,))
        jobs_to_reset = cursor.fetchall()

        cursor.execute("DELETE FROM invoice_line_items WHERE invoice_id = ?", (invoice_id,))
        
        cursor.execute("DELETE FROM invoices WHERE id = ?", (invoice_id,))
        
        for job_data in jobs_to_reset:
            job_id = job_data['job_id']
            original_final_price = job_data['final_price']

            cursor.execute("UPDATE jobs SET payment_status = 'Unpaid', balance = ?, invoice_id = NULL WHERE id = ?",
                           (original_final_price, job_id))
            print(f"[{datetime.datetime.now()}] DB: Associated job {job_id} reverted to 'Unpaid' with balance {original_final_price} and unlinked.")

        conn.commit()
        print(f"[{datetime.datetime.now()}] DB: Invoice {invoice_id} and its line items deleted. Associated jobs reset.")
        return True
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error deleting invoice: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def update_invoice_line_item_gst(line_item_id, hsn_sac_code, gst_rate, gst_calculation_method):
    """
    Updates HSN/SAC code, GST rate, and GST calculation method for an invoice line item.
    """
    print(f"[{datetime.datetime.now()}] DB: Updating line item {line_item_id} with HSN/SAC: {hsn_sac_code}, GST: {gst_rate}, Method: {gst_calculation_method}.")
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE invoice_line_items
            SET hsn_sac_code = ?, gst_rate = ?, gst_calculation_method = ?
            WHERE id = ?
        """, (hsn_sac_code, float(gst_rate), gst_calculation_method, line_item_id))
        conn.commit()
        print(f"[{datetime.datetime.now()}] DB: Invoice line item {line_item_id} updated successfully.")
        return True
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error updating invoice line item: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


def ensure_job_types_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""CREATE TABLE IF NOT EXISTS job_types (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(category, name)
        )""")
        conn.commit()
        print(f"[{datetime.datetime.now()}] DB: 'job_types' table ensured.")
    except sqlite3.Error as e:
        print(f"[{datetime.datetime.now()}] DB: Error ensuring 'job_types' table: {e}")
    finally:
        conn.close()




def get_assigned_jobs_for_user(user_id):
    """Fetch jobs assigned ONLY to this specific user — no payment or customer contact details."""
    if user_id is None:
        print(f"[{datetime.datetime.now()}] DB: get_assigned_jobs_for_user called with None user_id!")
        return []
    try:
        user_id = int(user_id)  # ensure integer, not string/Row object
    except (TypeError, ValueError):
        print(f"[{datetime.datetime.now()}] DB: Invalid user_id: {user_id!r}")
        return []

    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Verify column exists before querying
        cursor.execute("PRAGMA table_info(jobs)")
        cols = [row[1] for row in cursor.fetchall()]
        if 'assigned_staff_id' not in cols:
            print(f"[{datetime.datetime.now()}] DB: 'assigned_staff_id' column missing in jobs table!")
            return []

        cursor.execute("""
            SELECT
                j.id          AS job_id,
                j.job_type,
                j.description,
                j.size,
                j.status,
                j.start_date,
                j.due_date,
                j.completion_date,
                j.delivery_date,
                j.notes       AS remarks,
                c.name        AS customer_name
            FROM jobs j
            JOIN customers c ON j.customer_id = c.id
            WHERE j.assigned_staff_id = ?
              AND j.status NOT IN ('Completed', 'Delivered')
              AND (j.delivery_date IS NULL OR j.delivery_date = '')
            ORDER BY
                CASE j.status
                    WHEN 'Pending'     THEN 1
                    WHEN 'In Progress' THEN 2
                    WHEN 'Completed'   THEN 3
                    ELSE 4
                END,
                j.due_date ASC
        """, (user_id,))
        rows = cursor.fetchall()
        print(f"[{datetime.datetime.now()}] DB: get_assigned_jobs_for_user(user_id={user_id}) -> {len(rows)} rows")
        return rows
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching assigned jobs: {e}")
        return []
    finally:
        conn.close()

# ─────────────────────────────────────────────
# NOTIFICATION FUNCTIONS
# ─────────────────────────────────────────────

def add_notification(user_id, title, message, job_id=None):
    """Create a notification for a specific user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO notifications (user_id, title, message, job_id) VALUES (?, ?, ?, ?)",
            (user_id, title, message, job_id)
        )
        conn.commit()
        print(f"[{datetime.datetime.now()}] DB: Notification created for user_id={user_id}.")
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error creating notification: {e}")
        conn.rollback()
    finally:
        conn.close()


def get_notifications_for_user(user_id, unread_only=False):
    """Fetch notifications for a user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        if unread_only:
            cursor.execute("""
                SELECT id, title, message, job_id, is_read, created_at
                FROM notifications WHERE user_id=? AND is_read=0
                ORDER BY created_at DESC
            """, (user_id,))
        else:
            cursor.execute("""
                SELECT id, title, message, job_id, is_read, created_at
                FROM notifications WHERE user_id=?
                ORDER BY created_at DESC LIMIT 50
            """, (user_id,))
        return cursor.fetchall()
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching notifications: {e}")
        return []
    finally:
        conn.close()


def mark_notification_read(notification_id):
    """Mark a single notification as read."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE notifications SET is_read=1 WHERE id=?", (notification_id,))
        conn.commit()
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error marking notification read: {e}")
    finally:
        conn.close()


def mark_all_notifications_read(user_id):
    """Mark all notifications as read for a user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (user_id,))
        conn.commit()
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error marking all notifications read: {e}")
    finally:
        conn.close()


def get_unread_notification_count(user_id):
    """Return count of unread notifications for a user."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM notifications WHERE user_id=? AND is_read=0",
            (user_id,)
        )
        result = cursor.fetchone()
        return result[0] if result else 0
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error getting notification count: {e}")
        return 0
    finally:
        conn.close()

# -------------------------------------------------------------------
# --- NEW: INVENTORY TRANSACTION & REPORTING FUNCTIONS ---
# -------------------------------------------------------------------

def ensure_inventory_transactions_table():
    print(f"[{datetime.datetime.now()}] DB: Ensuring inventory_transactions table exists.")
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id INTEGER,
                user_id INTEGER,
                job_id INTEGER,
                transaction_type TEXT,
                quantity REAL,
                remarks TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (item_id) REFERENCES inventory_items(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        # Migrate: add job_id if missing in older DB
        cursor.execute("PRAGMA table_info(inventory_transactions)")
        existing = [c[1] for c in cursor.fetchall()]
        if 'job_id' not in existing:
            cursor.execute("ALTER TABLE inventory_transactions ADD COLUMN job_id INTEGER")
            print(f"[{datetime.datetime.now()}] DB: Migrated — added job_id to inventory_transactions.")
        conn.commit()
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error creating inventory_transactions table: {e}")
    finally:
        conn.close()

def process_inventory_transaction(item_id, user_id, trans_type, qty, remarks, job_id=None):
    """
    Records transaction, updates stock, sends Low Stock + High Wastage alerts to Admin.
    Staff/Sub-Staff are blocked from Stock In at DB level.
    job_id column is auto-migrated if missing.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # ── DB-level role guard ───────────────────────────────────────────────
        cursor.execute("SELECT role FROM users WHERE id=?", (user_id,))
        user_row = cursor.fetchone()
        user_role = str(user_row['role']).lower() if user_row else ''
        if user_role in ('staff', 'sub_staff') and trans_type == 'Stock In':
            print(f"[DB] BLOCKED: user_id={user_id} (role={user_role}) attempted Stock In.")
            return False

        # ── Auto-migrate job_id column if missing ─────────────────────────────
        cursor.execute("PRAGMA table_info(inventory_transactions)")
        existing_cols = [c[1] for c in cursor.fetchall()]
        if 'job_id' not in existing_cols:
            cursor.execute("ALTER TABLE inventory_transactions ADD COLUMN job_id INTEGER")
            print(f"[DB] Migrated: added job_id column to inventory_transactions.")

        # 1. Record transaction
        cursor.execute("""
            INSERT INTO inventory_transactions (item_id, user_id, job_id, transaction_type, quantity, remarks)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (item_id, user_id, job_id, trans_type, float(qty), remarks))

        # 2. Update stock
        if trans_type == 'Stock In':
            cursor.execute(
                "UPDATE inventory_items SET current_stock = current_stock + ?, last_updated=CURRENT_TIMESTAMP WHERE id=?",
                (float(qty), item_id))
        else:
            cursor.execute(
                "UPDATE inventory_items SET current_stock = current_stock - ?, last_updated=CURRENT_TIMESTAMP WHERE id=?",
                (float(qty), item_id))

        # 3. Fetch admins once for alerts
        cursor.execute("SELECT id FROM users WHERE role='admin' AND is_active=1")
        admins = cursor.fetchall()

        if trans_type in ('Usage', 'Wastage'):
            cursor.execute(
                "SELECT name, current_stock, reorder_level FROM inventory_items WHERE id=?",
                (item_id,))
            item = cursor.fetchone()

            if item:
                # Alert A: Low Stock
                if item['reorder_level'] > 0 and item['current_stock'] <= item['reorder_level']:
                    title = "⚠️ Low Stock Alert"
                    msg = (f"Material '{item['name']}' stock is now {item['current_stock']}. "
                           f"Reorder level: {item['reorder_level']}.")
                    for admin in admins:
                        cursor.execute(
                            "INSERT INTO notifications (user_id, title, message) VALUES (?,?,?)",
                            (admin['id'], title, msg))

                # Alert B: High Wastage (≥30% in last 30 days)
                if trans_type == 'Wastage':
                    try:
                        cursor.execute("""
                            SELECT
                                SUM(CASE WHEN transaction_type='Usage'   THEN quantity ELSE 0 END) AS u,
                                SUM(CASE WHEN transaction_type='Wastage' THEN quantity ELSE 0 END) AS w
                            FROM inventory_transactions
                            WHERE item_id=? AND timestamp >= datetime('now','-30 days')
                        """, (item_id,))
                        row = cursor.fetchone()
                        u30, w30 = (row['u'] or 0), (row['w'] or 0)
                        if (u30 + w30) > 0 and (w30 / (u30 + w30)) >= 0.30:
                            wtitle = "🚨 High Wastage Warning"
                            wmsg = (f"'{item['name']}' wastage is "
                                    f"{round(w30/(u30+w30)*100,1)}% of consumption "
                                    f"in last 30 days (Usage:{u30}, Wastage:{w30}).")
                            for admin in admins:
                                cursor.execute(
                                    "INSERT INTO notifications (user_id, title, message) VALUES (?,?,?)",
                                    (admin['id'], wtitle, wmsg))
                    except Exception:
                        pass  # wastage alert is non-critical

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f"[{datetime.datetime.now()}] DB: Error processing inventory transaction: {e}")
        return False
    finally:
        conn.close()

def get_material_usage_report(start_date_str, end_date_str):
    """Fetches combined Usage and Wastage report for the Admin including Type and Size."""
    conn = get_db_connection()
    cursor = conn.cursor()
    data = []
    try:
        start_date = start_date_str + " 00:00:00"
        end_date = end_date_str + " 23:59:59"
        
        cursor.execute("""
            SELECT 
                i.sku, 
                i.name as item_name, 
                i.item_type,
                i.item_size,
                i.uom,
                SUM(CASE WHEN t.transaction_type = 'Usage' THEN t.quantity ELSE 0 END) as total_usage,
                SUM(CASE WHEN t.transaction_type = 'Wastage' THEN t.quantity ELSE 0 END) as total_wastage,
                SUM(CASE WHEN t.transaction_type = 'Stock In' THEN t.quantity ELSE 0 END) as total_inward
            FROM inventory_transactions t
            JOIN inventory_items i ON t.item_id = i.id
            WHERE t.timestamp BETWEEN ? AND ?
            GROUP BY i.id, i.sku, i.name, i.item_type, i.item_size, i.uom
            ORDER BY i.name
        """, (start_date, end_date))
        data = cursor.fetchall()
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching material usage report: {e}")
    finally:
        conn.close()
    return [dict(row) for row in data]


# ─────────────────────────────────────────────────────────────────────────────
# PASSWORD MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

def change_user_password(user_id, old_password, new_password):
    """
    Verify old password then update to new hashed password.
    Returns (True, 'Success') or (False, 'error reason').
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT password_hash FROM users WHERE id=? AND is_active=1", (user_id,))
        row = cursor.fetchone()
        if not row:
            return False, "User not found."
        if not verify_password(row['password_hash'], old_password):
            return False, "Current password is incorrect."
        if len(new_password) < 6:
            return False, "New password must be at least 6 characters."
        cursor.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(new_password), user_id)
        )
        conn.commit()
        print(f"[{datetime.datetime.now()}] DB: Password changed for user_id={user_id}.")
        return True, "Password changed successfully."
    except Exception as e:
        conn.rollback()
        print(f"[{datetime.datetime.now()}] DB: Error changing password: {e}")
        return False, str(e)
    finally:
        conn.close()


def admin_reset_password(admin_id, target_user_id, new_password):
    """
    Admin can reset any user's password without knowing old password.
    Returns (True, msg) or (False, msg).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        # Verify caller is admin
        cursor.execute("SELECT role FROM users WHERE id=?", (admin_id,))
        admin = cursor.fetchone()
        if not admin or admin['role'] != 'admin':
            return False, "Only admins can reset passwords."
        if len(new_password) < 6:
            return False, "Password must be at least 6 characters."
        cursor.execute(
            "UPDATE users SET password_hash=? WHERE id=?",
            (hash_password(new_password), target_user_id)
        )
        conn.commit()
        print(f"[{datetime.datetime.now()}] DB: Admin {admin_id} reset password for user {target_user_id}.")
        return True, "Password reset successfully."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# WHATSAPP / SMS NOTIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def get_job_for_notification(job_id):
    """
    Returns all fields needed to compose a WhatsApp/SMS message for a job.
    Includes customer mobile, name, job type, status, delivery date.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                j.id            AS job_id,
                j.job_type,
                j.description,
                j.size,
                j.status,
                j.payment_status,
                j.start_date,
                j.due_date,
                j.completion_date,
                j.delivery_date,
                j.notes         AS remarks,
                c.name          AS customer_name,
                c.mobile        AS customer_mobile
            FROM jobs j
            JOIN customers c ON j.customer_id = c.id
            WHERE j.id = ?
        """, (job_id,))
        row = cursor.fetchone()
        if not row:
            return None
        d = dict(row)
        # Fetch currency from settings separately (simpler)
        settings = get_app_settings()
        d['currency'] = settings.get('currency_symbol', '₹')
        d['shop_name'] = settings.get('shop_name', 'KPR Lab')
        return d
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching job for notification: {e}")
        return None
    finally:
        conn.close()


def log_notification_sent(job_id, channel, mobile, message, sent_by_user_id):
    """Log every WhatsApp/SMS notification sent so admin can audit."""
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notification_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER,
                channel TEXT,
                mobile TEXT,
                message TEXT,
                sent_by INTEGER,
                sent_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "INSERT INTO notification_log (job_id, channel, mobile, message, sent_by) VALUES (?,?,?,?,?)",
            (job_id, channel, mobile, message, sent_by_user_id)
        )
        conn.commit()
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error logging notification: {e}")
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# ORDER SLIP DATA
# ─────────────────────────────────────────────────────────────────────────────

def get_order_slip_data(job_id):
    """
    Returns all data needed to render an Order Slip / Delivery Receipt PDF.
    Includes job details, customer info, payment summary, and shop settings.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                j.id            AS job_id,
                j.job_type,
                j.description,
                j.size,
                j.status,
                j.payment_status,
                j.start_date,
                j.due_date,
                j.completion_date,
                j.delivery_date,
                j.notes         AS remarks,
                j.assigned_staff_id,
                c.name          AS customer_name,
                c.mobile        AS customer_mobile,
                c.email         AS customer_email,
                c.address       AS customer_address,
                u.username      AS assigned_staff
            FROM jobs j
            JOIN customers c ON j.customer_id = c.id
            LEFT JOIN users u ON j.assigned_staff_id = u.id
            WHERE j.id = ?
        """, (job_id,))
        job = cursor.fetchone()
        if not job:
            return None
        data = dict(job)

        # Payments summary
        try:
            cursor.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN payment_type='initial_price' THEN amount END), 0) AS total_price,
                    COALESCE(SUM(CASE WHEN payment_type='advance' THEN amount END), 0)       AS total_advance,
                    COALESCE(SUM(CASE WHEN payment_type='discount' THEN amount END), 0)      AS total_discount,
                    COALESCE(SUM(CASE WHEN payment_type='final_payment' THEN amount END), 0) AS final_payment,
                    COALESCE(SUM(amount), 0)                                                  AS total_paid
                FROM payments WHERE job_id=?
            """, (job_id,))
            pay = cursor.fetchone()
            data['payments'] = dict(pay) if pay else {}
        except Exception:
            data['payments'] = {}

        # Shop settings
        settings = get_app_settings()
        data['shop_name']    = settings.get('shop_name', 'KPR Lab')
        data['shop_phone']   = settings.get('shop_phone', '')
        data['shop_address'] = settings.get('shop_address', '')
        data['currency']     = settings.get('currency_symbol', '₹')
        data['slip_footer']  = settings.get('slip_footer', 'Thank you for your business!')
        return data
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching order slip data: {e}")
        return None
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# MATERIAL USAGE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def get_active_jobs_for_selection(user_id=None, role=None):
    """Jobs for material-entry dropdown. Staff sees only assigned jobs."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        is_restricted = role in ('staff', 'sub_staff') if role else False
        if is_restricted and user_id:
            cursor.execute("""
                SELECT j.id, j.job_type, j.description, c.name AS customer_name, j.status
                FROM jobs j JOIN customers c ON j.customer_id = c.id
                WHERE j.assigned_staff_id = ? AND j.status NOT IN ('Delivered')
                ORDER BY j.id DESC LIMIT 200
            """, (user_id,))
        else:
            cursor.execute("""
                SELECT j.id, j.job_type, j.description, c.name AS customer_name, j.status
                FROM jobs j JOIN customers c ON j.customer_id = c.id
                WHERE j.status NOT IN ('Delivered')
                ORDER BY j.id DESC LIMIT 200
            """)
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching active jobs: {e}")
        return []
    finally:
        conn.close()


def get_my_material_entries(user_id, days=30):
    """Staff's own material entry history. No stock/price info exposed."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(inventory_transactions)")
        cols = [c[1] for c in cursor.fetchall()]
        has_job_id = 'job_id' in cols

        if has_job_id:
            job_select = "t.job_id, COALESCE(j.job_type,'-') AS job_type, COALESCE(c.name,'-') AS customer_name"
            job_joins  = "LEFT JOIN jobs j ON t.job_id = j.id LEFT JOIN customers c ON j.customer_id = c.id"
        else:
            job_select = "NULL AS job_id, '-' AS job_type, '-' AS customer_name"
            job_joins  = ""

        cursor.execute(f"""
            SELECT t.id AS txn_id, t.timestamp,
                   i.name AS material_name, COALESCE(i.uom,'Pcs') AS uom,
                   i.item_type, i.item_size,
                   t.transaction_type, t.quantity,
                   COALESCE(t.remarks,'') AS remarks,
                   {job_select}
            FROM inventory_transactions t
            JOIN inventory_items i ON t.item_id = i.id
            {job_joins}
            WHERE t.user_id = ?
              AND t.timestamp >= datetime('now', '-{int(days)} days')
            ORDER BY t.timestamp DESC
        """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching my entries: {e}")
        return []
    finally:
        conn.close()


def get_dashboard_material_stats():
    """Admin dashboard KPIs: low stock count, today usage/wastage, 30d wastage %, top wasted."""
    conn = get_db_connection()
    cursor = conn.cursor()
    stats = {'low_stock_count': 0, 'today_usage': 0.0,
             'today_wastage': 0.0, 'month_wastage_pct': 0.0, 'top_wasted': []}
    try:
        # Check if is_active column exists in inventory_items
        cursor.execute("PRAGMA table_info(inventory_items)")
        inv_cols = [c[1] for c in cursor.fetchall()]
        active_filter = "AND is_active=1" if 'is_active' in inv_cols else ""

        cursor.execute(f"""
            SELECT COUNT(*) AS cnt FROM inventory_items
            WHERE reorder_level > 0 AND current_stock <= reorder_level {active_filter}
        """)
        r = cursor.fetchone()
        stats['low_stock_count'] = r['cnt'] if r else 0

        cursor.execute("""
            SELECT
                SUM(CASE WHEN transaction_type='Usage'   THEN quantity ELSE 0 END) AS u,
                SUM(CASE WHEN transaction_type='Wastage' THEN quantity ELSE 0 END) AS w
            FROM inventory_transactions WHERE DATE(timestamp) = DATE('now')
        """)
        r = cursor.fetchone()
        stats['today_usage']   = round(r['u'] or 0, 2)
        stats['today_wastage'] = round(r['w'] or 0, 2)

        cursor.execute("""
            SELECT
                SUM(CASE WHEN transaction_type='Usage'   THEN quantity ELSE 0 END) AS u,
                SUM(CASE WHEN transaction_type='Wastage' THEN quantity ELSE 0 END) AS w
            FROM inventory_transactions
            WHERE timestamp >= datetime('now', '-30 days')
              AND transaction_type IN ('Usage','Wastage')
        """)
        r = cursor.fetchone()
        u30, w30 = (r['u'] or 0), (r['w'] or 0)
        stats['month_wastage_pct'] = round((w30/(u30+w30)*100) if (u30+w30) > 0 else 0, 1)

        cursor.execute("""
            SELECT i.name AS material, SUM(t.quantity) AS wasted
            FROM inventory_transactions t
            JOIN inventory_items i ON t.item_id = i.id
            WHERE t.transaction_type = 'Wastage'
              AND t.timestamp >= datetime('now', '-30 days')
            GROUP BY t.item_id ORDER BY wasted DESC LIMIT 5
        """)
        stats['top_wasted'] = [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching dashboard material stats: {e}")
    finally:
        conn.close()
    return stats


def get_material_transaction_details(start_date_str, end_date_str,
                                      user_id_filter=None, trans_type_filter=None):
    """Full per-transaction audit log for Admin reports."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = """
            SELECT t.id AS txn_id, t.timestamp,
                   COALESCE(u.full_name, u.username, 'Unknown') AS entered_by,
                   u.username, u.role AS user_role,
                   t.job_id,
                   COALESCE(j.job_type, '-')    AS job_type,
                   COALESCE(j.description, '-') AS job_description,
                   COALESCE(c.name, '-')        AS customer_name,
                   i.name                       AS material_name,
                   COALESCE(i.sku, '-')         AS sku,
                   COALESCE(i.uom, 'Pcs')       AS uom,
                   i.item_type, i.item_size,
                   t.transaction_type, t.quantity,
                   COALESCE(t.remarks, '')      AS remarks
            FROM inventory_transactions t
            JOIN inventory_items i ON t.item_id = i.id
            LEFT JOIN users u ON t.user_id = u.id
            LEFT JOIN jobs j ON t.job_id = j.id
            LEFT JOIN customers c ON j.customer_id = c.id
            WHERE t.timestamp BETWEEN ? AND ?
        """
        params = [start_date_str + " 00:00:00", end_date_str + " 23:59:59"]
        if user_id_filter:
            query += " AND t.user_id = ?"
            params.append(user_id_filter)
        if trans_type_filter and trans_type_filter != "All":
            query += " AND t.transaction_type = ?"
            params.append(trans_type_filter)
        query += " ORDER BY t.timestamp DESC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching transaction details: {e}")
        return []
    finally:
        conn.close()


def get_material_usage_by_job(start_date_str, end_date_str):
    """Per-job material consumption summary."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT COALESCE(t.job_id, 0)         AS job_id,
                   COALESCE(j.job_type,'No Job') AS job_type,
                   COALESCE(j.description,'')    AS job_description,
                   COALESCE(c.name,'N/A')        AS customer_name,
                   i.name AS material_name,
                   COALESCE(i.sku,'-')    AS sku,
                   COALESCE(i.uom,'Pcs') AS uom,
                   SUM(CASE WHEN t.transaction_type='Usage'   THEN t.quantity ELSE 0 END) AS total_usage,
                   SUM(CASE WHEN t.transaction_type='Wastage' THEN t.quantity ELSE 0 END) AS total_wastage
            FROM inventory_transactions t
            JOIN inventory_items i ON t.item_id = i.id
            LEFT JOIN jobs j ON t.job_id = j.id
            LEFT JOIN customers c ON j.customer_id = c.id
            WHERE t.timestamp BETWEEN ? AND ?
              AND t.transaction_type IN ('Usage','Wastage')
            GROUP BY t.job_id, i.id
            ORDER BY t.job_id DESC, i.name
        """, (start_date_str + " 00:00:00", end_date_str + " 23:59:59"))
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching per-job usage: {e}")
        return []
    finally:
        conn.close()


def get_staff_usage_summary(start_date_str, end_date_str):
    """Per-staff material usage/wastage totals for Admin accountability report."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT COALESCE(u.full_name, u.username,'Unknown') AS staff_name,
                   u.role,
                   COUNT(DISTINCT t.job_id) AS jobs_worked,
                   SUM(CASE WHEN t.transaction_type='Usage'   THEN t.quantity ELSE 0 END) AS total_usage_qty,
                   SUM(CASE WHEN t.transaction_type='Wastage' THEN t.quantity ELSE 0 END) AS total_wastage_qty,
                   COUNT(CASE WHEN t.transaction_type='Usage'   THEN 1 END) AS usage_entries,
                   COUNT(CASE WHEN t.transaction_type='Wastage' THEN 1 END) AS wastage_entries
            FROM inventory_transactions t
            LEFT JOIN users u ON t.user_id = u.id
            WHERE t.timestamp BETWEEN ? AND ?
              AND t.transaction_type IN ('Usage','Wastage')
            GROUP BY t.user_id
            ORDER BY total_usage_qty DESC
        """, (start_date_str + " 00:00:00", end_date_str + " 23:59:59"))
        return [dict(row) for row in cursor.fetchall()]
    except Exception as e:
        print(f"[{datetime.datetime.now()}] DB: Error fetching staff summary: {e}")
        return []
    finally:
        conn.close()


# Initial setup when the module is imported
create_tables()
ensure_job_types_table()
ensure_inventory_transactions_table()  # NEW: Automatically checks & creates inventory tracking
create_default_admin()
perform_automatic_backup()