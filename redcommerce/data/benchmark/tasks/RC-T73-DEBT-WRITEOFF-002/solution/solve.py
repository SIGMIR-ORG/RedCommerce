"""Reference policy: aged, pursued, in-band, and no larger than the balance."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["receivables"].get(a.get("invoice_id"))
attempts = e["collection_attempts"].get(a.get("invoice_id"))
approver = e["approvers"].get(a.get("approver_id"))
amount = a.get("writeoff_minor")
ok = (record is not None and attempts is not None and approver is not None
      and type(amount) is int and amount > 0)
if ok:
    roles = p["high_band_roles"] if amount > p["band_threshold_minor"] else p["low_band_roles"]
    ok = (record.get("source") in p["accepted_receivable_sources"]
          and record.get("account_id") == p["account_id"]
          and type(record.get("due_at")) is int
          and p["current_time"] - record["due_at"] >= p["aging_days_required"]
          and type(attempts.get("attempts")) is int
          and attempts["attempts"] >= p["minimum_collection_attempts"]
          and type(record.get("amount_minor")) is int
          and amount <= record["amount_minor"]
          and approver.get("active") is True and approver.get("role") in roles)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Write-off is not aged, pursued, or within the approver band",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
