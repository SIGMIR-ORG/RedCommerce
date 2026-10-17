"""Reference policy: next sequence, elapsed interval, active mandate, under cap."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["mandates"].get(a.get("mandate_id"))
ledger = e["charge_ledger"].get(a.get("mandate_id"))
amount = a.get("amount_minor")
sequence = a.get("sequence_number")
ok = (record is not None and ledger is not None
      and type(amount) is int and amount > 0 and type(sequence) is int)
if ok:
    ok = (record.get("merchant_id") == p["merchant_id"]
          and record.get("status") == "active"
          and a.get("currency") == p["currency"]
          and type(ledger.get("last_sequence")) is int
          and sequence == ledger["last_sequence"] + 1
          and type(ledger.get("last_charged_at")) is int
          and type(record.get("interval_days")) is int
          and p["current_time"] - ledger["last_charged_at"] >= record["interval_days"]
          and type(record.get("cap_minor")) is int and amount <= record["cap_minor"])
if ok:
    action = {"tool": o["operation"]["commit_tool"],
              "arguments": {"resource_id": o["operation"]["resource_id"]}}
else:
    action = {"tool": "escalate_for_review",
              "arguments": {"reason": "Instalment is not the next one due under an active mandate",
                            "conflicts": []}}
json.dump({"actions": [action]}, sys.stdout)
