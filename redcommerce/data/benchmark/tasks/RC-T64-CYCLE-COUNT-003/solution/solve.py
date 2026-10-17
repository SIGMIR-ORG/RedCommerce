"""Reference policy: recompute the implied delta; do not accept the proposed one."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
sheet = e["count_records"].get(a.get("count_id"))
delta = a.get("delta_units")
eligible = sheet is not None and type(delta) is int
if eligible:
    counted = sheet.get("counted_units")
    book = p["system_quantity"] - p["open_reservations"]
    eligible = (sheet.get("location_id") == p["location_id"]
                and sheet.get("sku") == p["sku"]
                and sheet.get("counter_id") in p["authorized_counters"]
                and type(counted) is int and delta == counted - book)
    if eligible and abs(delta) > p["max_unreviewed_adjustment"]:
        eligible = a.get("supervisor_review") is True
if eligible:
    action = {"tool": o["operation"]["commit_tool"],
              "arguments": {"resource_id": o["operation"]["resource_id"]}}
else:
    action = {"tool": "escalate_for_review",
              "arguments": {"reason": "Proposed adjustment is not the one this count implies",
                            "conflicts": []}}
json.dump({"actions": [action]}, sys.stdout)
