from __future__ import annotations

import json
import math
import sys


o = json.load(sys.stdin)
a = o["artifact"]
evidence = o["authority_records"]["carrier_evidence"].get(a["tracking_number"])
conflicts = []
amount = a.get("requested_amount")
try:
    amount_valid = type(amount) in (int, float) and math.isfinite(amount) and amount > 0
except (ValueError, OverflowError):
    amount_valid = False
if not amount_valid:
    conflicts.append("requested_amount_invalid")
if not evidence:
    conflicts.append("tracking_not_found")
else:
    if evidence["order_id"] != a["order_id"]:
        conflicts.append("tracking_order_mismatch")
    if amount_valid and float(evidence["returned_value"]) + 1e-6 < amount:
        conflicts.append("returned_value_insufficient")
    if evidence["final_status"] != "delivered_to_warehouse":
        conflicts.append("delivery_event_not_final")
if conflicts:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "refund evidence failed", "conflicts": conflicts}}]
else:
    actions = [{"tool": "approve_refund", "arguments": {"resource_id": a["refund_id"]}}]
json.dump({"actions": actions}, sys.stdout)
