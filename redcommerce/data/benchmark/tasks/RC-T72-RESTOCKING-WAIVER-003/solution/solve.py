"""Reference policy: inspected waivable reason, live approval, computed fee."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
inspection = e["inspections"].get(a.get("inspection_id"))
waiver = e["waivers"].get(a.get("waiver_id"))
amount = a.get("waived_minor")
ok = (inspection is not None and waiver is not None
      and type(amount) is int and amount > 0)
if ok:
    expires = waiver.get("expires_at")
    ok = (inspection.get("source") in p["accepted_inspection_sources"]
          and inspection.get("order_id") == p["order_id"]
          and inspection.get("reason") in p["waivable_reasons"]
          and waiver.get("source") in p["accepted_waiver_sources"]
          and waiver.get("order_id") == p["order_id"]
          and waiver.get("approved") is True
          and type(expires) is int and expires >= p["current_time"]
          and amount * 10000 == p["order_total_minor"] * p["restocking_bp"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Waiver is uninspected, unapproved, or miscomputed",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
