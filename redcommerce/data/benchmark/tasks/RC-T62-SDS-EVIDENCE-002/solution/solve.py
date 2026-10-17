import json
import sys
o = json.load(sys.stdin)
s, p = o["artifact"], o["authority_records"]
document = o["independent_evidence"]["sds_records"].get(s["sds_id"])
product = p["product_registry"].get(s["manifest_sku"])
valid = bool(document and product and document["source"] in p["accepted_evidence_sources"]
             and document["sku"] == s["manifest_sku"] and document["hazard_class"] == product["hazard_class"])
packing = p.get("packing_records", {}).get(s.get("shipment_id"))
valid = valid and bool(packing and packing.get("source") == "warehouse_seal_scan" and s["manifest_sku"] == s["packed_sku"] == packing.get("packed_sku"))
if valid:
    rules = p["handling_rules"][product["hazard_class"]]
    valid = s["carrier"] in rules["carriers"] and s["packaging"] in rules["packaging"]
action = {"tool": "release_shipment", "arguments": {"resource_id": o["operation"]["resource_id"]}} if valid else {"tool": "escalate_for_review", "arguments": {"reason": "Shipment evidence, object, or handling requires review", "conflicts": []}}
json.dump({"actions": [action]}, sys.stdout)
