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
NAVY      = (21, 61, 104)     # #153D68 — Markenblau, identisch zur Website
NAVY_DARK = (13, 40, 70)
WHITE     = (255, 255, 255)
MUTED     = (150, 168, 190)
GREEN     = (34, 168, 108)
CARD      = (255, 255, 255)
INK       = (24, 34, 48)
INK_SOFT  = (98, 112, 130)
LINE      = (222, 228, 236)
# Das Orange der Wortmarke. Auf dunklem Grund gilt der Dark-Theme-Wert #D4694A
# (index.css), nicht der hellere #C85E43 — auf Marineblau hat er mehr Kontrast.
ACCENT    = (212, 105, 74)

_FONT_DIR = Path(__file__).parent / "assets" / "fonts"

# Plus Jakarta Sans ist die Schrift der Website (frontend/public/fonts/pjs-*.woff2).
# Hier liegt sie als TTF, weil Pillow kein WOFF2 lesen kann; erzeugt mit fontTools
# aus genau diesen Dateien, damit Pin und Website dieselbe Schrift zeigen.
# Beide Schriften stehen unter freien Lizenzen (SIL OFL bzw. Bitstream Vera).
_FACES = {
    (False, False): "PlusJakartaSans-Regular.ttf",
    (True,  False): "PlusJakartaSans-Bold.ttf",
    (False, True):  "PlusJakartaSans-SemiBold.ttf",
}


def _font(size: int, bold: bool = False, semi: bool = False) -> ImageFont.FreeTypeFont:
    """
    Schrift aus dem Repo statt aus dem System: Render-Container bringen keine
    garantierten Fonts mit, und `ImageFont.load_default()` wäre eine
    Bitmap-Schrift — auf 1000 px Breite unbrauchbar.

    Fällt auf DejaVu zurück, falls eine Datei fehlt: ein Pin in der falschen
    Schrift ist immer noch besser als ein Absturz im Scheduler.
    """
    name = _FACES[(bold and not semi, semi)]
    try:
        return ImageFont.truetype(str(_FONT_DIR / name), size)
    except OSError:
        return ImageFont.truetype(
            str(_FONT_DIR / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), size)


def _wordmark(draw: ImageDraw.ImageDraw, x: int, y: int, size: int):
    """
    Offizielle Wortmarke: „snagga" weiss, „.de" im Akzent-Orange — dieselbe
    Zweiteilung wie im Seitenkopf (DealsPage.jsx) und in den SSR-Seiten
    (main.py, Klasse .accent).
    """
    f = _font(size, bold=True)
    draw.text((x, y), "snagga", font=f, fill=WHITE)
    draw.text((x + draw.textlength("snagga", font=f), y), ".de", font=f, fill=ACCENT)


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

    Warum kein Tagespreis auf dem Bild (Entscheidung David, 11.08.2026)
    -------------------------------------------------------------------
    Pinterest zeigt einen Pin über Monate, oft am stärksten lange nach dem
    Anlegen. Ein Pin, der „39,99 €" behauptet, ist dann schlicht falsch — und
    zwar bei einer Marke, deren ganzes Versprechen „wir prüfen Preise ehrlich"
    lautet. Deshalb wirbt der Pin für die DIENSTLEISTUNG, nicht für einen
    einzelnen Deal: Überschrift ist die Frage „Kaufen oder warten?", Beweis ist
    die Preiskurve, und der Tagespreis steht dort, wo er hingehört — auf der
    Zielseite, wo er stündlich aktualisiert wird.

    Was auf dem Bild bleibt, altert langsam: die Form der Kurve und die
    Preisspanne des gezeigten Zeitraums. Beides ist auch in einem Jahr noch eine
    ehrliche Aussage über das Produkt.

    `reference` (Ø-180-Tage-Preis) und `current` fliessen nur noch in die
    Spannen-Berechnung ein, nicht mehr als beworbene Zahl.
    """
    img  = Image.new("RGB", (W, H), NAVY)
    draw = ImageDraw.Draw(img)

    # Produktname klein und zweizeilig: er ist das Beispiel, nicht die Botschaft.
    # Die Kartenhöhe hängt davon ab und die Karte wird vor ihrem Inhalt
    # gezeichnet, deshalb der Umbruch vorab.
    name_font  = _font(30)
    name_lines = _wrap(draw, name, name_font, W - 200, 2)

    hist = [p for p in (prices or []) if p and p > 0]
    lo   = min(hist) if hist else 0.0
    hi   = max(hist) if hist else 0.0

    # ── Kopf ────────────────────────────────────────────────────────────────
    draw.rectangle([0, 0, W, 210], fill=NAVY_DARK)
    _wordmark(draw, 70, 66, 64)
    draw.text((70, 150), "AMAZON PREIS-CHECK", font=_font(26), fill=MUTED)
    if category:
        cf = _font(24)
        tw = draw.textlength(category.upper(), font=cf)
        draw.rounded_rectangle([W - 70 - tw - 40, 96, W - 70, 152], 28, fill=(35, 82, 132))
        draw.text((W - 90 - tw, 110), category.upper(), font=cf, fill=WHITE)

    # ── Karte ───────────────────────────────────────────────────────────────
    card_top = 270
    # +940 statt +902: der Beispielname wird nach unten gezeichnet, bei zwei
    # Zeilen stiess er sonst über die Kartenkante hinaus.
    card_bot = min(card_top + 940 + len(name_lines) * 34, H - 190)
    draw.rounded_rectangle([60, card_top, W - 60, card_bot], 36, fill=CARD)

    # Die Frage ist die Botschaft. Sie ist der Grund, warum jemand klickt, und
    # sie stimmt in einem Jahr genauso wie heute.
    y = card_top + 58
    draw.text((100, y), "Kaufen oder", font=_font(74, bold=True), fill=INK)
    draw.text((100, y + 84), "warten?", font=_font(74, bold=True), fill=NAVY)
    draw.text((100, y + 190), "Der Preisverlauf verrät es.",
              font=_font(34), fill=INK_SOFT)

    # ── Preisverlauf ────────────────────────────────────────────────────────
    cy = y + 262
    _sparkline(draw, hist, (100, cy, W - 100, cy + 290))
    draw.line([(100, cy + 296), (W - 100, cy + 296)], fill=LINE, width=3)

    # Spanne statt Tagespreis: eine Zahl, die den Pin überlebt.
    if lo > 0 and hi > lo:
        draw.text((100, cy + 336), "PREISSPANNE IM GEZEIGTEN ZEITRAUM",
                  font=_font(22, bold=True), fill=INK_SOFT)
        draw.text((100, cy + 376), f"{_eur(lo)}  –  {_eur(hi)}",
                  font=_font(46, bold=True), fill=NAVY)
        spread = round((1 - lo / hi) * 100)
        if spread >= 5:
            sf, label = _font(28, bold=True), f"{spread} % Unterschied"
            tw = draw.textlength(label, font=sf)
            draw.rounded_rectangle([100, cy + 448, 100 + tw + 44, cy + 504], 28, fill=GREEN)
            draw.text((122, cy + 461), label, font=sf, fill=WHITE)

    # Das Produkt ist das Beispiel, nicht die Werbung — entsprechend klein.
    ny = cy + 546
    draw.text((100, ny), "BEISPIEL", font=_font(20, bold=True), fill=MUTED)
    for line in name_lines:
        ny += 34
        draw.text((100, ny), line, font=name_font, fill=INK_SOFT)

    # ── Fuss ────────────────────────────────────────────────────────────────
    ff = _font(34, bold=True)
    lead = "Jeden Amazon-Preis prüfen: "
    draw.text((70, H - 140), lead, font=ff, fill=WHITE)
    _wordmark(draw, 70 + int(draw.textlength(lead, font=ff)), H - 140, 34)
    draw.text((70, H - 88), "Preisverlauf · Allzeittief · 90-Tage-Schnitt",
              font=_font(26), fill=MUTED)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
