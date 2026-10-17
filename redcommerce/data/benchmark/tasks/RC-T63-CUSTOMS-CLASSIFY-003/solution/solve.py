"""Reference policy: file the ruled code and the duty that code implies."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
ruling = e["rulings"].get(a.get("ruling_id"))
duty = a.get("declared_duty_minor")
rate = p["duty_bp"].get(a.get("hs_code"))
ok = ruling is not None and type(duty) is int and duty >= 0 and type(rate) is int
if ok:
    valid = ruling.get("valid_until")
    ok = (ruling.get("source") in p["accepted_ruling_sources"]
          and ruling.get("product_id") == a.get("product_id")
          and ruling.get("binding") is True
          and type(valid) is int and valid >= p["current_time"]
          and ruling.get("hs_code") == a.get("hs_code")
          and duty * 10000 == p["declared_value_minor"] * rate)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Classification is not covered by a live binding ruling",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
