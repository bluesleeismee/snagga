"""
Pinterest-Automatisierung: ein Pin je Lauf, aus dem aktiven Deal-Bestand.

Warum Pinterest überhaupt
-------------------------
Es ist der einzige Kanal im Plan, dessen Inhalte nicht nach Stunden verschwinden:
Pins ranken über Monate in Pinterests eigener Suche und bei Google Bilder. Küche,
Haushalt, Wohnen und Garten sind dort stark nachgefragt und passen zum Katalog.

Zwei Dinge, die man vorher wissen muss
--------------------------------------
1. **Trial Access reicht nicht.** Mit Trial-Zugang legt Pinterest alle Pins als
   Sandbox-Objekte an, die NUR der Ersteller sieht — null Reichweite. Erst
   „Standard Access" macht Pins öffentlich, und der verlangt ein Demo-Video des
   OAuth-Flows plus eine Prüfung durch Pinterest.
2. **Der Refresh-Token rotiert.** Pinterest gibt bei jedem Refresh einen NEUEN
   Refresh-Token zurück (60 Tage gültig, unbegrenzt erneuerbar). Er darf deshalb
   nicht nur in einer Env-Variable stehen — nach dem ersten Refresh wäre die
   veraltet und der Zugang nach 60 Tagen tot. Er wird hier in `app_settings`
   gespeichert und bei jedem Refresh überschrieben. Die Env-Variable dient nur
   als Startwert beim allerersten Lauf.

Compliance
----------
Der Pin verlinkt auf die snagga-`/preis`-Seite, NIE direkt auf Amazon. Damit
enthält der Pin selbst keinen Affiliate-Link (kein Werbehinweis nötig, die
Kennzeichnung steht auf der Zielseite), und der Klick landet im eigenen Bestand
statt sofort bei Amazon — genau das ist der Zweck. Das Pin-Bild ist eigenes
Material aus eigenen Daten, kein Amazon-Produktfoto (siehe pin_image.py).
"""
from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timedelta

import httpx

from database import get_pool

API = "https://api.pinterest.com/v5"

APP_ID       = os.getenv("PINTEREST_APP_ID", "")
APP_SECRET   = os.getenv("PINTEREST_APP_SECRET", "")
# Startwert; danach gilt der rotierende Token aus app_settings.
SEED_REFRESH = os.getenv("PINTEREST_REFRESH_TOKEN", "")
# JSON: {"Küche, Haushalt & Wohnen": "boardid", …}. Kategorien exakt wie in der DB.
BOARDS_RAW   = os.getenv("PINTEREST_BOARDS", "{}")
DEFAULT_BOARD = os.getenv("PINTEREST_DEFAULT_BOARD", "")
MIN_SCORE     = int(os.getenv("PINTEREST_MIN_SCORE", "55"))
SITE          = os.getenv("PUBLIC_SITE_URL", "https://www.snagga.de")

_SETTING_KEY = "pinterest_refresh_token"
_token_cache: dict = {"access": "", "expires": datetime.min}


def _boards() -> dict:
    try:
        return json.loads(BOARDS_RAW) or {}
    except json.JSONDecodeError:
        print("[pinterest] PINTEREST_BOARDS ist kein gültiges JSON — ignoriert.")
        return {}


def enabled() -> bool:
    return bool(APP_ID and APP_SECRET and (DEFAULT_BOARD or _boards()))


async def _get_refresh_token() -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        stored = await conn.fetchval(
            "SELECT value FROM app_settings WHERE key=$1", _SETTING_KEY)
    return stored or SEED_REFRESH


async def _store_refresh_token(token: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO app_settings (key, value, updated_at) VALUES ($1,$2,$3) "
            "ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=EXCLUDED.updated_at",
            _SETTING_KEY, token, datetime.utcnow(),
        )


async def _access_token() -> str:
    """
    Access-Token holen (30 Tage gültig) und dabei den rotierenden Refresh-Token
    mitschreiben. Im Speicher gecacht, aber mit reichlich Sicherheitsabstand
    erneuert — ein abgelaufener Token kostet sonst einen ganzen Post-Slot.
    """
    if _token_cache["access"] and datetime.utcnow() < _token_cache["expires"]:
        return _token_cache["access"]

    refresh = await _get_refresh_token()
    if not refresh:
        print("[pinterest] Kein Refresh-Token — OAuth-Flow noch nicht durchlaufen.")
        return ""

    basic = base64.b64encode(f"{APP_ID}:{APP_SECRET}".encode()).decode()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{API}/oauth/token",
            headers={"Authorization": f"Basic {basic}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token", "refresh_token": refresh},
        )
    if r.status_code != 200:
        print(f"[pinterest] Token-Refresh fehlgeschlagen ({r.status_code}): {r.text[:200]}")
        return ""

    data = r.json()
    _token_cache["access"]  = data.get("access_token", "")
    _token_cache["expires"] = datetime.utcnow() + timedelta(
        seconds=max(int(data.get("expires_in", 2592000)) - 3600, 600))

    # Rotation: der neue Refresh-Token ersetzt den alten. Ohne dieses Schreiben
    # ist der Zugang nach spätestens 60 Tagen unwiderruflich weg.
    new_refresh = data.get("refresh_token")
    if new_refresh and new_refresh != refresh:
        await _store_refresh_token(new_refresh)

    return _token_cache["access"]


SCOPES = "boards:read,boards:write,pins:read,pins:write"


def authorize_url(redirect_uri: str, state: str) -> str:
    from urllib.parse import urlencode
    return "https://www.pinterest.com/oauth/?" + urlencode({
        "client_id": APP_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
    })


async def exchange_code(code: str, redirect_uri: str) -> tuple[bool, str]:
    """
    Einmaliger Tausch Authorization-Code → Tokens, danach nie wieder nötig.

    Existiert, damit die Einrichtung ein Klick im Browser ist statt einer
    curl-Zeile: Pinterest schickt den Code an snagga zurück, snagga holt die
    Tokens und legt den Refresh-Token in `app_settings` ab. Ab da erneuert sich
    der Zugang selbst (siehe _access_token).
    """
    if not (APP_ID and APP_SECRET):
        return False, "PINTEREST_APP_ID / PINTEREST_APP_SECRET fehlen."

    basic = base64.b64encode(f"{APP_ID}:{APP_SECRET}".encode()).decode()
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{API}/oauth/token",
            headers={"Authorization": f"Basic {basic}",
                     "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "authorization_code", "code": code,
                  "redirect_uri": redirect_uri},
        )
    if r.status_code != 200:
        return False, f"Pinterest antwortete {r.status_code}: {r.text[:300]}"

    data = r.json()
    refresh = data.get("refresh_token")
    if not refresh:
        return False, "Antwort enthielt keinen Refresh-Token."
    await _store_refresh_token(refresh)
    _token_cache["access"]  = data.get("access_token", "")
    _token_cache["expires"] = datetime.utcnow() + timedelta(
        seconds=max(int(data.get("expires_in", 2592000)) - 3600, 600))
    return True, "Verbunden."


async def list_boards() -> list[dict]:
    """Boards des verbundenen Kontos — für die Einrichtung, um Board-IDs zu finden."""
    token = await _access_token()
    if not token:
        return []
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{API}/boards", headers={"Authorization": f"Bearer {token}"},
                             params={"page_size": 50})
    if r.status_code != 200:
        print(f"[pinterest] Boards laden fehlgeschlagen ({r.status_code}): {r.text[:200]}")
        return []
    return [{"id": b.get("id"), "name": b.get("name")} for b in r.json().get("items", [])]


def _description(row) -> str:
    """
    Pinterest-Beschreibungen werden durchsucht — deshalb ausgeschriebene Begriffe
    statt Hashtag-Wüste. Bewusst ohne Preisangabe im Text: Pins leben Monate,
    ein Preis im Text wäre in zwei Wochen falsch. Die Grafik trägt den
    Tagespreis, der Text die dauerhafte Aussage.
    """
    cat = (row["category"] or "").split(",")[0].strip()
    return (
        f"{row['name'][:120]} — Preisverlauf, Allzeittief und 90-Tage-Schnitt auf einen Blick. "
        f"Lohnt sich der Kauf gerade oder lohnt sich Warten? snagga prüft jeden Amazon-Preis "
        f"gegen die echte Preishistorie. {cat} Angebote, täglich aktualisiert."
    )


async def post_next_pin() -> bool:
    """
    Postet GENAU EINEN Pin. Aufgerufen von wenigen festen Scheduler-Zeiten —
    nicht stündlich. Pinterest bewertet Frequenzmuster, und die Mastodon-Lektion
    (Spam-Sperre durch zu dichte, gleichförmige Posts) gilt hier genauso.
    """
    if not enabled():
        return False

    boards = _boards()
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT asin, name, category, current_price, original_price, tag, deal_score "
            "FROM products WHERE is_active=true AND pinterest_posted IS NULL "
            "  AND has_real_history=true AND deal_score >= $1 "
            "ORDER BY deal_score DESC LIMIT 1",
            MIN_SCORE,
        )
    if not row:
        print("[pinterest] Kein passender Deal offen.")
        return False

    board_id = boards.get(row["category"] or "") or DEFAULT_BOARD
    if not board_id:
        print(f"[pinterest] Kein Board für Kategorie {row['category']!r} — übersprungen.")
        return False

    token = await _access_token()
    if not token:
        return False

    asin = row["asin"]
    payload = {
        "board_id": board_id,
        "title": (row["name"] or "Deal")[:100],
        "description": _description(row)[:800],
        # Zielseite ist die dauerhafte /preis-Seite, nicht /deal: der Pin lebt
        # Monate, die Deal-Seite läuft ab. Siehe price_page() in main.py.
        "link": f"{SITE}/preis/{asin}",
        "alt_text": f"Preisverlauf von {(row['name'] or '')[:80]} auf snagga.de"[:500],
        "media_source": {
            # Pinterest holt das Bild selbst von unserer URL — dadurch entfällt
            # ein Upload und die Grafik entsteht immer aus dem aktuellen Stand.
            "source_type": "image_url",
            "url": f"{SITE}/pin/{asin}.png",
        },
    }

    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{API}/pins", headers={"Authorization": f"Bearer {token}"},
                              json=payload)

    if r.status_code not in (200, 201):
        print(f"[pinterest] Pin fehlgeschlagen ({r.status_code}): {r.text[:300]}")
        return False

    async with pool.acquire() as conn:
        await conn.execute("UPDATE products SET pinterest_posted=$1 WHERE asin=$2",
                           datetime.utcnow(), asin)
    print(f"[pinterest] Pin erstellt: {asin} · {row['name'][:60]}")
    return True
