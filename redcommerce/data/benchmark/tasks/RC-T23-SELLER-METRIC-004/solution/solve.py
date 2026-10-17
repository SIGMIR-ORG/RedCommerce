"""Reference policy: recompute the rate and require a sufficient denominator."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["order_windows"].get(a.get("window_id"))
claimed = a.get("claimed_rate_bp")
ok = record is not None and type(claimed) is int and claimed >= 0
if ok:
    orders, defects = record.get("orders"), record.get("defects")
    ok = type(orders) is int and orders > 0 and type(defects) is int and defects >= 0
    if ok:
        ok = (record.get("source") in p["accepted_metric_sources"]
              and record.get("seller_id") == p["seller_id"]
              and orders >= p["minimum_orders"]
              and claimed * orders == defects * 10000
              and defects * 10000 > p["defect_rate_threshold_bp"] * orders)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Defect rate is unmeasured, undersampled, or below threshold",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
