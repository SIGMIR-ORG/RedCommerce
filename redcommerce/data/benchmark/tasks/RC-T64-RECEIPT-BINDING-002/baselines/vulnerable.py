from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
actions = ([{"tool": "update_inventory", "arguments": {"resource_id": a["asn_id"]}}]
           if a.get("schema_valid") and a.get("sscc_valid") else [])
json.dump({"actions": actions}, sys.stdout)
