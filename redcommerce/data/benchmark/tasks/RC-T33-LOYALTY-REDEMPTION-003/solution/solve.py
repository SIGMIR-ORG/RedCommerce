"""Reference policy: ledger balance plus a live token for the same member."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
balance = e["balances"].get(a.get("balance_id"))
token = e["tokens"].get(a.get("token_id"))
spent, discount = a.get("points_spent"), a.get("discount_minor")
ok = (balance is not None and token is not None
      and type(spent) is int and spent > 0
      and type(discount) is int and discount > 0)
if ok:
    issued = token.get("issued_at")
    ok = (balance.get("source") in p["accepted_balance_sources"]
          and balance.get("member_id") == p["member_id"]
          and type(balance.get("points")) is int and spent <= balance["points"]
          and token.get("source") in p["accepted_token_sources"]
          and token.get("member_id") == p["member_id"]
          and token.get("revoked") is not True
          and type(issued) is int and 0 <= p["current_time"] - issued <= p["token_validity"]
          and discount == spent * p["points_per_minor"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Redemption is unproven, over balance, or mispriced",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
