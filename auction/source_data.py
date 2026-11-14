"""Ground-truth content for the fake documents.

scripts/make_docs.py renders these into PDFs / scanned images / a messy
spreadsheet under docs/. NDI then parses those documents back into JSON.
In MOCK mode, ndi.py returns this ground truth (with citations) instead of
calling NDI, so the rest of the pipeline can be built in parallel.

All franchise and player names are fictional.
"""

RULES = {
    "doc_id": "rules_sheet",
    "purse_cr": 30.0,
    "squad_cap": 6,
    "overseas_limit": 2,
    "bid_increment_cr": 0.25,
    "min_reserve_per_open_slot_cr": 0.5,
    "pricing": "Winner pays one increment above the second-highest maximum bid, "
               "never below base price and never above their own maximum.",
    "tie_break": "Equal maximum bids: team with more remaining purse wins; then earlier paddle number.",
    "note": "SIMPLIFIED rules for a demo. Not the official IPL regulations.",
}

TEAMS = [
    {
        "team_id": "HH",
        "name": "Harbour Hawks",
        "colour": "#1f77b4",
        "paddle": 1,
        "needs": [
            {"tag": "death_bowler", "priority": 1, "text": "We MUST land a genuine death bowler; we leaked 11.4 an over at the death last season."},
            {"tag": "finisher", "priority": 2, "text": "Need a finisher who can strike at 160+ in overs 16-20."},
        ],
        "budget": "Go hard on at most two marquee buys (up to 13 Cr each). Keep at least 6 Cr in reserve after the first marquee.",
        "style": "Aggressive: pace-heavy attack on a bouncy home ground; power hitting over anchoring.",
        "risk": "Will tolerate minor, cleared injuries. Avoid recurring back injuries in fast bowlers.",
        "overseas": "Happy to use both overseas slots on bowlers.",
    },
    {
        "team_id": "PP",
        "name": "Plateau Panthers",
        "colour": "#2ca02c",
        "paddle": 2,
        "needs": [
            {"tag": "spinner", "priority": 1, "text": "Home pitch is slow and turning; a wicket-taking spinner is our top priority."},
            {"tag": "opener", "priority": 2, "text": "Need a young, consistent opener (average 35+)."},
            {"tag": "wicketkeeper", "priority": 3, "text": "Backup wicketkeeper wanted, cheap."},
        ],
        "budget": "Value hunters. Hard ceiling of 10 Cr on any single player. Prefer under-25s who can grow with us.",
        "style": "Spin-choke in the middle overs, bat deep, low-risk cricket.",
        "risk": "Moderate. Will gamble on young uncapped players at low prices.",
        "overseas": "Prefer Indian core; at most one overseas buy.",
    },
    {
        "team_id": "DS",
        "name": "Desert Strikers",
        "colour": "#d62728",
        "paddle": 3,
        "needs": [
            {"tag": "allrounder", "priority": 1, "text": "A frontline all-rounder is the missing piece; we will pay up to 15 Cr for the right one."},
            {"tag": "death_bowler", "priority": 2, "text": "Second priority: someone to bowl two of the last four overs."},
            {"tag": "opener", "priority": 3, "text": "An aggressive opener if budget allows."},
        ],
        "budget": "Balanced spend across the squad. One big swing (all-rounder), otherwise 2-6 Cr per player.",
        "style": "Balanced, depth-first; flat batting pitch at home.",
        "risk": "Strictly avoid players with an unresolved injury or pending fitness test.",
        "overseas": "Will use overseas slots on all-rounders or openers.",
    },
]

PLAYERS = [
    {
        "player_id": "P01", "name": "Arjun Malhotra", "country": "India", "overseas": False, "age": 27,
        "role": "Batter", "tags": ["finisher"], "base_price_cr": 2.0,
        "stats": {"matches": 58, "runs": 1240, "bat_avg": 34.4, "strike_rate": 168.2, "wickets": 0, "economy": None, "death_economy": None},
        "scouting": "Grade A. Elite six-hitter in overs 16-20 (SR 191 at the death). Struggles slightly vs. wrist spin.",
        "injury": "None. Fully fit.", "injury_risk": "low",
        "format": "pdf",
    },
    {
        "player_id": "P02", "name": "Liam Carver", "country": "Overseas", "overseas": True, "age": 29,
        "role": "Fast bowler", "tags": ["death_bowler"], "base_price_cr": 2.0,
        "stats": {"matches": 61, "runs": 140, "bat_avg": 9.3, "strike_rate": 118.0, "wickets": 79, "economy": 8.1, "death_economy": 8.6},
        "scouting": "Grade A. Best yorker in the pool; 24 wickets in overs 17-20 over two seasons. 145+ kph.",
        "injury": "Minor hamstring strain last season; cleared by medical panel in March.", "injury_risk": "low",
        "format": "pdf",
    },
    {
        "player_id": "P03", "name": "Rohan Deshpande", "country": "India", "overseas": False, "age": 24,
        "role": "Leg-spinner", "tags": ["spinner"], "base_price_cr": 1.0,
        "stats": {"matches": 33, "runs": 61, "bat_avg": 7.6, "strike_rate": 101.0, "wickets": 41, "economy": 7.0, "death_economy": 9.8},
        "scouting": "Grade A-. Googly is hard to pick; strike rate 18 balls/wicket in the middle overs. Thrives on slow pitches.",
        "injury": "None.", "injury_risk": "low",
        "format": "scanned",
    },
    {
        "player_id": "P04", "name": "Kofi Mensah", "country": "Overseas", "overseas": True, "age": 28,
        "role": "All-rounder", "tags": ["allrounder", "finisher"], "base_price_cr": 2.0,
        "stats": {"matches": 49, "runs": 980, "bat_avg": 29.7, "strike_rate": 155.4, "wickets": 37, "economy": 8.4, "death_economy": 9.6},
        "scouting": "Grade A. Genuine 4-over bowler who bats at 6. Match-winner in both disciplines.",
        "injury": "Side strain in October; missed 6 weeks. Fitness test PENDING before the season.", "injury_risk": "medium",
        "format": "pdf",
    },
    {
        "player_id": "P05", "name": "Ishaan Rao", "country": "India", "overseas": False, "age": 22,
        "role": "Opening batter", "tags": ["opener"], "base_price_cr": 1.5,
        "stats": {"matches": 30, "runs": 1105, "bat_avg": 41.0, "strike_rate": 142.3, "wickets": 0, "economy": None, "death_economy": None},
        "scouting": "Grade A-. Technically the best young opener in the pool. Powerplay SR 138, improving every season.",
        "injury": "None.", "injury_risk": "low",
        "format": "pdf",
    },
    {
        "player_id": "P06", "name": "Vikram Sethi", "country": "India", "overseas": False, "age": 31,
        "role": "Wicketkeeper-batter", "tags": ["wicketkeeper", "opener"], "base_price_cr": 1.0,
        "stats": {"matches": 72, "runs": 1530, "bat_avg": 26.8, "strike_rate": 131.0, "wickets": 0, "economy": None, "death_economy": None},
        "scouting": "Grade B. Safe gloves, 41 dismissals. Steady but not explosive with the bat.",
        "injury": "None.", "injury_risk": "low",
        "format": "pdf",
    },
    {
        "player_id": "P07", "name": "Dane Whitfield", "country": "Overseas", "overseas": True, "age": 26,
        "role": "Fast bowler", "tags": ["death_bowler"], "base_price_cr": 1.5,
        "stats": {"matches": 27, "runs": 35, "bat_avg": 5.0, "strike_rate": 97.0, "wickets": 36, "economy": 8.3, "death_economy": 8.9},
        "scouting": "Grade B+. Raw pace (150 kph), good slower ball. Death numbers strong in small sample.",
        "injury": "Lumbar stress fracture in 2025; second back injury in three years. Recurring risk.", "injury_risk": "high",
        "format": "scanned",
    },
    {
        "player_id": "P08", "name": "Sameer Qureshi", "country": "India", "overseas": False, "age": 25,
        "role": "Spin all-rounder", "tags": ["spinner", "allrounder"], "base_price_cr": 0.75,
        "stats": {"matches": 40, "runs": 520, "bat_avg": 22.6, "strike_rate": 134.0, "wickets": 31, "economy": 7.3, "death_economy": 10.2},
        "scouting": "Grade B. Tidy off-spin, useful lower-order hitter. Good value depth pick.",
        "injury": "None.", "injury_risk": "low",
        "format": "pdf",
    },
    {
        "player_id": "P09", "name": "Nikhil Bhatt", "country": "India", "overseas": False, "age": 20,
        "role": "Batter (uncapped)", "tags": ["finisher"], "base_price_cr": 0.5,
        "stats": {"matches": 11, "runs": 214, "bat_avg": 26.8, "strike_rate": 175.1, "wickets": 0, "economy": None, "death_economy": None},
        "scouting": "Grade B-. Uncapped domestic star; huge SR but tiny sample. High upside.",
        "injury": "None.", "injury_risk": "low",
        "format": "xlsx",
    },
    {
        "player_id": "P10", "name": "Jaden Brooks", "country": "Overseas", "overseas": True, "age": 30,
        "role": "Opening batter", "tags": ["opener"], "base_price_cr": 1.5,
        "stats": {"matches": 66, "runs": 1890, "bat_avg": 31.5, "strike_rate": 150.2, "wickets": 0, "economy": None, "death_economy": None},
        "scouting": "Grade B+. Fast starter, 9 fifties. Weak against short ball.",
        "injury": "None.", "injury_risk": "low",
        "format": "pdf",
    },
]

# Order in which players come up as lots.
LOT_ORDER = ["P02", "P04", "P03", "P01", "P05", "P07", "P08", "P09", "P10", "P06"]
