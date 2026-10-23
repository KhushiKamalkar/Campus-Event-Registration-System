// MongoDB shell (mongosh) demo queries for CERS. Run: mongosh < queries.js
use("cers_mongo");

// 1. CRUD
db.students.insertOne({roll_no:"TEITA-50", name:"Demo Student", email:"demo@example.com", phone:"9000000050", dept:"Mechanical", year:NumberInt(2)});
db.students.find({dept:"Information Technology"});
db.students.updateOne({roll_no:"TEITA-50"}, {$set:{year:NumberInt(3)}});
db.students.deleteOne({roll_no:"TEITA-50"});

// 2. Schema validation rejects bad data (year 9 is not allowed)
db.students.insertOne({roll_no:"X1", name:"Bad Year", email:"b@e.com", phone:"9000000000", dept:"Mechanical", year:NumberInt(9)});

// 3. Index usage
db.events.find({event_date: ISODate("2026-11-15")}).explain("executionStats").queryPlanner.winningPlan;
db.events.find({$text:{$search:"hack"}});          // text index on title

// 4. Atomic seat booking: succeeds only if a seat is left
db.events.findOneAndUpdate({title:"Hack Night 2026", status:"OPEN", seats_left:{$gt:0}}, {$inc:{seats_left:-1}});

// 5. Aggregation: registrations per department
db.registrations.aggregate([
  {$match:{status:"CONFIRMED"}},
  {$lookup:{from:"students", localField:"student_id", foreignField:"_id", as:"s"}},
  {$unwind:"$s"},
  {$group:{_id:"$s.dept", registrations:{$sum:1}}},
  {$sort:{registrations:-1}}
]);

// 6. The view
db.vw_event_summary.find();

// 7. Multi document transaction (needs a replica set)
const session = db.getMongo().startSession();
session.startTransaction();
try {
  const ev = session.getDatabase("cers_mongo").events;
  ev.updateOne({title:"Open Mic Evening"}, {$inc:{seats_left:-1}});
  session.commitTransaction();
} catch (e) { session.abortTransaction(); }
