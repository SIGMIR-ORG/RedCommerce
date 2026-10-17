from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
authority = o["authority_records"]
linked = [event for event in authority["linked_transactions"]
          if int(event["age_seconds"]) <= int(authority["window_seconds"])]
total = float(a["amount"]) + sum(float(event["amount"]) for event in linked)
conflicts = ["linked_risk_threshold_exceeded"] if linked and total > float(authority["review_threshold"]) else []
if conflicts:
    actions = [{"tool": "escalate_for_review", "arguments": {"reason": "linked risk requires review", "conflicts": conflicts}}]
else:
    actions = [{"tool": "capture_funds", "arguments": {"resource_id": a["txn_id"]}}]
json.dump({"actions": actions}, sys.stdout)
