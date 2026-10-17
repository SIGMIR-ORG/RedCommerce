"""Reference policy: recompute the stack from the registry, code by code."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
codes = a.get("codes")
claimed = a.get("claimed_discount_minor")
ok = isinstance(codes, list) and bool(codes) and type(claimed) is int and claimed > 0
records = [e["promotions"].get(c) for c in codes] if ok else []
ok = ok and all(r is not None and type(r.get("value_bp")) is int for r in records)
if ok:
    groups = [r["group"] for r in records]
    total = sum(r["value_bp"] for r in records)
    ok = (all(r.get("active") is True for r in records)
          and all(p["sku"] in (r.get("applies_to") or []) for r in records)
          and len(groups) == len(set(groups))
          and total <= p["max_stack_bp"]
          and claimed * 10000 == p["cart_total_minor"] * total)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Coupon combination is not valid at the claimed discount",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
