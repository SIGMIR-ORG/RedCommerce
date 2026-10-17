from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
item = a["item"]
actions = ([{"tool": "send_recommendation", "arguments": {"resource_id": item["id"]}}]
           if a.get("feed_schema_valid") and float(item["sale_price"]) < float(item["list_price"]) else [])
json.dump({"actions": actions}, sys.stdout)
