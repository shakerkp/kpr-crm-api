"""
reset_admin_password.py
=======================
Admin password మర్చిపోతే ఈ script run చేయండి.
App తో same folder లో ఉంచి run చేయండి:

    python reset_admin_password.py
"""

import sqlite3
import hashlib
import os
import glob

# ── Database file ని automatically వెతకడం ──────────────────────────────────
def find_database():
    # Common names used in KPR Lab app
    candidates = [
        "kprlab.db", "kpr_lab.db", "database.db",
        "lab_crm.db", "crm.db", "app.db", "data.db"
    ]
    # Check current folder first
    for name in candidates:
        if os.path.exists(name):
            return name
    # Search subfolders (1 level deep)
    for name in candidates:
        matches = glob.glob(os.path.join("**", name), recursive=True)
        if matches:
            return matches[0]
    return None


def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()


def reset_admin_password():
    print("=" * 50)
    print("  KPR Lab — Admin Password Reset Tool")
    print("=" * 50)

    # Find DB
    db_path = find_database()
    if not db_path:
        db_path = input("\nDatabase file దొరకలేదు.\nDB file path enter చేయండి (e.g. kprlab.db): ").strip()
        if not os.path.exists(db_path):
            print(f"\n❌ File not found: {db_path}")
            input("Press Enter to exit...")
            return

    print(f"\n✅ Database found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Show existing admin accounts
    cursor.execute("SELECT id, username, full_name, is_active FROM users WHERE role='admin'")
    admins = cursor.fetchall()

    if not admins:
        print("\n❌ No admin accounts found in database!")
        conn.close()
        input("Press Enter to exit...")
        return

    print("\nExisting Admin Accounts:")
    print("-" * 35)
    for a in admins:
        status = "Active" if a['is_active'] else "Inactive"
        name   = a['full_name'] or ""
        print(f"  [{a['id']}] {a['username']}  {name}  ({status})")
    print("-" * 35)

    # Select which admin
    if len(admins) == 1:
        selected = admins[0]
        print(f"\nAdmin selected: {selected['username']}")
    else:
        try:
            uid = int(input("\nReset చేయాల్సిన Admin ID enter చేయండి: ").strip())
            selected = next((a for a in admins if a['id'] == uid), None)
            if not selected:
                print("❌ Invalid ID.")
                conn.close()
                input("Press Enter to exit...")
                return
        except ValueError:
            print("❌ Invalid input.")
            conn.close()
            return

    # New password
    print(f"\n'{selected['username']}' కి new password set చేయండి.")
    new_pass = input("New Password (min 6 chars): ").strip()
    if len(new_pass) < 6:
        print("❌ Password చాలా short గా ఉంది. Minimum 6 characters.")
        conn.close()
        input("Press Enter to exit...")
        return

    confirm = input("Confirm Password: ").strip()
    if new_pass != confirm:
        print("❌ Passwords match కాలేదు!")
        conn.close()
        input("Press Enter to exit...")
        return

    # Update
    cursor.execute(
        "UPDATE users SET password_hash=?, is_active=1 WHERE id=?",
        (hash_password(new_pass), selected['id'])
    )
    conn.commit()
    conn.close()

    print(f"\n✅ Password reset successful!")
    print(f"   Username : {selected['username']}")
    print(f"   Password : {new_pass}")
    print("\nఇప్పుడు app లో login చేయండి.")
    print("=" * 50)
    input("\nPress Enter to exit...")


if __name__ == "__main__":
    reset_admin_password()
