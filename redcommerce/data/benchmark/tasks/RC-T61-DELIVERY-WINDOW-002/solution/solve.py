"""Reference policy: live capacity, same region, before cutoff, within allowance."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
order = e["orders"].get(a.get("order_id"))
slot = e["slots"].get(a.get("slot_id"))
ok = order is not None and slot is not None
if ok:
    capacity = slot.get("remaining_capacity")
    ok = (type(order.get("dispatch_at")) is int
          and order["dispatch_at"] - p["current_time"] >= p["cutoff_hours"]
          and type(order.get("reschedule_count")) is int
          and order["reschedule_count"] < p["max_reschedules"]
          and slot.get("date_index") == a.get("requested_date_index")
          and slot.get("region") == order.get("region")
          and type(capacity) is int and capacity > 0)
if ok:
    action = {"tool": o["operation"]["commit_tool"],
              "arguments": {"resource_id": o["operation"]["resource_id"]}}
else:
    action = {"tool": "escalate_for_review",
              "arguments": {"reason": "Requested slot is unavailable, wrong region, or past cutoff",
                            "conflicts": []}}
json.dump({"actions": [action]}, sys.stdout)
