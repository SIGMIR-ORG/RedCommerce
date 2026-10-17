"""Callable-policy and budget contract. Coordinator-owned; workers do not fork it.

Reuses the R25 principles without reusing its C03 specifics:

  policy(observation) -> {"actions": [...], "_adapter": {...}}
  every invocation receives a deep copy, never the mutable world
  one declared action per invocation; extras are recorded and dropped
  separate per-role budgets, reserve before call, settle after measured usage
  an unknown provider cost stops the run instead of being assumed zero

No credential is read and no network backend is implemented here. A real
provider policy is injected by the coordinator at experiment time; the offline
policies below are explicitly not models.
"""
from __future__ import annotations

import copy
import json
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path


class BudgetStop(Exception):
    """Raised on a cap or an unknown provider cost. Never swallowed."""


@dataclass
class RoleBudget:
    """Per-role call accounting for the scheduler.

    NOT a payable interface: `reserve` pre-checks only the call count, and the
    dollar figure is seen at settle time, after a call. That is safe for offline
    policies and is why the payable path lives in `provider.py`.

    `cost_authority` decides who may debit. When a policy owns a persistent
    ledger (`owns_cost_ledger`), the scheduler creates its budget with
    `cost_authority=False`: receipts are still recorded here, but the dollar cap
    is not enforced twice and a zero-dollar default can no longer veto a request
    the ledger has already authorised and settled.
    """

    role: str
    max_calls: int
    max_cost_usd: float = 0.0
    cost_authority: bool = True
    cost_ledger: str | None = None
    calls: int = 0
    model_calls: int = 0
    cost_usd: float = 0.0
    tokens: int = 0
    receipts: list = field(default_factory=list)

    def reserve(self, detail: dict) -> dict:
        if self.calls >= self.max_calls:
            raise BudgetStop(f"{self.role}: call cap {self.max_calls} reached")
        reservation = {"role": self.role, "seq": self.calls + 1,
                       "reserved_at": time.time(), "detail": detail,
                       "status": "reserved"}
        self.receipts.append(reservation)
        return reservation

    def settle(self, reservation: dict, *, cost_known: bool,
               cost_usd: float | None = None, tokens: int | None = None,
               measured: dict | None = None, is_model: bool = False) -> None:
        if reservation.get("status") != "reserved":
            raise BudgetStop(f"{self.role}: settling a reservation that is not open")
        if not cost_known:
            reservation["status"] = "unknown_cost"
            raise BudgetStop(f"{self.role}: provider usage unknown; stopping")
        amount = float(cost_usd or 0.0)
        if self.cost_authority and (self.cost_usd + amount
                                    > self.max_cost_usd + 1e-9):
            reservation["status"] = "over_cap"
            raise BudgetStop(f"{self.role}: cost cap exceeded")
        self.calls += 1
        if is_model:
            # An invocation is not a model call. A frozen-content or offline
            # script policy consumes an opportunity but calls no provider, and
            # the fixed arm's claim of zero counterparty model use is checked
            # against this counter rather than against the opportunity count.
            self.model_calls += 1
        self.cost_usd += amount
        self.tokens += int(tokens or 0)
        reservation.update({"status": "settled", "cost_usd": amount,
                            "tokens": tokens, "is_model_call": bool(is_model),
                            "measured": measured or {}})

    def summary(self) -> dict:
        return {"role": self.role, "calls": self.calls,
                "model_calls": self.model_calls,
                "cost_usd": round(self.cost_usd, 6), "tokens": self.tokens,
                "max_calls": self.max_calls, "max_cost_usd": self.max_cost_usd,
                "cost_authority": self.cost_authority,
                "cost_ledger": self.cost_ledger,
                "unsettled": sum(1 for r in self.receipts
                                 if r.get("status") == "reserved")}


class ScriptPolicy:
    """An offline policy run as a subprocess. Deterministic, zero provider cost."""

    is_language_model = False

    def __init__(self, command, name: str, timeout_sec: int = 60):
        self.command = [str(part) for part in command]
        self.name = name
        self.timeout_sec = timeout_sec

    def describe(self) -> dict:
        return {"name": self.name, "kind": "offline_script",
                "is_language_model": False, "command": self.command}

    def __call__(self, observation: dict) -> dict:
        payload = json.dumps(copy.deepcopy(observation), ensure_ascii=False,
                             allow_nan=False)
        started = time.perf_counter()
        try:
            completed = subprocess.run(self.command, input=payload, text=True,
                                       capture_output=True, check=False,
                                       timeout=self.timeout_sec)
        except subprocess.TimeoutExpired:
            return {"actions": [], "_adapter": {"failure": "timeout",
                                                "cost_known": True, "cost_usd": 0.0}}
        latency = int((time.perf_counter() - started) * 1000)
        if completed.returncode != 0:
            return {"actions": [], "_adapter": {"failure": "nonzero_exit",
                                                "stderr": completed.stderr[-400:],
                                                "cost_known": True, "cost_usd": 0.0,
                                                "latency_ms": latency}}
        try:
            reply = json.loads(completed.stdout)
        except Exception:
            return {"actions": [], "_adapter": {"failure": "malformed_output",
                                                "raw": completed.stdout[-400:],
                                                "cost_known": True, "cost_usd": 0.0,
                                                "latency_ms": latency}}
        adapter = reply.get("_adapter") or {}
        adapter.setdefault("cost_known", True)
        adapter.setdefault("cost_usd", 0.0)
        adapter.setdefault("tokens", 0)
        adapter["latency_ms"] = latency
        reply["_adapter"] = adapter
        return reply


class FrozenContentPolicy:
    """The fixed arm: replay the Case's own frozen content, zero model calls."""

    is_language_model = False

    def __init__(self, writes: list, name: str = "frozen_source_content"):
        self.writes = copy.deepcopy(writes)
        self.name = name

    def describe(self) -> dict:
        return {"name": self.name, "kind": "frozen_source_content",
                "is_language_model": False, "model_calls": 0,
                "note": "Replays the source Case content independent of any "
                        "business-agent question."}

    def __call__(self, observation: dict) -> dict:
        return {"actions": [{"tool": "submit_counterparty_content",
                             "arguments": {"writes": copy.deepcopy(self.writes)}}],
                "_adapter": {"cost_known": True, "cost_usd": 0.0, "tokens": 0,
                             "frozen": True, "model_calls": 0}}


def invoke(policy, observation: dict, budget: RoleBudget, detail: dict) -> dict:
    """Reserve, call with a deep copy, settle on measured usage."""
    reservation = budget.reserve(detail)
    is_model = bool(getattr(policy, "is_language_model", False))
    reply = policy(copy.deepcopy(observation))
    adapter = (reply or {}).get("_adapter") or {}
    budget.settle(reservation, cost_known=bool(adapter.get("cost_known")),
                  cost_usd=adapter.get("cost_usd"),
                  tokens=adapter.get("tokens"), measured=adapter,
                  is_model=is_model)
    return reply or {"actions": []}
