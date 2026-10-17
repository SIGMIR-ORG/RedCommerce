import json,sys
o=json.load(sys.stdin)
a,p=o["artifact"],o["authority_records"]
link=o["independent_evidence"]["links"].get(a.get("match_key"))
consent=p["consents"].get(a["member_id"])
ok=a["campaign_id"]==p["campaign_id"] and a["segment_id"] in p["allowed_segments"]
ok=ok and bool(consent and consent["active"] is True and a["campaign_id"] in consent["campaigns"])
ok=ok and bool(link and link["member_id"]==a["member_id"] and link["campaign_id"]==a["campaign_id"] and link["segment_id"]==a["segment_id"] and type(link["confidence"]) in (int,float) and p["minimum_confidence"]<=link["confidence"]<=1)
action={"tool":"allocate_impression","arguments":{"resource_id":o["operation"]["resource_id"]}} if ok else {"tool":"escalate_for_review","arguments":{"reason":"Audience identity, consent or campaign eligibility is unproven","conflicts":[]}}
json.dump({"actions":[action]},sys.stdout)
