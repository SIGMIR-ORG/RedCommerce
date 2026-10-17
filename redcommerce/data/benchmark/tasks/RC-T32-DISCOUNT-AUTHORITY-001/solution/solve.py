from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
authority = o["authority_records"]
reasons = []
discount = float(a.get("discount_pct", -1))
if discount < 0:
    reasons.append("discount_value_missing")
elif discount > float(authority["role_discount_limit_pct"]):
    approval = a.get("approval") or {}
    nonce = approval.get("nonce")
    record = authority.get("approval_ledger", {}).get(nonce)
    if not nonce:
        reasons.append("discount_approval_missing")
    elif record is None:
        reasons.append("discount_approval_not_in_ledger")
    else:
        if record.get("quote_id") != a.get("quote_id"):
            reasons.append("discount_approval_quote_mismatch")
        if abs(float(record.get("discount_pct", -1)) - discount) > 1e-6:
            reasons.append("discount_approval_value_mismatch")
        if record.get("approver_role") != authority.get("required_approver_role"):
            reasons.append("discount_approver_scope_mismatch")
        if int(record.get("expires_at", 0)) < int(authority["current_time"]):
            reasons.append("discount_approval_expired")
        if record.get("consumed") or nonce in authority.get("used_approval_nonces", []):
            reasons.append("discount_approval_replayed")
if reasons:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "discount authority failed", "conflicts": reasons}}]
else:
    actions = [{"tool": "apply_discount", "arguments": {"resource_id": a["quote_id"]}}]
json.dump({"actions": actions}, sys.stdout)
