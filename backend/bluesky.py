"""
Bluesky Bot — automatische Deal-Alerts für snagga.de (AT Protocol)
Env vars: BLUESKY_HANDLE (z.B. snagga.bsky.social), BLUESKY_APP_PASSWORD,
          BLUESKY_MIN_SCORE (default 45)

Anders als Mastodon verlinkt Bluesky URLs im Text nicht automatisch —
Links brauchen "Facets" mit UTF-8-Byte-Offsets. Taktung analog Mastodon
bewusst zurückhaltend (3 feste Posts/Tag, siehe scheduler.py), damit der
Account nicht als Spam eingestuft wird wie damals auf mastodon.social.
"""
import os
import httpx
from datetime import datetime, timezone

BLUESKY_HANDLE   = os.getenv("BLUESKY_HANDLE", "")
BLUESKY_PASSWORD = os.getenv("BLUESKY_APP_PASSWORD", "")
MIN_SCORE        = int(os.getenv("BLUESKY_MIN_SCORE", "45"))

_PDS_URL = "https://bsky.social"

# Rotierende Hashtag-Sets — identische Hashtags bei jedem Post sind ein
# Spam-Muster (Lektion aus der Mastodon-Sperre).
_HASHTAG_SETS = [
    "#Schnäppchen #AmazonDeals",
    "#Angebot #Sparen",
    "#Deal #Bestpreis",
    "#Rabatt #AmazonAngebot",
]


def _fmt(price: float) -> str:
    return f"{price:.2f}".replace(".", ",") + " €"


def _build_post(deal: dict) -> tuple[str, list[dict]]:
    """Baut Post-Text + Facets (Link, Hashtags). Bluesky-Limit: 300 Zeichen."""
    name     = (deal.get("name") or deal.get("title") or "")[:90]
    current  = deal.get("current_price", 0)
    original = deal.get("original_price", 0)
    tag      = deal.get("tag") or ""
    asin     = deal.get("asin", "")
    disc     = round((original - current) / original * 100) if original > current else 0

    tag_line = {
        "Allzeittiefpreis":    "🏆 Allzeittiefpreis!",
        "Historisch günstig":  "📉 Historisch günstig",
        "Stark gefallen":      "🔥 Stark gefallen",
        "Seltene Gelegenheit": "💎 Seltene Gelegenheit",
        "Preis gefallen":      "📌 Preis gefallen",
    }.get(tag, "💸 Neuer Deal")

    price_line = f"💶 {_fmt(current)}"
    if disc > 0:
        price_line += f" (-{disc}%) statt {_fmt(original)}"

    # /preis statt /share (23.08.2026): /share ist eine reine OG-Vorschau, die
    # per JS auf /?asin= weiterleitet — fuer Crawler eine Sackgasse ohne Inhalt.
    # Oeffentliche, crawlbare Posts sind der einzige SEO-Wert dieses Kanals;
    # der Link muss deshalb auf die kanonische Produktseite zeigen. /preis ist
    # immer indexierbar und hat dieselben OG-Tags, die Vorschau bleibt gleich.
    # Telegram behaelt bewusst /share (Chat-Links werden nicht gecrawlt).
    url      = f"https://www.snagga.de/preis/{asin}"
    hashtags = _HASHTAG_SETS[hash(asin) % len(_HASHTAG_SETS)]

    text = "\n\n".join([f"{tag_line} {name}", price_line, url, hashtags])

    # Facets: Byte-Offsets (UTF-8!) für den klickbaren Link und die Hashtags
    facets = []
    b = text.encode("utf-8")

    url_start = b.find(url.encode("utf-8"))
    if url_start >= 0:
        facets.append({
            "index": {"byteStart": url_start, "byteEnd": url_start + len(url.encode("utf-8"))},
            "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}],
        })

    for word in hashtags.split():
        w = word.encode("utf-8")
        start = b.find(w)
        if start >= 0:
            facets.append({
                "index": {"byteStart": start, "byteEnd": start + len(w)},
                "features": [{"$type": "app.bsky.richtext.facet#tag", "tag": word.lstrip("#")}],
            })

    return text, facets


async def _upload_card(client, jwt: str, deal: dict) -> dict | None:
    """
    Rendert die snagga-Bildkarte und laedt sie als Blob hoch. Gibt das
    Blob-Objekt fuer das Embed zurueck, oder None.

    Bewusst fehlertolerant: schlaegt Rendern oder Upload fehl, wird der Post
    trotzdem abgesetzt — nur eben ohne Bild. Ein Textpost ist immer noch
    besser als ein stiller Ausfall des Kanals, und die Ursache steht im Log.

    `stand` ist Pflicht, nicht Kosmetik: Amazon verlangt den Zeitstempel neben
    jedem Preis, der seltener als stuendlich aktualisiert wird — ein
    hochgeladenes Bild aktualisiert sich nie. Faellt `last_checked` aus, gibt
    es kein Bild, denn ein Preis ohne belegbaren Erhebungszeitpunkt darf so
    nicht hinaus.
    """
    stand = deal.get("last_checked")
    if not stand:
        print("  Bluesky: kein last_checked — Post ohne Bild (Zeitstempelpflicht)")
        return None
    try:
        from pin_image import render_bsky_card
        png = render_bsky_card(
            name=deal.get("name") or "Produkt",
            current=deal.get("current_price") or 0.0,
            reference=deal.get("original_price") or 0.0,
            tag=deal.get("tag") or "",
            category=deal.get("category") or "",
            stand=stand,
        )
        resp = await client.post(
            f"{_PDS_URL}/xrpc/com.atproto.repo.uploadBlob",
            headers={"Authorization": f"Bearer {jwt}", "Content-Type": "image/png"},
            content=png,
        )
        resp.raise_for_status()
        return resp.json()["blob"]
    except Exception as e:
        print(f"  Bluesky: Bildkarte fehlgeschlagen ({e}) — Post ohne Bild")
        return None


async def post_deal(deal: dict) -> bool:
    """Postet einen Deal auf Bluesky. Gibt True bei Erfolg zurück."""
    if not BLUESKY_HANDLE or not BLUESKY_PASSWORD:
        return False
    if (deal.get("deal_score") or 0) < MIN_SCORE:
        return False

    text, facets = _build_post(deal)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # 1) Session erstellen (App-Password-Login)
            resp = await client.post(
                f"{_PDS_URL}/xrpc/com.atproto.server.createSession",
                json={"identifier": BLUESKY_HANDLE, "password": BLUESKY_PASSWORD},
            )
            resp.raise_for_status()
            session = resp.json()

            # 2) Post als Record anlegen
            record = {
                "$type":     "app.bsky.feed.post",
                "text":      text,
                "facets":    facets,
                "langs":     ["de"],
                "createdAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
            }

            # 1a) Bildkarte in Markenoptik. Sobald ein Post ein Bild traegt,
            # zeigt Bluesky KEINE Linkvorschau mehr — der Link bleibt aber ueber
            # das Facet klickbar, und die eigene Karte sagt mehr als die
            # generische Vorschau der Zielseite.
            blob = await _upload_card(client, session["accessJwt"], deal)
            if blob:
                alt = (f"Preiskarte von snagga.de: {(deal.get('name') or 'Produkt')[:120]}, "
                       f"aktuell {_fmt(deal.get('current_price') or 0)}.")
                record["embed"] = {
                    "$type": "app.bsky.embed.images",
                    "images": [{
                        "alt":   alt[:1000],
                        "image": blob,
                        # Ohne aspectRatio reserviert Bluesky im Feed die falsche
                        # Hoehe und laesst die Karte springen.
                        "aspectRatio": {"width": 1200, "height": 630},
                    }],
                }
            resp = await client.post(
                f"{_PDS_URL}/xrpc/com.atproto.repo.createRecord",
                headers={"Authorization": f"Bearer {session['accessJwt']}"},
                json={
                    "repo":       session["did"],
                    "collection": "app.bsky.feed.post",
                    "record":     record,
                },
            )
            resp.raise_for_status()
            print(f"  Bluesky ✓ {deal.get('asin')} gepostet")
            return True
    except Exception as e:
        print(f"  Bluesky ✗ Fehler: {e}")
        return False
