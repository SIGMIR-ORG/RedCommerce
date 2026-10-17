"""Declared business mappings. No arity guessing, no semantic guessing.

Per DECISION.md §2: a mapping must state which predicate it calls, where each
argument comes from, and what the result means. The earlier version probed a
`violations` function with three different argument tuples and took whichever
did not raise TypeError. That is gone: an adapter now declares the call, and an
undeclared or unresolvable call is an error rather than a silent fallback.

Sources an argument may be resolved from:

  presented_world   the world AS PRESENTED at the business decision being judged
  source_world      the frozen author world for this Variant, unchanged
  final_state       the driver's own final state for the episode
  commit_artifact   the artifact inside the recorded commitment, if any
  truth             the Case's private ground truth, with this world's
                    `variant_authority` entry already merged in exactly as the
                    shared verifier merges it. A declared predicate must see the
                    same trusted facts the original judge sees, or a Case running
                    on a non-default world would be diagnosed against the wrong
                    authority records
  raw_truth         the unmerged truth file, for a mapping that genuinely needs it
  literal           a value written into the mapping itself

`presented_world` is deliberately the default for proposal diagnosis: judging a
mid-episode decision against the end-of-episode world was a real defect in v1.
"""
from __future__ import annotations

import copy
import importlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

SOURCES = ("presented_world", "source_world", "final_state", "commit_artifact",
           "truth", "raw_truth", "literal", "call", "candidate", "world_id")

# `call` resolves an argument by running one of the CASE'S OWN functions. It
# exists for Cases where the thing to be judged is not a plain path: T51's
# candidate order is a deterministic projection its own driver performs on the
# presented cart, and T22's served impression is what its own driver computes
# for the consumer at serve time. Using the Case's code keeps the projection the
# Case's semantics rather than business logic invented in this package. A `call`
# result is a DIAGNOSTIC: it is never written into a run directory and never
# counted as an actual commitment.

KINDS = (
    "declared_predicate",        # call a named callable in a named module
    "legacy_verifier_field",     # read one field of the Case's own verifier output
    "state_nonempty",            # a declared state path is non-empty
    "state_records_match",       # compare two declared state/world paths
    "conjunction",               # AND over declared terms
    "disjunction",               # OR over declared terms
    "negation",                  # NOT of one declared term
    "reference",                 # reuse an already-computed mapping result
    "any_candidate_passes",      # global feasibility: enumerate, then let the
                                 # Case's own predicate judge each candidate
    "not_available",             # honestly absent: returns null plus a reason
)

# Readings a reference may apply to another mapping result. Spelled out so that
# "the proposal had no violations" is a declared interpretation of a code list
# rather than an implicit truthiness accident.
REFERENCE_INTERPRETATIONS = ("boolean", "no_violations", "has_violations")


class MappingError(ValueError):
    """A mapping that cannot be resolved as declared. Never silently skipped."""


def load_module(task_path: Path, relative: str):
    """Load a declared module from inside the source Case (or the shared package)."""
    path = (Path(task_path) / relative).resolve()
    if not path.is_file():
        raise MappingError(f"declared module does not exist: {relative}")
    try:
        rel = path.relative_to(PROJECT)
    except ValueError:
        rel = None
    if rel is not None and rel.parts[:-1]:
        package = PROJECT.joinpath(*rel.parts[:-1])
        if (package / "__init__.py").is_file():
            return importlib.import_module(".".join(rel.parts[:-1] + (path.stem,)))
    spec = importlib.util.spec_from_file_location("mig_map_" + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    added = str(path.parent)
    inserted = added not in sys.path
    if inserted:
        sys.path.insert(0, added)
    try:
        spec.loader.exec_module(module)
    finally:
        if inserted:
            sys.path.remove(added)
    return module


def read_path(node, path):
    """Read a declared path.

    A path may be a dotted string or an explicit list of tokens. The list form
    exists because real record keys contain dots: T41's witness lives under the
    literal key "order.product_identity", which dot-splitting would tear in two.
    """
    if path in ("", None, []):
        return node
    tokens = list(path) if isinstance(path, (list, tuple)) else str(path).split(".")
    for token in tokens:
        if isinstance(node, dict):
            if token not in node:
                raise MappingError(f"path {path!r} is absent at {token!r}")
            node = node[token]
        elif isinstance(node, list):
            try:
                node = node[int(token)]
            except (ValueError, IndexError) as exc:
                raise MappingError(f"path {path!r} cannot index a list") from exc
        else:
            raise MappingError(f"path {path!r} descends into a scalar")
    return node



def resolve_truth(truth: dict, world_id: str | None) -> dict:
    """Merge this world's `variant_authority` entry, as the shared verifier does.

    redcommerce_v3/independent_verifier.py builds its policy truth as
    `dict(truth)` updated with `truth["variant_authority"][variant_id]`. A
    declared mapping that read the unmerged file would diagnose a proposal
    against the wrong trusted facts on any world other than the default one,
    which matters as soon as a route runs on a non-benign world.
    """
    resolved = copy.deepcopy(truth)
    per_variant = (truth.get("variant_authority") or {})
    if world_id and world_id in per_variant:
        resolved.update(copy.deepcopy(per_variant[world_id]))
    return resolved


class Context:
    """Everything a mapping may read, named explicitly."""

    def __init__(self, *, presented_world: dict, source_world: dict,
                 final_state: dict, truth: dict, commit_artifact: Any = None,
                 legacy_outcome: dict | None = None, world_id: str | None = None,
                 task_path: Path | None = None):
        self.task_path = Path(task_path) if task_path else None
        resolved_truth = resolve_truth(truth, world_id)
        self.values = {
            "presented_world": presented_world,
            "source_world": source_world,
            "final_state": final_state,
            "truth": resolved_truth,
            "raw_truth": truth,
            "commit_artifact": commit_artifact,
        }
        self.world_id = world_id
        self.legacy_outcome = legacy_outcome or {}

    def with_candidate(self, candidate):
        """A shallow clone bound to one enumerated candidate."""
        clone = copy.copy(self)
        clone.values = dict(self.values)
        clone.values["candidate"] = candidate
        return clone

    def resolve(self, argument: dict):
        source = argument.get("from")
        if source not in SOURCES:
            raise MappingError(f"argument.from must be one of {SOURCES}")
        if source == "literal":
            if "value" not in argument:
                raise MappingError("a literal argument needs a value")
            return copy.deepcopy(argument["value"])
        if source == "world_id":
            # The Variant id this episode ran on. Needed by a Case's own
            # `effective_mandate` / `effective_registry` helper, which selects an
            # immutable per-Variant fact. Passing a placeholder here would
            # silently read the base fact on any non-default world.
            return self.world_id
        if source == "call":
            if self.task_path is None:
                raise MappingError("a call argument needs the source Case path")
            if not argument.get("purpose"):
                raise MappingError("a call argument must state its purpose, so a "
                                   "projection is never mistaken for a commitment")
            try:
                value = _call_declared(self.task_path, argument, self)
            except MappingError:
                raise
            except Exception as exc:                               # noqa: BLE001
                if argument.get("allow_missing"):
                    return None
                raise MappingError(
                    f"call to {argument.get('callable')} raised "
                    f"{type(exc).__name__}: {exc}") from exc
            for step in argument.get("select", []):
                try:
                    value = value[step]
                except (KeyError, IndexError, TypeError) as exc:
                    if argument.get("allow_missing"):
                        return None
                    raise MappingError(
                        f"call result has no element {step!r}") from exc
            return copy.deepcopy(value)
        root = self.values.get(source)
        if root is None and argument.get("allow_missing"):
            return None
        if root is None:
            raise MappingError(f"source {source!r} is not available in this episode")
        try:
            return copy.deepcopy(read_path(root, argument.get("path", "")))
        except MappingError:
            if argument.get("allow_missing"):
                return None
            raise


def _call_declared(task_path: Path, spec: dict, context: Context):
    module = load_module(task_path, spec["module"])
    name = spec["callable"]
    target = getattr(module, name, None)
    if target is None and "." in name:
        holder, _, key = name.partition(".")
        container = getattr(module, holder, None)
        if isinstance(container, dict):
            lookup = spec.get("key_from")
            key_value = (context.resolve(lookup) if lookup else key)
            target = container.get(key_value)
            if target is None:
                raise MappingError(
                    f"{holder}[{key_value!r}] is not defined in {spec['module']}")
    if not callable(target):
        raise MappingError(f"{name} is not callable in {spec['module']}")
    args = [context.resolve(argument) for argument in spec.get("arguments", [])]
    kwargs = {key: context.resolve(argument)
              for key, argument in (spec.get("keyword_arguments") or {}).items()}
    return target(*args, **kwargs)


def _candidate_id(candidate) -> str:
    if isinstance(candidate, dict):
        for key in ("candidate_id", "product_id", "order_id", "sku", "id"):
            if key in candidate:
                return str(candidate[key])
    return json.dumps(candidate, sort_keys=True, default=str)[:120]


def _combine(task_path: Path, spec: dict, context: Context, resolved: dict,
             provenance: dict) -> dict:
    """conjunction / disjunction / negation over declared terms.

    Three-valued on purpose: a term that could not be evaluated makes the whole
    result unknown rather than false, unless the other terms already decide it.
    That is the rule "an unevaluated consequence is never reported as zero".
    """
    kind = spec["kind"]
    terms = spec.get("terms") if kind != "negation" else [spec.get("term")]
    if not terms or any(not isinstance(term, dict) for term in terms):
        raise MappingError(f"{kind} needs declared terms")
    results = [evaluate(task_path, term, context, resolved) for term in terms]
    provenance["terms"] = [{"kind": term.get("kind"), "status": result["status"],
                            "value": result["value"]}
                           for term, result in zip(terms, results)]
    values = [result["value"] if result["status"] == "computed" else None
              for result in results]
    if kind == "negation":
        value = None if values[0] is None else (not values[0])
    elif kind == "conjunction":
        value = False if any(v is False for v in values) else (
            None if any(v is None for v in values) else True)
    else:
        value = True if any(v is True for v in values) else (
            None if any(v is None for v in values) else False)
    if value is None:
        return {"status": "not_available", "value": None,
                "reason": "a declared term could not be evaluated",
                "provenance": provenance}
    return {"status": "computed", "value": value, "reason": None,
            "provenance": provenance}


def evaluate(task_path: Path, spec: dict, context: Context,
             resolved: dict | None = None) -> dict:
    """Run one declared mapping and return value plus full provenance."""
    kind = spec.get("kind")
    if kind not in KINDS:
        raise MappingError(f"mapping.kind must be one of {KINDS}")
    resolved = resolved if resolved is not None else {}
    provenance = {"kind": kind, "meaning": spec.get("meaning"),
                  "coverage": spec.get("coverage")}

    if kind in ("conjunction", "disjunction", "negation"):
        return _combine(task_path, spec, context, resolved, provenance)

    if kind == "any_candidate_passes":
        # Global feasibility: does ANY option the business side could actually
        # construct pass the Case's own predicate? This package only ENUMERATES
        # the options from the presented world; the judging is delegated to the
        # Case's own function, so no business rule is invented here. Answering
        # "the current proposal is unacceptable" is NOT an answer to this.
        try:
            candidates = context.resolve(spec["candidates"])
        except MappingError as exc:
            return {"status": "not_available", "value": None,
                    "reason": f"candidate enumeration failed: {exc}",
                    "provenance": provenance}
        if not isinstance(candidates, list):
            return {"status": "not_available", "value": None,
                    "reason": "candidate enumeration did not return a list",
                    "provenance": provenance}
        predicate = spec["predicate"]
        reading = predicate.get("interpret", "codes")
        judged = []
        for candidate in candidates:
            bound = context.with_candidate(candidate)
            try:
                raw = _call_declared(Path(task_path), predicate, bound)
            except Exception as exc:                               # noqa: BLE001
                judged.append({"candidate_id": _candidate_id(candidate),
                               "error": f"{type(exc).__name__}: {exc}"})
                continue
            if reading == "codes":
                codes = sorted(str(code) for code in (raw or []))
                judged.append({"candidate_id": _candidate_id(candidate),
                               "violations": codes, "passes": not codes})
            elif reading == "equals":
                # Some Cases expose their standing-policy verdict as a witness
                # field rather than a code list. The path and the expected value
                # are declared, so the reading is auditable.
                try:
                    observed = read_path(raw, predicate.get("select", ""))
                except MappingError as exc:
                    judged.append({"candidate_id": _candidate_id(candidate),
                                   "error": str(exc)})
                    continue
                judged.append({"candidate_id": _candidate_id(candidate),
                               "observed": observed,
                               "expected": predicate.get("expected"),
                               "passes": observed == predicate.get("expected")})
            else:
                judged.append({"candidate_id": _candidate_id(candidate),
                               "error": f"unknown predicate interpretation "
                                        f"{reading!r}"})
        provenance["candidates_considered"] = judged
        provenance["enumerated"] = len(candidates)
        if not candidates:
            return {"status": "computed", "value": False, "reason": None,
                    "provenance": provenance}
        if any(item.get("error") for item in judged) and not any(
                item.get("passes") for item in judged):
            return {"status": "not_available", "value": None,
                    "reason": "a candidate could not be judged, so feasibility "
                              "is unknown rather than false",
                    "provenance": provenance}
        return {"status": "computed",
                "value": any(item.get("passes") for item in judged),
                "reason": None, "provenance": provenance}

    if kind == "reference":
        name = spec.get("of")
        if name not in resolved:
            raise MappingError(f"reference to {name!r}, which is not computed yet")
        other = resolved[name]
        interpretation = spec.get("interpret", "boolean")
        if interpretation not in REFERENCE_INTERPRETATIONS:
            raise MappingError(f"unknown reference interpretation {interpretation!r}")
        provenance.update({"of": name, "interpret": interpretation,
                           "referenced_status": other["status"]})
        if other["status"] != "computed":
            return {"status": "not_available", "value": None,
                    "reason": f"{name} was not computed", "provenance": provenance}
        raw = other["value"]
        value = (not raw) if interpretation == "no_violations" else bool(raw)
        return {"status": "computed", "value": value, "reason": None,
                "provenance": provenance}

    if kind == "not_available":
        if not spec.get("reason"):
            raise MappingError("a not_available mapping must give a reason")
        return {"status": "not_available", "value": None,
                "reason": spec["reason"], "provenance": provenance}

    if kind == "legacy_verifier_field":
        field = spec["field"]
        if field not in context.legacy_outcome:
            raise MappingError(f"legacy outcome has no field {field!r}")
        provenance["field"] = field
        return {"status": "computed", "value": context.legacy_outcome[field],
                "reason": None, "provenance": provenance}

    if kind == "state_nonempty":
        value = context.resolve({"from": spec.get("source", "final_state"),
                                 "path": spec["path"],
                                 "allow_missing": spec.get("allow_missing", True)})
        provenance["path"] = spec["path"]
        return {"status": "computed", "value": bool(value), "reason": None,
                "provenance": provenance}

    if kind == "state_records_match":
        left = context.resolve(spec["left"])
        right = context.resolve(spec["right"])
        comparison = spec.get("comparison", "equal")
        provenance.update({"left": spec["left"], "right": spec["right"],
                           "comparison": comparison})
        if comparison == "equal":
            value = json.dumps(left, sort_keys=True) == json.dumps(right, sort_keys=True)
        elif comparison == "numeric_equal":
            tolerance = float(spec.get("tolerance", 1e-9))
            if left is None or right is None:
                return {"status": "not_available", "value": None,
                        "reason": "one side of the comparison is absent",
                        "provenance": provenance}
            value = abs(float(left) - float(right)) <= tolerance
        elif comparison == "left_exceeds_right":
            if left is None or right is None:
                return {"status": "not_available", "value": None,
                        "reason": "one side of the comparison is absent",
                        "provenance": provenance}
            value = float(left) > float(right) + float(spec.get("tolerance", 1e-9))
        else:
            raise MappingError(f"unknown comparison {comparison!r}")
        provenance["observed"] = {"left": left, "right": right}
        return {"status": "computed", "value": value, "reason": None,
                "provenance": provenance}

    # declared_predicate
    provenance.update({"module": spec["module"], "callable": spec["callable"],
                       "arguments": spec.get("arguments", []),
                       "keyword_arguments": spec.get("keyword_arguments") or {}})
    raw = _call_declared(Path(task_path), spec, context)
    interpretation = spec.get("interpret", "codes")
    if interpretation == "codes":
        if not isinstance(raw, (list, tuple, set)):
            raise MappingError(f"{spec['callable']} did not return a code list")
        value = sorted(str(code) for code in raw)
    elif interpretation == "boolean":
        value = bool(raw)
    elif interpretation == "raw":
        value = raw
    else:
        raise MappingError(f"unknown interpret {interpretation!r}")
    return {"status": "computed", "value": value, "reason": None,
            "provenance": provenance}


def validate_spec(spec: dict, task_path: Path) -> None:
    """Static checks on a declared mapping, run at profile-validation time."""
    kind = spec.get("kind")
    if kind not in KINDS:
        raise MappingError(f"mapping.kind must be one of {KINDS}")
    if not spec.get("meaning"):
        raise MappingError("every mapping must state what its result means")
    if kind == "not_available":
        if not spec.get("reason"):
            raise MappingError("a not_available mapping must give a reason")
        return
    if kind == "legacy_verifier_field":
        if not spec.get("field"):
            raise MappingError("legacy_verifier_field needs a field")
        return
    if kind == "state_nonempty":
        if not spec.get("path"):
            raise MappingError("state_nonempty needs a path")
        return
    if kind == "state_records_match":
        for side in ("left", "right"):
            argument = spec.get(side)
            if not isinstance(argument, dict) or argument.get("from") not in SOURCES:
                raise MappingError(f"state_records_match.{side} needs a declared source")
        if not spec.get("coverage"):
            raise MappingError("state_records_match must state its coverage")
        return
    if kind in ("conjunction", "disjunction"):
        terms = spec.get("terms")
        if not isinstance(terms, list) or not terms:
            raise MappingError(f"{kind} needs a non-empty terms list")
        for term in terms:
            validate_spec(term, task_path)
        return
    if kind == "negation":
        if not isinstance(spec.get("term"), dict):
            raise MappingError("negation needs one declared term")
        validate_spec(spec["term"], task_path)
        return
    if kind == "reference":
        if not spec.get("of"):
            raise MappingError("reference needs the name of another mapping")
        if spec.get("interpret", "boolean") not in REFERENCE_INTERPRETATIONS:
            raise MappingError("reference.interpret is not a declared reading")
        return
    if kind == "any_candidate_passes":
        candidates = spec.get("candidates")
        if not isinstance(candidates, dict) or candidates.get("from") not in SOURCES:
            raise MappingError("any_candidate_passes needs a declared candidates "
                               "source")
        predicate = spec.get("predicate")
        if not isinstance(predicate, dict):
            raise MappingError("any_candidate_passes needs a declared predicate")
        for key in ("module", "callable"):
            if not predicate.get(key):
                raise MappingError(f"the candidate predicate needs {key}")
        if not (Path(task_path) / predicate["module"]).is_file():
            raise MappingError("the candidate predicate names a module that does "
                               "not exist")
        if not any(argument.get("from") == "candidate"
                   for argument in predicate.get("arguments", [])) and not any(
                       argument.get("from") == "candidate"
                       for inner in predicate.get("arguments", [])
                       for argument in (inner.get("arguments") or [])) and not (
                           "candidate" in json.dumps(
                               predicate.get("arguments", []), default=str)):
            raise MappingError("the candidate predicate must actually be applied "
                               "to the candidate")
        reading = predicate.get("interpret", "codes")
        if reading not in ("codes", "equals"):
            raise MappingError(f"unknown predicate interpretation {reading!r}")
        if reading == "equals" and "expected" not in predicate:
            raise MappingError("an `equals` candidate predicate must declare the "
                               "expected value")
        if not spec.get("coverage"):
            raise MappingError("any_candidate_passes must state its coverage")
        if candidates.get("from") == "call":
            for key in ("module", "callable", "purpose"):
                if not candidates.get(key):
                    raise MappingError(f"the candidates call needs {key}")
        return
    for key in ("module", "callable"):
        if not spec.get(key):
            raise MappingError(f"declared_predicate needs {key}")
    path = (Path(task_path) / spec["module"]).resolve()
    if not path.is_file():
        raise MappingError(f"declared module does not exist: {spec['module']}")
    for argument in spec.get("arguments", []):
        if not isinstance(argument, dict) or argument.get("from") not in SOURCES:
            raise MappingError("every predicate argument needs a declared source")
        if argument.get("from") == "call":
            for key in ("module", "callable", "purpose"):
                if not argument.get(key):
                    raise MappingError(f"a call argument needs {key}")
            if not (Path(task_path) / argument["module"]).is_file():
                raise MappingError(
                    f"call argument names a module that does not exist: "
                    f"{argument['module']}")
            for inner in argument.get("arguments", []):
                if not isinstance(inner, dict) or inner.get("from") not in SOURCES:
                    raise MappingError("a call argument's own arguments need "
                                       "declared sources")
    if not spec.get("coverage"):
        raise MappingError("a declared predicate must state its coverage, so an "
                           "unevaluated consequence is never reported as zero")
