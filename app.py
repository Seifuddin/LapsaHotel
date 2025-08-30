import os
import sys
import subprocess
import datetime
import tkinter as tk
from tkinter import ttk, messagebox

import mysql.connector

# ReportLab (PDF)
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
)
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

# Charts in dashboard
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


# ---------------- CONFIG ----------------
TOTAL_ROOM_INVENTORY = 30          # adjust to your hotel inventory
PRICES = {"Single": 50, "Double": 80, "Suite": 120}
VAT_RATE = 0.16                    # 16% VAT (change to your region)


# ---------------- DATABASE CONNECTION ----------------
def connect_db():
    try:
        conn = mysql.connector.connect(
            host="localhost",
            user="root",
            password="",
            database="hotel_db"
        )
        return conn
    except mysql.connector.Error as err:
        messagebox.showerror("Database Error", f"Error: {err}")
        return None


# ---------------- UTILITIES ----------------
def format_money(value):
    try:
        return "${:,.2f}".format(float(value))
    except Exception:
        return f"${value}"


def open_file(path):
    try:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.call(["open", path])
        else:
            subprocess.call(["xdg-open", path])
    except Exception:
        # If opening fails silently, we at least keep the saved file.
        pass


# ---------------- MAIN APP ----------------
class HotelBookingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🏨 Hotel Booking System")
        self.root.geometry("1200x900")
        self.root.configure(bg="#f4f6f9")

        # Use ttk style
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", font=("Segoe UI", 11), padding=6)
        style.configure("Treeview.Heading", font=("Segoe UI", 11, "bold"))
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=28)

        # Title
        title = tk.Label(
            root,
            text="🏨 Hotel Booking Management System",
            font=("Segoe UI", 22, "bold"),
            bg="#2c3e50",
            fg="white",
            pady=12
        )
        title.pack(fill="x")

        # Layout frames
        container = tk.Frame(root, bg="#f4f6f9")
        container.pack(fill="both", expand=True, padx=15, pady=15)

        left_frame = tk.Frame(container, bg="white", bd=1, relief="solid")
        left_frame.pack(side="left", fill="y", padx=(0, 10), ipadx=15, ipady=15)

        right_frame = tk.Frame(container, bg="white", bd=1, relief="solid")
        right_frame.pack(side="right", fill="both", expand=True)

        # ----------- Dashboard (Top Cards) -----------
        dashboard_frame = tk.Frame(right_frame, bg="#f4f6f9")
        dashboard_frame.pack(fill="x", pady=10, padx=10)

        self.card_total = self.create_card(dashboard_frame, "📊 Total Bookings", "0", "#3498db")
        self.card_rooms = self.create_card(dashboard_frame, "🛏️ Available Rooms", "0", "#27ae60")
        self.card_revenue = self.create_card(dashboard_frame, "💰 Total Revenue", "$0", "#e67e22")

        # Refresh Dashboard button (doesn't reload table)
        refresh_bar = tk.Frame(right_frame, bg="white")
        refresh_bar.pack(fill="x", padx=10, pady=(0, 5))
        ttk.Button(
            refresh_bar,
            text="⟲ Refresh Dashboard",
            command=self.update_dashboard
        ).pack(anchor="e", padx=5, pady=6)

        # ----------- Chart Section -----------
        self.chart_frame = tk.Frame(right_frame, bg="white")
        self.chart_frame.pack(fill="x", padx=10, pady=10)
        self.chart_canvas = None
        self.chart_placeholder = tk.Label(
            self.chart_frame,
            text="No data to display yet.",
            font=("Segoe UI", 10),
            bg="white",
            fg="#7f8c8d"
        )
        self.chart_placeholder.pack(pady=10)

        # ----------- Booking Form (Left Panel) -----------
        tk.Label(left_frame, text="Booking Details", font=("Segoe UI", 14, "bold"), bg="white").pack(pady=10)
        form_frame = tk.Frame(left_frame, bg="white")
        form_frame.pack(pady=10)

        self.fields = {}
        labels = ["Full Name", "Phone", "Email", "ID/Passport No", "Room Type", "Nights"]
        for i, label in enumerate(labels):
            tk.Label(form_frame, text=label + ":", font=("Segoe UI", 11), bg="white", anchor="w").grid(row=i, column=0, sticky="w", pady=5)
            if label == "Room Type":
                self.fields[label] = ttk.Combobox(form_frame, values=list(PRICES.keys()), font=("Segoe UI", 11), state="readonly")
                self.fields[label].set("Single")
            else:
                self.fields[label] = tk.Entry(form_frame, font=("Segoe UI", 11))
            self.fields[label].grid(row=i, column=1, pady=5, padx=5)

        # Buttons
        btn_frame = tk.Frame(left_frame, bg="white")
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="Book Now", command=self.book_room).grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(btn_frame, text="Update", command=self.update_booking).grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(btn_frame, text="Delete", command=self.delete_booking).grid(row=2, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(btn_frame, text="Search", command=self.search_booking).grid(row=3, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(btn_frame, text="View All", command=self.view_bookings).grid(row=4, column=0, padx=5, pady=5, sticky="ew")
        ttk.Button(btn_frame, text="Generate Receipt", command=self.generate_receipt).grid(row=5, column=0, padx=5, pady=5, sticky="ew")

        # ----------- Booking Table (Right Panel) -----------
        table_frame = tk.Frame(right_frame, bg="white")
        table_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.tree = ttk.Treeview(
            table_frame,
            columns=("ID", "Name", "Phone", "Email", "ID No", "Room", "Nights", "Cost"),
            show="headings"
        )
        self.tree.pack(fill="both", expand=True)

        for col in self.tree["columns"]:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center")

        self.tree.tag_configure("oddrow", background="#ecf0f1")
        self.tree.tag_configure("evenrow", background="white")
        self.tree.bind("<<TreeviewSelect>>", self.on_row_selected)

        self.view_bookings()

    # ---------------- Dashboard Card ----------------
    def create_card(self, parent, title, value, color):
        frame = tk.Frame(parent, bg=color, bd=0, relief="flat")
        frame.pack(side="left", fill="both", expand=True, padx=8, pady=5)

        tk.Label(frame, text=title, font=("Segoe UI", 12, "bold"), fg="white", bg=color).pack(pady=(10, 0))
        label_val = tk.Label(frame, text=value, font=("Segoe UI", 18, "bold"), fg="white", bg=color)
        label_val.pack(pady=5)

        return label_val

    def update_dashboard(self):
        conn = connect_db()
        if conn:
            cursor = conn.cursor()

            # Total bookings
            cursor.execute("SELECT COUNT(*) FROM bookings")
            total_bookings = cursor.fetchone()[0]

            # Revenue
            cursor.execute("SELECT SUM(total_cost) FROM bookings")
            revenue = cursor.fetchone()[0] or 0

            # Available rooms
            available_rooms = max(TOTAL_ROOM_INVENTORY - (total_bookings or 0), 0)

            # Update dashboard labels
            self.card_total.config(text=str(total_bookings))
            self.card_revenue.config(text=format_money(revenue))
            self.card_rooms.config(text=str(available_rooms))

            # Update chart
            self.update_chart(cursor)

            conn.close()

    def update_chart(self, cursor):
        cursor.execute("SELECT room_type, COUNT(*) FROM bookings GROUP BY room_type")
        data = cursor.fetchall()

        # Clear old chart or placeholder
        if self.chart_canvas:
            self.chart_canvas.get_tk_widget().destroy()
            self.chart_canvas = None
        self.chart_placeholder.pack_forget()

        if not data:
            self.chart_placeholder.config(text="No data to display yet.")
            self.chart_placeholder.pack(pady=10)
            return

        room_types = [row[0] for row in data]
        counts = [row[1] for row in data]

        fig, ax = plt.subplots(figsize=(6.5, 3.2))
        ax.bar(room_types, counts)
        ax.set_title("Bookings per Room Type")
        ax.set_ylabel("Number of Bookings")
        ax.set_xlabel("Room Type")
        ax.grid(axis="y", linestyle="--", alpha=0.3)

        self.chart_canvas = FigureCanvasTkAgg(fig, master=self.chart_frame)
        self.chart_canvas.draw()
        self.chart_canvas.get_tk_widget().pack(fill="both", expand=True)

    # ---------------- CRUD Functions ----------------
    def book_room(self):
        data = self.get_form_data()
        if not data:
            return
        name, phone, email, id_number, room_type, nights, total_cost = data
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO bookings (name, phone, email, id_number, room_type, nights, total_cost) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (name, phone, email, id_number, room_type, nights, total_cost)
            )
            conn.commit()
            conn.close()
            messagebox.showinfo("Success", f"Room booked! Total cost: {format_money(total_cost)}")
            self.clear_form()
            self.view_bookings()

    def update_booking(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror("Error", "Select a booking to update")
            return
        booking_id = self.tree.item(selected[0])["values"][0]
        data = self.get_form_data()
        if not data:
            return
        name, phone, email, id_number, room_type, nights, total_cost = data
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("""UPDATE bookings 
                              SET name=%s, phone=%s, email=%s, id_number=%s, room_type=%s, nights=%s, total_cost=%s 
                              WHERE id=%s""",
                           (name, phone, email, id_number, room_type, nights, total_cost, booking_id))
            conn.commit()
            conn.close()
            messagebox.showinfo("Success", "Booking updated successfully")
            self.clear_form()
            self.view_bookings()

    def delete_booking(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror("Error", "Select a booking to delete")
            return
        booking_id = self.tree.item(selected[0])["values"][0]
        confirm = messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this booking?")
        if confirm:
            conn = connect_db()
            if conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM bookings WHERE id=%s", (booking_id,))
                conn.commit()
                conn.close()
                messagebox.showinfo("Success", "Booking deleted successfully")
                self.clear_form()
                self.view_bookings()

    def search_booking(self):
        keyword = self.fields["Full Name"].get()
        if not keyword:
            messagebox.showerror("Error", "Enter a name or ID/Passport to search")
            return
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bookings WHERE name LIKE %s OR id_number LIKE %s", (f"%{keyword}%", f"%{keyword}%"))
            rows = cursor.fetchall()
            conn.close()
            self.populate_table(rows)

    def view_bookings(self):
        conn = connect_db()
        if conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM bookings")
            rows = cursor.fetchall()
            conn.close()
            self.populate_table(rows)
            # Also refresh dashboard/cards & chart
            self.update_dashboard()

    def populate_table(self, rows):
        self.tree.delete(*self.tree.get_children())
        for i, row in enumerate(rows):
            tag = "evenrow" if i % 2 == 0 else "oddrow"
            self.tree.insert("", tk.END, values=row, tags=(tag,))

    def on_row_selected(self, event):
        selected = self.tree.selection()
        if selected:
            values = self.tree.item(selected[0])["values"]
            self.fields["Full Name"].delete(0, tk.END)
            self.fields["Full Name"].insert(0, values[1])
            self.fields["Phone"].delete(0, tk.END)
            self.fields["Phone"].insert(0, values[2])
            self.fields["Email"].delete(0, tk.END)
            self.fields["Email"].insert(0, values[3])
            self.fields["ID/Passport No"].delete(0, tk.END)
            self.fields["ID/Passport No"].insert(0, values[4])
            self.fields["Room Type"].set(values[5])
            self.fields["Nights"].delete(0, tk.END)
            self.fields["Nights"].insert(0, values[6])

    def get_form_data(self):
        name = self.fields["Full Name"].get()
        phone = self.fields["Phone"].get()
        email = self.fields["Email"].get()
        id_number = self.fields["ID/Passport No"].get()
        room_type = self.fields["Room Type"].get()
        nights = self.fields["Nights"].get()
        if not (name and phone and email and id_number and room_type and nights):
            messagebox.showerror("Error", "All fields are required!")
            return None
        try:
            nights = int(nights)
            if nights <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Nights must be a positive number!")
            return None

        # Use configured price list
        rate = PRICES.get(room_type, 0)
        subtotal = rate * nights
        tax = round(subtotal * VAT_RATE, 2)
        grand_total = round(subtotal + tax, 2)

        # Save the grand total to DB (so revenue includes tax)
        return name, phone, email, id_number, room_type, nights, grand_total

    def clear_form(self):
        for field in self.fields.values():
            if isinstance(field, ttk.Combobox):
                field.set("Single")
            else:
                field.delete(0, tk.END)

    # ---------------- BILLING RECEIPT (SMART & PROFESSIONAL) ----------------
    def generate_receipt(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showerror("Error", "Select a booking to generate receipt")
            return

        values = self.tree.item(selected[0])["values"]
        booking_id, name, phone, email, id_number, room_type, nights, stored_total = values

        # Derive rate & breakdown smartly
        rate = PRICES.get(room_type, 0)
        calculated_subtotal = round(rate * int(nights), 2)
        calculated_tax = round(calculated_subtotal * VAT_RATE, 2)
        calculated_grand = round(calculated_subtotal + calculated_tax, 2)

        # If DB total differs (e.g., historical data before tax), show both clearly
        note_diff = ""
        if abs(float(stored_total) - calculated_grand) > 0.01:
            note_diff = "(Note: stored total differs from current tax settings.)"

        # Paths & filename
        os.makedirs("receipts", exist_ok=True)
        ref = f"HB-{int(booking_id):06d}" if str(booking_id).isdigit() else f"HB-{booking_id}"
        today_str = datetime.datetime.now().strftime("%Y-%m-%d")
        filename = f"receipts/Receipt_{ref}_{today_str}.pdf"

        # Build PDF
        doc = SimpleDocTemplate(
            filename,
            pagesize=letter,
            rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
        )
        styles = getSampleStyleSheet()
        styles.add(ParagraphStyle(name="SmallGrey", fontSize=9, textColor=colors.grey))
        styles.add(ParagraphStyle(name="HeaderBig", fontSize=16, leading=20, spaceAfter=8, textColor=colors.darkblue))
        styles.add(ParagraphStyle(name="Tag", fontSize=10, textColor=colors.white))

        story = []

        # Header with optional logo
        header_table_data = []
        logo_path = "logo.png"
        if os.path.exists(logo_path):
            logo_img = Image(logo_path, width=1.1*inch, height=1.1*inch)
        else:
            # Placeholder drawing if no logo
            logo_img = Paragraph("<b>HOTEL</b>", styles["Title"])

        hotel_info = Paragraph(
            "<b>Grand Azure Hotel</b><br/>"
            "123 Ocean Drive, Seaview City<br/>"
            "Tel: +1 (555) 123-4567 · bookings@grandazure.example<br/>"
            f"Receipt Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
            styles["Normal"]
        )
        header_table_data.append([logo_img, hotel_info])
        header_table = Table(header_table_data, colWidths=[1.4*inch, 4.6*inch])
        header_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE")
        ]))
        story.append(header_table)
        story.append(Spacer(1, 12))

        # Receipt Title & Reference
        story.append(Paragraph(f"Booking Receipt — <b>{ref}</b>", styles["HeaderBig"]))
        story.append(Spacer(1, 6))

        # Guest & Stay Info
        guest_table_data = [
            ["Guest Name", name],
            ["Phone", phone],
            ["Email", email],
            ["ID/Passport", id_number],
            ["Room Type", room_type],
            ["Nights", str(nights)],
        ]
        guest_table = Table(guest_table_data, colWidths=[1.5*inch, 4.5*inch])
        guest_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#ecf0f1")),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#2c3e50")),
            ("BOX", (0, 0), (-1, -1), 0.25, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica")
        ]))
        story.append(guest_table)
        story.append(Spacer(1, 12))

        # Charges Table (smart breakdown)
        charges_data = [
            ["Description", "Qty", "Rate", "Amount"],
            [f"{room_type} Room", str(nights), format_money(rate), format_money(calculated_subtotal)],
            ["Tax / VAT", "", f"{int(VAT_RATE*100)}%", format_money(calculated_tax)],
            ["", "", "Grand Total", format_money(calculated_grand)],
        ]
        charges_table = Table(charges_data, colWidths=[3.2*inch, 0.8*inch, 1.2*inch, 1.2*inch])
        charges_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("BOX", (0, 0), (-1, -1), 0.25, colors.grey),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#ecf0f1")),
            ("FONTNAME", (2, -1), (2, -1), "Helvetica-Bold"),
            ("FONTNAME", (3, -1), (3, -1), "Helvetica-Bold"),
        ]))
        story.append(charges_table)
        story.append(Spacer(1, 6))

        # Stored total note (if different)
        if note_diff:
            story.append(Paragraph(
                f"<font color='#e67e22'><b>Note:</b> The amount stored in the system for this booking is "
                f"{format_money(stored_total)}; current calculation shows {format_money(calculated_grand)}. "
                f"{note_diff}</font>",
                styles["SmallGrey"]
            ))
            story.append(Spacer(1, 6))

        # QR Code (Booking reference + guest + total)
        qr_text = f"{ref}|{name}|{format_money(calculated_grand)}"
        qr_code = qr.QrCodeWidget(qr_text)
        bounds = qr_code.getBounds()
        size = 1.6 * inch
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        d = Drawing(size, size, transform=[size/width, 0, 0, size/height, 0, 0])
        d.add(qr_code)
        # put QR and a small legend in a table for alignment
        qr_table = Table([[d, Paragraph(
            "<b>Scan for booking summary</b><br/>"
            "Use this at check-in for quick lookup.",
            styles["SmallGrey"]
        )]], colWidths=[size+12, 3.1*inch])
        qr_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(qr_table)
        story.append(Spacer(1, 10))

        # Payment / Terms
        story.append(Paragraph(
            "<b>Payment Method:</b> Cash / Card on file<br/>"
            "<b>Terms:</b> Please present a valid ID at check-in. "
            "Cancellations within 24h may incur charges. Taxes subject to local regulations.",
            styles["SmallGrey"]
        ))
        story.append(Spacer(1, 4))
        story.append(Paragraph("Thank you for choosing Grand Azure Hotel. We wish you a pleasant stay!", styles["Normal"]))

        # Build and save
        doc.build(story)

        messagebox.showinfo("Receipt Generated", f"Receipt saved as:\n{filename}")
        open_file(filename)


if __name__ == "__main__":
    root = tk.Tk()
    app = HotelBookingApp(root)
    root.mainloop()
