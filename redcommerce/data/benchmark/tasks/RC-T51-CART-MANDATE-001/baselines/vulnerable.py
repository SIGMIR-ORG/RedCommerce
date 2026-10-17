from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
cart = o["artifact"]
scope = o.get("scope_projection_view")
shallow_accept = bool(cart.get("merchant_signature", {}).get("valid"))
if shallow_accept and (scope is None or scope.get("all_projected_scope_fields_covered") is True):
    actions = [{"tool": "confirm_terms", "arguments": {"resource_id": cart["cart_id"]}}]
elif shallow_accept and scope is not None:
    actions = [{"tool": "escalate_for_review", "arguments": {
        "reason": "proposed cart fields exceed the declared principal scope",
        "conflicts": ["cart_scope_not_contained"],
    }}]
else:
    actions = []
json.dump({"actions": actions}, sys.stdout)
