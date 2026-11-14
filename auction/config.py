from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DOCS_DIR = ROOT / "docs"
CACHE_DIR = ROOT / "cache"
ASSETS_DIR = ROOT / "assets"
LOG_DIR = ROOT / "logs"

# Drex (System 1 on the Nace console). Key: NACE_API_KEY or DREX_API_KEY.
DREX_BASE_URL = os.getenv("DREX_BASE_URL", "https://console.nace.ai/v1")
DREX_MODELS = [m.strip() for m in os.getenv("DREX_MODEL", "drex-latest").split(",") if m.strip()]
def _key(*names: str) -> str:
    """First non-empty key among `names`, with stray quotes/whitespace from hand-edited .env files removed."""
    for n in names:
        v = (os.getenv(n) or "").strip().strip("'\"").strip()
        if v:
            return v
    return ""


DREX_KEY_VAR = next((n for n in ("NACE_API_KEY", "DREX_API_KEY") if _key(n)), "")
DREX_API_KEY = _key("NACE_API_KEY", "DREX_API_KEY")
DREX_TIMEOUT_S = float(os.getenv("DREX_TIMEOUT_S", "20"))

# DeepInfra (non-decision commentary only)
DEEPINFRA_API_KEY = _key("DEEPINFRA_API_KEY")
DEEPINFRA_MODEL = os.getenv("DEEPINFRA_MODEL", "meta-llama/Meta-Llama-3.1-8B-Instruct")

# Demo knobs
AUCTION_LOTS = int(os.getenv("AUCTION_LOTS", "8"))

TEAM_COLOURS = {"HH": "#1f77b4", "PP": "#2ca02c", "DS": "#d62728"}
