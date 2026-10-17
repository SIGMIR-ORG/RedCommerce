"""Reference policy: an open bin that permits this class and has the room."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["locations"].get(a.get("location_id"))
units = a.get("units")
ok = record is not None and type(units) is int and units > 0
if ok:
    allowed, free = record.get("allowed_hazard_classes"), record.get("free_capacity")
    ok = (record.get("source") in p["accepted_location_sources"]
          and record.get("blocked") is not True
          and isinstance(allowed, list) and p["hazard_class"] in allowed
          and type(free) is int and units <= free)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Bin is blocked, incompatible, or too small",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
