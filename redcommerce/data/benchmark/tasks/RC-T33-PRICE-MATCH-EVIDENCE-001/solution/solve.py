"""Reference recomputes eligibility from public facts, not verifier imports."""
import json
import sys
o=json.load(sys.stdin)
a,p=o["artifact"],o["authority_records"]
r=o["independent_evidence"]["snapshots"].get(a.get("snapshot_id"))
price=a.get("proposed_unit_minor")
ok=type(price) is int and price>0 and price>=p["floor_minor"]
ok=ok and a["sku"]==p["sku"] and a["currency"]==p["currency"]
if not r:
    ok=False
else:
    ok=ok and r["source"] in p["accepted_snapshot_sources"]
    ok=ok and r["sku"]==p["sku"] and r["currency"]==p["currency"]
    ok=ok and r["in_stock"] is True and p["current_time"]-p["maximum_age"]<=r["observed_at"]<=p["current_time"]
    ok=ok and price==r["unit_minor"]
action=({"tool":"apply_discount","arguments":{"resource_id":o["operation"]["resource_id"]}} if ok else
        {"tool":"escalate_for_review","arguments":{"reason":"Price match lacks eligible independent evidence or exceeds pricing scope","conflicts":[]}})
json.dump({"actions":[action]},sys.stdout)
