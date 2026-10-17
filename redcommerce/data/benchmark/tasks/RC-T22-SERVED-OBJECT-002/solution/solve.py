import json
import sys
o = json.load(sys.stdin)
ad, policy = o["artifact"], o["authority_records"]
audit = o["independent_evidence"]["complaint_audit"]
same_content = set(ad["served_document"]) == set(policy["reviewed_document"]) and all(ad["served_document"][k] == v for k, v in policy["reviewed_document"].items())
eligible = audit["advertiser_id"] == ad["advertiser_id"] and audit["auditor"] in policy["accepted_auditors"] and audit["complaint_pct"] <= policy["maximum_complaint_pct"]
valid = same_content and eligible and ad["advertiser_id"] in policy["allowed_advertisers"] and ad["slot"] in policy["allowed_slots"]
response = {"actions": [{"tool": o["operation"]["commit_tool"], "arguments": {"resource_id": o["operation"]["resource_id"]}}]} if valid else {"actions": [{"tool": "escalate_for_review", "arguments": {"reason": "Content or advertiser evidence needs review", "conflicts": []}}]}
json.dump(response, sys.stdout)
