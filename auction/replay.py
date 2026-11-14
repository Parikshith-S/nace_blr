"""Replay a recorded live auction (results/final_run.json) lot by lot.

Same surface the Streamlit board reads from engine.Auction (data, rules, agents, names, purses, squads,
lots, log, done, run_lot), but every bid, price and explanation comes from the recorded live Drex run.
Nothing calls Drex, so a public link costs no credit and needs no API key.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from auction.config import ROOT
from auction.ndi import load_profiles

DEFAULT_RUN = ROOT / "results" / "final_run.json"


class ReplayAuction:
    replay = True

    def __init__(self, path: Path = DEFAULT_RUN, data: dict | None = None) -> None:
        run = json.loads(Path(path).read_text())
        self.recorded = run["log"]
        self.recorded_metrics = run["summary"]["drex"]
        self.data = data or load_profiles(verbose=False)
        self.rules = self.data["rules"]
        self.names = {t["team_id"]: t["name"] for t in self.data["teams"]}
        self.agents = {tid: SimpleNamespace(name=n) for tid, n in self.names.items()}
        self.purses = {tid: float(self.rules["purse_cr"]) for tid in self.names}
        self.squads: dict[str, list[dict]] = {tid: [] for tid in self.names}
        self.lots = [e["player"] for e in self.recorded]
        self.log: list[dict] = []

    @property
    def done(self) -> bool:
        return len(self.log) >= len(self.recorded)

    def run_lot(self) -> dict:
        entry = self.recorded[len(self.log)]
        r, p = entry["result"], entry["player"]
        if r["status"] == "SOLD":
            self.squads[r["winner"]].append({"player_id": p["player_id"], "name": p["name"], "price": r["price"],
                                             "tags": p.get("tags", []), "overseas": p.get("overseas", False),
                                             "role": p.get("role")})
        self.purses = {k: float(v) for k, v in entry["purses_after"].items()}
        self.log.append(entry)
        return entry
