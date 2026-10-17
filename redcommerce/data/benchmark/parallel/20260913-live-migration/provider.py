"""Generic provider policy factory. Zero-cost wiring only — nothing can spend.

Generic over BOTH sides. The §5 review found that the first version only fitted
a counterparty observation: handed a business observation it produced
`You are acting as: None`, an empty objective, counterparty-only wording, and
five null user fields, so the business model saw neither the task, the facts nor
its tools. A role now declares its kind and gets a request built from what its
own driver actually authorised.

Budget rules, all of which the review required:

  one authority              the persistent ledger here is the only layer that
                             may debit. The scheduler's `RoleBudget` records the
                             same receipts with `cost_authority=False`, so a
                             zero-dollar default can no longer veto an
                             authorised request or double-charge it.
  reserve before dispatch    a conservative upper bound is written to disk
                             before the request leaves.
  one settlement per request a second settlement of the same id raises.
  unknown usage stops        a reply with no usable usage raises instead of
                             settling as zero.
  a dispatched request is    if the client was entered and the outcome is
  never assumed free         unknown — a transport timeout, say — the
                             reservation is KEPT, the request is marked
                             `unknown_outcome`, further calls are halted, and the
                             state survives a restart. A reservation is released
                             only when the transport itself asserts the request
                             never left, by raising `NotDispatched`; every other
                             failure is treated as possibly charged, because
                             from outside the client the two are
                             indistinguishable.
  costs are validated        non-finite, negative, or over-reservation costs are
                             refused rather than absorbed.
  a refusal keeps evidence   every refusal above is a `BudgetStop` subclass, so
                             the scheduler records it as a protocol failure and
                             still writes the episode, the receipts and the
                             request references.

`FakeProvider` is the only provider implemented: no network, no credential. A
real transport is NOT implemented — see `RealTransportNotImplemented`. This
module never reads an environment variable, a key file or a credential.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backend                                                   # noqa: E402

FORBIDDEN_ENVIRONMENT = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "AZURE_OPENAI_KEY")

ROLE_KINDS = ("counterparty", "business")


class BudgetError(backend.BudgetStop, RuntimeError):
    """A reservation, settlement or ledger problem. Never swallowed.

    A subclass of `backend.BudgetStop` on purpose: the scheduler already treats
    a budget stop as a recorded protocol failure that KEEPS the episode, its
    receipts and its request references. Without that inheritance a ledger
    refusal — an over-cap reservation, an unknown usage, an invalid cost —
    escaped as an unhandled exception and the run directory was lost, which is
    exactly the P2 defect the review reproduced. Losing the episode is not
    evidence that no request was made.
    """


class NotDispatched(Exception):
    """A transport raises this ONLY when the request provably never left.

    The policy cannot tell from the outside whether a client that blew up had
    already written to a socket, so any OTHER exception out of the client is
    treated as a dispatched request with an unknown outcome. A transport that
    genuinely fails before sending — a payload it refuses to build, a cap it
    checks itself — must say so with this exception to have its reservation
    released. Silence is charged, not forgiven.
    """


class RealTransportNotImplemented(NotImplementedError):
    """There is no real provider transport in this package.

    Raised so nobody can describe the current state as "just add a key": a real
    run needs a transport, a price table, a cap and an authorisation, none of
    which exist here.
    """


# ===========================================================================
# Ledger
# ===========================================================================
class PersistentLedger:
    """An append-only spend ledger with one total and per-role sub-accounts."""

    def __init__(self, path: Path, *, total_cap_usd: float,
                 role_caps_usd: dict | None = None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.total_cap_usd = float(total_cap_usd)
        self.role_caps_usd = dict(role_caps_usd or {})
        self.entries: list[dict] = []
        if self.path.is_file():
            self.entries = [json.loads(line) for line in
                            self.path.read_text(encoding="utf-8").splitlines()
                            if line.strip()]

    # --- derived state --------------------------------------------------
    def _by_request(self) -> dict:
        out: dict[str, dict] = {}
        for entry in self.entries:
            out.setdefault(entry["request_id"], {})[entry["event"]] = entry
        return out

    @staticmethod
    def _is_closed(request: dict) -> bool:
        return "settled" in request or "released" in request

    def committed_usd(self) -> float:
        """Settled spend plus every still-open reservation.

        An `unknown_outcome` request stays open on purpose, so its reservation
        keeps counting against the cap until it is reconciled.
        """
        total = 0.0
        for request in self._by_request().values():
            if "settled" in request:
                total += float(request["settled"].get("cost_usd") or 0.0)
            elif "released" in request:
                continue
            elif "reserved" in request:
                total += float(request["reserved"].get("reserved_usd") or 0.0)
        return round(total, 6)

    def committed_for_role(self, role: str) -> float:
        total = 0.0
        for request in self._by_request().values():
            entry = request.get("settled") or request.get("reserved")
            if not entry or entry.get("role") != role:
                continue
            if "settled" in request:
                total += float(request["settled"].get("cost_usd") or 0.0)
            elif "released" not in request:
                total += float(request["reserved"].get("reserved_usd") or 0.0)
        return round(total, 6)

    def unresolved_unknown_outcomes(self) -> list:
        """Dispatched requests whose outcome is still unknown.

        Survives a restart because it is read back off disk, and nothing here
        clears it automatically.
        """
        out = []
        for request_id, request in self._by_request().items():
            if "unknown_outcome" in request and not self._is_closed(request):
                out.append({"request_id": request_id,
                            "role": request["reserved"].get("role"),
                            "reserved_usd": request["reserved"].get("reserved_usd"),
                            "reason": request["unknown_outcome"].get("reason"),
                            "raw_reference":
                                request["unknown_outcome"].get("raw_reference")})
        return sorted(out, key=lambda item: item["request_id"])

    def _append(self, entry: dict) -> None:
        entry = {**entry, "at": time.time()}
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(entry, ensure_ascii=False, sort_keys=True)
                         + "\n")
        self.entries.append(entry)

    # --- operations -----------------------------------------------------
    def reserve(self, *, role: str, reserved_usd: float, detail: dict) -> str:
        reserved_usd = float(reserved_usd)
        if not math.isfinite(reserved_usd) or reserved_usd < 0:
            raise BudgetError(f"a reservation must be finite and non-negative, "
                              f"got {reserved_usd!r}")
        unresolved = self.unresolved_unknown_outcomes()
        if unresolved:
            raise BudgetError(
                f"{len(unresolved)} dispatched request(s) have an unknown "
                f"outcome and must be reconciled before another is sent: "
                f"{[item['request_id'] for item in unresolved]}")
        projected = self.committed_usd() + reserved_usd
        if projected > self.total_cap_usd + 1e-9:
            raise BudgetError(
                f"reserving {reserved_usd} would take committed spend to "
                f"{projected}, over the total cap {self.total_cap_usd}")
        role_cap = self.role_caps_usd.get(role)
        if role_cap is not None:
            role_projected = self.committed_for_role(role) + reserved_usd
            if role_projected > float(role_cap) + 1e-9:
                raise BudgetError(
                    f"reserving {reserved_usd} would take {role} to "
                    f"{role_projected}, over its cap {role_cap}")
        request_id = "REQ-" + uuid.uuid4().hex[:16]
        self._append({"event": "reserved", "request_id": request_id,
                      "role": role, "reserved_usd": reserved_usd,
                      "detail": detail})
        return request_id

    def settle(self, request_id: str, *, cost_usd: float | None,
               usage: dict | None, raw_reference: str) -> None:
        request = self._by_request().get(request_id)
        if not request or "reserved" not in request:
            raise BudgetError(f"{request_id} was never reserved")
        if self._is_closed(request):
            raise BudgetError(f"{request_id} is already closed; one settlement "
                              f"per request")
        if cost_usd is None or usage is None:
            self._append({"event": "unknown_usage", "request_id": request_id,
                          "raw_reference": raw_reference})
            raise BudgetError(
                f"{request_id}: provider usage is unknown, so the call cannot be "
                f"settled. Stopping rather than assuming zero.")
        cost = float(cost_usd)
        if not math.isfinite(cost) or cost < 0:
            self._append({"event": "invalid_cost", "request_id": request_id,
                          "reported_cost_usd": str(cost_usd),
                          "raw_reference": raw_reference})
            raise BudgetError(f"{request_id}: reported cost {cost_usd!r} is not "
                              f"a finite non-negative number")
        reserved = float(request["reserved"].get("reserved_usd") or 0.0)
        if cost > reserved + 1e-9:
            self._append({"event": "reservation_insufficient",
                          "request_id": request_id, "reserved_usd": reserved,
                          "reported_cost_usd": cost,
                          "raw_reference": raw_reference})
            raise BudgetError(
                f"{request_id}: cost {cost} exceeds its reservation {reserved}. "
                f"The reservation was not a conservative upper bound, so the "
                f"run stops instead of absorbing the difference.")
        self._append({"event": "settled", "request_id": request_id,
                      "role": request["reserved"]["role"],
                      "cost_usd": cost, "usage": usage,
                      "raw_reference": raw_reference})

    def release(self, request_id: str, *, reason: str) -> None:
        """Release a reservation for a request that PROVABLY never left."""
        request = self._by_request().get(request_id)
        if not request or "reserved" not in request:
            raise BudgetError(f"{request_id} was never reserved")
        if self._is_closed(request):
            raise BudgetError(f"{request_id} is already closed")
        if "unknown_outcome" in request:
            raise BudgetError(
                f"{request_id} was dispatched and its outcome is unknown; it "
                f"may not be released as unspent")
        self._append({"event": "released", "request_id": request_id,
                      "role": request["reserved"]["role"], "reason": reason})

    def mark_unknown_outcome(self, request_id: str, *, reason: str,
                             raw_reference: str) -> None:
        """The request was dispatched and we do not know what it cost.

        The reservation is deliberately left open: a server may have processed
        and charged the request even though no response arrived.
        """
        request = self._by_request().get(request_id)
        if not request or "reserved" not in request:
            raise BudgetError(f"{request_id} was never reserved")
        if self._is_closed(request):
            raise BudgetError(f"{request_id} is already closed")
        self._append({"event": "unknown_outcome", "request_id": request_id,
                      "role": request["reserved"]["role"], "reason": reason,
                      "raw_reference": raw_reference})

    def reconcile_unknown_outcome(self, request_id: str, *, cost_usd: float,
                                  usage: dict, raw_reference: str) -> None:
        """Close an unknown outcome once its real usage is known."""
        request = self._by_request().get(request_id)
        if not request or "unknown_outcome" not in request:
            raise BudgetError(f"{request_id} has no unknown outcome to reconcile")
        self._append({"event": "reconciling", "request_id": request_id,
                      "raw_reference": raw_reference})
        self.settle(request_id, cost_usd=cost_usd, usage=usage,
                    raw_reference=raw_reference)

    def summary(self) -> dict:
        by_request = self._by_request()
        return {"ledger": str(self.path),
                "requests": len(by_request),
                "settled": sum(1 for r in by_request.values() if "settled" in r),
                "released": sum(1 for r in by_request.values() if "released" in r),
                "open_reservations": sum(
                    1 for r in by_request.values()
                    if "reserved" in r and not self._is_closed(r)),
                "unknown_outcomes": len(self.unresolved_unknown_outcomes()),
                "unknown_usage_events": sum(
                    1 for e in self.entries if e["event"] == "unknown_usage"),
                "invalid_cost_events": sum(
                    1 for e in self.entries if e["event"] == "invalid_cost"),
                "reservation_insufficient_events": sum(
                    1 for e in self.entries
                    if e["event"] == "reservation_insufficient"),
                "committed_usd": self.committed_usd(),
                "total_cap_usd": self.total_cap_usd,
                "role_caps_usd": self.role_caps_usd}


# ===========================================================================
# Request rendering — one builder per role kind
# ===========================================================================
def _counterparty_request(observation: dict, role: str) -> dict:
    system = [
        f"You are acting as: {observation.get('role') or role}.",
        observation.get("role_description") or "",
        "Your objective in this episode:",
        observation.get("arm_objective") or "",
        "You may only act with the tool and arguments described in the action "
        "schema. Any other path is refused and recorded.",
        "You cannot see the other side's decision, its internal records, or any "
        "grading information.",
    ]
    user = {
        "what_you_can_see": observation.get("readable"),
        "task_brief": observation.get("task_brief"),
        "writable_surface": observation.get("writable_surface"),
        "action_schema": observation.get("action_schema"),
        "trigger": observation.get("trigger"),
    }
    return {"role": role, "role_kind": "counterparty",
            "messages": [
                {"role": "system", "content": "\n".join(p for p in system if p)},
                {"role": "user", "content": json.dumps(
                    user, ensure_ascii=False, sort_keys=True, indent=1)}],
            "response_contract": {
                "type": "object", "required": ["actions"],
                "properties": {"actions": {
                    "type": "array", "minItems": 0, "maxItems": 1,
                    "items": observation.get("action_schema")}}}}


def _business_response_contract(observation: dict) -> dict:
    """The action contract from THIS role's real tools.

    Built from the driver's own `available_actions`, so a role keeps every tool
    it was given — not forced into `writes`, and not reduced to the commit tool.
    """
    actions = observation.get("available_actions")
    if not isinstance(actions, list) or not actions:
        return {"type": "object", "required": ["actions"],
                "note": "this role's tools are described in the observation "
                        "above; no separate action list was supplied by the "
                        "driver",
                "properties": {"actions": {"type": "array", "maxItems": 1}}}
    options = []
    for action in actions:
        if not isinstance(action, dict) or not action.get("name"):
            continue
        required = [str(name) for name in
                    (action.get("required_arguments") or [])]
        option = {"type": "object", "required": ["tool", "arguments"],
                  "properties": {
                      "tool": {"const": action["name"]},
                      "arguments": {"type": "object", "required": required}}}
        if action.get("description"):
            option["description"] = action["description"]
        options.append(option)
    return {"type": "object", "required": ["actions"],
            "properties": {"actions": {
                "type": "array", "minItems": 1, "maxItems": 1,
                "items": {"oneOf": options}}}}


def _business_request(observation: dict, role: str,
                      role_description: str | None = None) -> dict:
    """A request built from what the ORIGINAL driver authorised for this role.

    The observation is passed through as the driver produced it: that is exactly
    the information the Case already grants this role, so nothing private is
    added and nothing authorised is dropped. No counterparty-only wording is
    applied.
    """
    actions = [action.get("name") for action in
               (observation.get("available_actions") or [])
               if isinstance(action, dict) and action.get("name")]
    system = [
        f"You are acting as: {role}.",
        role_description or "",
        "Your task:",
        str(observation.get("instruction") or
            "see the observation below; the driver supplied no separate "
            "instruction for this role"),
        ("The tools available to you are: " + ", ".join(actions) + ". "
         "Use exactly one of them, with the arguments it requires."
         if actions else
         "Act with the tools described in the observation below."),
        "Everything you need is in the observation. There is no other source "
        "of information, and no grading information is available to you.",
    ]
    return {"role": role, "role_kind": "business",
            "messages": [
                {"role": "system", "content": "\n".join(p for p in system if p)},
                {"role": "user", "content": json.dumps(
                    {"observation": observation}, ensure_ascii=False,
                    sort_keys=True, indent=1)}],
            "response_contract": _business_response_contract(observation)}


def render_request(observation: dict, *, role: str,
                   role_kind: str = "counterparty",
                   role_description: str | None = None) -> dict:
    """Render the request a provider would receive, for either role kind."""
    if role_kind not in ROLE_KINDS:
        raise ValueError(f"role_kind must be one of {ROLE_KINDS}")
    if role_kind == "counterparty":
        return _counterparty_request(observation, role)
    return _business_request(observation, role, role_description)


# ===========================================================================
# Policy
# ===========================================================================
class ProviderPolicy:
    """A callable policy backed by an injected provider client.

    Declares `owns_cost_ledger`, so the scheduler's own budget steps back to
    recording receipts and cannot veto an authorised request with a zero-dollar
    default or debit it twice.
    """

    is_language_model = True
    owns_cost_ledger = True

    def __init__(self, *, role: str, client, ledger: PersistentLedger,
                 reserve_usd: float, transcript_dir: Path,
                 model: str = "unspecified", role_kind: str = "counterparty",
                 role_description: str | None = None):
        if role_kind not in ROLE_KINDS:
            raise ValueError(f"role_kind must be one of {ROLE_KINDS}")
        for name in FORBIDDEN_ENVIRONMENT:
            if name in os.environ and client is None:
                raise BudgetError(
                    "a credential is present in the environment but no client "
                    "was injected; this module does not read credentials")
        self.role = role
        self.role_kind = role_kind
        self.role_description = role_description
        self.client = client
        self.ledger = ledger
        self.reserve_usd = float(reserve_usd)
        self.model = model
        self.transcript_dir = Path(transcript_dir)
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        self.calls = 0
        self.halted_reason: str | None = None
        unresolved = ledger.unresolved_unknown_outcomes()
        if unresolved:
            # A restart does not clear an unknown outcome.
            self.halted_reason = (
                f"{len(unresolved)} dispatched request(s) from an earlier run "
                f"have an unknown outcome and must be reconciled first")

    def describe(self) -> dict:
        # `is_simulated` is None when the client does not declare it. That is
        # reported as unknown rather than defaulted either way: an aggregate
        # must not claim "offline" about a client it cannot identify.
        declared = getattr(self.client, "is_simulated", None)
        return {"name": f"provider-{self.model}-{self.role}",
                "kind": "provider_policy", "is_language_model": True,
                "owns_cost_ledger": True, "model": self.model,
                "is_simulated": None if declared is None else bool(declared),
                "role": self.role, "role_kind": self.role_kind,
                "reserve_usd_per_call": self.reserve_usd}

    def _store(self, request_id: str, payload: dict) -> str:
        path = self.transcript_dir / f"{request_id}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=1)
                        + "\n", encoding="utf-8")
        return str(path)

    def __call__(self, observation: dict) -> dict:
        if self.halted_reason:
            return {"actions": [],
                    "_adapter": {"failure": "provider_halted",
                                 "detail": self.halted_reason,
                                 "cost_known": True, "cost_usd": 0.0}}
        request = render_request(observation, role=self.role,
                                 role_kind=self.role_kind,
                                 role_description=self.role_description)
        request_id = self.ledger.reserve(
            role=self.role, reserved_usd=self.reserve_usd,
            detail={"model": self.model, "role_kind": self.role_kind,
                    "arm": observation.get("arm")})
        stored = self._store(request_id, {"request": request,
                                          "reserved_usd": self.reserve_usd})
        if self.client is None:
            self.ledger.release(request_id, reason="no client injected")
            return {"actions": [],
                    "_adapter": {"failure": "no_provider_client",
                                 "cost_known": True, "cost_usd": 0.0,
                                 "request_id": request_id,
                                 "request_reference": stored}}

        try:
            reply = self.client(request)
        except NotDispatched as exc:
            # The transport asserts the request never left. Only an explicit
            # assertion releases a reservation; see `NotDispatched`.
            detail = f"{type(exc).__name__}: {exc}"
            stored = self._store(request_id, {"request": request,
                                              "error": detail,
                                              "dispatched": False})
            self.ledger.release(request_id, reason=f"never sent: {detail}")
            return {"actions": [],
                    "_adapter": {"failure": "provider_not_sent",
                                 "cost_known": True, "cost_usd": 0.0,
                                 "request_id": request_id,
                                 "request_reference": stored}}
        except Exception as exc:                                  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            stored = self._store(request_id, {"request": request,
                                              "error": detail,
                                              "dispatched": "unknown"})
            # Possibly dispatched, outcome unknown. The server may have
            # processed and charged it, so the reservation stays and nothing
            # else is sent.
            self.ledger.mark_unknown_outcome(
                request_id, reason=detail, raw_reference=stored)
            self.halted_reason = (
                f"request {request_id} was dispatched and its outcome is "
                f"unknown ({detail}); no further requests will be sent until it "
                f"is reconciled")
            return {"actions": [],
                    "_adapter": {"failure": "provider_unknown_outcome",
                                 "detail": detail,
                                 "cost_known": False,
                                 "request_id": request_id,
                                 "request_reference": stored,
                                 "reservation_kept_usd": self.reserve_usd}}

        raw = reply.get("raw") if isinstance(reply, dict) else None
        usage = reply.get("usage") if isinstance(reply, dict) else None
        cost = reply.get("cost_usd") if isinstance(reply, dict) else None
        stored = self._store(request_id, {"request": request, "response": raw,
                                          "usage": usage, "cost_usd": cost})
        self.ledger.settle(request_id, cost_usd=cost, usage=usage,
                           raw_reference=stored)
        self.calls += 1
        actions = reply.get("actions") if isinstance(reply, dict) else None
        return {"actions": actions if isinstance(actions, list) else [],
                "_adapter": {"cost_known": True, "cost_usd": float(cost),
                             "tokens": int((usage or {}).get("total_tokens", 0)),
                             "request_id": request_id,
                             "request_reference": stored,
                             "model": self.model,
                             "cost_ledger": str(self.ledger.path)}}


# ===========================================================================
# Fake provider
# ===========================================================================
class FakeProvider:
    """A deterministic stand-in for a provider client. No network, no cost.

    `is_simulated` is read by `ProviderPolicy.describe()` and ends up in the
    episode, so a downstream aggregate can tell a stand-in from a real provider
    without guessing from a model name.

    It reads the rendered request the way a model would have to — the objective
    and tools out of the system message, the facts out of the user message — and
    answers in the declared shape for whichever role kind it was sent.
    """

    is_simulated = True

    def __init__(self, *, behaviour: str = "cooperative",
                 usage_tokens: int = 128, cost_usd: float = 0.0,
                 malformed: bool = False, omit_usage: bool = False,
                 negative_cost: bool = False, huge_cost: bool = False):
        self.behaviour = behaviour
        self.usage_tokens = usage_tokens
        self.cost_usd = cost_usd
        self.malformed = malformed
        self.omit_usage = omit_usage
        self.negative_cost = negative_cost
        self.huge_cost = huge_cost
        self.seen: list[dict] = []

    # --- per role kind --------------------------------------------------
    def _counterparty_actions(self, user: dict, schema: dict) -> list:
        surface = user.get("writable_surface") or []
        readable = user.get("what_you_can_see") or {}
        writes = []
        for item in surface:
            path = str(item.get("path"))
            root, _, field = path.partition(".")
            current = readable.get(root)
            if isinstance(current, dict) and field in current:
                writes.append({"path": path, "value": current[field]})
        return [{"tool": schema.get("tool"), "arguments": {"writes": writes}}]

    def _business_actions(self, user: dict) -> list:
        """Pick a declared tool and fill its required arguments from the facts."""
        observation = user.get("observation") or {}
        actions = [action for action in
                   (observation.get("available_actions") or [])
                   if isinstance(action, dict) and action.get("name")]
        if not actions:
            return []
        chosen = actions[0]
        contract = observation.get("operation_contract") or {}
        artifact = observation.get("artifact") or {}
        arguments: dict[str, Any] = {}
        for name in (chosen.get("required_arguments") or []):
            if name in contract:
                arguments[name] = contract[name]
            elif name in artifact:
                arguments[name] = artifact[name]
            elif name == "reason":
                arguments[name] = ("stand-in reason recorded by the offline "
                                   "fake provider")
            elif name in observation:
                arguments[name] = observation[name]
            else:
                arguments[name] = None
        return [{"tool": chosen["name"], "arguments": arguments}]

    def __call__(self, request: dict) -> dict:
        self.seen.append(request)
        user = json.loads(request["messages"][1]["content"])
        kind = request.get("role_kind", "counterparty")
        if kind == "counterparty":
            schema = user.get("action_schema") or {}
            actions = self._counterparty_actions(user, schema)
        else:
            actions = self._business_actions(user)
        reply: dict[str, Any] = {
            "actions": actions,
            "raw": {"stub": True, "behaviour": self.behaviour,
                    "role_kind": kind,
                    "system_seen": request["messages"][0]["content"][:600]},
            "cost_usd": self.cost_usd,
            "usage": {"total_tokens": self.usage_tokens},
        }
        if self.malformed:
            reply["actions"] = [{"tool": "not_the_declared_tool",
                                 "arguments": {"writes": "not-a-list"}}]
        if self.negative_cost:
            reply["cost_usd"] = -1.0
        if self.huge_cost:
            reply["cost_usd"] = 10.0
        if self.omit_usage:
            reply.pop("usage", None)
            reply.pop("cost_usd", None)
        return reply


class RealProviderClient:
    """Placeholder for a real transport. Deliberately not implemented."""

    def __init__(self, *args, **kwargs):
        raise RealTransportNotImplemented(
            "No real provider transport exists in this package. A real run "
            "needs a transport implementation, a price table, a hard cap and an "
            "explicit authorisation. It is not 'just add a key'.")


def build_policy(*, role: str, client, ledger: PersistentLedger,
                 reserve_usd: float, transcript_dir: Path,
                 model: str = "fake", role_kind: str = "counterparty",
                 role_description: str | None = None) -> ProviderPolicy:
    """The factory. Any business role, any declared tool, one shared ledger."""
    return ProviderPolicy(role=role, client=client, ledger=ledger,
                          reserve_usd=reserve_usd,
                          transcript_dir=transcript_dir, model=model,
                          role_kind=role_kind,
                          role_description=role_description)


def build_business_policies(profile: dict, *, client_factory, ledger,
                            reserve_usd: float, transcript_dir: Path,
                            model: str = "fake"):
    """One provider policy per business role, matching the Case's own mode.

    A single-agent Case gets one policy; a role-chain Case gets one per declared
    role, so the chain runs as itself rather than being flattened.
    """
    business = profile["business_role"]
    if business["agent_mode"] == "single":
        return build_policy(
            role=business["name"], client=client_factory(business["name"]),
            ledger=ledger, reserve_usd=reserve_usd,
            transcript_dir=Path(transcript_dir) / business["name"], model=model,
            role_kind="business",
            role_description=f"the business agent of {profile['case_id']}, "
                             f"committing as {business['commit_agent']}")
    return {role: build_policy(
        role=role, client=client_factory(role), ledger=ledger,
        reserve_usd=reserve_usd,
        transcript_dir=Path(transcript_dir) / role, model=model,
        role_kind="business",
        role_description=f"the {role} role in {profile['case_id']}'s declared "
                         f"chain {business['role_chain']}")
        for role in business["role_chain"]}
