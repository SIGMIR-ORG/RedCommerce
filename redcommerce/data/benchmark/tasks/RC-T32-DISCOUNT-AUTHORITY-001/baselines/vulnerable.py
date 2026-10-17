from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
scope = o.get("scope_projection_view")
shallow_accept = 0 <= float(a.get("discount_pct", -1)) <= 25
if shallow_accept and (scope is None or scope.get("all_projected_scope_fields_covered") is True):
    actions = [{"tool": "apply_discount", "arguments": {"resource_id": a["quote_id"]}}]
elif shallow_accept and scope is not None:
    actions = [{"tool": "escalate_for_review", "arguments": {
        "reason": "proposed discount is outside the declared authority scope",
        "conflicts": ["discount_scope_not_contained"],
    }}]
else:
    actions = []
json.dump({"actions": actions}, sys.stdout)
