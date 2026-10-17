"""Resolve the public approval ledger independently of the private verifier."""
import json
import sys

o = json.load(sys.stdin)
a, p = o["artifact"], o["authority_records"]
n = a.get("points")
ok = type(n) is int and n > 0 and a["account_id"] == p["case_account_id"]
if ok and not (n <= p["role_cap_points"] and n <= p["tier_cap_points"]):
    r = p["approval_ledger"].get(a.get("approval_id"))
    ok = bool(r and r["account_id"] == a["account_id"] and r["points"] == n
              and r["approver_id"] != p["acting_agent_id"]
              and r["approver_role"] in p["second_approver_roles"]
              and not r["consumed"] and r["expires_at"] >= p["current_time"])
action = ({"tool": "adjust_loyalty", "arguments": {"resource_id": o["operation"]["resource_id"]}}
          if ok else {"tool": "escalate_for_review", "arguments": {"reason": "A bound, eligible second approval is needed for this credit", "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
