from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
actions = ([{"tool": "release_shipment", "arguments": {"resource_id": a["shipment_id"]}}]
           if a.get("product", {}).get("description") else [])
json.dump({"actions": actions}, sys.stdout)
