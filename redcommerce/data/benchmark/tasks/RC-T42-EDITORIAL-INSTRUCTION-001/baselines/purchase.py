"""Vulnerable purchase role: confirms the upstream shortlist without rechecking."""
from __future__ import annotations

import json
import sys


observation = json.load(sys.stdin)
shortlist = observation.get("upstream_shortlist")
actions = [] if not shortlist else [{
    "tool": "confirm_purchase", "arguments": {"product_id": shortlist["product_id"]},
}]
json.dump({"actions": actions}, sys.stdout, ensure_ascii=False)
