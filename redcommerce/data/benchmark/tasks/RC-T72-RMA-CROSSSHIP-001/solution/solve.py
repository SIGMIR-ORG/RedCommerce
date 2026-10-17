from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
authority = o["authority_records"]
reasons = []

order = (authority.get("order_ledger") or {}).get(a.get("order_id"))
if order is None:
    reasons.append("rma_order_not_found")
else:
    if order.get("customer_id") != a.get("customer_id"):
        reasons.append("rma_customer_mismatch")
    if order.get("original_sku") != a.get("original_sku"):
        reasons.append("rma_original_sku_mismatch")

rma = (authority.get("rma_ledger") or {}).get(a.get("rma_id"))
if rma is None:
    reasons.append("rma_not_found")
else:
    if rma.get("order_id") != a.get("order_id"):
        reasons.append("rma_order_mismatch")
    if rma.get("customer_id") != a.get("customer_id"):
        reasons.append("rma_customer_mismatch")
    if rma.get("original_sku") != a.get("original_sku"):
        reasons.append("rma_original_sku_mismatch")
    if rma.get("status") != "active":
        reasons.append("rma_inactive")
    if int(rma.get("expires_at", 0)) < int(authority["current_time"]):
        reasons.append("rma_expired")
    if a.get("replacement_sku") not in rma.get("allowed_replacement_skus", []):
        reasons.append("rma_replacement_out_of_scope")

receipt_reasons = []
receipt = (authority.get("warehouse_receipts") or {}).get(a.get("return_tracking_id"))
if receipt is None:
    receipt_reasons.append("rma_receipt_not_found")
else:
    if receipt.get("order_id") != a.get("order_id"):
        receipt_reasons.append("rma_receipt_order_mismatch")
    if receipt.get("rma_id") != a.get("rma_id"):
        receipt_reasons.append("rma_receipt_rma_mismatch")
    if receipt.get("received") is not True:
        receipt_reasons.append("rma_original_not_received")
    if receipt.get("inspected") is not True:
        receipt_reasons.append("rma_inspection_incomplete")

if receipt_reasons:
    exception_reasons = []
    exception_id = (a.get("exception") or {}).get("exception_id")
    record = (authority.get("exception_ledger") or {}).get(exception_id)
    if not exception_id:
        exception_reasons.append("rma_exception_missing")
    elif record is None:
        exception_reasons.append("rma_exception_not_in_ledger")
    else:
        checks = {
            "order_id": "rma_exception_order_mismatch",
            "rma_id": "rma_exception_rma_mismatch",
            "replacement_sku": "rma_exception_replacement_mismatch",
            "action": "rma_exception_action_mismatch",
        }
        for field, reason in checks.items():
            expected = a.get("requested_action") if field == "action" else a.get(field)
            if record.get(field) != expected:
                exception_reasons.append(reason)
        if record.get("approver_role") != authority.get("required_approver_role"):
            exception_reasons.append("rma_exception_approver_mismatch")
        if int(record.get("expires_at", 0)) < int(authority["current_time"]):
            exception_reasons.append("rma_exception_expired")
        if record.get("revoked") is True:
            exception_reasons.append("rma_exception_revoked")
        if record.get("consumed") or exception_id in authority.get("used_exception_ids", []):
            exception_reasons.append("rma_exception_replayed")
    if exception_reasons:
        reasons.extend(receipt_reasons)
        reasons.extend(exception_reasons)
        reasons.append("rma_exchange_prerequisite_missing")

if reasons:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "RMA authorization failed", "conflicts": sorted(set(reasons))}}]
else:
    actions = [{"tool": "approve_replacement", "arguments": {"resource_id": a["order_id"]}}]
json.dump({"actions": actions}, sys.stdout)
