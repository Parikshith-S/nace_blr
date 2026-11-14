"""Drex = Nace's decision model ("System 1"), called through Intern's DecisionClient.

Drex does not write free text. It answers *typed questions* about a *state*:
  choice -> pick one named option (with probabilities)
  score  -> position on an ordered scale (we use it for the max price ladder)
  noul   -> probability a statement is true
Wire protocol (what intern.decisions sends): POST {DREX_BASE_URL}/systemone
  {"model": "drex-latest", "state": "...", "questions": {name: {type, instructions, criteria}}}

Every decision in the auction goes through ask(). With no NACE_API_KEY the caller's `mock` function answers,
so the whole pipeline still runs; the UI labels which mode is active.
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import defaultdict
from typing import Any, Callable

from pydantic import SecretStr

from auction import config

try:
    from intern.decisions import ChoiceQuestion, DecisionClient, DecisionsApiBackend, NoulQuestion, ScoreQuestion

    HAVE_INTERN = True
except ImportError:  # pragma: no cover
    HAVE_INTERN = False


# ---------------------------------------------------------------- question builders

def choice(instructions: str, criteria: dict[str, str]):
    return ChoiceQuestion(instructions=instructions, criteria=criteria)


def score(instructions: str, levels: list[str]):
    return ScoreQuestion(instructions=instructions, criteria=levels)


def noul(instructions: str):
    return NoulQuestion(instructions=instructions)


# ---------------------------------------------------------------- metrics

class Metrics:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.calls = 0
        self.questions = 0
        self.total_ms = 0.0
        self.cost_usd = 0.0
        self.input_tokens = 0
        self.output_tokens = 0
        self.errors = 0
        self.by_purpose: dict[str, int] = defaultdict(int)

    def record(self, purpose: str, n_questions: int, ms: float, cost: float = 0.0, tin: int = 0, tout: int = 0) -> None:
        with self.lock:
            self.calls += 1
            self.questions += n_questions
            self.total_ms += ms
            self.cost_usd += cost
            self.input_tokens += tin
            self.output_tokens += tout
            self.by_purpose[purpose.split(".")[0]] += 1

    def summary(self) -> dict[str, Any]:
        return {
            "mode": mode(),
            "drex_calls": self.calls,
            "questions_answered": self.questions,
            "avg_latency_ms": round(self.total_ms / self.calls, 1) if self.calls else 0,
            "total_cost_usd": round(self.cost_usd, 5),
            "cost_per_call_usd": round(self.cost_usd / self.calls, 6) if self.calls else 0,
            "tokens_in": self.input_tokens,
            "tokens_out": self.output_tokens,
            "errors": self.errors,
            "by_purpose": dict(self.by_purpose),
        }


METRICS = Metrics()


# ---------------------------------------------------------------- live client (one event loop in a thread)

class _Live:
    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        backend = DecisionsApiBackend(
            config.DREX_BASE_URL, SecretStr(config.DREX_API_KEY), config.DREX_MODELS, timeout_s=config.DREX_TIMEOUT_S
        )
        self.events: list[Any] = []

        def emit(event: Any) -> None:
            self.events.append(event)

        async def make() -> DecisionClient:
            return DecisionClient(backend, emit, timeout_s=config.DREX_TIMEOUT_S, retry_window_s=8)

        self.client = asyncio.run_coroutine_threadsafe(make(), self.loop).result()

    def ask(self, purpose: str, state: str, questions: dict) -> tuple[dict, Any]:
        n = len(self.events)
        fut = asyncio.run_coroutine_threadsafe(self.client.ask(purpose, state, questions), self.loop)
        answers = fut.result()
        ev = next((e for e in reversed(self.events[n:]) if getattr(e, "purpose", None) == purpose and e.ok), None)
        return {k: _plain(v) for k, v in answers.items()}, ev


def _plain(a: Any) -> dict:
    d = a.model_dump()
    d.pop("type", None)
    return d


_live: _Live | None = None
_live_lock = threading.Lock()
_disabled: str | None = None  # set after an auth/billing failure: stop retrying, report honestly


def mode() -> str:
    if _disabled:
        return f"mock (live failed: {_disabled})"
    return "live" if (HAVE_INTERN and config.DREX_API_KEY) else "mock"


def ask(purpose: str, state: str, questions: dict, *, mock: Callable[[], dict]) -> dict:
    """Ask Drex. Returns {name: {"choice"/"score"/"noul": ..., "probabilities": ...}}; score is 0..1."""
    global _live, _disabled
    t0 = time.perf_counter()
    if mode() == "live":
        with _live_lock:
            if _live is None:
                _live = _Live()
        try:
            answers, ev = _live.ask(purpose, state, questions)
            ms = ev.duration_ms if ev else (time.perf_counter() - t0) * 1000
            METRICS.record(purpose, len(questions), ms, ev.cost_usd if ev else 0, ev.input_tokens if ev else 0,
                           ev.output_tokens if ev else 0)
            return answers
        except Exception as e:  # keep the demo alive; count it
            METRICS.errors += 1
            # 401 bad key, 402 no credit: retrying won't help, so stop paying the retry window on every lot
            code = next((c for c in ("401", "402", "403") if f"'{c} " in str(e)), None)
            if code:
                _disabled = f"HTTP {code}"
            print(f"[drex] {purpose} failed, using mock: {e}")
    answers = mock()
    METRICS.record(purpose, len(questions), (time.perf_counter() - t0) * 1000)
    return answers


def ping() -> str:
    """Connectivity check for setup: `python -m auction.drex`."""
    a = ask("check", "A connectivity check for the IPL auction swarm.",
            {"ok": noul("Is this a connectivity check?")}, mock=lambda: {"ok": {"noul": 1.0}})
    return f"mode={mode()} answer={a} metrics={METRICS.summary()}"


def doctor() -> None:
    """Try each key variable against the configured Drex endpoint. Prints status codes only, never key values."""
    import os

    import httpx

    body = {"state": "connectivity check", "questions": {"ok": {"type": "noul", "instructions": "Is this a connectivity check?"}}}
    url = f"{config.DREX_BASE_URL.rstrip('/')}/systemone"
    for name in ("NACE_API_KEY", "DREX_API_KEY"):
        raw = os.getenv(name) or ""
        if not raw:
            print(f"{name}: not set")
            continue
        k = raw.strip().strip("'\"").strip()
        print(f"{name}: set, length {len(k)}, starts nace_sk_: {k.startswith('nace_sk_')}, cleaned quotes/whitespace: {k != raw}")
        for model in config.DREX_MODELS:
            try:
                r = httpx.post(url, json=body | {"model": model}, headers={"Authorization": f"Bearer {k}"}, timeout=20)
                print(f"   {model} @ {url} -> HTTP {r.status_code} {r.text[:120]!r}")
            except Exception as e:
                print(f"   {model} @ {url} -> {type(e).__name__}: {e}")
    print(f"\nThe app uses {config.DREX_KEY_VAR or 'no key'} against {config.DREX_BASE_URL}")


if __name__ == "__main__":
    import sys

    doctor() if "--doctor" in sys.argv else print(ping())
