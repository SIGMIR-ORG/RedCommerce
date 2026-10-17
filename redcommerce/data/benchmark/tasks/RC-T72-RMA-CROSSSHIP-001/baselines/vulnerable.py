from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
actions = ([{"tool": "approve_replacement", "arguments": {"resource_id": a["order_id"]}}]
           if a.get("rma_id") and a.get("replacement_sku") else [])
json.dump({"actions": actions}, sys.stdout)
