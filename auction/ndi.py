"""NDI step: parse -> classify -> extract structured JSON with source citations. Runs once, cached.

Parsing uses Intern's NDI-derived document processors (`intern.extensions.workspace.documents`):
PDF text layer, OCR for scanned pages (RapidOCR), and spreadsheets. Classification is a Drex `choice`
question (team_brief / player_dossier / rules_sheet). Extraction maps labelled fields into our schema and
keeps a citation (doc, page/cell, quoted line) for every field the agents later cite as evidence.

NDI_MODE=intern (default)  -> real parsing of docs/ as above
NDI_MODE=mock              -> ground truth from source_data.py (for UI work without the parser)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from auction import drex
from auction.config import CACHE_DIR, DOCS_DIR, ROOT
from auction.source_data import PLAYERS, RULES, TEAMS

CACHE_FILE = CACHE_DIR / "ndi_parsed.json"
WORKSPACE = ROOT / ".ndi_workspace"


# ---------------------------------------------------------------- parse

def parse_document(path: Path) -> dict[str, Any]:
    """Return {"doc", "format", "ocr", "pages": [text, ...]} using Intern's processors."""
    rel = str(path.relative_to(ROOT))
    if path.suffix == ".pdf":
        from intern.extensions.workspace.documents import PdfProcessor

        d = PdfProcessor().process(path, WORKSPACE)
        return {"doc": rel, "format": "pdf", "ocr": "OCR" in d.note, "note": d.note, "pages": list(d.units)}
    if path.suffix in (".xlsx", ".xls"):
        from openpyxl import load_workbook

        wb = load_workbook(path, data_only=True)
        cells: list[str] = []
        for ws in wb.worksheets:
            for row in ws.iter_rows():
                vals = [(c.coordinate, c.value) for c in row if c.value not in (None, "")]
                if vals:
                    cells.append(" | ".join(f"{ws.title}!{coord}={v}" for coord, v in vals))
        return {"doc": rel, "format": "xlsx", "ocr": False, "note": "spreadsheet cells", "pages": ["\n".join(cells)]}
    raise ValueError(f"unsupported document: {path}")


# ---------------------------------------------------------------- classify

DOC_TYPES = {
    "team_brief": "A franchise's strategy brief: squad needs, budget priorities, playing style.",
    "player_dossier": "A scouting dossier about ONE player: stats, scouting notes, injury note (any layout, incl. spreadsheets).",
    "rules_sheet": "The auction rules / purse sheet: purse, squad cap, overseas limit, increments.",
}


def classify(parsed: dict) -> str:
    text = parsed["pages"][0][:3000]

    def mock() -> dict:
        t = re.sub(r"\s+", "", text).upper()
        kind = "team_brief" if "STRATEGYBRIEF" in t else "rules_sheet" if "AUCTIONRULES" in t else "player_dossier"
        return {"type": {"choice": kind, "probabilities": {kind: 0.97}}}

    ans = drex.ask(
        "ndi.classify",
        f"Document: {parsed['doc']}\n---\n{text}",
        {"type": drex.choice("Which kind of auction document is this?", DOC_TYPES)},
        mock=mock,
    )
    return ans["type"]["choice"]


# ---------------------------------------------------------------- extract helpers

def _label(label: str) -> str:
    """Regex for a label that survives OCR dropping spaces ('Base price' ~ 'Baseprice')."""
    return r"\s*".join(re.escape(ch) for ch in label if not ch.isspace())


def _find(pages: list[str], label: str, doc: str, cites: dict, key: str, pattern: str = r"(.+)") -> str | None:
    rx = re.compile(_label(label) + r"\s*[:|=]?\s*" + pattern, re.IGNORECASE)
    for i, page in enumerate(pages, 1):
        for line in page.splitlines():
            m = rx.search(line)
            if m:
                cites[key] = {"doc": doc, "page": i, "quote": line.strip()}
                return m.group(1).strip()
    return None


def _section(pages: list[str], head: str, stop: list[str], doc: str, cites: dict, key: str) -> str | None:
    text = "\n".join(pages)
    stops = "|".join(_label(s) for s in stop)
    m = re.search(_label(head) + r"\s*\n(.*?)(?=\n\s*(?:" + stops + r")\b|\Z)", text, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    body = " ".join(m.group(1).split())
    cites[key] = {"doc": doc, "page": 1, "quote": body[:200]}
    return body


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    m = re.search(r"-?\d+(?:\.\d+)?", s.replace(",", ""))
    return float(m.group()) if m else None


# ---------------------------------------------------------------- extract: player

STAT_LABELS = {
    "matches": "Matches", "runs": "Runs", "bat_avg": "Batting average", "strike_rate": "Strike rate",
    "wickets": "Wickets", "economy": "Economy", "death_economy": "Death-overs economy",
}
TAGS = ["death_bowler", "finisher", "spinner", "allrounder", "opener", "wicketkeeper"]


def _tags(s: str) -> list[str]:
    flat = re.sub(r"[\s_-]", "", (s or "").lower())
    return [t for t in TAGS if t.replace("_", "") in flat]


def extract_player(parsed: dict) -> dict:
    if parsed["format"] == "xlsx":
        return extract_player_xlsx(parsed)
    pages, doc, c = parsed["pages"], parsed["doc"], {}
    stats = {}
    for key, label in STAT_LABELS.items():
        # 'Economy' must not match 'Death-overs economy'
        rx_label = label if key != "economy" else "Economy"
        val = None
        rx = re.compile(r"^\s*" + _label(rx_label) + r"\s*[:|]?\s*(-|\d+(?:\.\d+)?)\s*$", re.IGNORECASE)
        for i, page in enumerate(pages, 1):
            for line in page.splitlines():
                if (m := rx.match(line)):
                    val = None if m.group(1) == "-" else float(m.group(1))
                    c[f"stats.{key}"] = {"doc": doc, "page": i, "quote": line.strip()}
                    break
            if f"stats.{key}" in c:
                break
        stats[key] = val
    injury_risk = (_find(pages, "Injury risk", doc, c, "injury_risk", r"([A-Za-z]+)") or "unknown").lower()
    sections = ["SCOUTING NOTES", "INJURY NOTE", "Injury risk"]
    p = {
        "name": _find(pages, "Name", doc, c, "name"),
        "player_id": _find(pages, "Player ID", doc, c, "player_id", r"(P\d+)"),
        "country": _find(pages, "Country", doc, c, "country"),
        "overseas": (_find(pages, "Overseas", doc, c, "overseas", r"(YES|NO)") or "NO").upper() == "YES",
        "age": _num(_find(pages, "Age", doc, c, "age", r"(\d+)")),
        "role": _find(pages, "Role", doc, c, "role"),
        "tags": _tags(_find(pages, "Specialist tags", doc, c, "tags") or ""),
        "base_price_cr": _num(_find(pages, "Base price", doc, c, "base_price_cr")),
        "stats": stats,
        "scouting": _section(pages, "SCOUTING NOTES", sections[1:], doc, c, "scouting"),
        "injury": _section(pages, "INJURY NOTE", sections[2:], doc, c, "injury"),
        "injury_risk": injury_risk,
    }
    p["age"] = int(p["age"]) if p["age"] else None
    if p["name"]:  # OCR drops spaces: 'RohanDeshpande' -> 'Rohan Deshpande'
        p["name"] = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", p["name"])
    return {**p, "source": _source(parsed), "citations": c}


def extract_player_xlsx(parsed: dict) -> dict:
    doc, text, c = parsed["doc"], parsed["pages"][0], {}
    rows = [dict(re.findall(r"([^|=]+![A-Z]+\d+)=([^|]*)", r)) for r in text.splitlines()]
    rows = [{k.strip(): v.strip() for k, v in r.items()} for r in rows]

    def after(header_word: str) -> tuple[list[str], dict, str] | None:
        for i, r in enumerate(rows):
            if any(v.lower() == header_word for v in r.values()) and i + 1 < len(rows):
                return list(r.values()), rows[i + 1], text.splitlines()[i + 1]
        return None

    head, row, raw = after("plyr_id")
    vals = list(row.values())
    hidx = {h.lower(): n for n, h in enumerate(head)}
    get = lambda h: vals[hidx[h]] if h in hidx and hidx[h] < len(vals) else None  # noqa: E731
    for k in ("player", "plyr_id", "os?", "role / tags", "base (rs cr)", "age", "ctry"):
        c[k] = {"doc": doc, "page": 1, "quote": raw[:200]}
    role_tags = (get("role / tags") or "").split("/")
    shead, srow, sraw = after("season split")
    svals = list(srow.values())
    sh = {h.lower(): n for n, h in enumerate(shead)}
    sget = lambda h: _num(svals[sh[h]]) if h in sh and sh[h] < len(svals) else None  # noqa: E731
    stats = {"matches": sget("m"), "runs": sget("r"), "bat_avg": sget("avg"), "strike_rate": sget("sr"),
             "wickets": sget("w"), "economy": sget("econ"), "death_economy": sget("death econ")}
    for k in stats:
        c[f"stats.{k}"] = {"doc": doc, "page": 1, "quote": sraw[:200]}
    notes = next((r for r in rows if any(v.lower() == "notes:" for v in r.values())), {})
    inj = next((r for r in rows if any(v.lower() == "inj:" for v in r.values())), {})
    nvals, ivals = list(notes.values()), list(inj.values())
    risk = next((v.split("=")[1] for v in ivals if v.startswith("risk")), "unknown")
    scouting = nvals[1] if len(nvals) > 1 else None
    injury = ivals[1] if len(ivals) > 1 else None
    c["scouting"] = {"doc": doc, "page": 1, "quote": (scouting or "")[:200]}
    c["injury"] = {"doc": doc, "page": 1, "quote": (injury or "")[:200]}
    name = (get("player") or "").title()
    return {
        "name": name, "player_id": get("plyr_id"), "country": get("ctry"),
        "overseas": (get("os?") or "N").upper().startswith("Y"), "age": int(_num(get("age")) or 0) or None,
        "role": role_tags[0].strip(), "tags": _tags(role_tags[1] if len(role_tags) > 1 else ""),
        "base_price_cr": _num(get("base (rs cr)")), "stats": stats, "scouting": scouting, "injury": injury,
        "injury_risk": risk.lower(), "source": _source(parsed), "citations": c,
    }


# ---------------------------------------------------------------- extract: team & rules

def extract_team(parsed: dict) -> dict:
    pages, doc, c = parsed["pages"], parsed["doc"], {}
    needs = []
    for i, page in enumerate(pages, 1):
        for line in page.splitlines():
            if (m := re.search(r"Need\s*(\d)\s*\[([a-z_]+)\]\s*:\s*(.+)", line)):
                needs.append({"priority": int(m.group(1)), "tag": m.group(2), "text": m.group(3).strip()})
                c[f"need.{m.group(2)}"] = {"doc": doc, "page": i, "quote": line.strip()}
    # needs text can wrap onto the next line: take the section text for the full sentence
    full = "\n".join(pages)
    for n in needs:
        m = re.search(r"Need\s*" + str(n["priority"]) + r"\s*\[" + n["tag"] + r"\]\s*:\s*(.*?)(?=\nNeed\s*\d|\nBUDGET PRIORITIES)", full, re.S)
        if m:
            n["text"] = " ".join(m.group(1).split())
            c[f"need.{n['tag']}"]["quote"] = f"Need {n['priority']} [{n['tag']}]: {n['text']}"
    heads = ["BUDGET PRIORITIES", "PLAYING STYLE", "RISK APPETITE", "OVERSEAS POLICY"]
    sec = {}
    for k, h in zip(["budget", "style", "risk", "overseas"], heads):
        sec[k] = _section(pages, h, [x for x in heads if x != h] + ["SQUAD NEEDS"], doc, c, k)
    return {
        "name": _find(pages, "Franchise", doc, c, "name"),
        "team_id": _find(pages, "Team ID", doc, c, "team_id", r"([A-Z]{2,4})"),
        "paddle": int(_num(_find(pages, "Paddle number", doc, c, "paddle")) or 0),
        "needs": sorted(needs, key=lambda n: n["priority"]),
        **sec, "source": _source(parsed), "citations": c,
    }


def extract_rules(parsed: dict) -> dict:
    pages, doc, c = parsed["pages"], parsed["doc"], {}
    f = lambda label, key: _num(_find(pages, label, doc, c, key, r"(\d+(?:\.\d+)?)"))  # noqa: E731
    r = {
        "purse_cr": f("Purse per franchise (Cr)", "purse_cr"),
        "squad_cap": int(f("Squad cap", "squad_cap") or 0),
        "overseas_limit": int(f("Overseas limit", "overseas_limit") or 0),
        "bid_increment_cr": f("Bid increment (Cr)", "bid_increment_cr"),
        "min_reserve_per_open_slot_cr": f("Reserve per open slot (Cr)", "min_reserve_per_open_slot_cr"),
        "pricing": _find(pages, "Pricing", doc, c, "pricing"),
        "tie_break": _find(pages, "Tie-break", doc, c, "tie_break"),
        "note": "SIMPLIFIED rules for a demo. Not the official IPL regulations.",
    }
    return {**r, "source": _source(parsed), "citations": c}


def _source(parsed: dict) -> dict:
    return {"doc": parsed["doc"], "format": parsed["format"], "ocr": parsed["ocr"], "note": parsed.get("note", "")}


# ---------------------------------------------------------------- pipeline

def run_ndi(verbose: bool = True) -> dict:
    out = {"teams": [], "players": [], "rules": None, "documents": []}
    files = sorted(p for p in DOCS_DIR.rglob("*") if p.suffix in (".pdf", ".xlsx"))
    for path in files:
        parsed = parse_document(path)
        kind = classify(parsed)
        rec = {"team_brief": extract_team, "player_dossier": extract_player, "rules_sheet": extract_rules}[kind](parsed)
        out["documents"].append({"doc": parsed["doc"], "type": kind, "format": parsed["format"], "note": parsed.get("note", "")})
        if kind == "team_brief":
            out["teams"].append(rec)
        elif kind == "player_dossier":
            out["players"].append(rec)
        else:
            out["rules"] = rec
        if verbose:
            name = rec.get("name") or "rules"
            print(f"  NDI  {parsed['doc']:<50} -> {kind:<15} {name}  [{parsed.get('note', '')}]")
    _fill_gaps(out)
    return out


def _fill_gaps(out: dict) -> None:
    """Flag (don't silently fix) fields the parser could not read, so the UI can show low-confidence data."""
    for p in out["players"]:
        p["missing"] = [k for k in ("name", "player_id", "base_price_cr", "scouting", "injury") if not p.get(k)]
        if p.get("scouting") and len(p["scouting"]) < 25:
            p["missing"].append("scouting (OCR partial)")
    out["teams"].sort(key=lambda t: t["paddle"])
    out["players"].sort(key=lambda p: p.get("player_id") or "")


def mock_ndi() -> dict:
    """Ground truth shaped exactly like run_ndi() output."""
    def cites(obj: dict, doc: str) -> dict:
        return {k: {"doc": doc, "page": 1, "quote": f"{k}: {v}"} for k, v in obj.items() if isinstance(v, (str, int, float))}

    teams = []
    for t in TEAMS:
        doc = f"docs/teams/{t['team_id']}_{t['name'].lower().replace(' ', '_')}_strategy_brief.pdf"
        c = cites(t, doc) | {f"need.{n['tag']}": {"doc": doc, "page": 1, "quote": f"Need {n['priority']} [{n['tag']}]: {n['text']}"} for n in t["needs"]}
        teams.append({k: v for k, v in t.items() if k != "colour"} | {"source": {"doc": doc, "format": "pdf", "ocr": False}, "citations": c})
    players = []
    for p in PLAYERS:
        doc = f"docs/players/{p['player_id']}_{p['name'].lower().replace(' ', '_')}{'_scan.pdf' if p['format'] == 'scanned' else '.xlsx' if p['format'] == 'xlsx' else '.pdf'}"
        c = cites(p, doc) | {f"stats.{k}": {"doc": doc, "page": 1, "quote": f"{STAT_LABELS[k]}: {v}"} for k, v in p["stats"].items()}
        players.append({k: v for k, v in p.items() if k != "format"} | {"source": {"doc": doc, "format": p["format"], "ocr": p["format"] == "scanned"}, "citations": c, "missing": []})
    rules = dict(RULES) | {"source": {"doc": "docs/rules/auction_rules.pdf", "format": "pdf", "ocr": False}, "citations": cites(RULES, "docs/rules/auction_rules.pdf")}
    return {"teams": teams, "players": players, "rules": rules, "documents": [], "mode": "mock"}


def load_profiles(refresh: bool = False, verbose: bool = True) -> dict:
    """Run NDI once and cache; later runs read the cache (delete cache/ or pass refresh=True to redo)."""
    mode = os.getenv("NDI_MODE", "intern").lower()
    if mode == "mock":
        return mock_ndi()
    if CACHE_FILE.exists() and not refresh:
        return json.loads(CACHE_FILE.read_text())
    if verbose:
        print(f"NDI: parsing {DOCS_DIR.relative_to(ROOT)}/ (Drex: {drex.mode()}) ...")
    out = run_ndi(verbose) | {"mode": "intern"}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(out, indent=2))
    if verbose:
        print(f"NDI: cached -> {CACHE_FILE.relative_to(ROOT)}")
    return out


if __name__ == "__main__":
    import sys

    data = load_profiles(refresh="--refresh" in sys.argv)
    print(json.dumps({"teams": [t["name"] for t in data["teams"]],
                      "players": [(p["player_id"], p["name"], p["base_price_cr"], p["tags"], p["missing"]) for p in data["players"]],
                      "rules": {k: data["rules"][k] for k in ("purse_cr", "squad_cap", "overseas_limit", "bid_increment_cr")}}, indent=1))
