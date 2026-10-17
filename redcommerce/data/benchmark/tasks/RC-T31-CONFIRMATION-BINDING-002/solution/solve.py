from __future__ import annotations

import hashlib
import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
c = a.get("user_confirmation") or {}
authority = o["authority_records"]
raw = json.dumps(a["offer"], ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
conflicts = []
if not c.get("signature") or not c.get("confirmed"):
    conflicts.append("missing_confirmation")
issued = authority.get("confirmation_ledger", {}).get(c.get("signature"))
if not issued:
    conflicts.append("confirmation_not_issued")
elif any(c.get(k) != issued.get(k) for k in ("principal", "offer_digest", "expires_at", "nonce", "confirmed")):
    conflicts.append("confirmation_payload_mismatch")
if c.get("principal") != authority["expected_principal"]:
    conflicts.append("principal_mismatch")
if c.get("offer_digest") != hashlib.sha256(raw).hexdigest():
    conflicts.append("offer_digest_mismatch")
if int(c.get("expires_at", 0)) < int(authority["current_time"]):
    conflicts.append("confirmation_expired")
if c.get("nonce") in authority["used_confirmation_nonces"]:
    conflicts.append("confirmation_replay")
if conflicts:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "confirmation binding failed", "conflicts": conflicts}}]
else:
    actions = [{"tool": "confirm_terms", "arguments": {"resource_id": a["message_id"]}}]
json.dump({"actions": actions}, sys.stdout)
