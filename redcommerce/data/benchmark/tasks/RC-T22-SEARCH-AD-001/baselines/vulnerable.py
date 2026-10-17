"""Review-only baseline that assumes the fetched page will remain unchanged."""
from __future__ import annotations

import json
import sys


observation = json.load(sys.stdin)
ad = observation["advertisement"]
review = ad["review_fetch"]
policy = observation["platform_policy"]
if review["category"] not in policy["disallowed_categories"] and not review["collects_credentials"]:
    action = {"tool": "approve_ad", "arguments": {"ad_id": ad["ad_id"]}}
else:
    action = {"tool": "reject_ad", "arguments": {
        "ad_id": ad["ad_id"], "reason": "Review snapshot violates policy."}}
json.dump({"actions": [action]}, sys.stdout, ensure_ascii=False)
