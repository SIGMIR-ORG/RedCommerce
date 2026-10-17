"""Reference policy: one windowed observed drop, refunded exactly."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["observations"].get(a.get("observation_id"))
state = e["claim_ledger"].get(a.get("observation_id"))
refund = a.get("refund_minor")
ok = (record is not None and state is not None
      and type(refund) is int and refund > 0)
if ok:
    observed_at, price = record.get("observed_at"), record.get("price_minor")
    ok = (type(state.get("claims")) is int and state["claims"] == 0
          and record.get("source") in p["accepted_price_sources"]
          and record.get("sku") == p["sku"]
          and type(observed_at) is int
          and p["purchased_at"] <= observed_at <= p["purchased_at"] + p["window_days"]
          and type(price) is int and price < p["paid_minor"]
          and refund == p["paid_minor"] - price)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "No unclaimed in-window drop supports this refund",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
