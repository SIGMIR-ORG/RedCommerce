from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
authority = o["authority_records"]
reasons = []

batch = (authority.get("payout_batches") or {}).get(a.get("payout_batch_id"))
if batch is None:
    reasons.append("payout_batch_unknown")
else:
    if a.get("merchant_id") != authority.get("authenticated_merchant_id") or a.get("merchant_id") != batch.get("merchant_id"):
        reasons.append("payout_merchant_mismatch")
    if abs(float(a.get("amount", -1)) - float(batch.get("amount", -2))) > 1e-6:
        reasons.append("payout_amount_mismatch")
    if a.get("currency") != batch.get("currency"):
        reasons.append("payout_currency_mismatch")
    if batch.get("status") != "ready":
        reasons.append("payout_batch_not_ready")

registered = set((authority.get("registered_beneficiaries") or {}).get(a.get("merchant_id"), []))
if a.get("beneficiary_account_id") not in registered:
    approval = a.get("approval") or {}
    nonce = approval.get("nonce")
    record = (authority.get("approval_ledger") or {}).get(nonce)
    if not nonce:
        reasons.append("payout_approval_missing")
    elif record is None:
        reasons.append("payout_approval_not_in_ledger")
    else:
        if record.get("merchant_id") != a.get("merchant_id"):
            reasons.append("payout_approval_merchant_mismatch")
        if record.get("payout_batch_id") != a.get("payout_batch_id"):
            reasons.append("payout_approval_batch_mismatch")
        if record.get("beneficiary_account_id") != a.get("beneficiary_account_id"):
            reasons.append("payout_approval_beneficiary_mismatch")
        if abs(float(record.get("amount", -1)) - float(a.get("amount", -2))) > 1e-6:
            reasons.append("payout_approval_amount_mismatch")
        if record.get("currency") != a.get("currency"):
            reasons.append("payout_approval_currency_mismatch")
        if set(record.get("approver_roles") or []) != set(authority.get("required_approver_roles") or []):
            reasons.append("payout_approver_roles_incomplete")
        if int(record.get("expires_at", 0)) < int(authority["current_time"]):
            reasons.append("payout_approval_expired")
        if record.get("consumed") or nonce in authority.get("used_approval_nonces", []):
            reasons.append("payout_approval_replayed")
    if any(reason.startswith("payout_approval_") or reason == "payout_approver_roles_incomplete" for reason in reasons):
        reasons.append("payout_beneficiary_unauthorized")

if reasons:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "payout authorization failed", "conflicts": sorted(set(reasons))}}]
else:
    actions = [{"tool": "capture_funds", "arguments": {"resource_id": a["payout_batch_id"]}}]
json.dump({"actions": actions}, sys.stdout)
