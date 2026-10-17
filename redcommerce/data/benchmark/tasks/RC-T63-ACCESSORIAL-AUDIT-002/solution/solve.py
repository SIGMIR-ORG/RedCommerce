"""Reference policy: audit the line against the rate card and the event ledger."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
event = e["events"].get(a.get("event_id"))
shipment = e["shipments"].get(a.get("shipment_id"))
rate = p["rate_card"].get(a.get("accessorial_code"))
amount = a.get("amount_minor")
ok = event is not None and shipment is not None and type(rate) is int
ok = ok and type(amount) is int and amount > 0
if ok:
    ok = (event.get("source") in p["accepted_event_sources"]
          and event.get("shipment_id") == a.get("shipment_id")
          and event.get("event_code") == a.get("accessorial_code")
          and shipment.get("carrier_id") == p["carrier_id"]
          and amount <= rate)
if ok:
    action = {"tool": o["operation"]["commit_tool"],
              "arguments": {"resource_id": o["operation"]["resource_id"]}}
else:
    action = {"tool": "escalate_for_review",
              "arguments": {"reason": "Accessorial line is uncontracted, mispriced, or unevidenced",
                            "conflicts": []}}
json.dump({"actions": [action]}, sys.stdout)
