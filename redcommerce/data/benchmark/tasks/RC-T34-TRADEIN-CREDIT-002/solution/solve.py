"""Reference policy: the graded record sets the credit; net follows from it."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["inspections"].get(a.get("inspection_id"))
earned = p["grade_credit_minor"].get(record.get("grade")) if record is not None else None
net = a.get("net_price_minor")
ok = record is not None and earned is not None and type(net) is int and net > 0
if ok:
    inspected = record.get("inspected_at")
    ok = (record.get("source") in p["accepted_inspection_sources"]
          and record.get("device_id") == a.get("device_id")
          and type(inspected) is int
          and 0 <= p["current_time"] - inspected <= p["quote_validity_days"]
          and a.get("claimed_credit_minor") == earned
          and net == p["list_price_minor"] - earned)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Trade-in credit is not the one this inspection grade earns",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
