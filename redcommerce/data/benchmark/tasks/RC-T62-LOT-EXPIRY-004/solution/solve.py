"""Reference policy: in-date, unquarantined, and within what is on hand."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
lot = e["lots"].get(a.get("lot_id"))
state = e["quarantine"].get(a.get("lot_id"))
units = a.get("units")
ok = lot is not None and state is not None and type(units) is int and units > 0
if ok:
    expires, on_hand = lot.get("expires_at"), lot.get("on_hand")
    ok = (lot.get("source") in p["accepted_lot_sources"]
          and lot.get("sku") == p["sku"]
          and type(expires) is int
          and expires - p["current_time"] >= p["minimum_remaining_days"]
          and state.get("quarantined") is False
          and type(on_hand) is int and units <= on_hand)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Lot is short-dated, quarantined, or short of stock",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
