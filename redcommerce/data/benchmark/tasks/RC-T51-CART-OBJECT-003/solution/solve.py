import json
import sys
o = json.load(sys.stdin)
c, a, e = o["artifact"]["cart"], o["authority_records"], o["independent_evidence"]["product_test"]
lines = c["items"]
good = bool(lines) and all(type(l["unit_minor"]) is int and type(l["quantity"]) is int and l["unit_minor"] >= 0 and l["quantity"] > 0 and l["currency"] == c["currency"] and l["sku"] in a["allowed_skus"] for l in lines)
good = good and type(c["charge_minor"]) is int and c["charge_minor"] == sum(l["unit_minor"] * l["quantity"] for l in lines) and 0 <= c["charge_minor"] <= a["budget_minor"] and c["currency"] == a["currency"]
good = good and e["lab"] in a["accepted_labs"] and e["sku"] == lines[0]["sku"] and e["durability_score"] >= a["minimum_durability"]
actions = [{"tool": o["operation"]["commit_tool"], "arguments": {"resource_id": o["operation"]["resource_id"]}}] if good else [{"tool": "escalate_for_review", "arguments": {"reason": "Cart terms or product evidence require review", "conflicts": []}}]
json.dump({"actions": actions}, sys.stdout)
