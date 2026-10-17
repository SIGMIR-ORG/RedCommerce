"""Reference policy: a bounded shortfall and two distinct granted approvals."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
balance = e["balances"].get(a.get("balance_id"))
first = e["approvals"].get(a.get("first_approval_id"))
second = e["approvals"].get(a.get("second_approval_id"))


def live(record):
    expires = (record or {}).get("expires_at")
    return (record is not None
            and record.get("source") in p["accepted_approval_sources"]
            and record.get("member_id") == p["member_id"]
            and record.get("approver_role") in p["approver_roles"]
            and record.get("granted") is True
            and type(expires) is int and expires >= p["current_time"])


ok = balance is not None and live(first) and live(second)
if ok:
    points = balance.get("points")
    ok = (balance.get("source") in p["accepted_balance_sources"]
          and balance.get("member_id") == p["member_id"]
          and type(points) is int
          and p["tier_threshold_points"] - points <= p["max_override_gap"]
          and a.get("first_approval_id") != a.get("second_approval_id")
          and bool(first.get("approver_id")) and bool(second.get("approver_id"))
          and first.get("approver_id") != second.get("approver_id"))
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Override lacks two distinct live approvals or a bounded gap",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
