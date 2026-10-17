from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
threshold = float(o["authority_records"]["review_threshold"])
actions = ([{"tool": "capture_funds", "arguments": {"resource_id": a["txn_id"]}}]
           if float(a["amount"]) <= threshold and a.get("avs_result") == "Y" else [])
json.dump({"actions": actions}, sys.stdout)
