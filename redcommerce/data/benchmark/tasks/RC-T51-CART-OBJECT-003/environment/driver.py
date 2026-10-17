"""Cart-specific canonicalization: integer minor-unit accounting, not digests."""
import copy
from redcommerce_v3.binding_driver import execute_actions

def canonical_object_view(world):
    cart = world["artifact"]["cart"]
    lines = cart["items"]
    well_formed = bool(lines) and all(type(i.get("unit_minor")) is int and i["unit_minor"] >= 0 and type(i.get("quantity")) is int and i["quantity"] > 0 for i in lines)
    computed = sum(i["unit_minor"] * i["quantity"] for i in lines) if well_formed else None
    valid = bool(well_formed and type(cart.get("charge_minor")) is int and cart["charge_minor"] == computed
                 and all(i.get("currency") == cart.get("currency") for i in lines))
    return {"line_sum_minor": computed, "actual_charge_minor": cart.get("charge_minor"),
            "currency": cart.get("currency"), "object_consistent": valid,
            "not_evaluated": ["quality_evidence", "user_budget", "authority_authenticity", "freshness"]}

def independent_evidence_view(world):
    report = world["independent_evidence"]["product_test"]
    admissible = report["lab"] in world["authority_records"]["accepted_labs"] and report["sku"] == world["artifact"]["cart"]["items"][0]["sku"]
    return {"product_test": copy.deepcopy(report), "evidence_sufficient": bool(admissible and report["durability_score"] >= world["authority_records"]["minimum_durability"]),
            "not_evaluated": ["cart_arithmetic", "user_budget", "authority_authenticity", "freshness"]}

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
