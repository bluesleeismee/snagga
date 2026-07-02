"""
Mastodon Bot — automatische Deal-Alerts für snagga.de
Env vars: MASTODON_INSTANCE_URL, MASTODON_ACCESS_TOKEN, MASTODON_MIN_SCORE (default 45)
"""
import os
import httpx

MASTODON_INSTANCE = os.getenv("MASTODON_INSTANCE_URL", "").rstrip("/")
MASTODON_TOKEN    = os.getenv("MASTODON_ACCESS_TOKEN", "")
MIN_SCORE         = int(os.getenv("MASTODON_MIN_SCORE", "45"))


def _fmt(price: float) -> str:
    return f"{price:.2f}".replace(".", ",") + " €"


def _build_status(deal: dict) -> str:
    name     = (deal.get("name") or deal.get("title") or "")[:100]
    current  = deal.get("current_price", 0)
    original = deal.get("original_price", 0)
    tag      = deal.get("tag") or ""
    category = deal.get("category") or ""
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

    snagga_url = f"https://www.snagga.de/share/{asin}"
    full_name  = deal.get("name") or ""

    return "\n\n".join([
        tag_line,
        name + ("…" if len(full_name) > 100 else ""),
        f"{price_line}\n📂 {category}",
        snagga_url,
        "#Schnäppchen #AmazonDeals #Sparen",
    ])


async def post_deal(deal: dict) -> bool:
    """Postet einen Deal als öffentlichen Toot. Gibt True bei Erfolg zurück."""
    if not MASTODON_INSTANCE or not MASTODON_TOKEN:
        return False
    if (deal.get("deal_score") or 0) < MIN_SCORE:
        return False

    status = _build_status(deal)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{MASTODON_INSTANCE}/api/v1/statuses",
                headers={"Authorization": f"Bearer {MASTODON_TOKEN}"},
                data={"status": status, "visibility": "public", "language": "de"},
            )
            resp.raise_for_status()
            print(f"  Mastodon ✓ {deal.get('asin')} gepostet")
            return True
    except Exception as e:
        print(f"  Mastodon ✗ Fehler: {e}")
        return False
