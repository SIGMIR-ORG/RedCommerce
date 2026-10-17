"""Reference policy: live PIN-verified card, right currency, within both ceilings."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["cards"].get(a.get("card_id"))
applied = a.get("applied_minor")
ok = record is not None and type(applied) is int and applied > 0
if ok:
    expires, balance = record.get("expires_at"), record.get("balance_minor")
    ok = (record.get("source") in p["accepted_balance_sources"]
          and record.get("active") is True
          and type(expires) is int and expires >= p["current_time"]
          and record.get("pin_verified") is True
          and record.get("currency") == p["currency"]
          and type(balance) is int and applied <= balance
          and applied <= p["cart_total_minor"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Card is unverified, wrong currency, or over a ceiling",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
