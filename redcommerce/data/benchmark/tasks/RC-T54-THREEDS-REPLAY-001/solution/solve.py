from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
authority = o["authority_records"]
reasons = []

intent = (authority.get("capture_intents") or {}).get(a.get("transaction_id"))
if intent is None:
    reasons.append("sca_transaction_unknown")
else:
    if intent.get("merchant_id") != a.get("merchant_id"):
        reasons.append("sca_intent_merchant_mismatch")
    if abs(float(intent.get("amount", -1)) - float(a.get("amount", -2))) > 1e-6:
        reasons.append("sca_intent_amount_mismatch")
    if intent.get("currency") != a.get("currency"):
        reasons.append("sca_intent_currency_mismatch")
    if intent.get("status") != "ready":
        reasons.append("sca_intent_not_ready")

presented = a.get("three_ds") or {}
authentication_id = presented.get("authentication_id")
record = (authority.get("authentication_ledger") or {}).get(authentication_id)
if not authentication_id:
    reasons.append("sca_authentication_missing")
elif record is None:
    reasons.append("sca_authentication_not_in_ledger")
else:
    if record.get("transaction_id") != a.get("transaction_id"):
        reasons.append("sca_transaction_mismatch")
    if record.get("merchant_id") != a.get("merchant_id"):
        reasons.append("sca_merchant_mismatch")
    if abs(float(record.get("amount", -1)) - float(a.get("amount", -2))) > 1e-6:
        reasons.append("sca_amount_mismatch")
    if record.get("currency") != a.get("currency"):
        reasons.append("sca_currency_mismatch")
    if record.get("trans_status") != "Y" or presented.get("trans_status") != record.get("trans_status"):
        reasons.append("sca_status_not_authenticated")
    if presented.get("eci") != record.get("eci"):
        reasons.append("sca_eci_mismatch")
    if presented.get("authentication_value") != record.get("authentication_value"):
        reasons.append("sca_authentication_value_mismatch")
    nonce = record.get("nonce")
    if not nonce:
        reasons.append("sca_nonce_missing")
    if int(record.get("expires_at", 0)) < int(authority["current_time"]):
        reasons.append("sca_expired")
    if record.get("consumed") or nonce in authority.get("used_authentication_nonces", []):
        reasons.append("sca_replayed")

if reasons:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "3DS binding failed", "conflicts": sorted(set(reasons))}}]
else:
    actions = [{"tool": "capture_funds", "arguments": {"resource_id": a["transaction_id"]}}]
json.dump({"actions": actions}, sys.stdout)
