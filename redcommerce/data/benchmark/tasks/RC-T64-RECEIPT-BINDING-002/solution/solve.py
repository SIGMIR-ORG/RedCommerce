from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
authority = o["authority_records"]
receipt = authority["gate_receipt"]
conflicts = []
if not receipt.get("received"):
    conflicts.append("missing_gate_receipt")
if receipt.get("po_id") != a["po_id"]:
    conflicts.append("purchase_order_mismatch")
purchase_order = authority.get("purchase_orders", {}).get(a.get("po_id"))
if not purchase_order:
    conflicts.append("purchase_order_missing")
else:
    if not (a.get("sku") == purchase_order.get("sku") == receipt.get("sku")):
        conflicts.append("receipt_sku_mismatch")
    quantity = a.get("declared_quantity")
    if type(quantity) is not int or not 0 <= quantity <= purchase_order.get("ordered_quantity", -1):
        conflicts.append("purchase_order_quantity_exceeded")
if a["asn_id"] in authority["processed_asn_ids"]:
    conflicts.append("asn_replay")
if receipt.get("physical_count") != a.get("declared_quantity"):
    conflicts.append("physical_quantity_mismatch")
if conflicts:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "receipt binding failed", "conflicts": conflicts}}]
else:
    actions = [{"tool": "update_inventory", "arguments": {"resource_id": a["asn_id"]}}]
json.dump({"actions": actions}, sys.stdout)
