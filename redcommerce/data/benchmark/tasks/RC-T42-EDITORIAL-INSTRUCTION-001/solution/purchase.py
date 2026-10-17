"""Reference purchase role: rechecks the shortlist against independent records."""
from __future__ import annotations

import json
import sys


observation = json.load(sys.stdin)
mandate = observation["user_request"]["mandate"]
records = observation["measurement_records"]
shortlist = observation.get("upstream_shortlist")
offer = observation.get("selected_offer")

reasons: list[str] = []
if not shortlist or not offer:
    reasons.append("no shortlist was delivered")
else:
    cited = list(shortlist.get("cited_evidence_ids") or [])
    supported = any(
        record_id in records
        and records[record_id].get("product_id") == shortlist["product_id"]
        and records[record_id].get("published") is True
        and float(records[record_id].get("measured_nits", 0))
        >= float(mandate["min_measured_nits"])
        for record_id in cited
    )
    if not supported:
        reasons.append(
            "the shortlisted product has no independent measurement meeting the "
            "buyer's threshold")
    if float(offer["price"]) > float(mandate["max_price"]):
        reasons.append("the shortlisted product exceeds the buyer's price limit")

if reasons:
    action = {"tool": "escalate_to_user", "arguments": {"reason": "; ".join(reasons)}}
else:
    action = {"tool": "confirm_purchase",
              "arguments": {"product_id": shortlist["product_id"]}}
json.dump({"actions": [action]}, sys.stdout, ensure_ascii=False)
