from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
listing = o["artifact"]
gtin = str(listing.get("gtin", ""))
actions = ([{"tool": "cache_result", "arguments": {"resource_id": listing["listing_id"]}}]
           if gtin.isdigit() and gtin.startswith("0614141") else [])
json.dump({"actions": actions}, sys.stdout)
