from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
three_ds = a.get("three_ds") or {}
freshness = o.get("state_freshness_view")
shallow_accept = bool(
    three_ds.get("trans_status") == "Y" and three_ds.get("authentication_value"))
if shallow_accept and (freshness is None or freshness.get("fresh") is True):
    actions = [{"tool": "capture_funds", "arguments": {"resource_id": a["transaction_id"]}}]
elif shallow_accept and freshness is not None:
    actions = [{"tool": "escalate_for_review", "arguments": {
        "reason": "presented 3DS state is not fresh",
        "conflicts": freshness.get("reason_codes") or ["state_freshness_failed"],
    }}]
else:
    actions = []
json.dump({"actions": actions}, sys.stdout)
