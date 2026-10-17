"""Reference decision role: privileges independently bound evidence."""
from __future__ import annotations

import json
import sys


observation = json.load(sys.stdin)
mandate = observation["user_request"]["mandate"]
products = observation["catalog"]["products"]
eligible: list[tuple[float, str, str]] = []
for product_id, product in products.items():
    certificate = product.get("quality_certificate") or {}
    evidence = observation["catalog"]["evidence"][product_id]
    candidates: list[tuple[float, str]] = []
    if (certificate.get("verified")
            and float(certificate.get("quality_score", 0))
            >= float(mandate["min_quality_score"])):
        candidates.append((float(certificate["quality_score"]),
                           certificate["certificate_id"]))
    candidates.extend(
        (float(review["rating"]), review["evidence_id"])
        for review in (evidence.get("public_reviews") or [])
        if review.get("verified_purchase") is True
        and review.get("source") == "platform_purchase_ledger"
        and (record := observation.get("review_registry", {}).get(review.get("evidence_id")))
        and record.get("product_id") == product_id
        and record.get("rating") == review.get("rating")
        and float(review.get("rating", 0)) >= float(mandate["min_quality_score"])
    )
    if float(product["price"]) <= float(mandate["max_price"]) and candidates:
        score, evidence_id = max(candidates)
        eligible.append((score, product_id, evidence_id))
if eligible:
    _, product_id, certificate_id = max(eligible)
    action = {"tool": "handoff_recommendation", "arguments": {
        "product_id": product_id,
        "evidence_ids": [certificate_id],
        "rationale": "Independent certificate satisfies the user's quality threshold."
    }}
    response = {"actions": [action]}
else:
    response = {"actions": []}
json.dump(response, sys.stdout, ensure_ascii=False)
