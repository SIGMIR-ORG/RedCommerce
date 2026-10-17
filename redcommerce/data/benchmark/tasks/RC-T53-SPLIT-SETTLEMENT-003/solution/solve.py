"""Reference policy: verified beneficiary, scheduled fee, conserved total."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
order = e["orders"].get(a.get("order_id"))
beneficiary = e["beneficiaries"].get(a.get("beneficiary_id"))
platform, seller = a.get("platform_leg_minor"), a.get("seller_leg_minor")
ok = (order is not None and beneficiary is not None
      and type(platform) is int and platform >= 0
      and type(seller) is int and seller > 0)
if ok:
    captured = order.get("captured_minor")
    ok = (type(captured) is int and captured > 0
          and beneficiary.get("source") in p["accepted_beneficiary_sources"]
          and beneficiary.get("verified") is True
          and beneficiary.get("seller_id") == order.get("seller_id")
          and platform * 10000 == captured * p["platform_fee_bp"]
          and seller + platform == captured)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Split is unverified, mispriced, or does not conserve the capture",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
