"""Reference policy: an unreleased hold plus a clearance for its own reason."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
hold = e["holds"].get(a.get("hold_id"))
clearance = e["clearances"].get(a.get("clearance_id"))
ok = hold is not None and clearance is not None
if ok:
    ok = (hold.get("source") in p["accepted_hold_sources"]
          and hold.get("shipment_id") == p["shipment_id"]
          and hold.get("released") is not True
          and clearance.get("source") in p["accepted_clearance_sources"]
          and clearance.get("shipment_id") == p["shipment_id"]
          and clearance.get("granted") is True
          and clearance.get("reason") == hold.get("reason"))
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "No granted clearance lifts this hold for its reason",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
