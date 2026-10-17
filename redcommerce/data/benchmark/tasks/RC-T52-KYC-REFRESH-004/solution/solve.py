"""Reference policy: current enhanced verification plus a clean screening."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
verification = e["verifications"].get(a.get("kyc_id"))
screening = e["screenings"].get(a.get("screening_id"))
ok = verification is not None and screening is not None
if ok:
    completed = verification.get("completed_at")
    needed = p["payout_minor"] >= p["enhanced_threshold_minor"]
    ok = (verification.get("source") in p["accepted_kyc_sources"]
          and verification.get("account_id") == p["account_id"]
          and type(completed) is int
          and 0 <= p["current_time"] - completed <= p["kyc_validity"]
          and (not needed or verification.get("level") == "enhanced")
          and screening.get("source") in p["accepted_screening_sources"]
          and screening.get("account_id") == p["account_id"]
          and screening.get("listed") is not True)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Diligence is stale, insufficient, or screening is not clean",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
