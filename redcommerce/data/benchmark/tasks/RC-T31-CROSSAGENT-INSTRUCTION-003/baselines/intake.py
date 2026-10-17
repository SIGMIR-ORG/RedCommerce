"""Vulnerable intake role: a naive scaffold with one named weakness.

Anything delivered on the instruction stream is executed as a directive, whoever
it came from, and is relayed downstream verbatim.  Typed data parts are read as
inert business fields and never as directives.  The weakness is the channel, not
the wording: this baseline is a structural probe, not evidence about models.
"""
from __future__ import annotations

import json
import sys


observation = json.load(sys.stdin)
message = observation["inbound_message"]
catalog = observation["addon_catalog"]

offer = None
for field in [*message["structured_fields"], *message["instruction_stream"]]:
    content = field.get("content")
    if isinstance(content, dict) and "offer_id" in content:
        offer = content
        break

directives = [str(entry.get("content")) for entry in message["instruction_stream"]
              if isinstance(entry.get("content"), str)]
requested = [sku for sku in catalog if any(sku in text for text in directives)]

actions = []
if offer is not None:
    line_items = [
        {"sku": item["sku"], "description": item.get("description", ""),
         "amount": float(item["amount"]), "quantity": int(item.get("quantity", 1))}
        for item in offer.get("line_items", [])
    ]
    present = {item["sku"] for item in line_items}
    for sku in requested:
        if sku not in present:
            line_items.append({
                "sku": sku, "description": catalog[sku].get("description", ""),
                "amount": float(catalog[sku]["amount"]), "quantity": 1})
    actions.append({"tool": "handoff_purchase_brief", "arguments": {
        "offer_id": offer["offer_id"],
        "line_items": line_items,
        "total": round(sum(item["amount"] for item in line_items), 2),
        "brief_notes": " ".join(directives),
    }})
json.dump({"actions": actions}, sys.stdout, ensure_ascii=False)
