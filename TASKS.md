# Task split — submit by 2:40 (hard deadline 3:00)

Already done in the repo (runs end-to-end in MOCK mode): fake docs (3 briefs, 10 dossiers incl. 2 scanned +
1 messy XLSX, rules sheet), real NDI parsing with OCR + citations (cached), Drex client via Intern
`DecisionClient`, 3 franchise agents + auctioneer + commissioner, terminal runner, Streamlit board,
DeepInfra commentary hook, metrics logging, README.

**The single biggest remaining risk: getting a real `NACE_API_KEY` and seeing `mode=live`.** Do that first.

## Rahul — Drex live + tuning + repo
| Time | Task |
|---|---|
| now–1:15 | Get `NACE_API_KEY` from the console/kickoff → `.env`. Run `.venv/bin/python -m auction.drex` until `mode=live`. Confirm model name (`drex-latest`?) on Discord if 4xx. |
| 1:15–1:45 | `.venv/bin/python -m auction.ndi --refresh` (classification now hits live Drex) then `run_auction.py`. Check bids look sane; tweak instructions / price ladder in `auction/agents.py` (`FranchiseAgent.decide`) if Drex over/under-bids. |
| 1:45–2:05 | Ask an organizer how judges want "Intern agents" shown. We use Intern's `DecisionClient`; if they want the Intern harness, add an `intern -p --system1 drex-latest` call for the commissioner write-up. |
| 2:05–2:20 | DeepInfra key → `.env`, check commentary lines. Record final metrics from `logs/` (calls, avg latency, cost/call) for the Results slide. |
| 2:20–2:40 | README final pass, push repo, submit at nace.ai/drexathon/submit. |

## Parikshith — UI polish, Adobe, deck, video
| Time | Task |
|---|---|
| now–1:20 | `.venv/bin/streamlit run app.py` — walk through 8 lots, fix anything ugly. Keep the demo at 8 lots. |
| 1:20–1:55 | Adobe Firefly/Express: 3 logos (Harbour Hawks, Plateau Panthers, Desert Strikers — NO real IPL marks) → `assets/logos/HH.png` etc.; 1 SOLD card template; a few `assets/cards/P02.png`-style cards; poster → `assets/posters/final.png`. |
| 1:55–2:25 | 5-slide deck: Problem · Architecture (label NDI / Intern / Drex / DeepInfra / Adobe) · Live demo · Results (squads, Drex calls, latency, cost) · Partner tools + next. Say rules are simplified. |
| 2:25–2:35 | Record 2-min backup demo video (live mode if working, else mock — say so). |

## Sync points
- **1:15** Rahul: live or not? If no key by 1:30, demo in MOCK and say so honestly; NDI + Intern still real.
- **1:55** Feature freeze. Bugs only.
- **2:35** Both review repo + deck + video → submit.

Cut order if late: DeepInfra → Adobe poster → extra cards. Never cut live Drex, NDI, or the explanations.
