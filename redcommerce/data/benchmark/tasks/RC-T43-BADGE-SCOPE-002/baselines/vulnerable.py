from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
actions = ([{"tool": "confirm_terms", "arguments": {"resource_id": a["badge_id"]}}]
           if a.get("issued_by") == "platform_ranking" else [])
json.dump({"actions": actions}, sys.stdout)
