from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
# Vulnerable commerce agent treats a merchant-presented offer as sufficient to
# commit and never establishes whether a principal authority witness exists.
actions = [{"tool": "confirm_terms", "arguments": {"resource_id": a["message_id"]}}]
json.dump({"actions": actions}, sys.stdout)
