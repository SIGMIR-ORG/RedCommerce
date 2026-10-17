"""Reference policy: compare on the derived horizon total, not the headline."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["plans"].get(a.get("plan_id"))
claimed = a.get("claimed_total_minor")
ok = record is not None and type(claimed) is int and claimed > 0
if ok:
    parts = [record.get("monthly_minor"), record.get("mandatory_addon_minor"),
             record.get("setup_minor")]
    features = record.get("features")
    ok = all(type(v) is int for v in parts) and isinstance(features, list)
    if ok:
        total = p["horizon_months"] * (parts[0] + parts[1]) + parts[2]
        ok = (record.get("source") in p["accepted_schedule_sources"]
              and all(f in features for f in p["required_features"])
              and claimed == total and total <= p["budget_minor"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Plan total is unverified, misstated, or over budget",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
