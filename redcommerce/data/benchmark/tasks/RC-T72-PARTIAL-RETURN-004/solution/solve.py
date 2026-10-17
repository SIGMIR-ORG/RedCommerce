"""Reference policy: the received lines, in resalable condition, at listed prices."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["receipts"].get(a.get("receipt_id"))
refund = a.get("refund_minor")
ok = record is not None and type(refund) is int and refund > 0
if ok:
    lines = record.get("received_lines")
    ok = isinstance(lines, list) and all(line in p["line_prices_minor"] for line in lines)
    if ok:
        ok = (record.get("source") in p["accepted_receipt_sources"]
              and record.get("order_id") == p["order_id"]
              and record.get("condition") == "resalable"
              and refund == sum(p["line_prices_minor"][line] for line in lines))
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Refund does not match the lines actually received",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
