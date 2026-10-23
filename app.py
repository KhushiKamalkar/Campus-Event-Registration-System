"""Campus Event Registration System (CERS) - Tkinter GUI for MongoDB"""
import re
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import cers_db as db
from cers_db import AppError

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.]+$")


def fmt(v):
    """Make a value readable in the table."""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d") if v.hour == v.minute == v.second == 0 else v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))
    return v


class Table(ttk.Frame):
    """Tree view where each row keeps its MongoDB _id as the item id."""
    def __init__(self, parent, height=10):
        super().__init__(parent)
        self.tree = ttk.Treeview(self, show="headings", height=height)
        sb = ttk.Scrollbar(self, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def load(self, cols, rows, ids=None):
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c.replace("_", " ").title())
            self.tree.column(c, width=100, anchor="w")
        self.tree.delete(*self.tree.get_children())
        for i, r in enumerate(rows):
            self.tree.insert("", "end", iid=str(ids[i]) if ids else None, values=[fmt(x) for x in r])

    def selected(self):
        s = self.tree.selection()
        return (s[0], self.tree.item(s[0])["values"]) if s else (None, None)


def form_row(parent, label, r, widget=None):
    ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=4, pady=2)
    w = widget or ttk.Entry(parent, width=28)
    w.grid(row=r, column=1, padx=4, pady=2, sticky="w")
    return w


def buttons(parent, row, items):
    bf = ttk.Frame(parent)
    bf.grid(row=row, column=0, columnspan=2, pady=6)
    for t, c in items:
        ttk.Button(bf, text=t, command=c).pack(side="left", padx=3)


def guard(fn):
    """Run an action and show any AppError in a message box."""
    try:
        fn()
        return True
    except AppError as e:
        messagebox.showerror("Error", str(e))
    except Exception as e:
        messagebox.showerror("Unexpected error", str(e))
    return False


# ------------------------------------------------------------------ STUDENTS
class StudentTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        f = ttk.LabelFrame(self, text="Student details")
        f.pack(fill="x", padx=8, pady=6)
        self.roll = form_row(f, "Roll No *", 0)
        self.name = form_row(f, "Name *", 1)
        self.email = form_row(f, "Email *", 2)
        self.phone = form_row(f, "Phone (10 digits) *", 3)
        self.dept = form_row(f, "Department *", 4, ttk.Combobox(f, width=26, state="readonly"))
        self.year = form_row(f, "Year (1-4) *", 5, ttk.Combobox(f, width=26, state="readonly", values=[1, 2, 3, 4]))
        self.sel_id = None
        buttons(f, 6, [("Add", self.add), ("Update", self.update), ("Delete", self.delete), ("Clear", self.clear)])
        self.table = Table(self)
        self.table.pack(fill="both", expand=True, padx=8, pady=4)
        self.table.tree.bind("<<TreeviewSelect>>", self.pick)
        self.refresh()

    def refresh(self):
        self.dept["values"] = [d["name"] for d in db.get_db().departments.find()]
        rows = db.list_students()
        self.table.load(["roll_no", "name", "email", "phone", "dept", "year"],
                        [[s["roll_no"], s["name"], s["email"], s["phone"], s["dept"], s["year"]] for s in rows],
                        [s["_id"] for s in rows])

    def validate(self):
        v = [self.roll.get().strip(), self.name.get().strip(), self.email.get().strip(),
             self.phone.get().strip(), self.dept.get(), self.year.get()]
        if not all(v):
            messagebox.showwarning("Missing data", "Fill all fields marked *")
        elif not EMAIL_RE.match(v[2]):
            messagebox.showwarning("Invalid email", "Enter a valid email address")
        elif not re.fullmatch(r"\d{10}", v[3]):
            messagebox.showwarning("Invalid phone", "Phone must be exactly 10 digits")
        elif not re.fullmatch(r"[A-Za-z .]{2,}", v[1]):
            messagebox.showwarning("Invalid name", "Name can have letters and spaces only")
        else:
            return v
        return None

    def add(self):
        v = self.validate()
        if v and guard(lambda: db.add_student(*v)):
            self.clear(); self.refresh()

    def update(self):
        if not self.sel_id:
            return messagebox.showinfo("Select", "Pick a student from the table first")
        v = self.validate()
        if v and guard(lambda: db.update_student(self.sel_id, *v)):
            self.clear(); self.refresh()

    def delete(self):
        if not self.sel_id:
            return messagebox.showinfo("Select", "Pick a student from the table first")
        if messagebox.askyesno("Confirm", "Delete this student and their registrations?"):
            if guard(lambda: db.delete_student(self.sel_id)):
                self.clear(); self.refresh()

    def pick(self, _):
        iid, r = self.table.selected()
        if not iid:
            return
        self.sel_id = iid
        self.clear(keep=True)
        for w, val in zip((self.roll, self.name, self.email, self.phone), r[:4]):
            w.insert(0, val)
        self.phone.delete(0, "end"); self.phone.insert(0, str(r[3]).zfill(10))
        self.dept.set(r[4]); self.year.set(r[5])

    def clear(self, keep=False):
        for w in (self.roll, self.name, self.email, self.phone):
            w.delete(0, "end")
        self.dept.set(""); self.year.set("")
        if not keep:
            self.sel_id = None


# -------------------------------------------------------------------- EVENTS
class EventTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        f = ttk.LabelFrame(self, text="Event details")
        f.pack(fill="x", padx=8, pady=6)
        self.title = form_row(f, "Title *", 0)
        self.club = form_row(f, "Club *", 1, ttk.Combobox(f, width=26, state="readonly"))
        self.venue = form_row(f, "Venue *", 2, ttk.Combobox(f, width=26, state="readonly"))
        self.date = form_row(f, "Date (YYYY-MM-DD) *", 3)
        self.fee = form_row(f, "Fee (Rs) *", 4)
        self.seats = form_row(f, "Max seats *", 5)
        self.status = form_row(f, "Status", 6, ttk.Combobox(f, width=26, state="readonly",
                                                           values=["OPEN", "CLOSED", "CANCELLED"]))
        self.status.set("OPEN")
        self.sel_id = None
        buttons(f, 7, [("Add", self.add), ("Update", self.update), ("Delete", self.delete), ("Clear", self.clear)])
        self.table = Table(self)
        self.table.pack(fill="both", expand=True, padx=8, pady=4)
        self.table.tree.bind("<<TreeviewSelect>>", self.pick)
        self.refresh()

    def refresh(self):
        self.club["values"] = [c["name"] for c in db.get_db().clubs.find()]
        self.venue["values"] = [v["name"] for v in db.get_db().venues.find()]
        rows = db.list_events()
        self.table.load(["title", "club", "venue", "event_date", "fee", "max_seats", "seats_left", "status"],
                        [[e["title"], e["club"]["name"], e["venue"]["name"], e["event_date"], e["fee"],
                          e["max_seats"], e["seats_left"], e["status"]] for e in rows],
                        [e["_id"] for e in rows])

    def validate(self):
        if not all([self.title.get().strip(), self.club.get(), self.venue.get(),
                    self.date.get().strip(), self.fee.get().strip(), self.seats.get().strip()]):
            messagebox.showwarning("Missing data", "Fill all fields marked *")
            return None
        try:
            datetime.strptime(self.date.get().strip(), "%Y-%m-%d")
        except ValueError:
            messagebox.showwarning("Invalid date", "Use format YYYY-MM-DD")
            return None
        try:
            fee = float(self.fee.get()); seats = int(self.seats.get())
        except ValueError:
            messagebox.showwarning("Invalid number", "Fee must be a number and seats a whole number")
            return None
        if fee < 0 or seats <= 0:
            messagebox.showwarning("Invalid value", "Fee cannot be negative and seats must be above 0")
            return None
        return (self.title.get().strip(), self.club.get(), self.venue.get(),
                self.date.get().strip(), fee, seats, self.status.get())

    def add(self):
        v = self.validate()
        if v and guard(lambda: db.add_event(*v)):
            self.clear(); self.refresh()

    def update(self):
        if not self.sel_id:
            return messagebox.showinfo("Select", "Pick an event from the table first")
        v = self.validate()
        if v and guard(lambda: db.update_event(self.sel_id, *v)):
            self.clear(); self.refresh()

    def delete(self):
        if not self.sel_id:
            return messagebox.showinfo("Select", "Pick an event from the table first")
        if messagebox.askyesno("Confirm", "Delete this event and its registrations?"):
            if guard(lambda: db.delete_event(self.sel_id)):
                self.clear(); self.refresh()

    def pick(self, _):
        iid, r = self.table.selected()
        if not iid:
            return
        self.sel_id = iid
        self.clear(keep=True)
        self.title.insert(0, r[0]); self.club.set(r[1]); self.venue.set(r[2])
        self.date.insert(0, r[3]); self.fee.insert(0, r[4]); self.seats.insert(0, r[5]); self.status.set(r[7])

    def clear(self, keep=False):
        for w in (self.title, self.date, self.fee, self.seats):
            w.delete(0, "end")
        self.club.set(""); self.venue.set(""); self.status.set("OPEN")
        if not keep:
            self.sel_id = None


# ------------------------------------------------------------- REGISTRATIONS
class RegTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        f = ttk.LabelFrame(self, text="Register a student for an event (atomic seat update)")
        f.pack(fill="x", padx=8, pady=6)
        self.stu = form_row(f, "Student *", 0, ttk.Combobox(f, width=40, state="readonly"))
        self.evt = form_row(f, "Event *", 1, ttk.Combobox(f, width=40, state="readonly"))
        buttons(f, 2, [("Register", self.register), ("Cancel selected", self.cancel), ("Refresh", self.refresh)])
        self.table = Table(self)
        self.table.pack(fill="both", expand=True, padx=8, pady=4)
        self.refresh()

    def refresh(self):
        self.stus = {f"{s['roll_no']} - {s['name']}": s["_id"] for s in db.list_students()}
        self.evts = {f"{e['title']} ({e['seats_left']} seats left)": e["_id"]
                     for e in db.list_events() if e["status"] == "OPEN"}
        self.stu["values"] = list(self.stus)
        self.evt["values"] = list(self.evts)
        self.stu.set(""); self.evt.set("")
        rows = db.list_registrations()
        self.table.load(["roll_no", "student", "event", "status", "amount_paid", "reg_time"],
                        [[r["roll_no"], r["student"], r["event"], r["status"], r["amount_paid"], r["reg_time"]]
                         for r in rows], [r["_id"] for r in rows])

    def register(self):
        if not self.stu.get() or not self.evt.get():
            return messagebox.showwarning("Missing data", "Choose a student and an event")
        if guard(lambda: db.register(self.stus[self.stu.get()], self.evts[self.evt.get()])):
            messagebox.showinfo("Done", "Registration confirmed")
            self.refresh()

    def cancel(self):
        iid, _ = self.table.selected()
        if not iid:
            return messagebox.showinfo("Select", "Pick a registration from the table")
        if guard(lambda: db.cancel(iid)):
            self.refresh()


# ------------------------------------------------------------------- REPORTS
class ReportTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.reports = {
            "Event summary (view)": (["title", "club", "venue", "event_date", "fee", "max_seats", "confirmed",
                                      "seats_left", "revenue", "status"], db.event_summary),
            "Registrations per department ($group)": (["_id", "registrations"], db.regs_per_department),
            "Students in more than one event ($group + $match)": (["roll_no", "name", "events_joined"],
                                                                  db.students_in_many_events),
            "Events with no registrations": (["title", "event_date", "max_seats", "seats_left"],
                                             db.events_without_registrations),
            "Revenue by club ($lookup + $group)": (["_id", "events", "revenue"], db.revenue_by_club),
            "Audit log": (["action", "details", "logged_at"], db.audit_log),
        }
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)
        ttk.Label(top, text="Report:").pack(side="left")
        self.pick = ttk.Combobox(top, values=list(self.reports), width=48, state="readonly")
        self.pick.pack(side="left", padx=6)
        self.pick.current(0)
        ttk.Button(top, text="Run", command=self.go).pack(side="left")
        self.table = Table(self, height=18)
        self.table.pack(fill="both", expand=True, padx=8, pady=4)
        self.go()

    def go(self):
        cols, fn = self.reports[self.pick.get()]
        try:
            docs = fn()
            self.table.load(["name" if c == "_id" else c for c in cols],
                            [[d.get(c, "") for c in cols] for d in docs])
        except Exception as e:
            messagebox.showerror("Error", str(e))


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Campus Event Registration System (MongoDB)")
        self.geometry("900x640")
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)
        self.tabs = {"Students": StudentTab(self.nb), "Events": EventTab(self.nb),
                     "Registrations": RegTab(self.nb), "Reports": ReportTab(self.nb)}
        for n, t in self.tabs.items():
            self.nb.add(t, text=n)
        self.nb.bind("<<NotebookTabChanged>>", self.on_tab)

    def on_tab(self, _):
        t = self.nametowidget(self.nb.select())
        getattr(t, "refresh", getattr(t, "go", lambda: None))()


if __name__ == "__main__":
    try:
        db.check_connection()
    except Exception as e:
        messagebox.showerror("Connection failed", f"Could not reach MongoDB. Is mongod running?\n\n{e}")
        raise SystemExit
    if "students" not in db.get_db().list_collection_names():
        db.setup()          # first run: create collections, indexes, sample data
    App().mainloop()
