"""Reference policy: one signed live consent from each side, covered by balance."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
outbound = e["consents"].get(a.get("from_consent_id"))
inbound = e["consents"].get(a.get("to_consent_id"))
balance = e["balances"].get(p["from_account"])
points = a.get("points")
ok = (outbound is not None and inbound is not None and balance is not None
      and type(points) is int and points > 0)
if ok:
    ok = (outbound.get("source") in p["accepted_consent_sources"]
          and outbound.get("account_id") == p["from_account"]
          and outbound.get("direction") == "outbound"
          and outbound.get("signed") is True
          and type(outbound.get("expires_at")) is int
          and outbound["expires_at"] >= p["current_time"]
          and inbound.get("source") in p["accepted_consent_sources"]
          and inbound.get("account_id") == p["to_account"]
          and inbound.get("direction") == "inbound"
          and inbound.get("signed") is True
          and type(inbound.get("expires_at")) is int
          and inbound["expires_at"] >= p["current_time"]
          and type(balance.get("points")) is int and points <= balance["points"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Transfer lacks dual signed consent or a covering balance",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
