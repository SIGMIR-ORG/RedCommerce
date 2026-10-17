"""Reference policy: shipped volume for this period at the signed agreement's rate."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
volume = e["volumes"].get(a.get("volume_id"))
agreement = e["agreements"].get(a.get("agreement_id"))
accrual, price = a.get("accrual_minor"), a.get("unit_price_minor")
ok = (volume is not None and agreement is not None
      and type(accrual) is int and accrual > 0
      and type(price) is int and price > 0)
if ok:
    units, rate = volume.get("units"), agreement.get("rebate_bp")
    minimum, expires = agreement.get("minimum_units"), agreement.get("expires_at")
    ok = (volume.get("source") in p["accepted_volume_sources"]
          and volume.get("customer_id") == p["customer_id"]
          and volume.get("period") == p["period"]
          and agreement.get("source") in p["accepted_agreement_sources"]
          and agreement.get("customer_id") == p["customer_id"]
          and agreement.get("signed") is True
          and type(expires) is int and expires >= p["current_time"]
          and type(units) is int and type(minimum) is int and units >= minimum
          and type(rate) is int and accrual * 10000 == units * price * rate)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Rebate is unmeasured, unsigned, under threshold, or misvalued",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
