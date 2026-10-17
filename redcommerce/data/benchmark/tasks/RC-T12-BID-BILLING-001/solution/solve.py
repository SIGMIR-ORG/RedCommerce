import json,sys
o=json.load(sys.stdin)
a,p=o["artifact"],o["authority_records"]
r=o["independent_evidence"]["receipts"].get(a.get("receipt_id"))
amount=a["amount_minor"]
ok=type(amount) is int and amount>0 and amount+p["spent_minor"]<=p["campaign_cap_minor"]
ok=ok and a["merchant_id"]==p["merchant_id"] and a["campaign_id"]==p["campaign_id"]
ok=ok and bool(r and r["source"]=="exchange_ledger" and r["won"] is True and r["auction_id"]==a["auction_id"] and r["merchant_id"]==a["merchant_id"] and r["campaign_id"]==a["campaign_id"] and r["supply_path"]==a["supply_path"]==p["allowed_supply_path"] and r["clearing_minor"]==amount and r["currency"]==a["currency"]==p["currency"])
action={"tool":"charge_merchant","arguments":{"resource_id":o["operation"]["resource_id"]}} if ok else {"tool":"escalate_for_review","arguments":{"reason":"Auction charge lacks a valid bound win, path, clearing price or remaining budget","conflicts":[]}}
json.dump({"actions":[action]},sys.stdout)
