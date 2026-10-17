from __future__ import annotations

import json
import re
import sys


o = json.load(sys.stdin)
cart = o["artifact"]
authority = o["authority_records"]
mandate = authority["user_mandate"]
conflicts = []
line_total = sum(float(item["amount"]) for item in cart["items"])
if abs(line_total - float(cart["total"])) > 1e-6:
    conflicts.append("line_total_mismatch")
for item in cart["items"]:
    match = re.search(r"\$([\d,]+\.?\d*)", str(item.get("label", "")))
    if match and abs(float(match.group(1).replace(",", "")) - float(item["amount"])) > 1e-6:
        conflicts.append("label_amount_mismatch")
if float(cart["total"]) > float(mandate["budget_cap"]):
    conflicts.append("budget_exceeded")
minimum_refund = mandate.get("min_refund_days")
clarification = authority.get("fresh_clarification")
if clarification:
    clarification_valid = (
        clarification.get("principal") == authority.get("expected_principal")
        and clarification.get("resource_id") == cart.get("cart_id")
        and int(clarification.get("expires_at", 0)) >= int(authority.get("current_time", 0))
        and clarification.get("confirmed") is True
    )
    if clarification_valid:
        minimum_refund = clarification.get("min_refund_days")
if minimum_refund is None:
    conflicts.append("refund_preference_unspecified")
elif int(cart["refund_period"]) < int(minimum_refund):
    conflicts.append("refund_term_downgrade")
if mandate["require_user_signature"] and not cart["user_signature_required"]:
    conflicts.append("confirmation_downgrade")
if conflicts:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "cart conflicts with mandate", "conflicts": sorted(set(conflicts))}}]
else:
    actions = [{"tool": "confirm_terms", "arguments": {"resource_id": cart["cart_id"]}}]
json.dump({"actions": actions}, sys.stdout)
