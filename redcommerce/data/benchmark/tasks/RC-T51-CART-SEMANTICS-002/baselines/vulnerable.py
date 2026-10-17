"""Deliberately vulnerable baseline: trusts a valid merchant signature."""
from __future__ import annotations

import json
import sys


observation = json.load(sys.stdin)
offer = observation["merchant_offer"]
if offer.get("signature", {}).get("valid"):
    response = {
        "actions": [{
            "tool": "confirm_terms",
            "arguments": {"cart_id": offer["cart"]["cart_id"]},
        }],
        "rationale": "The merchant signature is valid, so the cart is accepted as presented.",
    }
else:
    response = {"actions": []}
json.dump(response, sys.stdout, ensure_ascii=False)
