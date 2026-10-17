"""Ad-specific canonicalization: hash fetched content, never trust a digest label."""
import copy
import hashlib
import json
from redcommerce_v3.binding_driver import execute_actions

def content_digest(document):
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

def canonical_object_view(world):
    reviewed = world["authority_records"]["reviewed_document"]
    served = world["artifact"]["served_document"]
    before, after = content_digest(reviewed), content_digest(served)
    return {"reviewed_digest": before, "served_digest": after,
            "changed_fields": sorted(k for k in set(reviewed) | set(served) if reviewed.get(k) != served.get(k)),
            "object_consistent": before == after,
            "not_evaluated": ["advertiser_evidence", "placement_scope", "approval_authenticity", "freshness"]}

def independent_evidence_view(world):
    audit = world["independent_evidence"]["complaint_audit"]
    bound = audit["advertiser_id"] == world["artifact"]["advertiser_id"] and audit["auditor"] in world["authority_records"]["accepted_auditors"]
    return {"complaint_audit": copy.deepcopy(audit), "evidence_sufficient": bool(bound and audit["complaint_pct"] <= world["authority_records"]["maximum_complaint_pct"]),
            "not_evaluated": ["served_content_identity", "placement_scope", "approval_authenticity", "freshness"]}

def apply_intervention(world, *, intervention, seed):
    del seed
    viewed = copy.deepcopy(world)
    if intervention == "canonical-object-view":
        viewed["canonical_object_view"] = canonical_object_view(world)
    elif intervention == "independent-evidence-only":
        viewed["independent_evidence_view"] = independent_evidence_view(world)
    else:
        raise ValueError(intervention)
    return viewed

def build_observation(world, instruction):
    return {"instruction": instruction, **copy.deepcopy(world)}
