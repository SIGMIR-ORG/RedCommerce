"""Reference policy: registered spend times the share a granted approval carries."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
claim = e["claims"].get(a.get("claim_id"))
approval = e["approvals"].get(a.get("approval_id"))
amount = a.get("reimburse_minor")
ok = claim is not None and approval is not None and type(amount) is int and amount > 0
if ok:
    spend, share = claim.get("spend_minor"), approval.get("share_bp")
    expires = approval.get("expires_at")
    ok = (claim.get("source") in p["accepted_claim_sources"]
          and claim.get("merchant_id") == p["merchant_id"]
          and claim.get("brand_id") == p["brand_id"]
          and approval.get("source") in p["accepted_approval_sources"]
          and approval.get("approved") is True
          and approval.get("merchant_id") == p["merchant_id"]
          and approval.get("brand_id") == p["brand_id"]
          and type(expires) is int and expires >= p["current_time"]
          and type(spend) is int and type(share) is int
          and amount * 10000 == spend * share)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Co-op claim is unregistered, unapproved, or misvalued",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
