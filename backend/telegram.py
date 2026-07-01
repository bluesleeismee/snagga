"""
Telegram Bot — automatische Deal-Alerts für snagga.de
Env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, TELEGRAM_MIN_SCORE (default 45)
"""
import os
import httpx

TELEGRAM_TOKEN   = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL = os.getenv("TELEGRAM_CHANNEL_ID", "")
MIN_SCORE        = int(os.getenv("TELEGRAM_MIN_SCORE", "45"))

_ESCAPE_CHARS = r"_*[]()~`>#+-=|{}.!"


def _esc(text: str) -> str:
    for ch in _ESCAPE_CHARS:
        text = text.replace(ch, f"\\{ch}")
    return text


def _fmt(price: float) -> str:
    return f"{price:.2f}".replace(".", ",") + " €"


def _build_message(deal: dict) -> str:
    name     = (deal.get("name") or deal.get("title") or "")[:80]
    current  = deal.get("current_price", 0)
    original = deal.get("original_price", 0)
    tag      = deal.get("tag") or ""
    category = deal.get("category") or ""
    asin     = deal.get("asin", "")
    disc     = round((original - current) / original * 100) if original > current else 0

    tag_line = {
        "Allzeittiefpreis":   "🏆 *Allzeittiefpreis\\!*",
        "Historisch günstig": "📉 *Historisch günstig*",
        "Stark gefallen":     "🔥 *Stark gefallen*",
        "Seltene Gelegenheit":"💎 *Seltene Gelegenheit*",
        "Preis gefallen":     "📌 *Preis gefallen*",
    }.get(tag, "💸 *Neuer Deal*")

    price_line = f"💶 *{_esc(_fmt(current))}*"
    if disc > 0:
        price_line += f" \\(\\-{disc}%\\)\n~~{_esc(_fmt(original))}~~ Ø\\-Preis 6 Monate"

    snagga_url = f"https://snagga.de/share/{asin}"
    amazon_url = f"https://www.amazon.de/dp/{asin}?tag=snagga\\-21"

    return "\n".join([
        tag_line,
        "",
        _esc(name + ("…" if len(deal.get("name") or "") > 80 else "")),
        "",
        price_line,
        "",
        f"📂 {_esc(category)}",
        "",
        f"[📦 Deal ansehen]({snagga_url})  ·  [🛒 Amazon]({amazon_url})",
    ])


async def post_deal(deal: dict) -> bool:
    """Post a deal to the Telegram channel. Returns True on success."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHANNEL:
        return False
    if (deal.get("deal_score") or 0) < MIN_SCORE:
        return False

    text = _build_message(deal)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                json={
                    "chat_id":                  TELEGRAM_CHANNEL,
                    "text":                     text,
                    "parse_mode":               "MarkdownV2",
                    "disable_web_page_preview": False,
                },
            )
            resp.raise_for_status()
            print(f"  Telegram ✓ {deal.get('asin')} gepostet")
            return True
    except Exception as e:
        print(f"  Telegram ✗ Fehler: {e}")
        return False
