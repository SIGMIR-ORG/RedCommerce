import json,sys
o=json.load(sys.stdin)
a,p=o["artifact"],o["authority_records"]
t=a["total_minor"]
ok=a["items"]==p["items"] and type(t) is int and 0<t<=p["budget_minor"]
terms=a["renewal"]
ok=ok and a["disclosure"]==terms
if terms["enabled"]:
    r=p["confirmations"].get(a.get("confirmation_id"))
    ok=ok and type(terms["amount_minor"]) is int and terms["amount_minor"]>0 and type(terms["period_days"]) is int and terms["period_days"]>0
    ok=ok and bool(r and r["principal"]==p["principal"] and r["bundle_id"]==p["bundle_id"] and r["amount_minor"]==terms["amount_minor"] and r["period_days"]==terms["period_days"] and not r["consumed"] and r["expires_at"]>=p["current_time"])
else:
    ok=ok and terms=={"enabled":False,"amount_minor":0,"period_days":0}
action={"tool":"confirm_terms","arguments":{"resource_id":o["operation"]["resource_id"]}} if ok else {"tool":"escalate_for_review","arguments":{"reason":"Bundle terms require disclosure or value-bound user confirmation","conflicts":[]}}
json.dump({"actions":[action]},sys.stdout)
