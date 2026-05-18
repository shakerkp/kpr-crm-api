"""
order_slip_module.py
====================
Provides:
  1. generate_order_slip_pdf(job_id) → saves PDF, opens it
  2. WhatsAppSMSDialog(parent, job_id, user_info) → compose & send WhatsApp / SMS
  3. PasswordChangeDialog(parent, user_info) → staff change own password
     AdminPasswordResetDialog(parent, admin_info) → admin reset any user's password
"""

import os
import datetime
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import webbrowser
import urllib.parse

from db_manager import (
    get_order_slip_data,
    get_job_for_notification,
    log_notification_sent,
    change_user_password,
    admin_reset_password,
    get_all_users,
    get_app_settings,
    update_app_settings,
)

# ─────────────────────────────────────────────────────────────────────────────
# PDF ORDER SLIP
# ─────────────────────────────────────────────────────────────────────────────

def generate_order_slip_pdf(job_id, save_path=None):
    """
    Generate a clean A5-sized order slip PDF for the given job_id.
    Returns (True, filepath) on success or (False, error_message).
    """
    try:
        from reportlab.lib.pagesizes import A5
        from reportlab.lib import colors
        from reportlab.lib.units import mm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    except ImportError:
        return False, "reportlab library not installed.\nRun: pip install reportlab"

    data = get_order_slip_data(job_id)
    if not data:
        return False, f"Job #{job_id} not found."

    # ── File path ──────────────────────────────────────────────────────────────
    if not save_path:
        docs_dir = os.path.join(os.path.expanduser("~"), "Documents", "KPRLab_Slips")
        os.makedirs(docs_dir, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        save_path = os.path.join(docs_dir, f"OrderSlip_Job{job_id}_{ts}.pdf")

    # ── Styles ─────────────────────────────────────────────────────────────────
    styles = getSampleStyleSheet()
    shop_style   = ParagraphStyle("shop",   fontSize=14, fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=2)
    phone_style  = ParagraphStyle("phone",  fontSize=9,  fontName="Helvetica",      alignment=TA_CENTER, textColor=colors.grey)
    title_style  = ParagraphStyle("title",  fontSize=11, fontName="Helvetica-Bold", alignment=TA_CENTER, spaceAfter=4, spaceBefore=6)
    label_style  = ParagraphStyle("label",  fontSize=9,  fontName="Helvetica-Bold")
    value_style  = ParagraphStyle("value",  fontSize=9,  fontName="Helvetica")
    footer_style = ParagraphStyle("footer", fontSize=8,  fontName="Helvetica-Oblique", alignment=TA_CENTER, textColor=colors.grey)

    # ── Status badge colour ───────────────────────────────────────────────────
    status_colours = {
        "Pending":     colors.HexColor("#FFF9C4"),
        "In Progress": colors.HexColor("#BBDEFB"),
        "Completed":   colors.HexColor("#C8E6C9"),
        "Delivered":   colors.HexColor("#A5D6A7"),
        "Cancelled":   colors.HexColor("#FFCDD2"),
    }
    status_bg = status_colours.get(data.get("status", ""), colors.HexColor("#F5F5F5"))

    # ── Build PDF ─────────────────────────────────────────────────────────────
    doc = SimpleDocTemplate(
        save_path,
        pagesize=A5,
        rightMargin=12*mm, leftMargin=12*mm,
        topMargin=10*mm, bottomMargin=10*mm
    )
    story = []

    # Header
    story.append(Paragraph(data.get("shop_name", "KPR Lab"), shop_style))
    contact_parts = []
    if data.get("shop_phone"):  contact_parts.append(f"📞 {data['shop_phone']}")
    if data.get("shop_address"): contact_parts.append(data["shop_address"])
    if contact_parts:
        story.append(Paragraph("  |  ".join(contact_parts), phone_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1565C0"), spaceAfter=4))

    story.append(Paragraph("ORDER SLIP", title_style))

    # Job meta row
    slip_date = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    meta_data = [
        [Paragraph("<b>Slip Date:</b>", label_style), Paragraph(slip_date, value_style),
         Paragraph("<b>Job #:</b>", label_style),     Paragraph(str(data["job_id"]), value_style)],
        [Paragraph("<b>Status:</b>", label_style),
         Paragraph(f"<b>{data.get('status','—')}</b>", ParagraphStyle("stat", fontSize=9, fontName="Helvetica-Bold")),
         Paragraph("<b>Pay Status:</b>", label_style), Paragraph(data.get("payment_status","—"), value_style)],
    ]
    meta_tbl = Table(meta_data, colWidths=["22%","28%","22%","28%"])
    meta_tbl.setStyle(TableStyle([
        ("BACKGROUND", (1,0), (1,0), colors.HexColor("#E3F2FD")),
        ("BACKGROUND", (1,1), (1,1), status_bg),
        ("BOX",   (0,0), (-1,-1), 0.5, colors.grey),
        ("GRID",  (0,0), (-1,-1), 0.3, colors.lightgrey),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
    ]))
    story.append(meta_tbl)
    story.append(Spacer(1, 5))

    # Customer section
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=3, spaceBefore=3))
    cust_data = [
        [Paragraph("<b>Customer:</b>", label_style), Paragraph(data.get("customer_name","—"), value_style),
         Paragraph("<b>Mobile:</b>",   label_style), Paragraph(data.get("customer_mobile","—"), value_style)],
    ]
    if data.get("customer_address"):
        cust_data.append([Paragraph("<b>Address:</b>", label_style),
                          Paragraph(data["customer_address"], value_style), "", ""])
    cust_tbl = Table(cust_data, colWidths=["22%","28%","22%","28%"])
    cust_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#FAFAFA")),
        ("BOX",  (0,0), (-1,-1), 0.5, colors.grey),
        ("GRID", (0,0), (-1,-1), 0.3, colors.lightgrey),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("SPAN", (1,1), (3,1)),
    ]))
    story.append(cust_tbl)
    story.append(Spacer(1, 5))

    # Job details
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=3, spaceBefore=3))
    def _f(v): return str(v) if v else "—"
    job_rows = [
        [Paragraph("<b>Job Type:</b>",   label_style), Paragraph(_f(data.get("job_type")), value_style),
         Paragraph("<b>Size:</b>",       label_style), Paragraph(_f(data.get("size")), value_style)],
        [Paragraph("<b>Description:</b>",label_style), Paragraph(_f(data.get("description")), value_style),
         Paragraph("<b>Assigned:</b>",   label_style), Paragraph(_f(data.get("assigned_staff")), value_style)],
        [Paragraph("<b>Start Date:</b>", label_style), Paragraph(_f(data.get("start_date")), value_style),
         Paragraph("<b>Due Date:</b>",   label_style), Paragraph(_f(data.get("due_date")), value_style)],
        [Paragraph("<b>Comp. Date:</b>", label_style), Paragraph(_f(data.get("completion_date")), value_style),
         Paragraph("<b>Delivery:</b>",   label_style), Paragraph(_f(data.get("delivery_date")), value_style)],
    ]
    if data.get("remarks"):
        job_rows.append([Paragraph("<b>Remarks:</b>", label_style),
                         Paragraph(_f(data.get("remarks")), value_style), "", ""])
    job_tbl = Table(job_rows, colWidths=["22%","28%","22%","28%"])
    job_tbl.setStyle(TableStyle([
        ("BOX",  (0,0), (-1,-1), 0.5, colors.grey),
        ("GRID", (0,0), (-1,-1), 0.3, colors.lightgrey),
        ("TOPPADDING",    (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
        ("LEFTPADDING",   (0,0), (-1,-1), 5),
        ("SPAN", (1,-1), (3,-1)),
    ]))
    story.append(job_tbl)
    story.append(Spacer(1, 5))

    # Payment summary
    pay = data.get("payments", {})
    if pay:
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey, spaceAfter=3, spaceBefore=3))
        cur = data.get("currency", "₹")
        price    = pay.get("total_price", 0) or 0
        discount = pay.get("total_discount", 0) or 0
        advance  = pay.get("total_advance", 0) or 0
        balance  = price - discount - advance
        pay_rows = [
            ["Job Price",   f"{cur} {price:.2f}"],
            ["Discount",    f"- {cur} {discount:.2f}"],
            ["Advance Paid",f"- {cur} {advance:.2f}"],
        ]
        pay_tbl = Table(
            [["Payment Summary", ""]] + pay_rows + [["Balance Due", f"{cur} {balance:.2f}"]],
            colWidths=["60%", "40%"]
        )
        pay_tbl.setStyle(TableStyle([
            ("BACKGROUND",  (0,0),  (-1,0),  colors.HexColor("#1565C0")),
            ("TEXTCOLOR",   (0,0),  (-1,0),  colors.white),
            ("FONTNAME",    (0,0),  (-1,0),  "Helvetica-Bold"),
            ("BACKGROUND",  (0,-1), (-1,-1), colors.HexColor("#E8F5E9")),
            ("FONTNAME",    (0,-1), (-1,-1), "Helvetica-Bold"),
            ("FONTSIZE",    (0,0),  (-1,-1), 9),
            ("ALIGN",       (1,0),  (1,-1),  "RIGHT"),
            ("BOX",   (0,0), (-1,-1), 0.5, colors.grey),
            ("GRID",  (0,0), (-1,-1), 0.3, colors.lightgrey),
            ("TOPPADDING",    (0,0), (-1,-1), 4),
            ("BOTTOMPADDING", (0,0), (-1,-1), 4),
            ("LEFTPADDING",   (0,0), (-1,-1), 6),
            ("RIGHTPADDING",  (1,0), (1,-1),  6),
            ("SPAN",          (0,0), (-1,0)),
        ]))
        story.append(pay_tbl)
        story.append(Spacer(1, 6))

    # Footer
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#1565C0"), spaceBefore=4, spaceAfter=4))
    story.append(Paragraph(data.get("slip_footer", "Thank you for your business!"), footer_style))
    story.append(Paragraph(f"Printed: {slip_date}", footer_style))

    doc.build(story)
    return True, save_path


def open_order_slip(job_id, parent_window=None):
    """Generate PDF and open it. Shows save dialog first."""
    default_dir = os.path.join(os.path.expanduser("~"), "Documents", "KPRLab_Slips")
    os.makedirs(default_dir, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    default_name = f"OrderSlip_Job{job_id}_{ts}.pdf"

    save_path = filedialog.asksaveasfilename(
        parent=parent_window,
        defaultextension=".pdf",
        filetypes=[("PDF Files", "*.pdf")],
        initialdir=default_dir,
        initialfile=default_name,
        title="Save Order Slip As"
    )
    if not save_path:
        return

    ok, result = generate_order_slip_pdf(job_id, save_path)
    if ok:
        messagebox.showinfo("Order Slip", f"✅ Saved:\n{result}\n\nOpening...", parent=parent_window)
        try:
            if sys.platform == "win32":
                os.startfile(result)
            elif sys.platform == "darwin":
                subprocess.run(["open", result])
            else:
                subprocess.run(["xdg-open", result])
        except Exception:
            pass
    else:
        messagebox.showerror("PDF Error", result, parent=parent_window)


# ─────────────────────────────────────────────────────────────────────────────
# WHATSAPP / SMS NOTIFICATION DIALOG
# ─────────────────────────────────────────────────────────────────────────────

# Default message templates
STATUS_TEMPLATES = {
    "Pending":     "Dear {customer_name}, your order (Job #{job_id} - {job_type}) has been received and is pending. We'll update you soon. – {shop_name}",
    "In Progress": "Dear {customer_name}, your order (Job #{job_id} - {job_type}) is now In Progress. Expected completion: {due_date}. – {shop_name}",
    "Completed":   "Dear {customer_name}, your order (Job #{job_id} - {job_type}) is COMPLETED! Please visit us to collect. – {shop_name}",
    "Delivered":   "Dear {customer_name}, your order (Job #{job_id} - {job_type}) has been Delivered. Thank you for choosing {shop_name}! 🙏",
    "Cancelled":   "Dear {customer_name}, your order (Job #{job_id} - {job_type}) has been Cancelled. Please contact us for details. – {shop_name}",
    "Custom":      "",
}


class WhatsAppSMSDialog:
    """
    Dialog to send a WhatsApp message (via wa.me link) or compose an SMS
    to the customer of a given job. Also saves a notification log.
    """
    def __init__(self, parent, job_id, user_info):
        self.parent    = parent
        self.job_id    = job_id
        self.user_info = user_info

        self.job_data = get_job_for_notification(job_id)
        if not self.job_data:
            messagebox.showerror("Error", f"Job #{job_id} not found.")
            return

        self._build_ui()

    def _build_ui(self):
        win = tk.Toplevel(self.parent)
        win.title(f"📲 Notify Customer — Job #{self.job_id}")
        win.geometry("560x480")
        win.resizable(False, False)
        win.grab_set()
        self.win = win

        jd = self.job_data
        mobile   = jd.get("customer_mobile", "")
        cust     = jd.get("customer_name", "")
        status   = jd.get("status", "")
        shop     = jd.get("shop_name", "KPR Lab")

        # Banner
        banner = tk.Frame(win, bg="#E3F2FD", padx=10, pady=8)
        banner.pack(fill=tk.X)
        tk.Label(banner, text=f"Job #{self.job_id}  |  {jd.get('job_type','—')}  |  Customer: {cust}  |  Mobile: {mobile}",
                 bg="#E3F2FD", font=("Arial",10,"bold"), fg="#0D47A1").pack(anchor="w")

        frame = ttk.Frame(win, padding=12)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        # Mobile override
        ttk.Label(frame, text="Mobile Number:").grid(row=0, column=0, sticky="w", pady=6)
        self.mobile_var = tk.StringVar(value=mobile)
        ttk.Entry(frame, textvariable=self.mobile_var, width=20).grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(frame, text="(include country code, e.g. 91XXXXXXXXXX)",
                  foreground="gray", font=("Arial",8)).grid(row=1, column=1, sticky="w")

        # Template picker
        ttk.Label(frame, text="Template:").grid(row=2, column=0, sticky="w", pady=6)
        self.tmpl_var = tk.StringVar(value=status if status in STATUS_TEMPLATES else "Custom")
        tmpl_cb = ttk.Combobox(frame, textvariable=self.tmpl_var,
                               values=list(STATUS_TEMPLATES.keys()), state="readonly", width=20)
        tmpl_cb.grid(row=2, column=1, sticky="w", pady=6)
        tmpl_cb.bind("<<ComboboxSelected>>", self._apply_template)

        # Message box
        ttk.Label(frame, text="Message:").grid(row=3, column=0, sticky="nw", pady=6)
        self.msg_text = tk.Text(frame, width=46, height=7, wrap=tk.WORD, font=("Arial", 9))
        self.msg_text.grid(row=3, column=1, sticky="ew", pady=6)
        sb = ttk.Scrollbar(frame, command=self.msg_text.yview)
        sb.grid(row=3, column=2, sticky="ns")
        self.msg_text.configure(yscrollcommand=sb.set)

        # Char counter
        self.char_lbl = ttk.Label(frame, text="0 chars", foreground="gray", font=("Arial",8))
        self.char_lbl.grid(row=4, column=1, sticky="w")
        self.msg_text.bind("<KeyRelease>", self._update_char_count)

        # Pre-fill template
        self._apply_template()

        # Buttons
        btn_f = ttk.Frame(win, padding=(12, 4, 12, 10))
        btn_f.pack(fill=tk.X)
        ttk.Button(btn_f, text="💬 Open WhatsApp",
                   command=self._send_whatsapp).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_f, text="📱 Open SMS",
                   command=self._send_sms).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_f, text="📋 Copy Message",
                   command=self._copy_message).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_f, text="Close",
                   command=win.destroy).pack(side=tk.RIGHT, padx=5)

        # Settings reminder
        settings = get_app_settings()
        if not settings.get("shop_name"):
            ttk.Label(win, text="⚠  Set shop_name in Settings for better messages.",
                      foreground="#E65100", font=("Arial",8)).pack(pady=2)

    def _format_message(self):
        jd   = self.job_data
        tmpl = STATUS_TEMPLATES.get(self.tmpl_var.get(), "")
        try:
            return tmpl.format(
                customer_name = jd.get("customer_name","Customer"),
                job_id        = jd.get("job_id",""),
                job_type      = jd.get("job_type",""),
                due_date      = jd.get("due_date","") or "TBD",
                shop_name     = jd.get("shop_name","KPR Lab"),
                status        = jd.get("status",""),
            )
        except Exception:
            return tmpl

    def _apply_template(self, event=None):
        msg = self._format_message()
        self.msg_text.delete("1.0", tk.END)
        self.msg_text.insert("1.0", msg)
        self._update_char_count()

    def _update_char_count(self, event=None):
        n = len(self.msg_text.get("1.0", tk.END).strip())
        self.char_lbl.config(text=f"{n} chars")

    def _get_message(self):
        return self.msg_text.get("1.0", tk.END).strip()

    def _get_mobile(self):
        # Strip non-digits, ensure starts with country code
        m = "".join(c for c in self.mobile_var.get() if c.isdigit())
        return m

    def _send_whatsapp(self):
        mobile = self._get_mobile()
        if not mobile:
            messagebox.showerror("Error", "Please enter a valid mobile number.", parent=self.win)
            return
        msg = self._get_message()
        url = f"https://wa.me/{mobile}?text={urllib.parse.quote(msg)}"
        webbrowser.open(url)
        log_notification_sent(self.job_id, "WhatsApp", mobile, msg, self.user_info.get("id"))
        messagebox.showinfo("WhatsApp", "✅ WhatsApp opened in browser!\nMessage logged.", parent=self.win)

    def _send_sms(self):
        mobile = self._get_mobile()
        if not mobile:
            messagebox.showerror("Error", "Please enter a valid mobile number.", parent=self.win)
            return
        msg = self._get_message()
        # sms: URI works on Windows/Android; on PC it opens default messaging app
        url = f"sms:{mobile}?body={urllib.parse.quote(msg)}"
        webbrowser.open(url)
        log_notification_sent(self.job_id, "SMS", mobile, msg, self.user_info.get("id"))
        messagebox.showinfo("SMS", "✅ SMS app opened!\nMessage logged.", parent=self.win)

    def _copy_message(self):
        msg = self._get_message()
        self.win.clipboard_clear()
        self.win.clipboard_append(msg)
        messagebox.showinfo("Copied", "Message copied to clipboard!", parent=self.win)


# ─────────────────────────────────────────────────────────────────────────────
# PASSWORD CHANGE / RESET DIALOGS
# ─────────────────────────────────────────────────────────────────────────────

class PasswordChangeDialog:
    """Staff / any user can change their own password."""
    def __init__(self, parent, user_info):
        self.parent    = parent
        self.user_info = user_info
        self._build_ui()

    def _build_ui(self):
        win = tk.Toplevel(self.parent)
        win.title("🔒 Change My Password")
        win.geometry("380x300")
        win.resizable(False, False)
        win.grab_set()
        self.win = win

        banner = tk.Frame(win, bg="#E8F5E9", padx=10, pady=8)
        banner.pack(fill=tk.X)
        uname = self.user_info.get("full_name") or self.user_info.get("username","")
        tk.Label(banner, text=f"👤  {uname}", bg="#E8F5E9",
                 font=("Arial",11,"bold"), fg="#1B5E20").pack(anchor="w")

        frame = ttk.Frame(win, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Current Password:").grid(row=0, column=0, sticky="w", pady=8)
        self.old_var = tk.StringVar()
        old_e = ttk.Entry(frame, textvariable=self.old_var, show="●", width=24)
        old_e.grid(row=0, column=1, sticky="ew", pady=8)
        old_e.focus_set()

        ttk.Label(frame, text="New Password:").grid(row=1, column=0, sticky="w", pady=8)
        self.new_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.new_var, show="●", width=24).grid(row=1, column=1, sticky="ew", pady=8)

        ttk.Label(frame, text="Confirm New:").grid(row=2, column=0, sticky="w", pady=8)
        self.conf_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.conf_var, show="●", width=24).grid(row=2, column=1, sticky="ew", pady=8)

        # Strength hint
        self.strength_lbl = ttk.Label(frame, text="", foreground="gray", font=("Arial",8))
        self.strength_lbl.grid(row=3, column=1, sticky="w")
        self.new_var.trace_add("write", self._check_strength)

        btn_f = ttk.Frame(win, padding=(16,4,16,12))
        btn_f.pack(fill=tk.X)
        ttk.Button(btn_f, text="🔒 Change Password", command=self._save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_f, text="Cancel", command=win.destroy).pack(side=tk.LEFT, padx=5)

    def _check_strength(self, *_):
        p = self.new_var.get()
        if len(p) == 0:
            self.strength_lbl.config(text="")
        elif len(p) < 6:
            self.strength_lbl.config(text="Too short (min 6)", foreground="#C62828")
        elif len(p) < 9:
            self.strength_lbl.config(text="Weak — consider a longer password", foreground="#E65100")
        else:
            self.strength_lbl.config(text="✅ Good strength", foreground="#2E7D32")

    def _save(self):
        old = self.old_var.get()
        new = self.new_var.get()
        conf = self.conf_var.get()
        if not old or not new:
            messagebox.showerror("Error", "All fields are required.", parent=self.win)
            return
        if new != conf:
            messagebox.showerror("Error", "New password and confirmation do not match.", parent=self.win)
            return
        ok, msg = change_user_password(self.user_info["id"], old, new)
        if ok:
            messagebox.showinfo("Success", f"✅ {msg}", parent=self.win)
            self.win.destroy()
        else:
            messagebox.showerror("Failed", msg, parent=self.win)


class AdminPasswordResetDialog:
    """Admin can reset any staff member's password without knowing old one."""
    def __init__(self, parent, admin_info):
        self.parent     = parent
        self.admin_info = admin_info
        self._build_ui()

    def _build_ui(self):
        win = tk.Toplevel(self.parent)
        win.title("🔑 Admin — Reset User Password")
        win.geometry("420x300")
        win.resizable(False, False)
        win.grab_set()
        self.win = win

        banner = tk.Frame(win, bg="#FFF3E0", padx=10, pady=8)
        banner.pack(fill=tk.X)
        tk.Label(banner, text="🔑  Admin Password Reset", bg="#FFF3E0",
                 font=("Arial",11,"bold"), fg="#E65100").pack(anchor="w")
        tk.Label(banner, text="Reset any user's password without needing their current password.",
                 bg="#FFF3E0", font=("Arial",8), fg="#555").pack(anchor="w")

        frame = ttk.Frame(win, padding=16)
        frame.pack(fill=tk.BOTH, expand=True)
        frame.columnconfigure(1, weight=1)

        # Load users
        try:
            all_users = get_all_users()
            self._user_map = {
                f"{u.get('full_name') or u['username']} ({u['username']}) — {u['role']}": u['id']
                for u in all_users if u['id'] != self.admin_info['id']
            }
        except Exception:
            self._user_map = {}

        ttk.Label(frame, text="Select User:").grid(row=0, column=0, sticky="w", pady=8)
        self.user_var = tk.StringVar()
        user_cb = ttk.Combobox(frame, textvariable=self.user_var,
                               values=list(self._user_map.keys()), state="readonly", width=34)
        user_cb.grid(row=0, column=1, sticky="ew", pady=8)

        ttk.Label(frame, text="New Password:").grid(row=1, column=0, sticky="w", pady=8)
        self.new_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.new_var, show="●", width=24).grid(row=1, column=1, sticky="ew", pady=8)

        ttk.Label(frame, text="Confirm:").grid(row=2, column=0, sticky="w", pady=8)
        self.conf_var = tk.StringVar()
        ttk.Entry(frame, textvariable=self.conf_var, show="●", width=24).grid(row=2, column=1, sticky="ew", pady=8)

        btn_f = ttk.Frame(win, padding=(16,4,16,12))
        btn_f.pack(fill=tk.X)
        ttk.Button(btn_f, text="🔑 Reset Password", command=self._save).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_f, text="Cancel", command=win.destroy).pack(side=tk.LEFT, padx=5)

    def _save(self):
        sel = self.user_var.get()
        if not sel or sel not in self._user_map:
            messagebox.showerror("Error", "Please select a user.", parent=self.win)
            return
        new  = self.new_var.get()
        conf = self.conf_var.get()
        if not new:
            messagebox.showerror("Error", "New password is required.", parent=self.win)
            return
        if new != conf:
            messagebox.showerror("Error", "Passwords do not match.", parent=self.win)
            return
        target_id = self._user_map[sel]
        ok, msg = admin_reset_password(self.admin_info["id"], target_id, new)
        if ok:
            messagebox.showinfo("Success", f"✅ {msg}", parent=self.win)
            self.win.destroy()
        else:
            messagebox.showerror("Failed", msg, parent=self.win)


# ─────────────────────────────────────────────────────────────────────────────
# NOTIFICATION SETTINGS PANEL (inside Settings module integration)
# ─────────────────────────────────────────────────────────────────────────────

class NotificationSettingsPanel:
    """
    Embeddable panel for Admin Settings to configure:
    - Shop name / phone / address (used in slips + WA messages)
    - Slip footer text
    - WhatsApp message templates per status
    """
    def __init__(self, parent_frame):
        self.parent = parent_frame
        self._build()

    def _build(self):
        settings = get_app_settings()
        frame = ttk.LabelFrame(self.parent, text="📲 Notification & Slip Settings", padding=12)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=8)
        frame.columnconfigure(1, weight=1)

        fields = [
            ("shop_name",    "Shop Name:",         "KPR Lab"),
            ("shop_phone",   "Shop Phone:",         ""),
            ("shop_address", "Shop Address:",       ""),
            ("slip_footer",  "Order Slip Footer:",  "Thank you for your business!"),
        ]
        self._vars = {}
        for i, (key, label, default) in enumerate(fields):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky="w", padx=5, pady=5)
            v = tk.StringVar(value=settings.get(key, default))
            ttk.Entry(frame, textvariable=v, width=50).grid(row=i, column=1, sticky="ew", padx=5, pady=5)
            self._vars[key] = v

        # WA Template customisation
        ttk.Label(frame, text="WhatsApp Templates:", font=("Arial",9,"bold")).grid(
            row=len(fields), column=0, columnspan=2, sticky="w", padx=5, pady=(12,4))

        self._tmpl_vars = {}
        for j, (status, tmpl) in enumerate(STATUS_TEMPLATES.items()):
            if status == "Custom":
                continue
            row_i = len(fields) + 1 + j
            ttk.Label(frame, text=f"{status}:").grid(row=row_i, column=0, sticky="nw", padx=5, pady=3)
            saved_key = f"wa_tmpl_{status.lower().replace(' ','_')}"
            v = tk.StringVar(value=settings.get(saved_key, tmpl))
            e = ttk.Entry(frame, textvariable=v, width=50)
            e.grid(row=row_i, column=1, sticky="ew", padx=5, pady=3)
            self._tmpl_vars[saved_key] = v

        def save_all():
            kwargs = {k: v.get() for k, v in self._vars.items()}
            kwargs.update({k: v.get() for k, v in self._tmpl_vars.items()})
            update_app_settings(**kwargs)
            # Update live templates dict
            for saved_key, v in self._tmpl_vars.items():
                status_name = saved_key.replace("wa_tmpl_","").replace("_"," ").title()
                if status_name in STATUS_TEMPLATES:
                    STATUS_TEMPLATES[status_name] = v.get()
            messagebox.showinfo("Saved", "✅ Notification & Slip settings saved!")

        row_save = len(fields) + 1 + len(STATUS_TEMPLATES)
        ttk.Button(frame, text="💾 Save Settings", command=save_all).grid(
            row=row_save, column=0, columnspan=2, pady=12)
