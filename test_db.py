"""Integrity tests for CERS (MongoDB). Run: python test_db.py"""
import cers_db as db
from cers_db import AppError

db.setup()

def expect_fail(name, fn, *a):
    try:
        fn(*a); print("FAIL ", name)
    except AppError as e:
        print("PASS ", name, "->", e)

S = {s["roll_no"]: s["_id"] for s in db.list_students()}
E = {e["title"]: e["_id"] for e in db.list_events()}

expect_fail("duplicate roll no (unique index)", db.add_student, "TEITA-01", "Some One", "x@e.com", "9999999999", "Mechanical", 2)
expect_fail("duplicate email (unique index)", db.add_student, "TEITA-77", "Some One", "aarav@example.com", "9999999999", "Mechanical", 2)
expect_fail("seats > venue capacity (rule)", db.add_event, "Big", "Coding Club", "Lab 204", "2026-12-01", 0, 500)
expect_fail("venue double booked (unique index)", db.add_event, "Clash", "Coding Club", "Lab 204", "2026-11-10", 0, 10)
expect_fail("bad date format", db.add_event, "Bad", "Coding Club", "Lab 204", "10-11-2026", 0, 10)
expect_fail("duplicate registration", db.register, S["TEITA-01"], E["Hack Night 2026"])

db.register(S["TEITA-03"], E["Hack Night 2026"])
print("seats left Hack Night after 3 registrations =", db.seats_left(E["Hack Night 2026"]))
expect_fail("overbooking blocked (atomic update)", db.register, S["TEITA-04"], E["Hack Night 2026"])

db.cancel([r for r in db.list_registrations() if r["roll_no"] == "TEITA-01" and r["event"] == "Hack Night 2026"][0]["_id"])
print("after cancel seats left =", db.seats_left(E["Hack Night 2026"]))
rid = [r for r in db.list_registrations() if r["status"] == "CANCELLED"][0]["_id"]
expect_fail("double cancel blocked", db.cancel, rid)
db.register(S["TEITA-04"], E["Hack Night 2026"])
print("freed seat taken by another student, seats left =", db.seats_left(E["Hack Night 2026"]))

print("audit counts:", {a: sum(1 for x in db.audit_log() if x["action"] == a) for a in ("REGISTER", "CANCEL")})

# CRUD
sid = db.add_student("TEITA-29", "Test User", "t@e.com", "9000000000", "Information Technology", 3)
db.update_student(sid, "TEITA-29", "Test User", "t@e.com", "9000000000", "Information Technology", 4)
print("CRUD update -> year =", db._get_year(sid) if hasattr(db, "_get_year") else db.get_db().students.find_one({"_id": sid})["year"])
db.delete_student(sid)
print("CRUD delete -> found =", db.get_db().students.find_one({"_id": sid}) is not None)

print("event summary:", [(r["title"], r["confirmed"], r["seats_left"], r["revenue"]) for r in db.event_summary()])
print("per department:", [(r["_id"], r["registrations"]) for r in db.regs_per_department()])
print("revenue by club:", [(r["_id"], r["revenue"]) for r in db.revenue_by_club()])
print("in many events:", [(r["roll_no"], r["events_joined"]) for r in db.students_in_many_events()])
print("no registrations:", [e["title"] for e in db.events_without_registrations()])
