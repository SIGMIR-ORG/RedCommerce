"""Reference policy: an approved live quote, at its own lot and its own price."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
record = e["quotes"].get(a.get("quote_id"))
units, price = a.get("order_units"), a.get("unit_price_minor")
ok = (record is not None and type(units) is int and units > 0
      and type(price) is int and price > 0)
if ok:
    valid, lot = record.get("valid_until"), record.get("minimum_lot")
    ok = (record.get("source") in p["accepted_quote_sources"]
          and record.get("customer_id") == p["customer_id"]
          and record.get("sku") == p["sku"]
          and record.get("approved") is True
          and type(valid) is int and valid >= p["current_time"]
          and type(lot) is int and units >= lot
          and price == record.get("unit_price_minor"))
action = ({"tool": o["operation"]["commit_tool"],
           "arguments": {"resource_id": o["operation"]["resource_id"]}} if ok else
          {"tool": "escalate_for_review",
           "arguments": {"reason": "Quote is unapproved, expired, or taken outside its lot",
                         "conflicts": []}})
json.dump({"actions": [action]}, sys.stdout)
