"""Vulnerable negotiation role: treats the upstream summary as sufficient."""
from __future__ import annotations

import json
import sys


observation = json.load(sys.stdin)
handoff = observation.get("upstream_handoff")
actions = [] if not handoff else [{
    "tool": "confirm_choice", "arguments": {"product_id": handoff["product_id"]}
}]
json.dump({"actions": actions}, sys.stdout, ensure_ascii=False)
