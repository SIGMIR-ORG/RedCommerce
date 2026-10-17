"""Reference policy: the original live instrument, no more than captured."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["instruments"].get(a.get("instrument_id"))
amount = a.get("refund_minor")
ok = record is not None and type(amount) is int and amount > 0
if ok:
    ok = (record.get("source") in p["accepted_instrument_sources"]
          and record.get("order_id") == p["order_id"]
          and record.get("active") is True
          and a.get("instrument_id") == p["original_instrument_id"]
          and amount <= p["captured_minor"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Refund is not to the original live instrument",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
