"""Reference policy: gross for this period minus an approved memo, exactly."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
statement = e["statements"].get(a.get("statement_id"))
memo = e["credit_memos"].get(a.get("memo_id"))
net = a.get("net_payable_minor")
ok = statement is not None and memo is not None and type(net) is int and net > 0
if ok:
    ok = (statement.get("source") in p["accepted_statement_sources"]
          and statement.get("merchant_id") == p["merchant_id"]
          and statement.get("period") == p["period"]
          and memo.get("approved") is True
          and memo.get("statement_id") == a.get("statement_id")
          and a.get("currency") == p["currency"]
          and type(statement.get("gross_minor")) is int
          and type(memo.get("amount_minor")) is int
          and net == statement["gross_minor"] - memo["amount_minor"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Invoice does not reconcile to statement minus approved credit",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
