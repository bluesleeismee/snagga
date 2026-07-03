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

    url      = f"https://www.snagga.de/share/{asin}"
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
