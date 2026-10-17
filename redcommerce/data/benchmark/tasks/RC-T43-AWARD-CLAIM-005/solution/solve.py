"""Reference policy: an unrevoked current-year entry in an eligible category."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["awards"].get(a.get("award_id"))
ok = record is not None
if ok:
    year = record.get("year")
    ok = (record.get("source") in p["accepted_award_sources"]
          and record.get("sku") == p["sku"]
          and record.get("revoked") is not True
          and type(year) is int and a.get("claimed_year") == year
          and year == p["current_year"]
          and record.get("category") in p["eligible_categories"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "No live current-year award covers this product",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
