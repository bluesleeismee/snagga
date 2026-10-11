"""
Pausenmodus — snagga "auf Eis" legen, ohne etwas zu löschen.

Eingeführt am 11.10.2026: David hat das Keepa-Abo gekündigt. Ohne Keepa frieren
alle Preise ein. Eine Deal-Seite mit eingefrorenen Preisen ist schlimmer als
gar keine — sie zeigt Besuchern falsche Preise, und das Amazon-Partnerprogramm
verlangt aktuelle Preisangaben. Deshalb ein Schalter statt Abschalten.

Einschalten:  Render → Environment → SNAGGA_PAUSED=true   (danach Neustart)
Ausschalten:  SNAGGA_PAUSED entfernen oder auf false setzen, Keepa-Key prüfen.

Was im Pausenmodus passiert:
  * Scheduler: nur der Keep-alive-Ping (scheduler.create_scheduler(paused=True)).
    Keine Keepa-Abrufe, keine Telegram/Bluesky/Mastodon/Pinterest-Posts,
    keine Preisalarme, kein Index-Budget, keine Chart-Eviction.
  * Seiten mit Preisen (Liste unten, "html") liefern eine Pausenseite mit
    Status 503 + Retry-After — "vorübergehend weg", nicht "gelöscht".
  * API-Endpunkte mit Preisen ("api") liefern 503 {"paused": true}.
  * Sitemap: nur Startseite, Ratgeber, Rechtliches.
  * Der Ratgeber /ratgeber/kaufzeitpunkt bleibt normal online (keine
    Live-Preise), nur sein Link auf den Preis-Check ist ausgeblendet.
  * Frontend: fragt /status ab und zeigt auf der Startseite die Pausenseite.
  * Datenbank und Code bleiben unverändert. Nichts wird gelöscht.

Bewusst NICHT gesperrt: /health (Keep-alive, hält Supabase wach), /status,
/sitemap.xml, /ratgeber/*, /alarm/abmelden (Abmelden muss immer gehen),
/debug/* und /admin/reindex-budget (nur mit Token, für Kontrollen).
"""
import os

PAUSED = os.getenv("SNAGGA_PAUSED", "").strip().lower() in ("1", "true", "yes", "ja", "on")

# Seiten, die Besucher direkt im Browser öffnen → Pausenseite (HTML).
_HTML_PREFIXES = (
    "/share/", "/deal/", "/preis/", "/preis-check", "/kategorie/",
    "/prime-day", "/feed.xml", "/alarm/bestaetigen",
)

# Endpunkte, die das Frontend oder Jobs per fetch aufrufen → JSON.
_API_PREFIXES = (
    "/deals", "/product/", "/produkt/", "/categories", "/alarm/setzen",
    "/refresh", "/deep-sync", "/admin/seed-bestsellers", "/admin/mark-all-posted",
    "/test-telegram", "/test-mastodon", "/pin/", "/pinterest/",
)


def pause_kind(path: str) -> str | None:
    """'html', 'api' oder None (= normal durchlassen)."""
    if path.startswith(_HTML_PREFIXES):
        return "html"
    if path.startswith(_API_PREFIXES):
        return "api"
    return None
