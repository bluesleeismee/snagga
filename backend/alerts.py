"""
Preisalarm-E-Mails via Brevo (transaktionale API).
Env vars: BREVO_API_KEY, BREVO_SENDER_EMAIL (in Brevo verifiziert),
          BREVO_SENDER_NAME (default "snagga.de")

DSGVO: Versand nur nach Double-Opt-in (Bestätigungs-Mail). Jede Mail enthält
einen Abmeldelink. Alarm-Mails verlinken auf die snagga-Deal-Seite, NIE direkt
auf Amazon — Amazon PartnerNet verbietet Affiliate-Links in E-Mails.
"""
import os
import httpx

BREVO_API_KEY  = os.getenv("BREVO_API_KEY", "")
SENDER_EMAIL   = os.getenv("BREVO_SENDER_EMAIL", "alarm@snagga.de")
SENDER_NAME    = os.getenv("BREVO_SENDER_NAME", "snagga.de")

_API_URL = "https://api.brevo.com/v3/smtp/email"
_BASE    = "https://www.snagga.de"


def alerts_enabled() -> bool:
    return bool(BREVO_API_KEY)


async def _send(to_email: str, subject: str, html_content: str) -> bool:
    """Verschickt eine transaktionale Mail über Brevo. False wenn nicht konfiguriert/Fehler."""
    if not BREVO_API_KEY:
        print("  Brevo ✗ kein API-Key gesetzt — Mail nicht versendet")
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                _API_URL,
                headers={
                    "api-key":      BREVO_API_KEY,
                    "content-type": "application/json",
                    "accept":       "application/json",
                },
                json={
                    "sender": {"name": SENDER_NAME, "email": SENDER_EMAIL},
                    "to":     [{"email": to_email}],
                    "subject": subject,
                    "htmlContent": html_content,
                },
            )
            resp.raise_for_status()
            print(f"  Brevo ✓ Mail an {to_email} ({subject})")
            return True
    except Exception as e:
        print(f"  Brevo ✗ Fehler: {e}")
        return False


def _shell(inner: str) -> str:
    """Einheitliches, schlichtes Mail-Layout in snagga-Farben."""
    return f"""<div style="font-family:system-ui,-apple-system,Segoe UI,sans-serif;max-width:520px;margin:0 auto;color:#1F1E1D">
  <div style="background:#153D68;padding:16px 20px">
    <span style="color:#EDE9E3;font-size:20px;font-weight:800">snagga<span style="color:#C85E43">.de</span></span>
  </div>
  <div style="padding:24px 20px;background:#FAF8F5">{inner}</div>
</div>"""


def _fmt(price: float) -> str:
    return f"{price:.2f}".replace(".", ",") + " €"


async def send_confirmation(email: str, asin: str, name: str, target: float, token: str) -> bool:
    """Double-Opt-in: Bestätigungslink, bevor überhaupt ein Alarm scharf wird."""
    confirm_url = f"{_BASE}/alarm/bestaetigen?token={token}"
    inner = f"""
    <h2 style="font-size:18px;margin:0 0 12px">Preisalarm bestätigen</h2>
    <p style="font-size:14px;line-height:1.6;color:#4A4845">
      Du möchtest benachrichtigt werden, sobald <strong>{name}</strong>
      auf <strong>{_fmt(target)}</strong> oder weniger fällt. Bitte bestätige einmal deine E-Mail-Adresse:
    </p>
    <p style="margin:20px 0">
      <a href="{confirm_url}" style="background:#C85E43;color:#fff;text-decoration:none;padding:12px 22px;font-weight:700;font-size:15px;display:inline-block">Preisalarm aktivieren</a>
    </p>
    <p style="font-size:12px;color:#7E7A75;line-height:1.5">
      Wenn du das nicht warst, ignoriere diese Mail einfach — ohne Bestätigung wird nichts gespeichert oder versendet.
    </p>"""
    return await _send(email, "Bitte bestätige deinen Preisalarm — snagga.de", _shell(inner))


async def send_alert(email: str, asin: str, name: str, price: float, target: float, token: str) -> bool:
    """Der eigentliche Alarm: Preis erreicht. Link auf snagga-Deal-Seite, NICHT Amazon."""
    deal_url  = f"{_BASE}/deal/{asin}"
    unsub_url = f"{_BASE}/alarm/abmelden?token={token}"
    inner = f"""
    <h2 style="font-size:18px;margin:0 0 12px">🔔 Dein Wunschpreis ist erreicht!</h2>
    <p style="font-size:14px;line-height:1.6;color:#4A4845">
      <strong>{name}</strong> kostet jetzt <strong style="color:#C85E43">{_fmt(price)}</strong>
      (dein Wunschpreis war {_fmt(target)}).
    </p>
    <p style="margin:20px 0">
      <a href="{deal_url}" style="background:#C85E43;color:#fff;text-decoration:none;padding:12px 22px;font-weight:700;font-size:15px;display:inline-block">Zum Deal auf snagga.de</a>
    </p>
    <p style="font-size:12px;color:#7E7A75;line-height:1.5">
      Preise ändern sich schnell — ohne Gewähr. Diesen Alarm hast du selbst gesetzt.
      <a href="{unsub_url}" style="color:#7E7A75">Abmelden</a>.
    </p>"""
    return await _send(email, f"Preisalarm: {name[:60]} für {_fmt(price)}", _shell(inner))
