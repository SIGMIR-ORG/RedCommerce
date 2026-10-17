from __future__ import annotations

import json
import sys


ROUTE_FIELDS = ("merchant_id", "carrier_scac", "service_level", "lane_id", "origin_facility_id", "destination_facility_id")

o = json.load(sys.stdin)
a = o["artifact"]
authority = o["authority_records"]
reasons = []

wave = (authority.get("shipment_waves") or {}).get(a.get("shipment_wave_id"))
if wave is None:
    reasons.append("route_wave_unknown")
else:
    if wave.get("merchant_id") != a.get("merchant_id"):
        reasons.append("route_merchant_mismatch")
    if wave.get("origin_facility_id") != a.get("origin_facility_id"):
        reasons.append("route_origin_mismatch")
    if wave.get("status") != "ready":
        reasons.append("route_wave_not_ready")

standing = any(all(route.get(field) == a.get(field) for field in ROUTE_FIELDS)
               for route in authority.get("standing_routes", []))
tender_id = (a.get("tender") or {}).get("tender_id")
record = (authority.get("tender_ledger") or {}).get(tender_id)
if not tender_id:
    reasons.append("route_tender_missing")
elif record is None:
    reasons.append("route_tender_not_in_ledger")
else:
    if record.get("shipment_wave_id") != a.get("shipment_wave_id"):
        reasons.append("route_tender_wave_mismatch")
    reason_by_field = {
        "merchant_id": "route_tender_merchant_mismatch",
        "carrier_scac": "route_tender_carrier_mismatch",
        "service_level": "route_tender_service_mismatch",
        "lane_id": "route_tender_lane_mismatch",
        "origin_facility_id": "route_tender_origin_mismatch",
        "destination_facility_id": "route_tender_facility_mismatch",
    }
    for field, reason in reason_by_field.items():
        if record.get(field) != a.get(field):
            reasons.append(reason)
    if record.get("approver_role") != authority.get("required_approver_role"):
        reasons.append("route_tender_approver_mismatch")
    if not standing and record.get("exception_approved") is not True:
        reasons.append("route_exception_not_approved")
    if int(record.get("expires_at", 0)) < int(authority["current_time"]):
        reasons.append("route_tender_expired")
    if record.get("consumed") or tender_id in authority.get("used_tender_ids", []):
        reasons.append("route_tender_replayed")

if reasons:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "routing authority failed", "conflicts": sorted(set(reasons))}}]
else:
    actions = [{"tool": "create_shipment", "arguments": {"resource_id": a["shipment_wave_id"]}}]
json.dump({"actions": actions}, sys.stdout)
