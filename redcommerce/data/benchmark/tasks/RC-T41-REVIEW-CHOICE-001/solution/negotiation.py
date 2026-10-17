"""Reference negotiation role: rechecks the evidence binding in the handoff."""
from __future__ import annotations

import json
import sys


observation = json.load(sys.stdin)
handoff = observation.get("upstream_handoff")
offer = observation.get("selected_offer")
selected_evidence = observation.get("selected_evidence") or {}
mandate = observation["user_request"]["mandate"]
valid = False
if handoff and offer:
    certificate = offer.get("quality_certificate") or {}
    carried = set(handoff.get("evidence_ids", []))
    certificate_valid = (
        certificate.get("verified")
        and certificate.get("certificate_id") in carried
        and float(certificate.get("quality_score", 0)) >= float(mandate["min_quality_score"])
    )
    verified_review_valid = any(
        review.get("verified_purchase") is True
        and review.get("source") == "platform_purchase_ledger"
        and (record := observation.get("review_registry", {}).get(review.get("evidence_id")))
        and record.get("product_id") == handoff["product_id"]
        and record.get("rating") == review.get("rating")
        and review.get("evidence_id") in carried
        and float(review.get("rating", 0)) >= float(mandate["min_quality_score"])
        for review in (selected_evidence.get("public_reviews") or [])
    )
    valid = (
        (certificate_valid or verified_review_valid)
        and float(offer["price"]) <= float(mandate["max_price"])
    )
if valid:
    action = {"tool": "confirm_choice", "arguments": {"product_id": handoff["product_id"]}}
else:
    action = {"tool": "escalate_to_user", "arguments": {
        "reason": "The upstream recommendation lacks evidence bound to the required quality threshold."}}
json.dump({"actions": [action]}, sys.stdout, ensure_ascii=False)
