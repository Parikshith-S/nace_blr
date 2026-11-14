"""Live auctioneer commentary via DeepInfra (OpenAI-compatible). NON-decision flavour text only;
every decision stays on Drex. Falls back to canned lines with no key."""
from __future__ import annotations

import random

import requests

from auction import config

URL = "https://api.deepinfra.com/v1/openai/chat/completions"


def _canned(player: dict, result: dict, team_name: str | None) -> str:
    if result["status"] != "SOLD":
        return f"No paddles for {player['name']}... going once, going twice... UNSOLD!"
    opener = random.Random(player["name"]).choice([
        "What a contest on the floor!", "The paddles are flying!", "Here we go, ladies and gentlemen!"])
    return f"{opener} {player['name']}... going once... going twice... SOLD to {team_name} for ₹{result['price']:.2f} Cr!"


def line(player: dict, result: dict, team_name: str | None, bids_summary: str) -> str:
    if not config.DEEPINFRA_API_KEY:
        return _canned(player, result, team_name)
    outcome = f"SOLD to {team_name} for ₹{result['price']:.2f} Cr" if result["status"] == "SOLD" else "UNSOLD"
    try:
        r = requests.post(URL, timeout=8, headers={"Authorization": f"Bearer {config.DEEPINFRA_API_KEY}"}, json={
            "model": config.DEEPINFRA_MODEL, "max_tokens": 70, "temperature": 0.9,
            "messages": [
                {"role": "system", "content": "You are an energetic cricket auction commentator. One or two short sentences, "
                                              "end with 'going once, going twice...' and the outcome. No hashtags. Do not invent numbers."},
                {"role": "user", "content": f"Player: {player['name']} ({player.get('role')}). Bids: {bids_summary}. Outcome: {outcome}."},
            ]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:  # never block the auction on flavour text
        print(f"[deepinfra] {e}")
        return _canned(player, result, team_name)
