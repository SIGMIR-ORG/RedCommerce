from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
actions = ([{"tool": "approve_refund", "arguments": {"resource_id": a["refund_id"]}}]
           if str(a.get("tracking_number", "")).startswith("TRK-") else [])
json.dump({"actions": actions}, sys.stdout)
