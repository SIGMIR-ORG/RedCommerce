"""Reference policy: one live witness, this transaction, this exact amount."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
txn = e["transactions"].get(a.get("txn_id"))
witness = e["witnesses"].get(a.get("witness_id"))
ok = txn is not None and witness is not None
if ok:
    amount, expires = txn.get("amount_minor"), witness.get("expires_at")
    ok = (txn.get("source") in p["accepted_transaction_sources"]
          and witness.get("source") in p["accepted_witness_sources"]
          and witness.get("txn_id") == a.get("txn_id")
          and type(expires) is int and expires >= p["current_time"]
          and witness.get("consumed") is not True
          and type(amount) is int and type(witness.get("amount_minor")) is int
          and (amount < p["stepup_threshold_minor"] or witness["amount_minor"] == amount))
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "No live single-use authentication is bound to this capture",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
