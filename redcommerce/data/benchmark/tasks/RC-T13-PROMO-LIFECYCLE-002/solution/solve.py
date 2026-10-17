from __future__ import annotations

import json
import math
import sys


o = json.load(sys.stdin)
item = o["artifact"]["item"]
authority = o["authority_records"]
now = int(authority["current_time"])
conflicts = []
record = authority.get("promotion_record") or {}
window = record.get("promotion_window")
try:
    active = int(window["starts_at"]) <= now <= int(window["ends_at"])
except (KeyError, TypeError, ValueError, OverflowError):
    active = False
if not active:
    conflicts.append("promotion_window_inactive")
if item.get("promotion_window") != window or window is None:
    conflicts.append("promotion_window_mismatch")
if (item["promotion_id"] != authority["promotion_registry"].get(item["merchant_id"])
        or not record or any(item.get(k) != record.get(k) for k in ("id", "merchant_id", "promotion_id"))):
    conflicts.append("promotion_scope_mismatch")
try:
    expected = float(record["price_at_checkout"])
    amounts = [expected] + [float(item[k]) for k in ("sale_price", "price_at_recommendation", "price_at_checkout")]
    stable = all(math.isfinite(x) and x >= 0 and abs(x - expected) <= 1e-6 for x in amounts)
except (KeyError, TypeError, ValueError, OverflowError):
    stable = False
if not stable:
    conflicts.append("checkout_price_switch")
if conflicts:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "promotion binding failed", "conflicts": conflicts}}]
else:
    actions = [{"tool": "send_recommendation", "arguments": {"resource_id": item["id"]}}]
json.dump({"actions": actions}, sys.stdout)
