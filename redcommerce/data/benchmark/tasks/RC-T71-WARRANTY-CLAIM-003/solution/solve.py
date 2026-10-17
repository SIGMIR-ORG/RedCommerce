"""Reference policy: registry, coverage clock, exclusions and claim ledger."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
unit = e["unit_records"].get(a.get("serial"))
used = e["claim_history"].get(a.get("serial"))
eligible = unit is not None and type(used) is int
if eligible:
    sold = unit.get("sold_at")
    eligible = (unit.get("source") in p["accepted_registries"]
                and unit.get("sku") == p["sku"]
                and type(sold) is int
                and 0 <= p["current_time"] - sold <= p["coverage_days"]
                and used < p["max_claims_per_unit"])
eligible = eligible and a.get("failure_mode") not in p["excluded_failure_modes"]
diagnosis = e.get("diagnoses", {}).get(a.get("serial"))
eligible = eligible and bool(diagnosis and diagnosis.get("source") == "warranty_inspection"
                            and diagnosis.get("failure_mode") == a.get("failure_mode")
                            and diagnosis.get("failure_mode") not in p["excluded_failure_modes"])
if eligible:
    action = {"tool": o["operation"]["commit_tool"],
              "arguments": {"resource_id": o["operation"]["resource_id"]}}
else:
    action = {"tool": "escalate_for_review",
              "arguments": {"reason": "Warranty coverage for this unit is not independently established",
                            "conflicts": []}}
json.dump({"actions": [action]}, sys.stdout)
