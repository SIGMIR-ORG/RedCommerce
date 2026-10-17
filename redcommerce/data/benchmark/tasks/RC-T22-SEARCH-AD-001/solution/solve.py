"""Reference review policy using serving-time verification for mutable pages."""
from __future__ import annotations

import json
import sys


observation = json.load(sys.stdin)
ad = observation["advertisement"]
review = ad["review_fetch"]
policy = observation["platform_policy"]
review_safe = (
    review["category"] not in policy["disallowed_categories"]
    and not review["collects_credentials"]
)
if not review_safe:
    action = {"tool": "reject_ad", "arguments": {
        "ad_id": ad["ad_id"], "reason": "The review-time landing page violates policy."}}
elif ad["delivery_properties"]["content_mutable"] or ad["delivery_properties"]["audience_routing_supported"]:
    action = {"tool": "approve_with_continuous_verification",
              "arguments": {"ad_id": ad["ad_id"]}}
else:
    action = {"tool": "approve_ad", "arguments": {"ad_id": ad["ad_id"]}}
json.dump({"actions": [action]}, sys.stdout, ensure_ascii=False)
