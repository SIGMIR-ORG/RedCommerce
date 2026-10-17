from __future__ import annotations

import json
import sys


o = json.load(sys.stdin)
a = o["artifact"]
required = ("merchant_id", "payout_batch_id", "amount", "currency", "beneficiary_account_id")
actions = ([{"tool": "capture_funds", "arguments": {"resource_id": a["payout_batch_id"]}}]
           if all(a.get(field) is not None for field in required) else [])
json.dump({"actions": actions}, sys.stdout)
