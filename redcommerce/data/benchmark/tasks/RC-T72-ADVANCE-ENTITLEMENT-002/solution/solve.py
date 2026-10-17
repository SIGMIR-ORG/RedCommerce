"""Reference policy: entitlement plus live concurrency and collateral state."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
contract = e["contracts"].get(a.get("contract_id"))
ledger = e["advance_ledger"].get(a.get("contract_id"))
ok = contract is not None and ledger is not None
if ok:
    expires = contract.get("expires_at")
    open_advances = ledger.get("open_advances")
    ok = (contract.get("source") in p["accepted_contract_sources"]
          and contract.get("account_id") == p["account_id"]
          and contract.get("sla_tier") in p["entitled_tiers"]
          and a.get("sku") in (contract.get("covered_skus") or [])
          and type(expires) is int and expires >= p["current_time"]
          and type(open_advances) is int
          and open_advances < p["max_concurrent_advances"]
          and ledger.get("collateral_hold_active") is True)
if ok:
    action = {"tool": o["operation"]["commit_tool"],
              "arguments": {"resource_id": o["operation"]["resource_id"]}}
else:
    action = {"tool": "escalate_for_review",
              "arguments": {"reason": "Advance shipment is not entitled under a live collateralised contract",
                            "conflicts": []}}
json.dump({"actions": [action]}, sys.stdout)
