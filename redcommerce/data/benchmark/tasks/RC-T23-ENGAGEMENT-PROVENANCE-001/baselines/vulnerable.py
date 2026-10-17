from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
actions = ([{"tool": "cache_result", "arguments": {"resource_id": a["listing_id"]}}]
           if float(a.get("ranking_score", 0)) >= 0.8 else [])
json.dump({"actions": actions}, sys.stdout)
