"""Reference policy: band, category and the cumulative counter all decide."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["transactions"].get(a.get("txn_id"))
counter = e["exemption_counters"].get((record or {}).get("card_token"))
ok = record is not None and counter is not None
if ok:
    amount = record.get("amount_minor")
    ok = (record.get("source") in p["accepted_transaction_sources"]
          and type(amount) is int and 0 < amount <= p["exemption_max_minor"]
          and record.get("mcc") not in p["restricted_mcc"]
          and type(counter.get("used")) is int
          and counter["used"] < p["cumulative_exemption_limit"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Transaction does not qualify for a low-value exemption",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
