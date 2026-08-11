"""
Pin-Grafik für Pinterest: 1000×1500 PNG aus snaggas eigenen Daten.

Warum eine eigene Grafik statt des Amazon-Produktfotos
------------------------------------------------------
Der Associates-Operating-Agreement erlaubt Amazon-Produktbilder nur über die
PA API. snagga bezieht seine Bilder über Keepa — auf der eigenen Seite ist das
der bestehende Zustand, aber diese Bilder zusätzlich auf eine fremde Plattform
hochzuladen wäre ein neuer, unnötiger Schritt ins Risiko. Siehe
`Snagga_Amazon_Guidelines.html`, Abschnitt „Was ausdrücklich erlaubt ist".

Der Verzicht ist kein Nachteil, sondern der Punkt: snaggas Alleinstellung ist
nicht das Produktfoto (das hat jede Deal-Seite), sondern die **Preiskurve**. Ein
Pin, der den Preisverlauf zeigt und die Frage „kaufen oder warten?" beantwortet,
sieht in einem Pinterest-Feed anders aus als das tausendste Packshot — und er
besteht zu 100 % aus eigenem Material.

Der Pin verlinkt auf die snagga-`/preis`-Seite, nie direkt auf Amazon. Damit
braucht der Pin selbst keinen Werbehinweis (er enthält keinen Affiliate-Link),
die Kennzeichnung steht auf der Zielseite — und der Klick landet im eigenen
Bestand statt sofort bei Amazon. Das ist der Sinn der Übung: Traffic.

Format 2:3 (1000×1500) ist Pinterests empfohlenes Pin-Format.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1000, 1500

# snagga-Farben (identisch zur Website, theme-color aus index.html)
NAVY      = (21, 61, 104)
NAVY_DARK = (13, 40, 70)
WHITE     = (255, 255, 255)
MUTED     = (150, 168, 190)
GREEN     = (34, 168, 108)
CARD      = (255, 255, 255)
INK       = (24, 34, 48)
INK_SOFT  = (98, 112, 130)
LINE      = (222, 228, 236)

_FONT_DIR = Path(__file__).parent / "assets" / "fonts"


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Mitgelieferte Schrift statt Systemschrift: Render-Container bringen keine
    garantierten Fonts mit, und `ImageFont.load_default()` wäre eine
    Bitmap-Schrift — auf 1000 px Breite unbrauchbar. DejaVu liegt unter einer
    freien Lizenz im Repo (assets/fonts/DejaVu-LICENSE.txt).
    """
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return ImageFont.truetype(str(_FONT_DIR / name), size)


def _eur(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".") + " €"


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_w: int, max_lines: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        probe = f"{cur} {w}".strip()
        if draw.textlength(probe, font=font) <= max_w:
            cur = probe
            continue
        if cur:
            lines.append(cur)
        cur = w
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and len(" ".join(lines)) < len(text):
        # Letzte Zeile kürzen statt hart abschneiden
        last = lines[-1]
        while last and draw.textlength(last + " …", font=font) > max_w:
            last = last[:-1]
        lines[-1] = last.rstrip() + " …"
    return lines


def _sparkline(draw: ImageDraw.ImageDraw, prices: list[float], box: tuple[int, int, int, int]):
    """
    Preisverlauf als Fläche + Linie. Bewusst ohne Achsenbeschriftung: der Pin
    soll die FORM der Kurve transportieren (fällt gerade / war schon tiefer),
    die Zahlen stehen darüber. Details holt sich der Klick auf der Seite ab.
    """
    x0, y0, x1, y1 = box
    if len(prices) < 2:
        return
    lo, hi = min(prices), max(prices)
    span = (hi - lo) or (hi * 0.1) or 1.0
    n = len(prices)
    pts = [
        (x0 + (x1 - x0) * i / (n - 1), y1 - (y1 - y0) * (p - lo) / span)
        for i, p in enumerate(prices)
    ]
    draw.polygon([(x0, y1)] + pts + [(x1, y1)], fill=(232, 240, 250))
    draw.line(pts, fill=NAVY, width=5, joint="curve")
    # Aktueller Punkt betonen
    cx, cy = pts[-1]
    draw.ellipse([cx - 11, cy - 11, cx + 11, cy + 11], fill=GREEN, outline=WHITE, width=4)


def render_pin(
    name: str,
    current: float,
    reference: float,
    tag: str,
    category: str,
    prices: list[float] | None = None,
) -> bytes:
    """
    Baut die Pin-Grafik und gibt PNG-Bytes zurück.

    `reference` ist der Ø-180-Tage-Preis (products.original_price) — NICHT
    Amazons Streichpreis. Deshalb steht auf dem Pin „Ø 6 Monate" und nicht
    „statt", sonst behauptet die Grafik einen beworbenen Rabatt, den die Daten
    nicht hergeben (siehe TODO.md, Eintrag vom 09.08.2026).
    """
    img  = Image.new("RGB", (W, H), NAVY)
    draw = ImageDraw.Draw(img)

    # Titelzeilen vorab umbrechen: die Kartenhöhe hängt davon ab, und die Karte
    # muss vor ihrem Inhalt gezeichnet werden. Ohne diesen Vorlauf klaffte bei
    # kurzen Produktnamen unten eine leere weisse Fläche.
    title_font  = _font(40, bold=True)
    title_lines = _wrap(draw, name, title_font, W - 200, 3)

    # ── Kopf ────────────────────────────────────────────────────────────────
    draw.rectangle([0, 0, W, 210], fill=NAVY_DARK)
    draw.text((70, 74), "snagga", font=_font(64, bold=True), fill=WHITE)
    draw.text((70, 148), "AMAZON PREIS-CHECK", font=_font(26), fill=MUTED)
    if category:
        cf = _font(24)
        tw = draw.textlength(category.upper(), font=cf)
        draw.rounded_rectangle([W - 70 - tw - 40, 96, W - 70, 152], 28, fill=(35, 82, 132))
        draw.text((W - 90 - tw, 110), category.upper(), font=cf, fill=WHITE)

    # ── Karte ───────────────────────────────────────────────────────────────
    # Höhe aus dem Inhalt: Titel + Preisblock + Chart + Urteil + Innenabstand.
    # Der Inhalt endet beim Urteils-Chip; darunter nur noch Innenabstand.
    # Rechnung: Titel (card_top+60 + 56 je Zeile) + 30 Abstand = Preis-Basis y,
    # Chart-Block liegt bei y+200, der Chip endet bei y+662.
    card_top = 270
    y_price  = card_top + 60 + len(title_lines) * 56 + 30
    card_bot = min(y_price + 662 + 50, H - 190)
    draw.rounded_rectangle([60, card_top, W - 60, card_bot], 36, fill=CARD)

    y = card_top + 60
    for line in title_lines:
        draw.text((100, y), line, font=title_font, fill=INK)
        y += 56

    y = y + 30
    draw.text((100, y), _eur(current), font=_font(96, bold=True), fill=NAVY)

    if reference and reference > current:
        pct = round((1 - current / reference) * 100)
        pf  = _font(34, bold=True)
        label = f"−{pct} %"
        tw = draw.textlength(label, font=pf)
        bx = 100 + draw.textlength(_eur(current), font=_font(96, bold=True)) + 40
        draw.rounded_rectangle([bx, y + 26, bx + tw + 44, y + 92], 33, fill=GREEN)
        draw.text((bx + 22, y + 40), label, font=pf, fill=WHITE)
        draw.text((100, y + 118), f"Ø 6 Monate: {_eur(reference)}",
                  font=_font(30), fill=INK_SOFT)

    # ── Preisverlauf ────────────────────────────────────────────────────────
    cy = y + 200
    draw.text((100, cy), "PREISVERLAUF", font=_font(24, bold=True), fill=INK_SOFT)
    _sparkline(draw, [p for p in (prices or []) if p and p > 0], (100, cy + 50, W - 100, cy + 330))
    draw.line([(100, cy + 336), (W - 100, cy + 336)], fill=LINE, width=3)

    # ── Urteil ──────────────────────────────────────────────────────────────
    if tag:
        tf = _font(36, bold=True)
        tw = draw.textlength(tag, font=tf)
        draw.rounded_rectangle([100, cy + 386, 100 + tw + 60, cy + 462], 38, fill=(232, 240, 250))
        draw.text((130, cy + 404), tag, font=tf, fill=NAVY)

    # ── Fuss ────────────────────────────────────────────────────────────────
    draw.text((70, H - 140), "Preisverlauf ansehen auf snagga.de",
              font=_font(34, bold=True), fill=WHITE)
    draw.text((70, H - 88), "Allzeittief · 90-Tage-Schnitt · kaufen oder warten?",
              font=_font(26), fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
