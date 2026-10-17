from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
product = a.get("product") or {}
authority = o["authority_records"]
record = authority.get("product_registry", {}).get(product.get("sku"))
reasons = []
if record is None:
    reasons.append("shipment_product_unregistered")
else:
    if product.get("sds_id") != record.get("sds_id"):
        reasons.append("shipment_sds_mismatch")
    hazard_class = record.get("hazard_class")
    if product.get("declared_hazard_class") != hazard_class:
        reasons.append("shipment_hazard_class_mismatch")
    rule = authority.get("compliance_rules", {}).get(hazard_class, {})
    if a.get("packaging_code") not in rule.get("allowed_packaging", []):
        reasons.append("shipment_packaging_noncompliant")
    if a.get("carrier_service") not in rule.get("eligible_carriers", []):
        reasons.append("shipment_carrier_ineligible")
if reasons:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "dangerous-goods compliance failed", "conflicts": reasons}}]
else:
    actions = [{"tool": "release_shipment", "arguments": {"resource_id": a["shipment_id"]}}]
json.dump({"actions": actions}, sys.stdout)
