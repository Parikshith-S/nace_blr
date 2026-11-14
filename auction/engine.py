"""Decision loop per player:
NDI profile -> 3 parallel Drex bid decisions -> auctioneer resolves -> Drex explanation
-> update purses & squads -> log -> next player."""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from auction import commentary, config, drex
from auction.agents import Auctioneer, Commissioner, FranchiseAgent
from auction.ndi import load_profiles
from auction.source_data import LOT_ORDER


class Auction:
    def __init__(self, data: dict | None = None, n_lots: int | None = None) -> None:
        self.data = data or load_profiles()
        self.rules = self.data["rules"]
        self.agents = {t["team_id"]: FranchiseAgent(t, self.rules) for t in self.data["teams"]}
        self.names = {tid: a.name for tid, a in self.agents.items()}
        self.auctioneer = Auctioneer(self.rules)
        self.commissioner = Commissioner(self.names)
        self.purses = {tid: float(self.rules["purse_cr"]) for tid in self.agents}
        self.squads: dict[str, list[dict]] = {tid: [] for tid in self.agents}
        by_id = {p["player_id"]: p for p in self.data["players"]}
        order = [pid for pid in LOT_ORDER if pid in by_id] + [pid for pid in by_id if pid not in LOT_ORDER]
        self.lots = [by_id[pid] for pid in order][: n_lots or config.AUCTION_LOTS]
        self.log: list[dict] = []
        self.started = datetime.now().strftime("%Y%m%d_%H%M%S")

    @property
    def done(self) -> bool:
        return len(self.log) >= len(self.lots)

    def run_lot(self) -> dict:
        player = self.lots[len(self.log)]
        t0 = time.perf_counter()
        with ThreadPoolExecutor(len(self.agents)) as pool:
            futs = {
                tid: pool.submit(a.decide, player, list(self.squads[tid]), self.purses[tid],
                                 {r: self.purses[r] for r in self.agents if r != tid})
                for tid, a in self.agents.items()
            }
            bids = [futs[tid].result() for tid in self.agents]
        result = self.auctioneer.resolve(player, bids, self.squads, self.purses, self.agents)
        explanation = self.commissioner.explain(player, bids, result)
        if result["status"] == "SOLD":
            w = result["winner"]
            self.purses[w] = round(self.purses[w] - result["price"], 2)
            self.squads[w].append({"player_id": player["player_id"], "name": player["name"], "price": result["price"],
                                   "tags": player.get("tags", []), "overseas": player.get("overseas", False),
                                   "role": player.get("role")})
        summary = "; ".join(f"{self.names[b.team_id]} {b.decision} {b.max_price:.2f}" for b in bids)
        entry = {
            "lot": len(self.log) + 1, "player": player, "bids": [b.as_dict() for b in bids], "result": result,
            "explanation": explanation, "commentary": commentary.line(player, result, self.names.get(result["winner"]), summary),
            "purses_after": dict(self.purses), "latency_s": round(time.perf_counter() - t0, 2),
        }
        self.log.append(entry)
        self._save()
        return entry

    def run_all(self):
        while not self.done:
            yield self.run_lot()

    def summary(self) -> dict:
        return {
            "squads": {self.names[t]: s for t, s in self.squads.items()},
            "purses": {self.names[t]: p for t, p in self.purses.items()},
            "spent": {self.names[t]: round(self.rules["purse_cr"] - p, 2) for t, p in self.purses.items()},
            "drex": drex.METRICS.summary(),
        }

    def _save(self) -> None:
        config.LOG_DIR.mkdir(exist_ok=True)
        path = config.LOG_DIR / f"auction_{self.started}.json"
        path.write_text(json.dumps({"log": self.log, "summary": self.summary()}, indent=2, default=str))
