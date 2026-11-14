"""The swarm: 3 FranchiseAgents, 1 Auctioneer, 1 Commissioner.

Every *decision* is a Drex ask (auction.drex -> Intern DecisionClient -> console /systemone):
  FranchiseAgent.decide   -> 1 Drex call, 5 typed questions (BID/PASS, max-price ladder, need fit,
                              injury concern, which evidence matters most)
  Commissioner.explain    -> 1 Drex call: why the winner won + why each other team lost
The Auctioneer is deterministic rules (purse, squad cap, overseas limit, second-price + increment).

Reasons are assembled from Drex's choices over *cited evidence items* pulled from NDI output, so every
sentence on screen points at a document line.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from auction import drex

NEED_FIT_LEVELS = [
    "Does not match any need stated in our brief",
    "Depth / nice-to-have, not a stated need",
    "Matches a lower-priority stated need",
    "Matches our TOP-priority stated need",
]


def cr(x: float) -> str:
    return f"₹{x:.2f} Cr"


def _round(x: float, inc: float) -> float:
    return round(round(x / inc) * inc, 2)


@dataclass
class Evidence:
    id: str
    text: str
    source: str

    def cite(self) -> str:
        return f"“{self.text}” [{self.source}]"


@dataclass
class Bid:
    team_id: str
    decision: str  # BID / PASS
    max_price: float
    reason: str
    evidence: list[Evidence]
    need_fit: float = 0.0
    injury_concern: float = 0.0
    confidence: float = 0.0
    ladder: list[float] = field(default_factory=list)
    note: str = ""  # auctioneer annotations (clamped / ineligible)

    def as_dict(self) -> dict:
        return {
            "team_id": self.team_id, "decision": self.decision, "max_price": self.max_price, "reason": self.reason,
            "evidence": [e.__dict__ for e in self.evidence], "need_fit": round(self.need_fit, 2),
            "injury_concern": round(self.injury_concern, 2), "confidence": round(self.confidence, 2), "note": self.note,
        }


class InternAgent:
    """Base for the swarm's agents: a name, a role, and Drex as its decision engine (Intern System 1)."""

    role = "agent"

    def __init__(self, name: str) -> None:
        self.name = name


# ======================================================================== Franchise

class FranchiseAgent(InternAgent):
    role = "franchise"

    def __init__(self, brief: dict, rules: dict) -> None:
        super().__init__(brief["name"])
        self.brief = brief
        self.rules = rules
        self.team_id = brief["team_id"]

    # ---------------------------------------------------------------- evidence
    def _evidence(self, player: dict, squad: list[dict], purse: float) -> list[Evidence]:
        ev: list[Evidence] = []
        pc, bc = player.get("citations", {}), self.brief.get("citations", {})

        def src(c: dict, key: str) -> str:
            x = c.get(key) or {}
            doc = (x.get("doc") or player.get("source", {}).get("doc", "?")).split("/")[-1]
            return f"{doc} p{x.get('page', 1)}"

        def add(text: str, source: str) -> None:
            if text:
                ev.append(Evidence(f"E{len(ev) + 1}", " ".join(str(text).split())[:220], source))

        s = {k: (int(v) if isinstance(v, float) and v.is_integer() else v) for k, v in player.get("stats", {}).items()}
        if s.get("death_economy") is not None:
            add(f"Death-overs economy {s['death_economy']}, {s.get('wickets')} wickets in {s.get('matches')} matches", src(pc, "stats.death_economy"))
        if s.get("strike_rate") and (s.get("runs") or 0) > 150:
            add(f"Strike rate {s['strike_rate']}, average {s.get('bat_avg')}, {s.get('runs')} runs", src(pc, "stats.strike_rate"))
        add(f"Scouting: {player.get('scouting')}", src(pc, "scouting"))
        add(f"Injury: {player.get('injury')} (risk {player.get('injury_risk')})", src(pc, "injury"))
        add(f"Base price {cr(player.get('base_price_cr') or 0)}; overseas={'yes' if player.get('overseas') else 'no'}; age {player.get('age')}", src(pc, "base_price_cr"))
        for n in self.brief.get("needs", []):
            add(f"Our Need {n['priority']} [{n['tag']}]: {n['text']}", src(bc, f"need.{n['tag']}"))
        add(f"Our budget policy: {self.brief.get('budget')}", src(bc, "budget"))
        add(f"Our risk policy: {self.brief.get('risk')}", src(bc, "risk"))
        add(f"Our overseas policy: {self.brief.get('overseas')}", src(bc, "overseas"))
        os_count = sum(1 for p in squad if p.get("overseas"))
        add(f"Our squad {len(squad)}/{self.rules['squad_cap']} ({os_count} overseas); purse left {cr(purse)}", "live auction state")
        return ev

    def affordable(self, squad: list[dict], purse: float) -> float:
        open_after = max(self.rules["squad_cap"] - len(squad) - 1, 0)
        return round(purse - open_after * self.rules["min_reserve_per_open_slot_cr"], 2)

    def ladder(self, base: float, hi: float) -> list[float]:
        inc = self.rules["bid_increment_cr"]
        if hi <= base:
            return [base, base]
        pts = sorted({_round(base + (hi - base) * (i / 7) ** 1.6, inc) for i in range(8)})
        return pts if len(pts) > 1 else [base, hi]

    # ---------------------------------------------------------------- decide
    def decide(self, player: dict, squad: list[dict], purse: float, rivals: dict[str, float]) -> Bid:
        base = player.get("base_price_cr") or 0.5
        hi = self.affordable(squad, purse)
        ladder = self.ladder(base, max(hi, base))
        ev = self._evidence(player, squad, purse)
        state = self._state(player, squad, purse, rivals, ev, hi)
        questions = {
            "decision": drex.choice(
                f"As the {self.name} franchise, should we bid on {player.get('name')}? Judge ONLY from our brief, "
                "the dossier, our squad and our purse.",
                {"BID": "Bid: the player fills a need in our brief and is worth buying within our budget and risk policy.",
                 "PASS": "Pass: no stated need, conflicts with our risk/overseas/budget policy, or we cannot afford a sensible price."},
            ),
            "max_price": drex.score(
                f"If we bid, what is the MOST we should pay for {player.get('name')}, given our budget policy "
                f"(including any per-player ceiling) and what is left in our purse?",
                [cr(x) for x in ladder],
            ),
            "need_fit": drex.score(f"How well does {player.get('name')} fit the needs in our brief?", NEED_FIT_LEVELS),
            "injury_concern": drex.noul(
                f"Our brief's risk policy would treat {player.get('name')}'s injury record as a reason NOT to buy."
            ),
            "key_evidence": drex.choice(
                "Which single evidence item most drives our decision on this player?",
                {e.id: e.text for e in ev},
            ),
        }
        ans = drex.ask(f"franchise.{self.team_id}", state, questions,
                       mock=lambda: self._mock(player, squad, purse, ladder, ev))
        return self._to_bid(player, ans, ladder, ev, hi)

    def _state(self, player, squad, purse, rivals, ev, hi) -> str:
        b = self.brief
        needs = "\n".join(f"  Need {n['priority']} [{n['tag']}]: {n['text']}" for n in b.get("needs", []))
        s = player.get("stats", {})
        return (
            f"ROLE: You are the bidding brain of the {b['name']} franchise in a SIMPLIFIED IPL-style auction.\n\n"
            f"OUR STRATEGY BRIEF ({b.get('source', {}).get('doc')}):\n{needs}\n  Budget: {b.get('budget')}\n"
            f"  Style: {b.get('style')}\n  Risk: {b.get('risk')}\n  Overseas: {b.get('overseas')}\n\n"
            f"PLAYER ON THE BLOCK ({player.get('source', {}).get('doc')}):\n"
            f"  {player.get('name')} | {player.get('role')} | tags {player.get('tags')} | age {player.get('age')} | "
            f"overseas {player.get('overseas')} | base {cr(player.get('base_price_cr') or 0)}\n"
            f"  Stats: {s}\n  Scouting: {player.get('scouting')}\n  Injury: {player.get('injury')} (risk {player.get('injury_risk')})\n\n"
            f"OUR SQUAD ({len(squad)}/{self.rules['squad_cap']}): {[p['name'] + ' (' + ','.join(p.get('tags', [])) + ')' for p in squad] or 'empty'}\n"
            f"OUR PURSE: {cr(purse)}; the most we can legally commit to this player: {cr(hi)}\n"
            f"RIVAL PURSES: {', '.join(f'{k} {cr(v)}' for k, v in rivals.items())}\n"
            f"RULES: overseas limit {self.rules['overseas_limit']}, squad cap {self.rules['squad_cap']}, winner pays one increment "
            f"({cr(self.rules['bid_increment_cr'])}) above the second-highest maximum.\n\n"
            "EVIDENCE ITEMS:\n" + "\n".join(f"  {e.id}: {e.text} [{e.source}]" for e in ev)
        )

    def _to_bid(self, player: dict, ans: dict, ladder: list[float], ev: list[Evidence], hi: float) -> Bid:
        decision = ans["decision"]["choice"]
        conf = float(ans["decision"].get("probabilities", {}).get(decision, 0) or 0)
        pos = float(ans["max_price"]["score"]) * (len(ladder) - 1)
        lo_i = int(pos)
        frac = pos - lo_i
        price = ladder[lo_i] if lo_i >= len(ladder) - 1 else ladder[lo_i] + frac * (ladder[lo_i + 1] - ladder[lo_i])
        price = min(_round(price, self.rules["bid_increment_cr"]), hi)
        need_fit = float(ans["need_fit"]["score"])
        inj = float(ans["injury_concern"]["noul"])
        probs = ans["key_evidence"].get("probabilities") or {}
        ranked = sorted(probs, key=lambda k: -probs[k]) if probs else []
        chosen = ans["key_evidence"]["choice"]
        ids = [chosen] + [k for k in ranked if k != chosen][:1]
        cited = [e for i in ids for e in ev if e.id == i]
        # always pair player evidence with a brief line (or vice versa) so the reason is grounded on both sides
        if len(cited) < 2:
            other = next((e for e in ev if e not in cited and ("Our" in e.text) != ("Our" in cited[0].text)), None) if cited else None
            if other:
                cited.append(other)
        fit_txt = NEED_FIT_LEVELS[round(need_fit * 3)].lower()
        if decision == "BID":
            reason = f"BID up to {cr(price)}: {fit_txt}."
        else:
            why = ("injury record conflicts with our risk policy" if inj >= 0.5
                   else "it does not fit our stated needs" if need_fit < 0.4
                   else "price/budget or squad constraints")
            reason = f"PASS: {why} ({fit_txt})."
            price = 0.0
        return Bid(self.team_id, decision, price, reason, cited, need_fit, inj, conf, ladder)

    # ---------------------------------------------------------------- mock (no Drex key)
    def _mock(self, player, squad, purse, ladder, ev) -> dict:
        """Deterministic stand-in for Drex so the pipeline runs offline. Live mode never uses this."""
        tid, tags = self.team_id, set(player.get("tags", []))
        prio = min((n["priority"] for n in self.brief.get("needs", []) if n["tag"] in tags), default=None)
        have = {t for p in squad for t in p.get("tags", [])}
        if prio and any(n["tag"] in have for n in self.brief["needs"] if n["priority"] == prio):
            prio += 2  # need already filled
        fit = {1: 1.0, 2: 0.67, 3: 0.55}.get(prio, 0.34 if prio else 0.0)
        g = re.search(r"Grade\s*([ABC][+-]?)", player.get("scouting") or "")
        quality = {"A": 1.0, "A-": 0.9, "B+": 0.78, "B": 0.62, "B-": 0.5}.get(g.group(1) if g else "", 0.6)
        risk = (player.get("injury_risk") or "low").lower()
        ceiling = {"HH": 13.0 if prio in (1, 2) else 4.0, "PP": 10.0 if prio else 2.0, "DS": 15.0 if prio == 1 else 6.0}.get(tid, 8.0)
        inj = {"low": 0.08, "medium": 0.45, "high": 0.8}.get(risk, 0.3)
        if tid == "DS" and risk != "low":
            inj = 0.92
        if tid == "HH" and risk == "high":
            inj = 0.85
        os_now = sum(1 for p in squad if p.get("overseas"))
        blocked = player.get("overseas") and ((tid == "PP" and os_now >= 1) or os_now >= self.rules["overseas_limit"])
        jitter = int(hashlib.md5(f"{tid}{player.get('player_id')}".encode()).hexdigest(), 16) % 100 / 1000
        target = (player.get("base_price_cr") or 0.5) + fit * quality * (ceiling - (player.get("base_price_cr") or 0.5)) * (0.85 + jitter)
        cheap = (player.get("base_price_cr") or 9) <= 1.0
        bid = (fit >= 0.5 or (fit > 0 and quality >= 0.75) or (quality >= 0.6 and cheap)) and inj < 0.5 and not blocked
        if not prio:
            ceiling = min(ceiling, (player.get("base_price_cr") or 0.5) + 1.5)
        target = min(target, ladder[-1])
        # invert ladder interpolation
        pos = 0.0
        for i in range(len(ladder) - 1):
            if ladder[i] <= target <= ladder[i + 1]:
                pos = i + (target - ladder[i]) / ((ladder[i + 1] - ladder[i]) or 1)
                break
        else:
            pos = len(ladder) - 1 if target >= ladder[-1] else 0
        need_ev = next((e.id for e in ev if e.text.startswith("Our Need") and any(f"[{t}]" in e.text for t in tags)), None)
        inj_ev = next(e.id for e in ev if e.text.startswith("Injury"))
        stat_ev = ev[0].id
        if inj >= 0.5:
            key = inj_ev
        elif blocked:
            key = next(e.id for e in ev if e.text.startswith("Our overseas"))
        else:
            key = need_ev or next(e.id for e in ev if e.text.startswith("Our Need 1"))
        second = stat_ev if key != stat_ev else inj_ev
        return {
            "decision": {"choice": "BID" if bid else "PASS", "probabilities": {"BID": 0.86 if bid else 0.14, "PASS": 0.14 if bid else 0.86}},
            "max_price": {"score": pos / max(len(ladder) - 1, 1)},
            "need_fit": {"score": fit if fit > 0.2 else 0.0},
            "injury_concern": {"noul": inj},
            "key_evidence": {"choice": key, "probabilities": {key: 0.6, second: 0.3}},
        }


# ======================================================================== Auctioneer

class Auctioneer(InternAgent):
    role = "auctioneer"

    def __init__(self, rules: dict) -> None:
        super().__init__("Auctioneer")
        self.rules = rules

    def resolve(self, player: dict, bids: list[Bid], squads: dict, purses: dict, agents: dict) -> dict:
        base = player.get("base_price_cr") or 0.5
        inc = self.rules["bid_increment_cr"]
        valid: list[Bid] = []
        for b in bids:
            if b.decision != "BID":
                continue
            squad = squads[b.team_id]
            if len(squad) >= self.rules["squad_cap"]:
                b.note = "Ineligible: squad full"
                continue
            if player.get("overseas") and sum(p.get("overseas", False) for p in squad) >= self.rules["overseas_limit"]:
                b.note = "Ineligible: overseas limit reached"
                continue
            cap = agents[b.team_id].affordable(squad, purses[b.team_id])
            if b.max_price > cap:
                b.note = f"Max clamped to purse limit {cr(cap)}"
                b.max_price = cap
            if b.max_price < base:
                b.note = f"Max {cr(b.max_price)} below base price {cr(base)}"
                continue
            valid.append(b)
        if not valid:
            return {"status": "UNSOLD", "winner": None, "price": 0.0, "second": None, "base": base,
                    "rule": "No eligible bids at or above base price."}
        paddle = {tid: a.brief.get("paddle", 9) for tid, a in agents.items()}
        valid.sort(key=lambda b: (-b.max_price, -purses[b.team_id], paddle[b.team_id]))
        w = valid[0]
        if len(valid) == 1:
            price, second, rule = base, None, "Only eligible bidder: pays base price."
        else:
            s = valid[1]
            second = s.team_id
            if s.max_price >= w.max_price:
                price, rule = w.max_price, "Tied maximums: tie-break on remaining purse, then paddle number."
            else:
                price = min(w.max_price, max(base, round(s.max_price + inc, 2)))
                rule = f"Second-highest maximum {cr(s.max_price)} + one increment {cr(inc)}."
        return {"status": "SOLD", "winner": w.team_id, "price": round(price, 2), "second": second, "base": base, "rule": rule}


# ======================================================================== Commissioner

LOSS_REASONS = {
    "outbid": "Bid, but their maximum was lower than the winner's.",
    "no_need": "Passed: the player does not fit their stated squad needs.",
    "injury_policy": "Passed: the player's injury record conflicts with their risk policy.",
    "budget": "Passed or capped by budget: purse, reserve or per-player ceiling.",
    "rules": "Blocked by the rules: squad cap or overseas limit.",
}
WIN_REASONS = {
    "need_fit": "The player matched their top stated need, so they valued him highest.",
    "budget_power": "They had the purse and willingness to go higher than every rival.",
    "sole_bidder": "They were the only eligible bidder.",
    "tie_break": "Equal maximums; they won on the tie-break.",
}


class Commissioner(InternAgent):
    role = "commissioner"

    def __init__(self, teams: dict[str, str]) -> None:
        super().__init__("Commissioner")
        self.teams = teams  # id -> name

    def explain(self, player: dict, bids: list[Bid], result: dict) -> dict:
        if result["status"] != "SOLD":
            return {"headline": f"{player['name']} goes UNSOLD.", "winner": "",
                    "losers": {b.team_id: self._own_words(b) for b in bids}, "codes": {}}
        win = result["winner"]
        losers = [b for b in bids if b.team_id != win]
        state = (
            f"LOT: {player['name']} ({player.get('role')}, base {cr(result['base'])}). "
            f"SOLD to {self.teams[win]} at {cr(result['price'])}. Pricing rule: {result['rule']}\n\n"
            + "\n".join(
                f"{self.teams[b.team_id]}: {b.decision} max {cr(b.max_price)}; need_fit={b.need_fit:.2f}; "
                f"injury_concern={b.injury_concern:.2f}; {b.reason} {b.note} Evidence: "
                + " | ".join(e.cite() for e in b.evidence) for b in bids)
        )
        qs = {"winner_edge": drex.choice(f"Why did {self.teams[win]} win this lot?", WIN_REASONS)}
        for b in losers:
            qs[f"loser_{b.team_id}"] = drex.choice(f"Why did {self.teams[b.team_id]} NOT win this lot?", LOSS_REASONS)
        ans = drex.ask("commissioner", state, qs, mock=lambda: self._mock(bids, result))
        wb = next(b for b in bids if b.team_id == win)
        edge = ans["winner_edge"]["choice"]
        winner_txt = (f"{self.teams[win]} won at {cr(result['price'])} (their max {cr(wb.max_price)}). "
                      f"{WIN_REASONS[edge]} In their words: {wb.evidence[0].cite() if wb.evidence else wb.reason}")
        lose = {}
        for b in losers:
            code = ans[f"loser_{b.team_id}"]["choice"]
            lose[b.team_id] = f"{LOSS_REASONS[code]} {self._own_words(b)}"
        return {"headline": f"SOLD to {self.teams[win]} at {cr(result['price'])}", "winner": winner_txt,
                "losers": lose, "codes": {"winner_edge": edge, **{k: v["choice"] for k, v in ans.items() if k.startswith("loser_")}}}

    @staticmethod
    def _own_words(b: Bid) -> str:
        bits = [b.reason] + ([b.note] if b.note else [])
        if b.evidence:
            bits.append("Evidence: " + b.evidence[0].cite())
        return " ".join(bits)

    def _mock(self, bids: list[Bid], result: dict) -> dict:
        win = result["winner"]
        wb = next(b for b in bids if b.team_id == win)
        if result["second"] is None:
            edge = "sole_bidder"
        elif "Tied" in result["rule"]:
            edge = "tie_break"
        elif wb.need_fit >= 0.9:
            edge = "need_fit"
        else:
            edge = "budget_power"
        out: dict[str, Any] = {"winner_edge": {"choice": edge}}
        for b in bids:
            if b.team_id == win:
                continue
            if b.note.startswith("Ineligible"):
                code = "rules"
            elif b.decision == "BID":
                code = "outbid"
            elif b.injury_concern >= 0.5:
                code = "injury_policy"
            elif b.need_fit < 0.4:
                code = "no_need"
            else:
                code = "budget"
            out[f"loser_{b.team_id}"] = {"choice": code}
        return out
