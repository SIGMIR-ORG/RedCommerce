"""Reference policy: the measured delay picks the band, once per order."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["deliveries"].get(a.get("order_id"))
ledger = e["compensation_ledger"].get(a.get("order_id"))
voucher = a.get("voucher_minor")
ok = record is not None and ledger is not None and type(voucher) is int and voucher > 0
if ok:
    promised, delivered = record.get("promised_at"), record.get("delivered_at")
    ok = type(promised) is int and type(delivered) is int
    if ok:
        delay = delivered - promised
        earned = None
        if 0 < delay <= p["tier1_max_delay"]:
            earned = p["tier1_voucher_minor"]
        elif delay <= p["tier2_max_delay"] and delay > 0:
            earned = p["tier2_voucher_minor"]
        ok = (record.get("source") in p["accepted_delivery_sources"]
              and type(ledger.get("vouchers_issued")) is int
              and ledger["vouchers_issued"] < p["max_vouchers_per_order"]
              and earned is not None and voucher == earned)
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "No measured breach, already compensated, or wrong band",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
