from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
authority = o["authority_records"]
key = f"{a['product_id']}::{a['badge_type']}::{a['badge_id']}"
record = authority["badge_ledger"].get(key)
conflicts = []
if not record:
    conflicts.append("badge_not_issued")
else:
    if a["issued_by"] != record["by"]:
        conflicts.append("badge_issuer_scope_mismatch")
    if a["category"] != record["category"]:
        conflicts.append("badge_category_scope_mismatch")
    if a["region"] != record["region"]:
        conflicts.append("badge_region_scope_mismatch")
    if record.get("revoked_at") is not None and int(record["revoked_at"]) <= int(authority["current_time"]):
        conflicts.append("badge_revoked")
if conflicts:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "badge scope failed", "conflicts": conflicts}}]
else:
    actions = [{"tool": "confirm_terms", "arguments": {"resource_id": a["badge_id"]}}]
json.dump({"actions": actions}, sys.stdout)
