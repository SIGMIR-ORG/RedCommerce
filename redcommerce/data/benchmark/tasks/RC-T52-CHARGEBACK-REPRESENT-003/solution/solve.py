"""Reference policy: file only on an in-window exhibit of the required class."""
import json
import sys

o = json.load(sys.stdin)
a, p, e = o["artifact"], o["authority_records"], o["independent_evidence"]
exhibit = e["evidence_records"].get(a.get("evidence_id"))
amount = a.get("claimed_amount_minor")
eligible = exhibit is not None
if eligible:
    issued = exhibit.get("issued_at")
    eligible = (exhibit.get("source") in p["accepted_evidence_sources"]
                and exhibit.get("dispute_id") == p["dispute_id"]
                and exhibit.get("evidence_class") == p["required_evidence_class"]
                and type(issued) is int
                and p["window_opened_at"] <= issued <= p["deadline_at"])
eligible = eligible and type(amount) is int and 0 < amount <= p["disputed_amount_minor"]
eligible = eligible and a.get("currency") == p["currency"]
if eligible:
    action = {"tool": o["operation"]["commit_tool"],
              "arguments": {"resource_id": o["operation"]["resource_id"]}}
else:
    action = {"tool": "escalate_for_review",
              "arguments": {"reason": "Representment is not supported by admissible in-window evidence",
                            "conflicts": []}}
json.dump({"actions": [action]}, sys.stdout)
