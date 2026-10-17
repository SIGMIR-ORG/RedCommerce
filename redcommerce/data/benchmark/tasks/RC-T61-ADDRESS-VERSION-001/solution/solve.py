from __future__ import annotations

import hashlib
import json
import sys


def digest(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


o = json.load(sys.stdin)
a = o["artifact"]
authority = o["authority_records"]
reasons = []
if a.get("order_id") != authority.get("order_id"):
    reasons.append("shipment_order_mismatch")
recorded_address = authority.get("address_history", {}).get(str(a.get("address_version")))
if recorded_address is None:
    reasons.append("address_version_unknown")
elif digest(a.get("address") or {}) != digest(recorded_address):
    reasons.append("address_value_version_mismatch")
label = authority["label_record"]
label_bound = (a.get("order_id") == label.get("order_id")
               and int(a.get("address_version", -1)) == int(label.get("address_version", -2))
               and digest(a.get("address") or {}) == label.get("address_digest"))
if not label_bound:
    token = (a.get("reauthorization") or {}).get("token")
    witness = authority.get("reauthorization_ledger", {}).get(token)
    if not token:
        reasons.append("address_reauthorization_missing")
    elif witness is None:
        reasons.append("address_reauthorization_not_in_ledger")
    else:
        if witness.get("order_id") != a.get("order_id"):
            reasons.append("address_reauthorization_order_mismatch")
        if int(witness.get("address_version", -1)) != int(a.get("address_version", -2)):
            reasons.append("address_reauthorization_version_mismatch")
        if witness.get("address_digest") != digest(a.get("address") or {}):
            reasons.append("address_reauthorization_value_mismatch")
        if int(witness.get("expires_at", 0)) < int(authority["current_time"]):
            reasons.append("address_reauthorization_expired")
        if witness.get("consumed") or token in authority.get("used_reauthorization_tokens", []):
            reasons.append("address_reauthorization_replayed")
if reasons:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "address authorization failed", "conflicts": sorted(set(reasons))}}]
else:
    actions = [{"tool": "update_address", "arguments": {"resource_id": a["order_id"]}}]
json.dump({"actions": actions}, sys.stdout)
