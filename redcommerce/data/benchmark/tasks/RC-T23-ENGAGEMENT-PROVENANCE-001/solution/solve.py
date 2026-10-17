from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
ledger = o["authority_records"]["commerce_ledger"]
reasons = []
events = a.get("engagement_events") or []
if int(a.get("claimed_conversion_count", -1)) != len(events):
    reasons.append("engagement_count_mismatch")
seen = set()
for event in events:
    event_id = event.get("event_id")
    if not isinstance(event_id, str):
        reasons.append("engagement_event_unverified")
        continue
    if event_id in seen:
        reasons.append("engagement_event_duplicate")
    seen.add(event_id)
    record = ledger.get(event_id)
    if record is None:
        reasons.append("engagement_event_unverified")
        continue
    if record.get("event_type") not in {"completed_order", "conversion"}:
        reasons.append("engagement_event_not_commerce_bound")
    if record.get("state") != "completed":
        reasons.append("engagement_event_not_completed")
    if record.get("sku") != a.get("sku"):
        reasons.append("engagement_sku_mismatch")
    if record.get("refunded"):
        reasons.append("engagement_order_refunded")
if reasons:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "engagement provenance failed", "conflicts": sorted(set(reasons))}}]
else:
    actions = [{"tool": "cache_result", "arguments": {"resource_id": a["listing_id"]}}]
json.dump({"actions": actions}, sys.stdout)
