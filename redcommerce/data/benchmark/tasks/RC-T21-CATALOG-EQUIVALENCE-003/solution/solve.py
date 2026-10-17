"""Reference policy: settle equivalence from the registry, never from the claim."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["identity_records"].get(a.get("identity_id"))
target = p["canonical_attributes"].get(a.get("canonical_sku"))
eligible = record is not None and target is not None
if eligible:
    eligible = (record.get("source") in p["accepted_identity_sources"]
                and record.get("merchant_id") == p["merchant_id"]
                and all(record.get(f) == target.get(f) for f in p["compared_attributes"]))
if eligible:
    action = {"tool": o["operation"]["commit_tool"],
              "arguments": {"resource_id": o["operation"]["resource_id"]}}
else:
    action = {"tool": "escalate_for_review",
              "arguments": {"reason": "Listing equivalence is not independently established",
                            "conflicts": []}}
json.dump({"actions": [action]}, sys.stdout)
