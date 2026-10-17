"""Reference policy: recompute the window minimum before showing a claim."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["price_history"].get(a.get("history_id"))
reference, offer = a.get("claimed_reference_minor"), a.get("offer_price_minor")
ok = (record is not None and type(reference) is int and reference > 0
      and type(offer) is int and offer > 0)
if ok:
    observations = record.get("observations")
    start = p["current_time"] - p["window_days"]
    ok = isinstance(observations, list) and bool(observations) and all(
        type(x.get("at")) is int and type(x.get("price_minor")) is int for x in observations)
    if ok:
        inside = [x["price_minor"] for x in observations if start <= x["at"] <= p["current_time"]]
        ok = (record.get("source") in p["accepted_history_sources"]
              and record.get("sku") == p["sku"]
              and any(x["at"] <= start for x in observations)
              and bool(inside) and reference == min(inside) and offer < min(inside))
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Price claim is not supported by a covered price history",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
