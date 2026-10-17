from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
listing = o["artifact"]
scope = o["authority_records"]["gtin_registry"].get(listing["gtin"])
conflicts = []
if not scope:
    conflicts.append("gtin_unregistered")
else:
    for field in ("brand", "item_id", "market", "seller_id"):
        if listing.get(field) != scope.get(field):
            conflicts.append(f"gtin_{field}_scope_mismatch")
if conflicts:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "GTIN scope failed", "conflicts": conflicts}}]
else:
    actions = [{"tool": "cache_result", "arguments": {"resource_id": listing["listing_id"]}}]
json.dump({"actions": actions}, sys.stdout)
