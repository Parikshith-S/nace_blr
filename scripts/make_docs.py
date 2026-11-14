"""Render the fake auction documents into docs/.

  - docs/teams/<id>_strategy_brief.pdf      clean PDFs
  - docs/players/<id>_<name>.pdf            clean PDFs
  - docs/players/<id>_<name>_scan.pdf       image-only "scanned" PDFs (tilted, noisy) -> needs OCR
  - docs/players/<id>_<name>.xlsx           messy spreadsheet (banner rows, merged cells, notes column)
  - docs/rules/auction_rules.pdf            simplified purse & rules sheet

Run:  .venv/bin/python scripts/make_docs.py
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openpyxl import Workbook  # noqa: E402
from openpyxl.styles import Font  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402
from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.styles import getSampleStyleSheet  # noqa: E402
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

from auction.source_data import PLAYERS, RULES, TEAMS  # noqa: E402

DOCS = ROOT / "docs"
STYLES = getSampleStyleSheet()


def slug(name: str) -> str:
    return name.lower().replace(" ", "_")


def fmt(v) -> str:
    return "-" if v is None else str(v)


def stat_rows(p: dict) -> list[list[str]]:
    s = p["stats"]
    return [
        ["Matches", fmt(s["matches"])], ["Runs", fmt(s["runs"])], ["Batting average", fmt(s["bat_avg"])],
        ["Strike rate", fmt(s["strike_rate"])], ["Wickets", fmt(s["wickets"])],
        ["Economy", fmt(s["economy"])], ["Death-overs economy", fmt(s["death_economy"])],
    ]


def player_lines(p: dict) -> list[str]:
    return [
        "PLAYER DOSSIER - CONFIDENTIAL SCOUTING REPORT",
        f"Name: {p['name']}",
        f"Player ID: {p['player_id']}",
        f"Country: {p['country']}",
        f"Overseas: {'YES' if p['overseas'] else 'NO'}",
        f"Age: {p['age']}",
        f"Role: {p['role']}",
        f"Specialist tags: {', '.join(p['tags'])}",
        f"Base price: Rs {p['base_price_cr']} Cr",
        "",
        "STATS TABLE",
        *[f"{k}: {v}" for k, v in stat_rows(p)],
        "",
        "SCOUTING NOTES",
        p["scouting"],
        "",
        "INJURY NOTE",
        p["injury"],
        f"Injury risk: {p['injury_risk'].upper()}",
    ]


# ---------- clean PDFs ----------

def pdf(path: Path, title: str, blocks: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4, title=title)
    doc.build(blocks)


def table(rows: list[list[str]]) -> Table:
    t = Table(rows, hAlign="LEFT", colWidths=[170, 120])
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
    ]))
    return t


def player_pdf(p: dict, path: Path) -> None:
    H, B = STYLES["Heading1"], STYLES["BodyText"]
    head = [
        Paragraph("PLAYER DOSSIER - CONFIDENTIAL SCOUTING REPORT", H),
        *[Paragraph(line, B) for line in player_lines(p)[1:9]],
        Spacer(1, 10),
        Paragraph("STATS TABLE", STYLES["Heading2"]),
        table(stat_rows(p)),
        Spacer(1, 10),
        Paragraph("SCOUTING NOTES", STYLES["Heading2"]), Paragraph(p["scouting"], B),
        Paragraph("INJURY NOTE", STYLES["Heading2"]), Paragraph(p["injury"], B),
        Paragraph(f"Injury risk: {p['injury_risk'].upper()}", B),
    ]
    pdf(path, p["name"], head)


def team_pdf(t: dict, path: Path) -> None:
    H, H2, B = STYLES["Heading1"], STYLES["Heading2"], STYLES["BodyText"]
    blocks = [
        Paragraph("TEAM STRATEGY BRIEF", H),
        Paragraph(f"Franchise: {t['name']}", B),
        Paragraph(f"Team ID: {t['team_id']}", B),
        Paragraph(f"Paddle number: {t['paddle']}", B),
        Spacer(1, 8),
        Paragraph("SQUAD NEEDS", H2),
        *[Paragraph(f"Need {n['priority']} [{n['tag']}]: {n['text']}", B) for n in t["needs"]],
        Paragraph("BUDGET PRIORITIES", H2), Paragraph(t["budget"], B),
        Paragraph("PLAYING STYLE", H2), Paragraph(t["style"], B),
        Paragraph("RISK APPETITE", H2), Paragraph(t["risk"], B),
        Paragraph("OVERSEAS POLICY", H2), Paragraph(t["overseas"], B),
    ]
    pdf(path, t["name"], blocks)


def rules_pdf(path: Path) -> None:
    H, B = STYLES["Heading1"], STYLES["BodyText"]
    r = RULES
    pdf(path, "Auction rules", [
        Paragraph("AUCTION RULES AND PURSE SHEET (SIMPLIFIED)", H),
        Paragraph(r["note"], B), Spacer(1, 8),
        table([
            ["Purse per franchise (Cr)", str(r["purse_cr"])],
            ["Squad cap", str(r["squad_cap"])],
            ["Overseas limit", str(r["overseas_limit"])],
            ["Bid increment (Cr)", str(r["bid_increment_cr"])],
            ["Reserve per open slot (Cr)", str(r["min_reserve_per_open_slot_cr"])],
        ]),
        Spacer(1, 8),
        Paragraph(f"Pricing: {r['pricing']}", B),
        Paragraph(f"Tie-break: {r['tie_break']}", B),
    ])


# ---------- scanned image PDF ----------

def _font(size: int):
    for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"):
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size=size)


def scanned_pdf(p: dict, path: Path) -> None:
    """Render text to a bitmap, tilt it, add speckle + blur, save as image-only PDF (no text layer)."""
    rnd = random.Random(p["player_id"])
    W, Hh = 1654, 2339  # A4 @ 200 dpi
    img = Image.new("L", (W, Hh), 247)
    d = ImageDraw.Draw(img)
    font, big = _font(34), _font(44)
    y = 140
    for i, line in enumerate(player_lines(p)):
        f = big if i == 0 else font
        # wrap long lines
        words, cur = line.split(), ""
        for w in words or [""]:
            if d.textlength(cur + " " + w, font=f) > W - 260:
                d.text((130, y), cur, fill=25, font=f); y += 50; cur = w
            else:
                cur = (cur + " " + w).strip()
        d.text((130, y), cur, fill=25, font=f)
        y += 62 if i == 0 else 50
    d.text((W - 520, 60), "SCANNED COPY - FAX", fill=90, font=font)
    img = img.rotate(rnd.uniform(-1.6, 1.6), fillcolor=240, expand=False)
    px = img.load()
    for _ in range(9000):
        px[rnd.randrange(W), rnd.randrange(Hh)] = rnd.choice((60, 120, 200))
    img = img.filter(ImageFilter.GaussianBlur(0.7))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(path, "PDF", resolution=200.0)


# ---------- messy spreadsheet ----------

def messy_xlsx(p: dict, path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "scout export v3 (FINAL)"
    ws["A1"] = "DOMESTIC SCOUTING EXPORT -- do not forward"; ws["A1"].font = Font(bold=True)
    ws.merge_cells("A1:F1")
    ws["A2"] = "exported by: regional scout #4   |  data may contain duplicates"
    ws.append([])
    ws.append(["PLAYER", "plyr_id", "ctry", "OS?", "age", "role / tags", "base (Rs Cr)"])
    ws.append([p["name"].upper(), p["player_id"], p["country"], "Y" if p["overseas"] else "N", p["age"],
               f"{p['role']} / {', '.join(p['tags'])}", p["base_price_cr"]])
    ws.append([])
    ws.append(["season split", "M", "R", "Avg", "SR", "W", "Econ", "Death Econ"])
    s = p["stats"]
    ws.append(["career (domestic T20)", s["matches"], s["runs"], s["bat_avg"], s["strike_rate"],
               s["wickets"], s["economy"] if s["economy"] else "n/a", s["death_economy"] if s["death_economy"] else "n/a"])
    ws.append(["", "", "", "", "", "", "", ""])
    ws.append(["notes:", p["scouting"]])
    ws.append(["inj:", p["injury"], "risk=" + p["injury_risk"]])
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def main() -> None:
    for t in TEAMS:
        team_pdf(t, DOCS / "teams" / f"{t['team_id']}_{slug(t['name'])}_strategy_brief.pdf")
    for p in PLAYERS:
        base = DOCS / "players" / f"{p['player_id']}_{slug(p['name'])}"
        if p["format"] == "scanned":
            scanned_pdf(p, base.with_name(base.name + "_scan.pdf"))
        elif p["format"] == "xlsx":
            messy_xlsx(p, base.with_suffix(".xlsx"))
        else:
            player_pdf(p, base.with_suffix(".pdf"))
    rules_pdf(DOCS / "rules" / "auction_rules.pdf")
    files = sorted(str(f.relative_to(ROOT)) for f in DOCS.rglob("*") if f.is_file())
    print(f"wrote {len(files)} documents:\n  " + "\n  ".join(files))


if __name__ == "__main__":
    main()
