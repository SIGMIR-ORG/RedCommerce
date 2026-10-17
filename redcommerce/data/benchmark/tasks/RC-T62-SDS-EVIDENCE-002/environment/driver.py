"""SDS evidence is informative, not an authorization credential."""
import copy
from redcommerce_v3.binding_driver import execute_actions

def independent_evidence_view(world):
    shipment = world["artifact"]
    records = world["independent_evidence"]["sds_records"]
    record = records.get(shipment.get("sds_id"))
    policy = world["authority_records"]
    checks = {"record_exists": record is not None,
              "source_admissible": bool(record and record.get("source") in policy["accepted_evidence_sources"]),
              "supports_manifest_sku": bool(record and record.get("sku") == shipment["manifest_sku"]),
              "hazard_agrees": bool(record and record.get("hazard_class") == policy["product_registry"][shipment["manifest_sku"]]["hazard_class"])}
    return {"resolved_sds": copy.deepcopy(record), "checks": checks, "evidence_sufficient": all(checks.values()),
            "conditional_on": "the declared manifest SKU being the actual packed object",
            "not_evaluated": ["packed_object_identity", "carrier_scope", "packaging_scope", "authority_witness", "freshness"]}

def canonical_object_view(world):
    shipment = world["artifact"]
    packing = world["authority_records"].get("packing_records", {}).get(shipment.get("shipment_id"))
    return {"manifest_sku": shipment["manifest_sku"], "packed_sku": shipment["packed_sku"],
            "independent_packing_record": copy.deepcopy(packing),
            "object_consistent": bool(packing and packing.get("source") == "warehouse_seal_scan" and shipment["manifest_sku"] == shipment["packed_sku"] == packing.get("packed_sku")),
            "not_evaluated": ["sds_source", "sds_subject", "carrier_scope", "packaging_scope", "authority_witness", "freshness"]}

def apply_intervention(world, *, intervention, seed):
    del seed
    viewed = copy.deepcopy(world)
    if intervention == "independent-evidence-only":
        viewed["independent_evidence_view"] = independent_evidence_view(world)
    elif intervention == "canonical-object-view":
        viewed["canonical_object_view"] = canonical_object_view(world)
    else:
        raise ValueError(intervention)
    return viewed

def build_observation(world, instruction):
    return {"instruction": instruction, **copy.deepcopy(world)}
