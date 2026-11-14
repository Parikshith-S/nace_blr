# 🏏 IPL Auction Swarm — Drexathon (Swarm Intelligence track)

Three franchise agents read their own **strategy brief** and messy **player dossiers**, decide with **Drex**
whether to bid and how high, an **auctioneer** resolves each lot under the rules, and a **commissioner**
uses Drex again to explain why the winner won and why every other team lost, citing each team's own evidence.

> Franchise and player names are fictional. Auction rules are **simplified** for the demo (₹30 Cr purse,
> squad cap 6, overseas ≤ 2, second-price + one ₹0.25 Cr increment). Not official IPL regulations.

## Architecture

```
docs/ (3 team briefs PDF · 10 dossiers: 7 PDF, 2 scanned image-only PDFs, 1 messy XLSX · rules PDF)
   │
   ▼  NDI step (auction/ndi.py) — once at startup, cached to cache/ndi_parsed.json
   │   parse:     Intern's NDI document processors (PDF text layer, RapidOCR on scans, spreadsheet cells)
   │   classify:  Drex choice question → team_brief | player_dossier | rules_sheet
   │   extract:   structured JSON + citation (doc, page/cell, quoted line) for every field
   ▼
Intern agent swarm (auction/agents.py)          per lot (auction/engine.py)
   FranchiseAgent ×3 ──► Drex (parallel) ──► BID/PASS · max price · need fit · injury concern · key evidence
   Auctioneer        ──► rules: purse/reserve, squad cap, overseas limit, 2nd-price + increment, tie-break
   Commissioner      ──► Drex: why winner won (choice) + why each loser lost (choice per team)
   │
   ├─ DeepInfra (optional): auctioneer commentary only — never a decision
   ▼
Streamlit board (app.py) / terminal (run_auction.py) · Adobe assets in assets/
```

### How Drex is used
Drex is a decision model: it answers **typed questions** about a **state**
(`POST https://console.nace.ai/v1/systemone`, model `drex-latest`, called through Intern's
`intern.decisions.DecisionClient`). Each franchise decision is one Drex call with 5 questions:

| question | type | becomes |
|---|---|---|
| `decision` | choice BID/PASS | the bid |
| `max_price` | score over a price ladder (base → legal max) | max price in ₹ Cr |
| `need_fit` | score over 4 anchored levels | "matches our top-priority need" |
| `injury_concern` | noul | risk-policy check |
| `key_evidence` | choice over evidence items E1..En (from NDI, with citations) | the quoted evidence shown on screen |

Because reasons are built from Drex's choice among **cited evidence items**, every explanation points at a
document line (e.g. `“Need 1 [death_bowler]: We MUST land a genuine death bowler…” [HH_..._brief.pdf p1]`).
Per auction: 3 calls/lot for bids + 1 commissioner call/lot + 1 classify call per document.

## Run

```bash
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt
cp .env.example .env          # add NACE_API_KEY (Drex) and optionally DEEPINFRA_API_KEY
.venv/bin/python scripts/make_docs.py      # (re)generate the fake documents
.venv/bin/python -m auction.drex           # Drex connectivity check → mode=live
.venv/bin/python -m auction.ndi --refresh  # run NDI over docs/, writes cache/ndi_parsed.json
.venv/bin/python run_auction.py            # terminal auction
.venv/bin/streamlit run app.py             # board
```
No `NACE_API_KEY` → **MOCK** mode (deterministic stand-in answers, badge shows `Drex MOCK`). `NDI_MODE=mock`
skips parsing and uses ground truth.

Results: every run is logged to `logs/auction_<ts>.json` with Drex metrics (calls, avg latency, cost/call).

## Partner tools
- **Adobe Firefly / Express**: franchise logos → `assets/logos/{HH,PP,DS}.png`, SOLD cards →
  `assets/cards/<player_id>.png`, final poster → `assets/posters/final.png` (the UI picks them up automatically).
- **DeepInfra**: live commentary line per lot (`auction/commentary.py`), never used for decisions.

## Layout
`auction/source_data.py` ground truth for docs · `scripts/make_docs.py` renders docs · `auction/ndi.py` NDI step ·
`auction/drex.py` Drex client + metrics · `auction/agents.py` swarm · `auction/engine.py` lot loop ·
`auction/commentary.py` DeepInfra · `app.py` Streamlit · `run_auction.py` terminal.
