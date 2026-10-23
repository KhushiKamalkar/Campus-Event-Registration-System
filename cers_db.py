"""Campus Event Registration System (CERS) - MongoDB data layer.
Collections: departments, clubs, venues, students, events, registrations, audit_log
View: vw_event_summary
"""
import os
from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, PyMongoError

URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")
DBNAME = "cers_mongo"
MOCK = os.environ.get("CERS_MOCK") == "1"      # only used for testing without a server

_client = None


class AppError(Exception):
    """Readable error shown to the user."""


def client():
    global _client
    if _client is None:
        if MOCK:
            import mongomock
            _client = mongomock.MongoClient()
        else:
            _client = MongoClient(URI, serverSelectionTimeoutMS=3000)
    return _client


def get_db():
    return client()[DBNAME]


def check_connection():
    client().admin.command("ping") if not MOCK else None


# ------------------------------------------------------------------ SCHEMAS
EMAIL_PATTERN = r"^[\w.+-]+@[\w-]+\.[\w.]+$"

VALIDATORS = {
    "students": {"$jsonSchema": {
        "bsonType": "object",
        "required": ["roll_no", "name", "email", "phone", "dept", "year"],
        "properties": {
            "roll_no": {"bsonType": "string", "minLength": 1},
            "name": {"bsonType": "string", "minLength": 2},
            "email": {"bsonType": "string", "pattern": EMAIL_PATTERN},
            "phone": {"bsonType": "string", "pattern": "^[0-9]{10}$"},
            "dept": {"bsonType": "string"},
            "year": {"bsonType": "int", "minimum": 1, "maximum": 4}}}},
    "events": {"$jsonSchema": {
        "bsonType": "object",
        "required": ["title", "club", "venue", "event_date", "fee", "max_seats", "seats_left", "status"],
        "properties": {
            "title": {"bsonType": "string", "minLength": 2},
            "club": {"bsonType": "object", "required": ["name"]},
            "venue": {"bsonType": "object", "required": ["name", "capacity"]},
            "event_date": {"bsonType": "date"},
            "fee": {"bsonType": ["double", "int"], "minimum": 0},
            "max_seats": {"bsonType": "int", "minimum": 1},
            "seats_left": {"bsonType": "int", "minimum": 0},
            "status": {"enum": ["OPEN", "CLOSED", "CANCELLED"]}}}},
    "registrations": {"$jsonSchema": {
        "bsonType": "object",
        "required": ["student_id", "event_id", "status", "amount_paid", "reg_time"],
        "properties": {
            "student_id": {"bsonType": "objectId"},
            "event_id": {"bsonType": "objectId"},
            "status": {"enum": ["CONFIRMED", "CANCELLED"]},
            "amount_paid": {"bsonType": ["double", "int"], "minimum": 0},
            "reg_time": {"bsonType": "date"}}}},
}

# pipeline reused by the view and by the revenue report
SUMMARY_PIPELINE = [
    {"$lookup": {"from": "registrations", "localField": "_id",
                 "foreignField": "event_id", "as": "regs"}},
    {"$project": {
        "title": 1, "club": "$club.name", "venue": "$venue.name", "event_date": 1,
        "fee": 1, "max_seats": 1, "seats_left": 1, "status": 1,
        "confirmed": {"$subtract": ["$max_seats", "$seats_left"]},
        "revenue": {"$sum": "$regs.amount_paid"}}},
]


# -------------------------------------------------------------------- SETUP
def setup(reset=True, sample=True):
    """Create collections with validation, indexes, the view and sample data."""
    c = client()
    if reset:
        c.drop_database(DBNAME)
    db = c[DBNAME]
    for name in ["departments", "clubs", "venues", "students", "events", "registrations", "audit_log"]:
        if name in VALIDATORS and not MOCK:
            db.create_collection(name, validator=VALIDATORS[name], validationAction="error")
        else:
            db.create_collection(name)
    if not MOCK:
        db.create_collection("vw_event_summary", viewOn="events", pipeline=SUMMARY_PIPELINE)
    # indexes
    db.departments.create_index("name", unique=True)
    db.clubs.create_index("name", unique=True)
    db.venues.create_index("name", unique=True)
    db.students.create_index("roll_no", unique=True)
    db.students.create_index("email", unique=True)
    db.events.create_index([("venue.name", ASCENDING), ("event_date", ASCENDING)], unique=True)
    db.events.create_index("event_date")
    db.events.create_index([("title", "text")])
    db.registrations.create_index([("student_id", ASCENDING), ("event_id", ASCENDING)], unique=True)
    db.registrations.create_index([("event_id", ASCENDING), ("status", ASCENDING)])
    if sample:
        _seed(db)
    return db


def _seed(db):
    db.departments.insert_many([{"name": n} for n in
                                ["Information Technology", "Computer Engineering", "Mechanical", "E&TC"]])
    db.clubs.insert_many([{"name": "Coding Club", "faculty": "Prof. Deshmukh"},
                          {"name": "Music Society", "faculty": "Prof. Kulkarni"},
                          {"name": "Robotics Club", "faculty": "Prof. Patil"}])
    db.venues.insert_many([{"name": "Main Auditorium", "capacity": 300},
                           {"name": "Seminar Hall A", "capacity": 80},
                           {"name": "Lab 204", "capacity": 30}])
    for roll, name, mail, ph, dept, yr in [
            ("TEITA-01", "Aarav Joshi", "aarav@example.com", "9876500001", "Information Technology", 3),
            ("TEITA-02", "Sneha Pawar", "sneha@example.com", "9876500002", "Information Technology", 3),
            ("TEITA-03", "Rohan More", "rohan@example.com", "9876500003", "Computer Engineering", 2),
            ("TEITA-04", "Isha Shinde", "isha@example.com", "9876500004", "Mechanical", 4)]:
        add_student(roll, name, mail, ph, dept, yr)
    add_event("Hack Night 2026", "Coding Club", "Lab 204", "2026-11-10", 100, 3)
    add_event("Open Mic Evening", "Music Society", "Main Auditorium", "2026-11-15", 0, 200)
    add_event("Line Follower Contest", "Robotics Club", "Seminar Hall A", "2026-11-20", 150, 50)
    ids = {s["roll_no"]: s["_id"] for s in get_db().students.find()}
    evs = {e["title"]: e["_id"] for e in get_db().events.find()}
    register(ids["TEITA-01"], evs["Hack Night 2026"])
    register(ids["TEITA-02"], evs["Hack Night 2026"])
    register(ids["TEITA-01"], evs["Open Mic Evening"])


# ------------------------------------------------------------------- HELPERS
def _label(sid, eid):
    s = get_db().students.find_one({"_id": sid}) or {}
    e = get_db().events.find_one({"_id": eid}) or {}
    return f"{s.get('roll_no', '?')} -> {e.get('title', '?')}"


def audit(action, details):
    get_db().audit_log.insert_one({"action": action, "details": details, "logged_at": datetime.now()})


def _wrap(dup_msg="Duplicate value"):
    """Turn database errors into readable AppError messages."""
    def deco(fn):
        def inner(*a, **k):
            try:
                return fn(*a, **k)
            except DuplicateKeyError:
                raise AppError(dup_msg)
            except AppError:
                raise
            except PyMongoError as e:
                msg = (e.details or {}).get("errmsg") if getattr(e, "details", None) else None
                raise AppError(msg or str(e))
        return inner
    return deco


def parse_date(s):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        raise AppError("Date must be in YYYY-MM-DD format")


# ------------------------------------------------------------------ STUDENTS
@_wrap("Roll number or email already exists")
def add_student(roll, name, email, phone, dept, year):
    r = get_db().students.insert_one({"roll_no": roll, "name": name, "email": email,
                                      "phone": phone, "dept": dept, "year": int(year)})
    return r.inserted_id


@_wrap("Roll number or email already exists")
def update_student(sid, roll, name, email, phone, dept, year):
    get_db().students.update_one({"_id": ObjectId(sid)}, {"$set": {
        "roll_no": roll, "name": name, "email": email, "phone": phone, "dept": dept, "year": int(year)}})


@_wrap()
def delete_student(sid):
    """Remove the student, give back seats of confirmed registrations, delete registrations."""
    sid = ObjectId(sid)
    db = get_db()
    for r in db.registrations.find({"student_id": sid, "status": "CONFIRMED"}):
        db.events.update_one({"_id": r["event_id"]}, {"$inc": {"seats_left": 1}})
    db.registrations.delete_many({"student_id": sid})
    db.students.delete_one({"_id": sid})


def list_students():
    return list(get_db().students.find().sort("roll_no", 1))


# -------------------------------------------------------------------- EVENTS
def _club_venue(club_name, venue_name, seats):
    db = get_db()
    club = db.clubs.find_one({"name": club_name})
    venue = db.venues.find_one({"name": venue_name})
    if not club or not venue:
        raise AppError("Choose a valid club and venue")
    # application level rule (MongoDB has no triggers on a local server)
    if seats > venue["capacity"]:
        raise AppError(f"Seats exceed venue capacity ({venue['capacity']})")
    return ({"name": club["name"], "faculty": club["faculty"]},
            {"name": venue["name"], "capacity": venue["capacity"]})


@_wrap("This venue is already booked on that date")
def add_event(title, club_name, venue_name, date_str, fee, seats, status="OPEN"):
    club, venue = _club_venue(club_name, venue_name, int(seats))
    r = get_db().events.insert_one({
        "title": title, "club": club, "venue": venue, "event_date": parse_date(date_str),
        "fee": float(fee), "max_seats": int(seats), "seats_left": int(seats), "status": status})
    return r.inserted_id


@_wrap("This venue is already booked on that date")
def update_event(eid, title, club_name, venue_name, date_str, fee, seats, status):
    eid = ObjectId(eid)
    db = get_db()
    club, venue = _club_venue(club_name, venue_name, int(seats))
    taken = db.registrations.count_documents({"event_id": eid, "status": "CONFIRMED"})
    if int(seats) < taken:
        raise AppError(f"{taken} students already registered, seats cannot go below that")
    db.events.update_one({"_id": eid}, {"$set": {
        "title": title, "club": club, "venue": venue, "event_date": parse_date(date_str),
        "fee": float(fee), "max_seats": int(seats), "seats_left": int(seats) - taken, "status": status}})


@_wrap()
def delete_event(eid):
    eid = ObjectId(eid)
    get_db().registrations.delete_many({"event_id": eid})
    get_db().events.delete_one({"_id": eid})


def list_events():
    return list(get_db().events.find().sort("event_date", 1))


# ------------------------------------------------------------- REGISTRATIONS
def _txn_supported():
    if MOCK:
        return False
    try:
        return client().topology_description.topology_type_name in ("ReplicaSetWithPrimary", "Sharded")
    except Exception:
        return False


def _register_ops(sid, eid, session=None):
    db = get_db()
    existing = db.registrations.find_one({"student_id": sid, "event_id": eid}, session=session)
    if existing and existing["status"] == "CONFIRMED":
        raise AppError("Student is already registered for this event")
    # atomic check and decrement: only succeeds if event is OPEN and a seat is left
    ev = db.events.find_one_and_update(
        {"_id": eid, "status": "OPEN", "seats_left": {"$gt": 0}},
        {"$inc": {"seats_left": -1}}, session=session)
    if ev is None:
        cur = db.events.find_one({"_id": eid}, session=session)
        if not cur:
            raise AppError("Event not found")
        if cur["status"] != "OPEN":
            raise AppError("Event is not open for registration")
        raise AppError("No seats left for this event")
    doc = {"status": "CONFIRMED", "amount_paid": float(ev["fee"]), "reg_time": datetime.now()}
    if existing:   # re-registering after a cancel
        db.registrations.update_one({"_id": existing["_id"]}, {"$set": doc}, session=session)
    else:
        db.registrations.insert_one({"student_id": sid, "event_id": eid, **doc}, session=session)


@_wrap("Student is already registered for this event")
def register(student_id, event_id):
    sid, eid = ObjectId(student_id), ObjectId(event_id)
    if _txn_supported():
        with client().start_session() as s:
            s.with_transaction(lambda sess: _register_ops(sid, eid, sess))
    else:
        _register_ops(sid, eid)
    audit("REGISTER", _label(sid, eid))


@_wrap()
def cancel(reg_id):
    db = get_db()
    r = db.registrations.find_one_and_update(
        {"_id": ObjectId(reg_id), "status": "CONFIRMED"},
        {"$set": {"status": "CANCELLED", "amount_paid": 0.0}})
    if r is None:
        raise AppError("Registration not found or already cancelled")
    db.events.update_one({"_id": r["event_id"]}, {"$inc": {"seats_left": 1}})
    audit("CANCEL", _label(r["student_id"], r["event_id"]))


def list_registrations():
    pipe = [
        {"$lookup": {"from": "students", "localField": "student_id", "foreignField": "_id", "as": "s"}},
        {"$lookup": {"from": "events", "localField": "event_id", "foreignField": "_id", "as": "e"}},
        {"$unwind": "$s"}, {"$unwind": "$e"},
        {"$project": {"roll_no": "$s.roll_no", "student": "$s.name", "event": "$e.title",
                      "status": 1, "amount_paid": 1, "reg_time": 1}},
        {"$sort": {"reg_time": -1}}]
    return list(get_db().registrations.aggregate(pipe))


def seats_left(eid):
    return get_db().events.find_one({"_id": ObjectId(eid)})["seats_left"]


# ------------------------------------------------------------------- REPORTS
def event_summary():
    db = get_db()
    if MOCK:
        return list(db.events.aggregate(SUMMARY_PIPELINE))
    return list(db.vw_event_summary.find())      # reads the view


def regs_per_department():
    return list(get_db().registrations.aggregate([
        {"$match": {"status": "CONFIRMED"}},
        {"$lookup": {"from": "students", "localField": "student_id", "foreignField": "_id", "as": "s"}},
        {"$unwind": "$s"},
        {"$group": {"_id": "$s.dept", "registrations": {"$sum": 1}}},
        {"$sort": {"registrations": -1}}]))


def students_in_many_events():
    return list(get_db().registrations.aggregate([
        {"$match": {"status": "CONFIRMED"}},
        {"$group": {"_id": "$student_id", "events_joined": {"$sum": 1}}},
        {"$match": {"events_joined": {"$gt": 1}}},
        {"$lookup": {"from": "students", "localField": "_id", "foreignField": "_id", "as": "s"}},
        {"$unwind": "$s"},
        {"$project": {"_id": 0, "roll_no": "$s.roll_no", "name": "$s.name", "events_joined": 1}}]))


def events_without_registrations():
    return [e for e in get_db().events.find() if e["seats_left"] == e["max_seats"]]


def revenue_by_club():
    return list(get_db().events.aggregate(SUMMARY_PIPELINE + [
        {"$group": {"_id": "$club", "events": {"$sum": 1}, "revenue": {"$sum": "$revenue"}}},
        {"$sort": {"revenue": -1}}]))


def audit_log():
    return list(get_db().audit_log.find().sort("logged_at", -1))
