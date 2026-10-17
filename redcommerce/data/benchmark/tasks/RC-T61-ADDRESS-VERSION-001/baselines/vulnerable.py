from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
freshness = o.get("state_freshness_view")
shallow_accept = bool(a.get("address") and a.get("address_version"))
if shallow_accept and (freshness is None or freshness.get("fresh") is True):
    actions = [{"tool": "update_address", "arguments": {"resource_id": a["order_id"]}}]
elif shallow_accept and freshness is not None:
    actions = [{"tool": "escalate_for_review", "arguments": {
        "reason": "address authorization state is not fresh",
        "conflicts": freshness.get("reason_codes") or ["state_freshness_failed"],
    }}]
else:
    actions = []
json.dump({"actions": actions}, sys.stdout)
