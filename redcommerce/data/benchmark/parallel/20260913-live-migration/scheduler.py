"""The shared episode scheduler, v2. Coordinator-owned; one implementation only.

Rewritten against DECISION.md §3. What changed from v1, and why:

  two driver classes   Single-agent Cases use `build_observation` /
                       `execute_actions`. Multi-agent-sequential Cases use
                       `initialize_state` / `build_role_observation` /
                       `apply_role_response` / `finalize_state` and are run as
                       the real role chain with state threaded between roles.
                       v1 only knew the first contract, so the four role-chain
                       Cases could not have run at all.

  no invented state    v1 normalised every driver's state into
                       {commits, escalations, rejected_actions}. That is wrong:
                       T22 returns placements / served_impressions /
                       monitoring_blocks / rejections, T51 returns orders. The
                       episode now carries the driver's OWN state verbatim, and
                       the terminal is found through a per-Case declared mapping
                       over that state instead of assuming `commits`.

  per-decision worlds  v1 wrote the end-of-episode world as
                       `state/initial_world.json`, so a mid-episode decision
                       could be judged against a world it never saw. Every
                       decision now has its own snapshot, the frozen author
                       world is kept separately, and the legacy file is bound to
                       a declared decision index.

Generic on purpose: nothing here knows about SKUs, suppliers, ad placements or
turn counts. All of that comes from the per-Case profile.
"""
from __future__ import annotations

import copy
import hashlib
import inspect
import json
import sys
import time
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(HERE))

from redcommerce_v3.schema import load_task, deep_merge          # noqa: E402
from redcommerce_v3.runtime import _load_driver                   # noqa: E402
import backend                                                    # noqa: E402
import profile as contract                                        # noqa: E402


class ProtocolFailure(Exception):
    """A protocol-level failure. Never scored as an attack or a defence."""


class CounterpartyFailure(ProtocolFailure):
    """The counterparty policy failed at the interface level.

    Raised rather than absorbed: an episode where the counterparty never spoke
    is not an episode where the counterparty behaved benignly, and grading it as
    a clean business success would be the most flattering possible lie.
    """


class DriverContractError(ProtocolFailure):
    """The source driver does not provide what its declared mode requires."""


class DriverStageError(ProtocolFailure):
    """The ORIGINAL driver raised while executing a stage of the episode.

    Carries the stage, the role and whatever state existed, so the episode is
    preserved with its failure point instead of vanishing as an exception.
    """

    def __init__(self, stage: str, role: str, detail: str,
                 state: dict | None = None, events: list | None = None):
        super().__init__(f"{stage}: {detail}")
        self.stage = stage
        self.role = role
        self.detail = detail
        self.state = state or {}
        self.events = events or []


# ---------------------------------------------------------------- utilities
def canonical(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def digest(value) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _tokens(path: str):
    out = []
    for chunk in str(path).split("."):
        while "[" in chunk:
            head, _, rest = chunk.partition("[")
            if head:
                out.append(head)
            index, _, chunk = rest.partition("]")
            out.append(int(index))
        if chunk:
            out.append(chunk)
    return out


def read_path(node, path: str):
    for token in _tokens(path):
        node = node[token]
    return node


def try_read_path(node, path: str, default=None):
    try:
        return read_path(node, path)
    except (KeyError, IndexError, TypeError):
        return default


def write_path(node, path: str, value) -> None:
    tokens = _tokens(path)
    for token in tokens[:-1]:
        node = node[token]
    node[tokens[-1]] = value


def project(world: dict, readable: list, keys_only: list | None = None) -> dict:
    """Build a role observation from declared readable paths only.

    keys_only paths expose the record identifiers at that path and nothing else,
    so a counterparty can name a reference it plausibly knows without being
    handed the record's internal state.
    """
    view = {}
    for path in readable:
        try:
            view[path] = copy.deepcopy(read_path(world, path))
        except (KeyError, IndexError, TypeError):
            view[path] = None
    for path in keys_only or []:
        try:
            node = read_path(world, path)
        except (KeyError, IndexError, TypeError):
            view[path] = {"keys": None}
            continue
        view[path] = {"keys": sorted(node) if isinstance(node, dict) else None,
                      "values_withheld": True}
    return view


def _shape_violation(value, schema: dict) -> str | None:
    """Check a declared nested shape. Returns a refusal reason or None.

    Only what the profile actually declares is enforced: `items` for arrays
    (element type and required keys), `required` / `properties` for objects, and
    `minimum` / `maximum` for numbers. An undeclared shape is not invented here.
    """
    kind = schema.get("type")
    if kind == "array" and isinstance(value, list):
        items = schema.get("items")
        if isinstance(items, dict):
            expected = items.get("type")
            required = items.get("required") or []
            for index, element in enumerate(value):
                actual = {str: "string", int: "integer", float: "number",
                          bool: "boolean", dict: "object",
                          list: "array"}.get(type(element))
                if expected and actual != expected:
                    return (f"schema_items_element_{index}_is_{actual}_not_"
                            f"{expected}")
                if required:
                    if not isinstance(element, dict):
                        return f"schema_items_element_{index}_is_not_an_object"
                    missing = [key for key in required if key not in element]
                    if missing:
                        return (f"schema_items_element_{index}_missing_"
                                + "_".join(missing))
    if kind == "object" and isinstance(value, dict):
        missing = [key for key in (schema.get("required") or [])
                   if key not in value]
        if missing:
            return "schema_object_missing_" + "_".join(missing)
        properties = schema.get("properties") or {}
        for key, declared in properties.items():
            if key in value and declared.get("type"):
                actual = {str: "string", int: "integer", float: "number",
                          bool: "boolean", dict: "object",
                          list: "array"}.get(type(value[key]))
                if actual != declared["type"] and not (
                        declared["type"] == "number" and actual == "integer"):
                    return f"schema_object_{key}_is_{actual}_not_{declared['type']}"
    if kind in ("number", "integer") and isinstance(value, (int, float)) \
            and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            return "schema_below_minimum"
        if "maximum" in schema and value > schema["maximum"]:
            return "schema_above_maximum"
    return None


def validate_counterparty_reply(reply: dict, profile: dict) -> str | None:
    """Check the action envelope against the DECLARED action schema.

    Acceptance A2: v2 read `actions[0]["arguments"]["writes"]` without checking
    the tool name or the action count, so a reply naming a different tool became
    a silent no-op and an extra action was dropped without a trace. Both are now
    contract breaches with a typed reason.
    """
    schema = (profile.get("counterparty") or {}).get("action_schema") or {}
    declared_tool = schema.get("tool")
    actions = reply.get("actions")
    if actions is None:
        return "invalid_action:actions_missing"
    if not isinstance(actions, list):
        return "invalid_action:actions_not_a_list"
    if not actions:
        # A policy may legitimately decline to act. That is a business choice,
        # not a malformed reply, and it stays in the denominator.
        return None
    if len(actions) != 1:
        return f"invalid_action:expected_one_action_got_{len(actions)}"
    action = actions[0]
    if not isinstance(action, dict):
        return "invalid_action:action_not_an_object"
    if declared_tool and action.get("tool") != declared_tool:
        return (f"invalid_action:tool_{action.get('tool')!r}_is_not_the_declared_"
                f"{declared_tool!r}")
    arguments = action.get("arguments")
    if not isinstance(arguments, dict):
        return "invalid_action:arguments_not_an_object"
    writes = arguments.get("writes")
    if writes is None:
        return "invalid_action:writes_missing"
    if not isinstance(writes, list):
        return "invalid_action:writes_not_a_list"
    for index, write in enumerate(writes):
        if not isinstance(write, dict) or set(write) != {"path", "value"}:
            return f"invalid_action:write_{index}_is_not_a_path_value_pair"
    return None


def apply_counterparty_writes(world: dict, writes: list, allowlist: list) -> list:
    """Apply only allowlisted writes; refuse and record anything else."""
    permitted = {item["path"]: item for item in allowlist}
    applied, refused = [], []
    for write in writes or []:
        if not isinstance(write, dict) or set(write) != {"path", "value"}:
            refused.append({"write": write, "reason": "malformed_write_envelope"})
            continue
        path = write["path"]
        rule = permitted.get(path)
        if rule is None:
            refused.append({"path": path, "reason": "path_not_in_surface_allowlist"})
            continue
        value = write["value"]
        expected = rule["schema"].get("type")
        actual = {str: "string", int: "integer", float: "number", bool: "boolean",
                  dict: "object", list: "array"}.get(type(value))
        if value is None and rule["schema"].get("nullable"):
            # The Case's own Variants leave this field empty somewhere, so an
            # empty submission for it is legitimate content, not a breach.
            actual, expected = None, None
        if expected and actual != expected and not (expected == "number"
                                                    and actual == "integer"):
            refused.append({"path": path, "reason": f"schema_type_{actual}_not_{expected}"})
            continue
        limit = rule["execution_limit"]
        encoded = value if isinstance(value, str) else canonical(value)
        if "max_bytes" in limit and len(encoded.encode("utf-8")) > int(limit["max_bytes"]):
            refused.append({"path": path, "reason": "execution_limit_max_bytes"})
            continue
        if "max_items" in limit and isinstance(value, list) \
                and len(value) > int(limit["max_items"]):
            refused.append({"path": path, "reason": "execution_limit_max_items"})
            continue
        if "max_keys" in limit and isinstance(value, dict) \
                and len(value) > int(limit["max_keys"]):
            refused.append({"path": path, "reason": "execution_limit_max_keys"})
            continue
        shape = _shape_violation(value, rule["schema"])
        if shape is not None:
            # Acceptance A2: an outer type check is not enough. T31 declares
            # `inbound_message.parts` as an array, and an array holding a bare
            # string passed v2's check and then made the ORIGINAL driver raise
            # AttributeError inside `_render_parts`. The declared element shape
            # is enforced here, before anything reaches the driver.
            refused.append({"path": path, "reason": shape})
            continue
        try:
            before = copy.deepcopy(read_path(world, path))
        except Exception:
            refused.append({"path": path, "reason": "path_absent_in_source_world"})
            continue
        write_path(world, path, copy.deepcopy(value))
        applied.append({"path": path,
                        "before_sha256": hashlib.sha256(
                            canonical(before).encode()).hexdigest(),
                        "after_sha256": hashlib.sha256(
                            canonical(value).encode()).hexdigest(),
                        "changed": canonical(before) != canonical(value)})
    return applied, refused


def prove_only_allowlist_changed(baseline: dict, world: dict, applied: list,
                                 allowlist: list) -> dict:
    """Restore the applied paths and require the rest of the world to be identical."""
    restored = copy.deepcopy(world)
    for path in {item["path"] for item in applied}:
        write_path(restored, path, read_path(baseline, path))
    ok = canonical(restored) == canonical(baseline)
    return {"only_allowlisted_paths_changed": ok,
            "checked_paths": sorted({item["path"] for item in applied}),
            "allowlist": [item["path"] for item in allowlist]}


def driver_kwargs(func, *, seed: int) -> dict:
    """Supply only the keyword arguments the ORIGINAL driver actually declares.

    The live protocol never applies an intervention: a diagnostic intervention is
    a separate experiment, so it stays "none" here rather than being smuggled in
    through the counterparty.
    """
    try:
        params = inspect.signature(func).parameters
    except (TypeError, ValueError):
        return {}
    supplied = {"intervention": "none", "seed": seed}
    return {name: value for name, value in supplied.items()
            if name in params
            and params[name].kind in (inspect.Parameter.KEYWORD_ONLY,
                                      inspect.Parameter.POSITIONAL_OR_KEYWORD)}


# --------------------------------------------------------- terminal detection
def detect_terminal(state: dict, detection: list) -> dict | None:
    """Per-Case declared mapping from the driver's OWN state to a terminal.

    v1 asked "is `commits` non-empty?", which is meaningless for a Case whose
    driver records `placements` or `orders`. The mapping is declared in the
    profile and checked against the source driver's state keys at validation.
    """
    for rule in detection:
        path = rule["state_path"]
        value = try_read_path(state, path)
        when = rule.get("when", "nonempty")
        hit = bool(value) if when == "nonempty" else (value == rule.get("equals"))
        if hit:
            return {"terminal": rule["terminal"], "state_path": path,
                    "legal": bool(rule.get("legal", True)),
                    "observed_count": len(value) if isinstance(value, (list, dict))
                    else value}
    return None


# --------------------------------------------------------------- the episode
def run_episode(profile: dict, world_id: str, business_policy,
                counterparty_policy, *, arm: str, out_dir: Path,
                business_turns: int | None = None,
                counterparty_opportunities: int | None = None,
                seed: int = 0, route_id: str | None = None) -> dict:
    """One counterparty/business episode over one frozen source world.

    `business_policy` is one callable for a single-agent Case, or a mapping of
    role name to callable for a role-chain Case.
    """
    if arm not in contract.ARMS:
        raise ProtocolFailure(f"unknown arm {arm}")
    task_path = PROJECT / profile["source"]["path"]
    contract.validate_profile(profile, task_path)

    bundle = load_task(task_path)
    if world_id not in bundle.variants:
        raise ProtocolFailure(f"{world_id} is not a world of this source Case")
    driver = _load_driver(bundle)
    mode = profile["business_role"]["agent_mode"]

    schedule = profile["schedule"]
    turns = int(business_turns or schedule["business_turns"])
    chances = int(counterparty_opportunities or schedule["counterparty_opportunities"])
    if profile["interaction_mode"] == "single_submission" and chances != 1:
        raise ProtocolFailure("single_submission permits exactly one opportunity")

    # The business budget is generous because a role chain spends one call per
    # role; the counterparty budget is the one the protocol actually limits.
    #
    # Where a policy owns a persistent cost ledger, that ledger is the single
    # authority and this layer only records receipts. Otherwise the scheduler's
    # zero-dollar default would veto a request the ledger had already authorised
    # and settled, and the cost would be debited twice.
    budgets = {
        "business": backend.RoleBudget(
            "business", max_calls=turns * 8 + 8,
            **_cost_authority_for(business_policy)),
        "counterparty": backend.RoleBudget(
            "counterparty", max_calls=chances,
            **_cost_authority_for(counterparty_policy))}

    source_world = deep_merge(copy.deepcopy(bundle.base_world),
                              copy.deepcopy(bundle.variants[world_id].world_patch))
    world = copy.deepcopy(source_world)
    allowlist = profile["surface_allowlist"]
    detection = profile["terminal_detection"]

    record = {
        "protocol": contract.CONTRACT_VERSION,
        "result_space": contract.RESULT_SPACE,
        "episode_id": "MIG-" + uuid.uuid4().hex[:16],
        "case_id": profile["case_id"],
        "route_id": route_id or profile.get("route_id") or (profile["case_id"] + "-R00"),
        "variant_id": world_id, "world_id": world_id, "arm": arm,
        "interaction_mode": profile["interaction_mode"],
        "agent_mode": mode,
        "source": profile["source"],
        "actors": {"business": _describe(business_policy),
                   "counterparty": _describe(counterparty_policy)},
        "limits": {"business_turns": turns, "counterparty_opportunities": chances,
                   "intervention": "none", "seed": seed},
        "source_world_sha256": digest(source_world),
        "counterparty_exchanges": [], "decisions": [],
        "world_snapshots": [], "surface_proofs": [], "refused_writes": [],
        "terminal": None, "terminal_detail": None, "protocol_failures": [],
        "decisive_decision_index": None,
    }

    def counterparty_act(trigger: dict | None):
        counter = profile["observation_contract"]["counterparty"]
        view = project(world, counter["readable"], counter.get("readable_keys_only"))
        # The role and the ARM OBJECTIVE are separate fields and both travel
        # with the request. v2 wrote `objective_statement or arms[arm].objective`,
        # and since the former was always set, no arm objective ever reached a
        # policy: every arm saw the same generic role text.
        observation = {"role": profile["counterparty"]["name"], "arm": arm,
                       "role_description": profile["counterparty"]["role_description"],
                       "arm_objective": profile["arms"][arm]["business_objective"],
                       "task_brief": profile["counterparty"].get("task_brief"),
                       "action_schema": profile["counterparty"].get("action_schema"),
                       "writable_surface": [
                           {k: v for k, v in item.items()
                            if k != "business_justification"} for item in allowlist],
                       "readable": view, "trigger": trigger}
        reply = backend.invoke(counterparty_policy, observation,
                               budgets["counterparty"],
                               {"world_id": world_id, "arm": arm,
                                "trigger": (trigger or {}).get("kind")})
        adapter = reply.get("_adapter") or {}
        if adapter.get("failure"):
            record["protocol_failures"].append(
                {"role": "counterparty", "trigger": trigger,
                 "failure": adapter["failure"]})
            record["counterparty_exchanges"].append({
                "trigger": trigger, "observation_sha256": digest(observation),
                "raw_response": reply, "extra_actions_dropped": 0,
                "applied": [], "refused": []})
            raise CounterpartyFailure(str(adapter["failure"]))
        envelope = validate_counterparty_reply(reply, profile)
        if envelope is not None:
            record["protocol_failures"].append(
                {"role": "counterparty", "stage": "action_envelope",
                 "trigger": trigger, "failure": envelope,
                 "settled_cost_usd": budgets["counterparty"].cost_usd})
            record["counterparty_exchanges"].append({
                "trigger": trigger, "observation_sha256": digest(observation),
                "raw_response": reply, "extra_actions_dropped": 0,
                "applied": [], "refused": [],
                "envelope_failure": envelope})
            raise CounterpartyFailure(envelope)
        actions = reply.get("actions") or []
        writes = (((actions[0].get("arguments") or {}).get("writes") or [])
                  if actions else [])
        applied, refused = apply_counterparty_writes(world, writes, allowlist)
        proof = prove_only_allowlist_changed(source_world, world, applied, allowlist)
        if not proof["only_allowlisted_paths_changed"]:
            raise ProtocolFailure("counterparty mutated a surface outside the allowlist")
        record["counterparty_exchanges"].append({
            "trigger": trigger, "observation_sha256": digest(observation),
            "raw_response": reply,
            "extra_actions_dropped": max(0, len(actions) - 1),
            "applied": applied, "refused": refused})
        record["surface_proofs"].append(proof)
        record["refused_writes"].extend(refused)

    def snapshot(label: str) -> dict:
        entry = {"index": len(record["world_snapshots"]), "label": label,
                 "sha256": digest(world), "world": copy.deepcopy(world)}
        record["world_snapshots"].append(entry)
        return entry

    terminal = None
    try:
        counterparty_act({"kind": "opening_submission", "before_business_turn": 1})
    except CounterpartyFailure:
        terminal = "protocol_failure"
    except backend.BudgetStop as stop:
        # A budget stop is a protocol failure like any other: the episode, the
        # request references and the receipts are all kept.
        record["protocol_failures"].append(
            {"role": "counterparty", "stage": "budget",
             "failure": f"BudgetStop: {stop}",
             "cost_ledger": budgets["counterparty"].cost_ledger,
             "receipts": budgets["counterparty"].receipts[-1:]})
        terminal = "protocol_failure"

    state: dict = {}
    events: list = []
    context = {"profile": profile, "bundle": bundle, "driver": driver,
               "record": record, "snapshot": snapshot,
               "counterparty_act": counterparty_act, "world": lambda: world,
               "turns": turns, "chances": chances, "budgets": budgets,
               "detection": detection, "seed": seed, "arm": arm,
               "world_id": world_id, "policy": business_policy}

    if terminal is None:
        try:
            if mode == "single":
                terminal, state, events = _run_single(**context)
            elif mode == "multi-agent-sequential":
                terminal, state, events = _run_role_chain(**context)
            else:
                raise DriverContractError(f"unsupported agent mode {mode!r}")
        except DriverStageError as failure:
            # Acceptance A2: a business driver exception must keep the whole
            # episode, the raw reply and the failure stage. It is never a safe
            # success and never a lost run.
            record["protocol_failures"].append(
                {"role": failure.role, "stage": failure.stage,
                 "failure": failure.detail,
                 "settled_cost_usd": budgets["business"].cost_usd})
            terminal = "protocol_failure"
            state, events = failure.state, failure.events
        except backend.BudgetStop as stop:
            # Review P2: every budget-stop path keeps the episode and its
            # request references. A lost episode is not evidence that no request
            # was made.
            record["protocol_failures"].append(
                {"role": "business", "stage": "budget",
                 "failure": f"BudgetStop: {stop}",
                 "cost_ledger": budgets["business"].cost_ledger,
                 "receipts": [receipt for budget in budgets.values()
                              for receipt in budget.receipts[-1:]]})
            terminal = "protocol_failure"
            state, events = {}, []

    record["terminal"] = terminal
    record["final_state"] = state
    record["events"] = events
    record["final_world_sha256"] = digest(world)
    record["budgets"] = {name: b.summary() for name, b in budgets.items()}
    record["receipts"] = {name: b.receipts for name, b in budgets.items()}
    record["legal_terminal"] = terminal in profile["termination"]["legal"]

    run_dir = Path(out_dir)
    _write_run_directory(run_dir, bundle, world_id, record, state, events,
                         source_world, arm, seed)
    record["run_dir"] = run_dir.as_posix()
    with (run_dir / "episode.json").open("x", encoding="utf-8") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=1, allow_nan=False)
        stream.write("\n")
    return record


def _cost_authority_for(policy) -> dict:
    """Who may debit for this role: the policy's own ledger, or this layer."""
    policies = policy.values() if isinstance(policy, dict) else [policy]
    owners = [item for item in policies
              if getattr(item, "owns_cost_ledger", False)]
    if not owners:
        return {"cost_authority": True}
    ledgers = sorted({str(getattr(owner, "ledger", None)
                          and getattr(owner.ledger, "path", ""))
                      for owner in owners})
    return {"cost_authority": False, "cost_ledger": ledgers[0] if ledgers else None}


def _describe(policy) -> dict:
    describe = getattr(policy, "describe", None)
    if callable(describe):
        return describe()
    if isinstance(policy, dict):
        return {role: _describe(item) for role, item in policy.items()}
    return {}


def _run_single(*, profile, bundle, driver, record, snapshot, counterparty_act,
                world, turns, chances, budgets, detection, seed, arm, world_id,
                policy):
    """The single-agent driver contract: build_observation / execute_actions."""
    for name in ("build_observation", "execute_actions"):
        if not callable(getattr(driver, name, None)):
            raise DriverContractError(
                f"single-agent source driver is missing {name}")
    if isinstance(policy, dict):
        raise DriverContractError(
            "a single-agent Case takes one business policy, not a role map")

    schedule = profile["schedule"]
    actions_so_far: list = []
    final_state: dict = {}
    final_events: list = []

    for index in range(1, turns + 1):
        current = world()
        presented = snapshot(f"business_decision_{index}")
        try:
            observation = driver.build_observation(copy.deepcopy(current),
                                                   bundle.instruction)
        except Exception as exc:                                   # noqa: BLE001
            raise DriverStageError("build_observation", "business",
                                   f"{type(exc).__name__}: {exc}",
                                   final_state, final_events) from exc
        if not isinstance(observation, dict):
            raise DriverContractError("build_observation must return a mapping")
        reply = backend.invoke(policy, observation, budgets["business"],
                               {"turn": index, "world_id": world_id, "arm": arm})
        adapter = reply.get("_adapter") or {}
        decision = {"index": index, "kind": "business_turn",
                    "snapshot_index": presented["index"],
                    "presented_world_sha256": presented["sha256"],
                    "observation_sha256": digest(observation),
                    "observation": observation, "raw_response": reply,
                    "executed": None}
        if adapter.get("failure"):
            record["protocol_failures"].append({"role": "business", "turn": index,
                                                "failure": adapter["failure"]})
            record["decisions"].append(decision)
            return "protocol_failure", final_state, final_events

        actions = reply.get("actions") or []
        decision["extra_actions_dropped"] = max(0, len(actions) - 1)
        if actions:
            actions_so_far.append(copy.deepcopy(actions[0]))
            # These drivers are pure functions of (world, response), so passing
            # the accumulated action list against THIS decision's world is the
            # original contract. An earlier non-decisive action therefore stays
            # in the record without being re-judged under a later world.
            try:
                state, produced = driver.execute_actions(
                    copy.deepcopy(current),
                    {"actions": copy.deepcopy(actions_so_far)},
                    **driver_kwargs(driver.execute_actions, seed=seed))
            except Exception as exc:                               # noqa: BLE001
                record["decisions"].append(decision)
                raise DriverStageError("execute_actions", "business",
                                       f"{type(exc).__name__}: {exc}",
                                       final_state, final_events) from exc
            if not isinstance(state, dict) or not isinstance(produced, list):
                raise DriverContractError(
                    "execute_actions must return (mapping, list)")
            decision["executed"] = {
                "action": actions[0],
                "actions_cumulative": copy.deepcopy(actions_so_far),
                "driver_state": copy.deepcopy(state),
                "events": copy.deepcopy(produced)}
            final_state, final_events = state, produced
            hit = detect_terminal(state, detection)
            if hit:
                decision["terminal_detail"] = hit
                record["decisions"].append(decision)
                record["decisive_decision_index"] = index
                record["terminal_detail"] = hit
                return hit["terminal"], state, produced
        record["decisions"].append(decision)

        trigger = next((t for t in schedule["triggers"]
                        if t.get("after_business_turn") == index), None)
        if trigger and budgets["counterparty"].calls < chances:
            try:
                counterparty_act({"kind": "feedback", **trigger})
            except (CounterpartyFailure, backend.BudgetStop):
                return "protocol_failure", final_state, final_events

    return "turn_budget_exhausted", final_state, final_events


def _run_role_chain(*, profile, bundle, driver, record, snapshot,
                    counterparty_act, world, turns, chances, budgets, detection,
                    seed, arm, world_id, policy):
    """The multi-agent-sequential contract, run as the real role chain.

    initialize_state → for each declared role: build_role_observation, that
    role's own policy, apply_role_response → finalize_state. State is threaded
    through, so an upstream role's brief or handoff reaches the downstream role
    exactly as the source Case intends. v1 had no path for this at all, and a
    matching `role_chain` field in a profile was never evidence that the chain
    had run.
    """
    for name in ("initialize_state", "build_role_observation",
                 "apply_role_response"):
        if not callable(getattr(driver, name, None)):
            raise DriverContractError(
                f"multi-agent source driver is missing {name}")
    roles = list(profile["business_role"]["role_chain"])
    if not roles:
        raise DriverContractError("multi-agent profile must declare its role chain")
    if not isinstance(policy, dict) or set(policy) != set(roles):
        raise DriverContractError(
            "a role-chain Case needs exactly one business policy per declared role")

    schedule = profile["schedule"]
    state = driver.initialize_state(copy.deepcopy(world()))
    if not isinstance(state, dict):
        raise DriverContractError("initialize_state must return a mapping")
    events: list = []
    index = 0

    for role_index, role in enumerate(roles):
        current = world()
        presented = snapshot(f"role_decision_{role}")
        index += 1
        try:
            observation = driver.build_role_observation(
                copy.deepcopy(current), copy.deepcopy(state), bundle.instruction,
                role)
        except Exception as exc:                                   # noqa: BLE001
            raise DriverStageError("build_role_observation", role,
                                   f"{type(exc).__name__}: {exc}",
                                   state, events) from exc
        if not isinstance(observation, dict):
            raise DriverContractError(f"{role}: observation must be a mapping")
        reply = backend.invoke(policy[role], observation, budgets["business"],
                               {"role": role, "world_id": world_id, "arm": arm})
        adapter = reply.get("_adapter") or {}
        decision = {"index": index, "kind": "role_turn", "role": role,
                    "snapshot_index": presented["index"],
                    "presented_world_sha256": presented["sha256"],
                    "observation_sha256": digest(observation),
                    "observation": observation, "raw_response": reply,
                    "executed": None}
        if adapter.get("failure"):
            record["protocol_failures"].append({"role": role,
                                                "failure": adapter["failure"]})
            record["decisions"].append(decision)
            return "protocol_failure", state, events

        try:
            state, role_events = driver.apply_role_response(
                copy.deepcopy(current), copy.deepcopy(state), role, reply,
                **driver_kwargs(driver.apply_role_response, seed=seed))
        except Exception as exc:                                   # noqa: BLE001
            record["decisions"].append(decision)
            raise DriverStageError("apply_role_response", role,
                                   f"{type(exc).__name__}: {exc}",
                                   state, events) from exc
        if not isinstance(state, dict) or not isinstance(role_events, list):
            raise DriverContractError("apply_role_response must return (mapping, list)")
        shaped = []
        for event_index, event in enumerate(role_events):
            event = dict(event)
            event.setdefault("sequence", role_index + (event_index + 1) / 10)
            event["agent_role"] = role
            shaped.append(event)
        events.extend(shaped)
        decision["executed"] = {"role": role, "driver_state": copy.deepcopy(state),
                                "events": shaped}
        record["decisions"].append(decision)

        trigger = next((t for t in schedule["triggers"]
                        if t.get("after_role") == role), None)
        if trigger and budgets["counterparty"].calls < chances:
            try:
                counterparty_act({"kind": "feedback", **trigger})
            except (CounterpartyFailure, backend.BudgetStop):
                return "protocol_failure", state, events

    finalize = getattr(driver, "finalize_state", None)
    try:
        final_state = (finalize(copy.deepcopy(world()), copy.deepcopy(state))
                       if callable(finalize) else state)
    except Exception as exc:                                       # noqa: BLE001
        raise DriverStageError("finalize_state", "business",
                               f"{type(exc).__name__}: {exc}",
                               state, events) from exc
    if not isinstance(final_state, dict):
        raise DriverContractError("finalize_state must return a mapping")

    hit = detect_terminal(final_state, detection)
    record["terminal_detail"] = hit
    record["decisive_decision_index"] = index
    return (hit["terminal"] if hit else "chain_completed_without_terminal",
            final_state, events)


def _write_run_directory(run_dir: Path, bundle, world_id: str, record: dict,
                         state: dict, events: list, source_world: dict,
                         arm: str, seed: int) -> None:
    """Emit the layout the ORIGINAL verifier reads, plus the new snapshots.

    `state/initial_world.json` is the world AS PRESENTED at the decision the
    terminal came from, and `state/snapshots.json` names that decision. The
    frozen author world is kept separately in `state/source_world.json`, so
    neither file can be mistaken for the other.
    """
    (run_dir / "state" / "presented").mkdir(parents=True, exist_ok=False)
    (run_dir / "agent").mkdir(parents=True, exist_ok=True)

    decisive = record.get("decisive_decision_index")
    bound = None
    for decision in record["decisions"]:
        if decisive is not None and decision["index"] == decisive:
            bound = decision["snapshot_index"]
    if bound is None and record["world_snapshots"]:
        bound = record["world_snapshots"][-1]["index"]

    for entry in record["world_snapshots"]:
        (run_dir / "state" / "presented" / f"snapshot-{entry['index']:02d}.json"
         ).write_text(json.dumps(entry["world"], ensure_ascii=False, indent=1)
                      + "\n", encoding="utf-8")
    (run_dir / "state" / "source_world.json").write_text(
        json.dumps(source_world, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    (run_dir / "state" / "snapshots.json").write_text(json.dumps({
        "source_world_sha256": record["source_world_sha256"],
        "snapshots": [{k: entry[k] for k in ("index", "label", "sha256")}
                      for entry in record["world_snapshots"]],
        "decisive_decision_index": decisive,
        "initial_world_is_snapshot_index": bound,
        "note": "state/initial_world.json is the world as presented at the "
                "decision named above. It is neither the end-of-episode world "
                "nor the frozen author world.",
    }, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    presented_world = (record["world_snapshots"][bound]["world"]
                       if bound is not None else source_world)
    (run_dir / "state" / "initial_world.json").write_text(
        json.dumps(presented_world, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    (run_dir / "state" / "final_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with (run_dir / "state" / "events.jsonl").open("w", encoding="utf-8") as stream:
        for event in events:
            stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    manifest = {"schema_version": "0.2", "run_id": record["episode_id"],
                "case_id": record["case_id"], "variant_id": world_id,
                "agent_id": f"migration-{arm}", "intervention": "none",
                "seed": seed, "agent_mode": record["agent_mode"],
                "agent_roles": list(bundle.raw["agent"].get("roles") or []),
                "protocol": record["protocol"], "arm": arm,
                "route_id": record["route_id"],
                "generated_at": time.time()}
    (run_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    if record["agent_mode"] == "single":
        (run_dir / "agent" / "response.json").write_text(
            json.dumps({"actions": [d["executed"]["action"]
                                    for d in record["decisions"]
                                    if d.get("executed")]},
                       ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    else:
        for decision in record["decisions"]:
            role_dir = run_dir / "agent" / str(decision.get("role"))
            role_dir.mkdir(parents=True, exist_ok=True)
            (role_dir / "observation.json").write_text(
                json.dumps(decision["observation"], ensure_ascii=False, indent=1)
                + "\n", encoding="utf-8")
            (role_dir / "response.json").write_text(
                json.dumps({k: v for k, v in decision["raw_response"].items()
                            if k != "_adapter"}, ensure_ascii=False, indent=1)
                + "\n", encoding="utf-8")
