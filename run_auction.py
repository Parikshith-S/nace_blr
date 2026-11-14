"""Terminal demo:  .venv/bin/python run_auction.py [--lots 8] [--refresh-ndi]"""
from __future__ import annotations

import argparse
import textwrap

from auction import drex
from auction.engine import Auction
from auction.ndi import load_profiles

W = 100


def wrap(s: str, indent: str = "    ") -> str:
    return textwrap.fill(s, W, initial_indent=indent, subsequent_indent=indent)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lots", type=int, default=None)
    ap.add_argument("--refresh-ndi", action="store_true")
    a = ap.parse_args()
    data = load_profiles(refresh=a.refresh_ndi)
    auction = Auction(data, a.lots)
    print(f"\nDrex mode: {drex.mode().upper()}   NDI: {data.get('mode')}   lots: {len(auction.lots)}   "
          f"rules: purse ₹{auction.rules['purse_cr']} Cr, squad cap {auction.rules['squad_cap']}, "
          f"overseas ≤ {auction.rules['overseas_limit']} (SIMPLIFIED)\n")
    for e in auction.run_all():
        p, r, x = e["player"], e["result"], e["explanation"]
        print("=" * W)
        print(f"LOT {e['lot']}: {p['name']} | {p.get('role')} | base ₹{p.get('base_price_cr')} Cr | "
              f"{'OVERSEAS' if p.get('overseas') else 'Indian'} | source {p['source']['doc']} ({p['source']['format']})")
        for b in e["bids"]:
            print(f"  [{auction.names[b['team_id']]:<17}] {b['decision']:<4} max ₹{b['max_price']:>5.2f} Cr  "
                  f"fit {b['need_fit']:.2f}  inj {b['injury_concern']:.2f}  {b['note']}")
            print(wrap(b["reason"] + " " + " ".join(f"“{ev['text']}” [{ev['source']}]" for ev in b["evidence"]), "      "))
        print(f"\n  >>> {x['headline']}   ({r.get('rule')})")
        if x["winner"]:
            print(wrap("WHY WON: " + x["winner"]))
        for tid, why in x["losers"].items():
            print(wrap(f"WHY {auction.names[tid]} LOST: {why}"))
        print(wrap("🎙 " + e["commentary"]))
        print("  Purses: " + "  ".join(f"{auction.names[t]} ₹{v:.2f}" for t, v in e["purses_after"].items()))
    s = auction.summary()
    print("=" * W + "\nFINAL SQUADS")
    for team, squad in s["squads"].items():
        print(f"  {team:<17} spent ₹{s['spent'][team]:.2f} Cr: " + ", ".join(f"{p['name']} (₹{p['price']})" for p in squad))
    print(f"\nDrex metrics: {s['drex']}")


if __name__ == "__main__":
    main()
