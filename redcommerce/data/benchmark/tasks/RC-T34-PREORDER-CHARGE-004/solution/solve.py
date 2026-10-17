"""Reference policy: charge once, after a confirmed shipment, within tolerance."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
event = e["ship_events"].get(a.get("event_id"))
ledger = e["charge_ledger"].get(a.get("event_id"))
charge = a.get("charge_minor")
ok = (event is not None and ledger is not None
      and type(charge) is int and charge > 0)
if ok:
    ok = (event.get("source") in p["accepted_event_sources"]
          and event.get("order_id") == p["order_id"]
          and event.get("shipped") is True
          and type(ledger.get("charges_posted")) is int
          and ledger["charges_posted"] == 0
          and charge * 10000 <= p["authorized_price_minor"] * (10000 + p["tolerance_bp"]))
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Pre-order is unshipped, already charged, or over tolerance",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
