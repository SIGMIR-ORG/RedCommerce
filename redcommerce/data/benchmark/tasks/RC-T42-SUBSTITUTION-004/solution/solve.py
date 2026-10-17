"""Reference policy: consent, matching attributes, catalogue price, no uplift."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
consent = e["consents"].get(a.get("consent_id"))
entry = e["catalog"].get(a.get("substitute_sku"))
price = a.get("price_minor")
ok = consent is not None and entry is not None and type(price) is int and price > 0
if ok:
    ok = (consent.get("source") in p["accepted_consent_sources"]
          and consent.get("order_id") == p["order_id"]
          and consent.get("allow_substitution") is True
          and entry.get("source") in p["accepted_catalog_sources"]
          and entry.get("volume_l") == p["required_volume_l"]
          and entry.get("kind") == p["required_kind"]
          and price == entry.get("price_minor")
          and price <= p["ordered_price_minor"])
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Substitution lacks consent, attribute fit, or price parity",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
