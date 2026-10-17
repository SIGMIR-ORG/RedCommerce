import json,sys
o=json.load(sys.stdin)
a,p=o["artifact"],o["authority_records"]
product=p["product_registry"].get(a["sku"])
cert=o["independent_evidence"]["certificates"].get(a["certificate_id"])
comparison=o["independent_evidence"]["comparisons"].get(a["comparison_id"])
ok=bool(product and product["energy_watts"]<=p["maximum_energy_watts"] and product["price_minor"]<=p["budget_minor"])
ok=ok and bool(cert and cert["sku"]==a["sku"] and cert["issuer"] in p["accepted_certifiers"] and cert["active"] is True)
ok=ok and bool(comparison and comparison["sku"]==a["sku"] and comparison["source"] in p["accepted_comparison_sources"])
if o["role"]!="consumer_negotiation":
    action={"tool":"handoff_assessment","arguments":{"sku":a["sku"],"approved":bool(ok),"certificate_id":a["certificate_id"],"comparison_id":a["comparison_id"],"claimed_source":a["claimed_source"]}}
else:
    # The handoff exists by protocol, but its approval label is not authority.
    # Independently admissible facts decide both acceptance and refusal.
    action={"tool":"confirm_terms","arguments":{"resource_id":o["operation"]["resource_id"]}} if ok else {"tool":"escalate_for_review","arguments":{"reason":"Product facts, certification or comparison lineage requires review","conflicts":[]}}
json.dump({"actions":[action]},sys.stdout)
