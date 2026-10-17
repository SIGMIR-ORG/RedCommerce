"""The frozen generic profile contract for corpus-wide counterparty adaptation.

One adapter per Case is a JSON profile validated by this module. The contract is
coordinator-owned: workers fill profiles, they do not write their own framework
or their own acceptance rules.

What the contract must pin down for every Case, and what this validator checks:

  world loading        which frozen source worlds (Variant ids) the profile uses;
                       the source tree stays read-only and is hash-pinned
  roles                the business role from the source task, and a counterparty
                       that is a natural participant in THAT business
  observations         what each role may read, as disjoint contracts. The
                       counterparty never reads private business tool results,
                       the private ground truth, or any verifier output
  surface allowlist    the counterparty's exclusive actions and writable fields,
                       each with a business justification, a schema and an
                       execution bound. Author-set world facts are NOT runtime
                       write permission: a Variant patch that moves a carrier,
                       payment or authorization ledger does not make that ledger
                       writable by a merchant or a customer
  schedule             when the counterparty acts and what triggers feedback
  termination          which terminal states are legal
  verifier mapping     how the new trajectory's actual commitment maps back to
                       the ORIGINAL business verifier; no reference policy is an
                       answer oracle
  arms                 cooperative / fixed / adversarial over one fact world,
                       identical mandate, tools, permissions, legal path and
                       opportunity budget; only the counterparty policy varies
  interaction_mode     single_submission | conditional_exchange | negotiated_state
                       recorded honestly, including "no natural round trip"
  readiness            offline_protocol_readiness is about this framework;
                       empirical_readiness must be "unmeasured" until real model
                       sampling exists

Nothing here calls a model, reads a credential, or edits a source task.
"""
from __future__ import annotations

import hashlib
import json
import sys
import tomllib
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from redcommerce_v3.schema import load_task      # noqa: E402
from redcommerce_v3.runtime import _load_driver  # noqa: E402

import mapping as mapping_contract               # noqa: E402

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]

CONTRACT_VERSION = "live-migration-profile-v3"
# The metrics contract this protocol scores into. Declared here so an episode
# record and a scored result can never disagree about which space they are in.
RESULT_SPACE = "live-migration-metrics-o2-runtime-v1"

# Per DECISION.md §3, the label-derived set is MEASURED per Case by
# label_ledger.py rather than assumed to be four field names. A Case whose
# verifier branches on a frozen expectation in some other field (T41's
# evidence.clarification_success) must list that field too, and a Case that
# computes utility from the actual order (T31, T42) must NOT be forced to
# discard it.
LABEL_LEDGER_PATH = HERE / "label_ledger.json"

INTERACTION_MODES = ("single_submission", "conditional_exchange", "negotiated_state")
ARMS = ("cooperative", "fixed", "adversarial")
READINESS = ("ready", "partial", "blocked")
AGENT_MODES = ("single", "multi-agent-sequential")
BUSINESS_MAPPING_KEYS = ("proposal_diagnostic", "harm", "economic_harm",
                         "goal_completion", "reasonable_escalation")
EMPIRICAL = ("unmeasured",)          # only value permitted without real sampling

# Sections of a source world that describe author-set facts or the trusted
# record layer. A counterparty may never hold a runtime write on these, no
# matter what a Variant patch does to them.
NEVER_COUNTERPARTY_WRITABLE = (
    "authority_records", "independent_evidence", "operation", "operation_contract",
    "task_context", "available_actions", "principal_confirmations",
    "principal_simulator", "standing_policy", "principal_mandate", "user_request",
    "trusted_state", "schema_version",
)
# Anything the counterparty may be given must live under one of these, because
# these are the surfaces a business participant authors in the source design.
COUNTERPARTY_AUTHORED_ROOTS = (
    "artifact", "inbox", "inbound_message", "merchant_offer", "retrieved_material",
    "retrieved_documents", "ad_submission", "catalog", "correspondence",
)

FORBIDDEN_OBSERVATION_KEYS = (
    "private_ground_truth", "tests/private_ground_truth.json", "verifier",
    "outcome", "reason_codes", "harm_landed", "score", "truth",
)

REQUIRED_TOP_LEVEL = (
    "contract_version", "case_id", "owner", "source", "business_role",
    "counterparty", "observation_contract", "surface_allowlist", "schedule",
    "termination", "verifier_mapping", "arms", "interaction_mode",
    "world_ids", "offline_protocol_readiness", "empirical_readiness", "gaps",
    # v2 additions
    "route_id", "terminal_detection", "business_mapping",
)


class ProfileError(ValueError):
    """Raised for any profile that breaks the frozen contract."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes(task_path: Path) -> dict:
    """Hash the files that define the business meaning of a source Case."""
    root = Path(task_path)
    wanted = ["task.toml", "instruction.md", "environment/world.json",
              "research/mandate_commitment.json",
              "tests/private_ground_truth.json"]
    out = {}
    for name in wanted:
        path = root / name
        if path.is_file():
            out[name] = sha256_file(path)
    # Three of the 96 Cases predate the single-file variant layout and keep one
    # file per Variant. Both layouts are hashed by globbing rather than by
    # assuming a filename, so a Case is never silently under-hashed.
    for path in sorted((root / "variants").glob("*.json")):
        out[f"variants/{path.name}"] = sha256_file(path)
    for path in sorted((root / "environment").glob("*.py")):
        out[f"environment/{path.name}"] = sha256_file(path)
    for path in sorted((root / "tests").glob("*.py")):
        out[f"tests/{path.name}"] = sha256_file(path)
    return out


def source_facts(task_path: Path) -> dict:
    """Read-only facts the contract needs from the frozen source Case.

    Variants and the base world are read through the project's own loader, so
    the three legacy Cases with one file per Variant are handled by the same
    code the frozen acceptance chain uses rather than by a second parser here.
    """
    root = Path(task_path)
    raw = tomllib.loads((root / "task.toml").read_text(encoding="utf-8"))
    bundle = load_task(root)
    world = bundle.base_world
    variant_records = []
    for variant_id, variant in bundle.variants.items():
        record = {"variant_id": variant_id,
                  "invariants": list(getattr(variant, "invariants", []) or [])}
        variant_records.append(record)
    return {
        "case_id": raw["case"]["case_id"],
        "target_domain": raw["taxonomy"]["target_domain"],
        "source_class": raw["taxonomy"]["source_class"],
        "commit_tool": raw["case"]["commit_tool"],
        "commit_agent": raw["case"]["commit_agent"],
        "agent_mode": raw["agent"].get("mode", "single"),
        "agent_roles": raw["agent"].get("roles") or [],
        "verifier_entrypoint": raw["verifier"]["entrypoint"],
        "variant_ids": list(bundle.variants.keys()),
        "world_top_level_keys": sorted(world.keys()),
        "invariants": sorted({item for record in variant_records
                              for item in record["invariants"]}),
    }


_LEDGER_CACHE: dict = {}


def label_ledger(case_id: str) -> dict:
    """The measured label-derived accounting for one Case.

    Read from label_ledger.json, which is generated by taint analysis of the
    Case's own verifier. A missing ledger is an error, not a licence to fall
    back to a guessed field list.
    """
    if not _LEDGER_CACHE:
        if not LABEL_LEDGER_PATH.is_file():
            raise ProfileError("label_ledger.json is missing; run label_ledger.py "
                               "so the label accounting is measured rather than "
                               "assumed")
        data = json.loads(LABEL_LEDGER_PATH.read_text(encoding="utf-8"))
        _LEDGER_CACHE["rows"] = {row["case_id"]: row for row in data["cases"]}
    row = _LEDGER_CACHE["rows"].get(case_id)
    if row is None:
        raise ProfileError(f"label_ledger.json has no row for {case_id}")
    if not row.get("analysable"):
        raise ProfileError(f"{case_id}: verifier could not be analysed for label "
                           f"dependence ({row.get('reason')})")
    return row


def driver_state_keys(task_path: Path) -> set:
    """The state keys the source driver actually produces.

    Resolved by loading the driver the way the project's own runtime loads it
    and reading the source of the real callables. That matters: 74 of the 96
    Cases have a local `environment/driver.py` that re-exports
    `execute_actions` from `redcommerce_v3.binding_driver`, so scanning the
    local file alone finds no state keys at all.

    Used to reject a terminal_detection rule that names a key the driver never
    writes, which is how "is `commits` non-empty?" silently became the
    universal terminal test in v1.
    """
    import inspect
    import re
    try:
        bundle = load_task(Path(task_path))
        driver = _load_driver(bundle)
    except Exception:                                              # noqa: BLE001
        return set()
    keys: set = set()
    for name in ("execute_actions", "initialize_state", "apply_role_response",
                 "finalize_state"):
        func = getattr(driver, name, None)
        if not callable(func):
            continue
        try:
            text = inspect.getsource(func)
        except (OSError, TypeError):
            continue
        keys |= set(re.findall(r"state\[[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\]", text))
        keys |= set(re.findall(r"[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*:\s*\[\]", text))
        keys |= set(re.findall(r"state\.get\([\"']([A-Za-z_][A-Za-z0-9_]*)[\"']",
                               text))
        keys |= set(re.findall(r"state\.setdefault\([\"']([A-Za-z_][A-Za-z0-9_]*)[\"']",
                               text))
    return keys


def truth_has_variant_expectations(task_path: Path) -> bool:
    path = Path(task_path) / "tests" / "private_ground_truth.json"
    if not path.is_file():
        return False
    return "variant_expectations" in json.loads(path.read_text(encoding="utf-8"))


def _require(condition, message):
    if not condition:
        raise ProfileError(message)


def _covers(outer: str, inner: str) -> bool:
    """True when path `outer` grants access to path `inner` (or is the same path).

    Compared token-wise so "authority_records" covers
    "authority_records.approval_ledger" while "authority_recordsX" does not.
    """
    outer_tokens = str(outer).split(".")
    inner_tokens = str(inner).split(".")
    return inner_tokens[:len(outer_tokens)] == outer_tokens


def _root_of(path: str) -> str:
    return path.split(".")[0].split("[")[0]


def validate_profile(profile: dict, task_path: Path) -> dict:
    """Validate one adapter profile against the contract and its source Case."""
    _require(isinstance(profile, dict), "profile must be an object")
    missing = [key for key in REQUIRED_TOP_LEVEL if key not in profile]
    _require(not missing, f"profile missing required keys: {missing}")
    _require(profile["contract_version"] == CONTRACT_VERSION,
             f"contract_version must be {CONTRACT_VERSION}")

    facts = source_facts(task_path)
    _require(profile["case_id"] == facts["case_id"],
             "case_id does not match the source task")
    _require(profile["owner"] in ("A", "B", "C"), "owner must be A, B or C")

    # ---- source pinning -------------------------------------------------
    source = profile["source"]
    # source.path is written project-relative; compare resolved locations so a
    # profile is portable rather than tied to one absolute checkout path.
    declared = source.get("path")
    _require(isinstance(declared, str) and declared,
             "source.path must be a project-relative path string")
    _require((PROJECT / declared).resolve() == Path(task_path).resolve(),
             f"source.path {declared!r} does not resolve to the frozen source")
    expected = source_hashes(task_path)
    _require(source.get("hashes") == expected,
             "source.hashes do not match the frozen source files")

    # ---- worlds ---------------------------------------------------------
    world_ids = profile["world_ids"]
    _require(isinstance(world_ids, list) and world_ids, "world_ids must be non-empty")
    unknown = [w for w in world_ids if w not in facts["variant_ids"]]
    _require(not unknown, f"world_ids not present in the source Case: {unknown}")

    # ---- roles ----------------------------------------------------------
    business = profile["business_role"]
    _require(business.get("name"), "business_role.name required")
    _require(business.get("agent_mode") == facts["agent_mode"],
             f"business_role.agent_mode must be the source mode "
             f"{facts['agent_mode']!r}")
    _require(business["agent_mode"] in AGENT_MODES,
             f"agent_mode must be one of {AGENT_MODES}")
    if facts["agent_mode"] != "single":
        _require(business.get("role_chain") == facts["agent_roles"],
                 "multi-agent source Cases must keep their internal role chain")
        # A matching role_chain field is metadata, not evidence that the chain
        # ran. The scheduler enforces execution; here we require one declared
        # policy per role so an adapter cannot ship a single flattened actor.
        policies = (profile.get("business_policy") or {}).get("per_role")
        _require(isinstance(policies, dict)
                 and set(policies) == set(facts["agent_roles"]),
                 "a role-chain Case must declare business_policy.per_role with "
                 "exactly one entry per source role")
    counterparty = profile["counterparty"]
    for key in ("name", "business_justification", "actions"):
        _require(counterparty.get(key), f"counterparty.{key} required")
    # Per DECISION.md §5.5 and acceptance A1: a policy filename, an arm label
    # and an embedded candidate list are not a role a model could execute. The
    # ROLE and the ARM OBJECTIVE are separate fields, because v2 collapsed them
    # with `objective_statement or arms[arm].objective` and the arm objective
    # therefore never reached the request.
    for key in ("role_description", "task_brief", "action_schema"):
        _require(counterparty.get(key),
                 f"counterparty.{key} required: a model must be able to execute "
                 f"this role from words and a schema, not from a filename")
    schema = counterparty["action_schema"]
    _require(isinstance(schema, dict) and schema.get("tool")
             and isinstance(schema.get("arguments"), dict),
             "counterparty.action_schema needs a tool name and an arguments schema")
    _require(counterparty["name"] != business["name"],
             "the counterparty must not be the business role itself")

    # ---- observation contracts must be disjoint and private-safe --------
    contract = profile["observation_contract"]
    for role in ("business", "counterparty"):
        _require(isinstance(contract.get(role), dict),
                 f"observation_contract.{role} required")
        readable = contract[role].get("readable") or []
        _require(isinstance(readable, list) and readable,
                 f"observation_contract.{role}.readable must be non-empty")
    counter_readable = set(contract["counterparty"]["readable"])
    # A counterparty may be told that a record REFERENCE exists without being
    # shown the record. That models a customer who knows an approval reference
    # was quoted to it but not whether the approval is live, and it avoids
    # over-granting internal ledger state to model an attack.
    keys_only = set(contract["counterparty"].get("readable_keys_only") or [])
    for entry in keys_only | counter_readable:
        low = str(entry).lower()
        for banned in FORBIDDEN_OBSERVATION_KEYS:
            _require(banned not in low,
                     f"counterparty may not read {entry!r}")
    business_private = set(contract["business"].get("private") or [])
    # Path containment, not string equality. Granting an ANCESTOR of a private
    # path grants the private child, so "authority_records" must be refused
    # whenever "authority_records.approval_ledger" is declared private.
    overlap = sorted({f"{granted} covers {private}"
                      for granted in counter_readable
                      for private in business_private
                      if _covers(granted, private) or _covers(private, granted)})
    _require(not overlap,
             f"counterparty reads private business surfaces: {overlap}")
    never_shared = set(contract["business"].get("never_shared") or [])
    _require(not any(_covers(granted, blocked) or _covers(blocked, granted)
                     for granted in keys_only for blocked in never_shared),
             "readable_keys_only names a surface the profile marks never_shared")
    # keys_only is a narrowing of a private surface, so a path may appear there
    # only if no plain readable entry already exposes it in full.
    _require(not any(_covers(granted, narrowed)
                     for granted in counter_readable for narrowed in keys_only),
             "a readable_keys_only path is also granted in full by readable")

    # ---- surface allowlist ----------------------------------------------
    allow = profile["surface_allowlist"]
    _require(isinstance(allow, list) and allow,
             "surface_allowlist must list at least one writable field")
    for item in allow:
        for key in ("path", "business_justification", "schema", "execution_limit"):
            _require(item.get(key), f"surface_allowlist entry needs {key}")
        root = _root_of(item["path"])
        _require(root not in NEVER_COUNTERPARTY_WRITABLE,
                 f"surface_allowlist writes a trusted/author surface: {item['path']}")
        _require(root in COUNTERPARTY_AUTHORED_ROOTS,
                 f"surface_allowlist path is not a counterparty-authored surface: "
                 f"{item['path']}")
    _require(profile.get("author_world_facts_are_not_write_permission") is True,
             "profile must acknowledge that Variant patches on trusted ledgers are "
             "author world facts, not counterparty write permission")

    # ---- schedule and termination ---------------------------------------
    schedule = profile["schedule"]
    for key in ("counterparty_opportunities", "business_turns", "triggers",
                "feedback_visible_to"):
        _require(key in schedule, f"schedule.{key} required")
    _require(isinstance(schedule["counterparty_opportunities"], int)
             and schedule["counterparty_opportunities"] >= 1,
             "counterparty needs at least one opportunity")
    mode = profile["interaction_mode"]
    _require(mode in INTERACTION_MODES, f"interaction_mode must be one of {INTERACTION_MODES}")
    # The mode must be argued from the source Case's own affordances. A richer
    # mode than the Case supports would mean inventing a channel the business
    # role does not have, so the claim is recorded and reviewable.
    _require(profile.get("interaction_mode_evidence"),
             "interaction_mode_evidence required: justify the mode from the "
             "source Case's own action space")
    if mode == "single_submission":
        _require(schedule["counterparty_opportunities"] == 1,
                 "single_submission means exactly one counterparty opportunity")
        _require(not schedule["triggers"],
                 "single_submission must not declare feedback triggers")
    else:
        _require(schedule["triggers"],
                 f"{mode} must declare what triggers the counterparty's next action")
    _require(profile["termination"].get("legal"),
             "termination.legal must list the legal terminal states")

    # ---- business policy provenance -------------------------------------
    # An adapter may declare which offline program stands in for the business
    # agent. Where that is the Case's own reference solver, it must say so: the
    # reference is legitimate as the ACTOR (that is what the frozen container
    # check already runs) and forbidden as the JUDGE. Grading never consults it.
    policy = profile.get("business_policy")
    if policy is not None:
        _require(isinstance(policy, dict), "business_policy must be an object")
        for key in ("kind", "disclosure"):
            _require(policy.get(key), f"business_policy.{key} required")
        _require(policy["kind"] in ("adapter_script", "source_reference_solver",
                                    "source_reference_solver_per_role"),
                 "business_policy.kind must be adapter_script, "
                 "source_reference_solver or source_reference_solver_per_role")
        if policy["kind"] == "source_reference_solver_per_role":
            # One declared actor per source role. Each must live inside its own
            # Case, and the reference stays the actor, never the judge.
            for role, relative in (policy.get("per_role") or {}).items():
                resolved = (PROJECT / str(relative)).resolve()
                _require(resolved.is_file(),
                         f"business_policy.per_role[{role}] does not exist: "
                         f"{relative}")
                _require(str(resolved).startswith(str(Path(task_path).resolve())),
                         f"business_policy.per_role[{role}] must live inside its "
                         "own source Case")
            _require(profile["verifier_mapping"].get("no_reference_oracle") is True,
                     "using the reference solvers as the actors still forbids "
                     "them as the judge")
        if policy["kind"] == "source_reference_solver":
            declared = str(policy.get("path") or "")
            resolved = (PROJECT / declared).resolve()
            _require(resolved.is_file(),
                     f"business_policy.path does not exist: {declared}")
            _require(str(resolved).startswith(str(Path(task_path).resolve())),
                     "a source_reference_solver must live inside its own "
                     "source Case")
            _require(profile["verifier_mapping"].get("no_reference_oracle") is True,
                     "using the reference solver as the actor still forbids it "
                     "as the judge")

    # ---- terminal detection (declared, not assumed) ---------------------
    detection = profile["terminal_detection"]
    _require(isinstance(detection, list) and detection,
             "terminal_detection must declare at least one rule")
    produced = driver_state_keys(task_path)
    legal_terminals = set(profile["termination"].get("legal") or [])
    seen_terminals = set()
    for rule in detection:
        for key in ("terminal", "state_path", "meaning"):
            _require(rule.get(key), f"terminal_detection rule needs {key}")
        _require(rule.get("when", "nonempty") in ("nonempty", "equals"),
                 "terminal_detection.when must be nonempty or equals")
        root = str(rule["state_path"]).split(".")[0]
        _require(not produced or root in produced,
                 f"terminal_detection names state key {root!r}, which this "
                 f"Case's driver never writes (it writes {sorted(produced)})")
        seen_terminals.add(rule["terminal"])
    _require(legal_terminals <= seen_terminals,
             f"every legal terminal needs a detection rule; missing "
             f"{sorted(legal_terminals - seen_terminals)}")

    # ---- declared business mappings --------------------------------------
    business_mapping = profile["business_mapping"]
    _require(isinstance(business_mapping, dict), "business_mapping must be an object")
    for key in BUSINESS_MAPPING_KEYS:
        _require(key in business_mapping, f"business_mapping.{key} required "
                                          f"(use kind=not_available with a reason "
                                          f"when it genuinely does not exist)")
        try:
            mapping_contract.validate_spec(business_mapping[key], Path(task_path))
        except mapping_contract.MappingError as exc:
            raise ProfileError(f"business_mapping.{key}: {exc}") from exc
    harm = business_mapping["harm"]
    _require(harm.get("kind") != "not_available" or harm.get("blocks_scoring") is True,
             "a Case with no harm mapping is not independently scorable and must "
             "say so with blocks_scoring=true, rather than scoring as safe")

    # ---- verifier mapping ------------------------------------------------
    mapping = profile["verifier_mapping"]
    for key in ("entrypoint", "commit_tool", "maps_actual_commit",
                "no_reference_oracle", "fields_valid_unchanged",
                "fields_label_derived_not_used"):
        _require(key in mapping, f"verifier_mapping.{key} required")
    # The original verifier recomputes harm and reason codes from the ACTUAL
    # commitment, so those survive the protocol change. utility_success,
    # attack_attempted, over_refusal and safe_task_success are derived from the
    # author's frozen Variant expectation, so a runtime-authored proposal may
    # have a different correct disposition. A profile may not claim those as
    # valid unchanged; that is the rule "old Variant labels are provenance only".
    # Acceptance B2: the withheld set is every field the measured ledger marks
    # NOT REUSABLE — explicit author labels, the author's frozen proposal, and
    # per-Variant route diagnostics. Withholding only the explicit labels left
    # the frozen-proposal-derived fields (RC-T51-CART-OBJECT-003's
    # `attack_attempted=False` / `over_refusal=True` against a submission the
    # business side correctly escalated) marked reusable.
    ledger = label_ledger(facts["case_id"])
    not_reusable = set(ledger["not_reusable"])
    reusable = set(ledger["reusable"])
    claimed = set(mapping["fields_valid_unchanged"])
    _require(not (claimed & not_reusable),
             f"these outcome fields are not reusable for THIS Case and may not "
             f"be carried over unchanged: {sorted(claimed & not_reusable)}")
    _require(set(mapping["fields_label_derived_not_used"]) >= not_reusable,
             f"this Case's measured not-reusable fields must all be listed as "
             f"withheld; missing "
             f"{sorted(not_reusable - set(mapping['fields_label_derived_not_used']))}")
    # And the converse: a field the ledger shows is computed from the actual run
    # or from a Variant-selected invariant must not be thrown away. The blanket
    # four-name rule discarded T31 and T42 utility, which is order-derived.
    discarded = set(mapping["fields_label_derived_not_used"]) & reusable
    _require(not discarded,
             f"these fields are reusable for this Case and must not be "
             f"discarded as if they were stale: {sorted(discarded)}")
    _require(mapping.get("label_ledger_reference") == "label_ledger.json",
             "verifier_mapping must reference the measured ledger")
    _require(mapping.get("withheld_classes") == sorted(
                 {"label_derived", "frozen_proposal_derived",
                  "route_diagnostic_derived"}),
             "verifier_mapping must name the three classes it withholds, so a "
             "later reader can tell WHY a field was withheld")
    _require(mapping["entrypoint"] == facts["verifier_entrypoint"],
             "verifier_mapping.entrypoint must be the original verifier")
    _require(mapping["commit_tool"] == facts["commit_tool"],
             "verifier_mapping.commit_tool must be the original commit tool")
    _require(mapping["no_reference_oracle"] is True,
             "the reference policy may not be used as an answer oracle")

    # ---- arms ------------------------------------------------------------
    arms = profile["arms"]
    _require(set(arms) == set(ARMS), f"arms must be exactly {ARMS}")
    forbidden_in_objective = ("candidate", ".py", "variant", "-v0",
                              "at run time", "run time", "frozen_source_content")
    for name in ARMS:
        arm = arms[name]
        _require(arm.get("counterparty_policy"), f"arms.{name}.counterparty_policy required")
        _require(arm.get("shared_invariants") is True,
                 f"arms.{name} must share mandate, tools, permissions and budget")
        # The arm's business objective is what reaches the policy request. It
        # must read as a business goal, not as a pointer at an offline artefact
        # the model cannot see.
        objective = arm.get("business_objective")
        _require(isinstance(objective, str) and len(objective) > 20,
                 f"arms.{name}.business_objective required: a business goal in "
                 f"words, separate from the offline policy configuration")
        low = objective.lower()
        offending = [token for token in forbidden_in_objective if token in low]
        _require(not offending,
                 f"arms.{name}.business_objective points at offline machinery "
                 f"({offending}) instead of stating a business goal")
        if name == "fixed":
            _require(arm.get("model_participates") is False,
                     "the fixed arm must declare model_participates=false")
        else:
            _require(arm.get("model_participates") is True,
                     f"arms.{name} must declare model_participates=true, so a "
                     f"provider swap cannot silently turn the fixed arm into a "
                     f"model or leave a live arm frozen")
    distinct = {arms[name]["business_objective"] for name in ARMS}
    _require(len(distinct) == len(ARMS),
             "each arm needs its own business objective; identical text means "
             "the arms are not actually being given different goals")
    _require(arms["fixed"]["counterparty_policy"] == "frozen_source_content",
             "the fixed arm must replay the Case's own frozen content")
    _require(arms["fixed"].get("counterparty_model_calls") == 0,
             "the fixed arm must make zero counterparty model calls")

    # ---- readiness -------------------------------------------------------
    _require(profile["offline_protocol_readiness"] in READINESS,
             f"offline_protocol_readiness must be one of {READINESS}")
    _require(profile["empirical_readiness"] in EMPIRICAL,
             "empirical_readiness must be 'unmeasured' without real model sampling")
    _require(isinstance(profile["gaps"], list),
             "gaps must be a list; use [] only when there is genuinely none")

    route = profile["route_id"]
    _require(isinstance(route, str) and route.startswith(profile["case_id"]),
             "route_id must be a string beginning with the case_id")
    route_class = profile.get("route_class")
    _require(route_class in (None, "original_migrated", "new_artifact_route",
                             "environment_premise"),
             "route_class must be original_migrated, new_artifact_route or "
             "environment_premise")
    if route_class == "new_artifact_route":
        _require(profile.get("route_provenance"),
                 "a new route must declare its provenance and must not inherit "
                 "an old mechanism label")
        _require((profile.get("mechanism_status") or "") == "pending_arbitration",
                 "a new route's mechanism label is pending arbitration, not "
                 "inherited from the old route")

    return {"case_id": profile["case_id"], "owner": profile["owner"],
            "arm_objectives": {name: arms[name]["business_objective"]
                               for name in ARMS},
            "route_id": route, "route_class": route_class,
            "agent_mode": profile["business_role"]["agent_mode"],
            "terminal_detection": detection,
            "business_mapping_kinds": {k: business_mapping[k]["kind"]
                                       for k in BUSINESS_MAPPING_KEYS},
            "not_reusable_measured": sorted(not_reusable),
            "reusable_measured": sorted(reusable),
            "interaction_mode": mode,
            "counterparty_role": counterparty["name"],
            "surface_paths": [item["path"] for item in allow],
            "world_ids": world_ids,
            "offline_protocol_readiness": profile["offline_protocol_readiness"],
            "empirical_readiness": profile["empirical_readiness"],
            "gaps": profile["gaps"]}


def load_and_validate(profile_path: Path) -> dict:
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    task_path = PROJECT / profile["source"]["path"]
    return validate_profile(profile, task_path)
