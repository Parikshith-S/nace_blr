"""Streamlit board:  .venv/bin/streamlit run app.py"""
from __future__ import annotations

import time
from pathlib import Path

import streamlit as st

from auction import config, drex
from auction.engine import Auction
from auction.ndi import load_profiles

st.set_page_config(page_title="IPL Auction Swarm", page_icon="🏏", layout="wide")

ASSETS = config.ASSETS_DIR


def asset(kind: str, key: str) -> Path | None:
    for ext in ("png", "jpg", "jpeg", "webp"):
        p = ASSETS / kind / f"{key}.{ext}"
        if p.exists():
            return p
    return None


@st.cache_resource(show_spinner="NDI: parsing team briefs, dossiers & rules (once, then cached)…")
def profiles() -> dict:
    return load_profiles()


def new_auction() -> None:
    drex.METRICS.reset()
    st.session_state.auction = Auction(profiles())
    st.session_state.autoplay = False


if "auction" not in st.session_state:
    new_auction()
A: Auction = st.session_state.auction
colour = config.TEAM_COLOURS

st.markdown("""
<style>
.sold {padding:18px 24px;border-radius:14px;color:white;font-size:2rem;font-weight:800;text-align:center;margin:8px 0}
.unsold {background:#555}
.badge {display:inline-block;padding:2px 10px;border-radius:999px;font-size:.8rem;font-weight:700;color:white;margin-right:6px}
.ev {font-size:.85rem;opacity:.9;border-left:3px solid #999;padding-left:8px;margin:4px 0}
</style>""", unsafe_allow_html=True)

# ------------------------------------------------------------------ header
h1, h2 = st.columns([3, 2])
with h1:
    st.title("🏏 IPL Auction Swarm")
    st.caption("NDI → Intern agent swarm → Drex decisions → Drex explanations · fictional franchises · SIMPLIFIED rules")
with h2:
    m = drex.mode()
    st.markdown(
        f"<span class='badge' style='background:{'#16a34a' if m == 'live' else '#d97706'}'>Drex {m.upper()}</span>"
        f"<span class='badge' style='background:#2563eb'>NDI {A.data.get('mode', '?')}: {len(A.data['players'])} dossiers · {len(A.data['teams'])} briefs</span>"
        f"<span class='badge' style='background:#7c3aed'>Intern swarm: {len(A.agents)} franchises + auctioneer + commissioner</span>",
        unsafe_allow_html=True)
    b1, b2, b3 = st.columns(3)
    if b1.button("▶ Next lot", disabled=A.done, width="stretch"):
        with st.spinner("3 franchise agents asking Drex in parallel…"):
            A.run_lot()
    if b2.button("⏩ Auto-run" if not st.session_state.autoplay else "⏸ Pause", disabled=A.done, width="stretch"):
        st.session_state.autoplay = not st.session_state.autoplay
    if b3.button("↺ Reset", width="stretch"):
        new_auction()
        st.rerun()

# ------------------------------------------------------------------ purse bars
cols = st.columns(len(A.agents))
for c, (tid, agent) in zip(cols, A.agents.items()):
    with c:
        logo = asset("logos", tid)
        if logo:
            st.image(str(logo), width=70)
        purse, full = A.purses[tid], A.rules["purse_cr"]
        st.markdown(f"<b style='color:{colour.get(tid, '#333')};font-size:1.15rem'>{agent.name}</b>", unsafe_allow_html=True)
        st.progress(max(purse / full, 0.0), text=f"Purse ₹{purse:.2f} / {full:.0f} Cr · squad {len(A.squads[tid])}/{A.rules['squad_cap']}")
        st.caption(", ".join(p["name"] for p in A.squads[tid]) or "—")

st.divider()

# ------------------------------------------------------------------ current lot
if not A.log:
    st.info(f"{len(A.lots)} lots queued: " + ", ".join(p["name"] for p in A.lots) + ". Press **Next lot** or **Auto-run**.")
else:
    e = A.log[-1]
    p, r, x = e["player"], e["result"], e["explanation"]
    left, right = st.columns([1, 3])
    with left:
        st.subheader(f"Lot {e['lot']}/{len(A.lots)}")
        card = asset("cards", p["player_id"]) if r["status"] == "SOLD" else None
        if card:
            st.image(str(card))
        st.markdown(f"### {p['name']}")
        st.markdown(f"**{p.get('role')}** · age {p.get('age')} · {'🌍 overseas' if p.get('overseas') else '🇮🇳 Indian'}  \n"
                    f"tags: `{', '.join(p.get('tags', []))}` · base **₹{p.get('base_price_cr')} Cr**")
        s = p.get("stats", {})
        st.dataframe({k: [v] for k, v in s.items() if v is not None}, hide_index=True)
        st.caption(f"📝 {p.get('scouting')}")
        st.caption(f"🩹 {p.get('injury')} (risk **{p.get('injury_risk')}**)")
        src = p["source"]
        st.caption(f"📄 NDI source: `{src['doc'].split('/')[-1]}` · {src['format']}{' · OCR' if src.get('ocr') else ''}"
                   + (f" · ⚠ low-confidence: {', '.join(p['missing'])}" if p.get("missing") else ""))
    with right:
        bc = st.columns(len(e["bids"]))
        for c, b in zip(bc, e["bids"]):
            with c:
                tid = b["team_id"]
                won = r.get("winner") == tid
                st.markdown(f"<b style='color:{colour.get(tid)}'>{A.names[tid]}</b> {'🏆' if won else ''}", unsafe_allow_html=True)
                st.markdown(f"<span class='badge' style='background:{'#16a34a' if b['decision'] == 'BID' else '#6b7280'}'>{b['decision']}</span>"
                            + (f" max <b>₹{b['max_price']:.2f} Cr</b>" if b["decision"] == "BID" else ""), unsafe_allow_html=True)
                st.progress(b["need_fit"], text=f"need fit {b['need_fit']:.2f}")
                st.progress(b["injury_concern"], text=f"injury concern {b['injury_concern']:.2f}")
                st.write(b["reason"])
                for ev in b["evidence"]:
                    st.markdown(f"<div class='ev'>“{ev['text']}”<br><i>{ev['source']}</i></div>", unsafe_allow_html=True)
                if b["note"]:
                    st.warning(b["note"])
        if r["status"] == "SOLD":
            st.markdown(f"<div class='sold' style='background:{colour.get(r['winner'])}'>SOLD to {A.names[r['winner']]} at ₹{r['price']:.2f} Cr</div>",
                        unsafe_allow_html=True)
        else:
            st.markdown("<div class='sold unsold'>UNSOLD</div>", unsafe_allow_html=True)
        st.caption(f"Auctioneer rule: {r['rule']} · lot latency {e['latency_s']}s")
        st.markdown(f"🎙 *{e['commentary']}*")
        with st.container(border=True):
            st.markdown("**Commissioner (Drex) explanation**")
            if x["winner"]:
                st.markdown(f"✅ {x['winner']}")
            for tid, why in x["losers"].items():
                st.markdown(f"❌ **{A.names[tid]}**: {why}")

# ------------------------------------------------------------------ tabs
st.divider()
t1, t2, t3, t4 = st.tabs(["📜 Lot log", "🏆 Squads", "📈 Drex metrics", "📄 NDI documents"])
with t1:
    st.dataframe([{"lot": e["lot"], "player": e["player"]["name"], "result": e["explanation"]["headline"],
                   **{A.names[b["team_id"]]: f"{b['decision']} {b['max_price']:.2f}" for b in e["bids"]}} for e in A.log],
                 hide_index=True, width="stretch")
with t2:
    poster = asset("posters", "final")
    if poster and A.done:
        st.image(str(poster))
    sc = st.columns(len(A.agents))
    for c, (tid, squad) in zip(sc, A.squads.items()):
        with c:
            st.markdown(f"**{A.names[tid]}** · spent ₹{A.rules['purse_cr'] - A.purses[tid]:.2f} Cr")
            for pl in squad:
                st.write(f"• {pl['name']} ({pl['role']}) ₹{pl['price']:.2f}")
with t3:
    st.json(drex.METRICS.summary())
with t4:
    st.dataframe(A.data.get("documents") or [{"doc": p["source"]["doc"], "format": p["source"]["format"]} for p in A.data["players"]],
                 hide_index=True, width="stretch")
    pick = st.selectbox("Inspect parsed JSON", [p["name"] for p in A.data["players"]] + [t["name"] for t in A.data["teams"]])
    st.json(next(o for o in A.data["players"] + A.data["teams"] if o["name"] == pick), expanded=False)

# ------------------------------------------------------------------ autoplay
if st.session_state.autoplay and not A.done:
    time.sleep(2.5)
    A.run_lot()
    st.rerun()
elif A.done:
    st.session_state.autoplay = False
