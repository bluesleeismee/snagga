"""
Datenbank-Sicherung vor der Pause (11.10.2026).

Exportiert jede Tabelle der Supabase-Datenbank als CSV (gzip) in den Ordner
backup_JJJJ-MM-TT neben diesem Skript. Liest nur, ändert nichts.

Warum: ~580.000 Preispunkte und ~28.000 Produkte stecken in der DB — Daten,
die Keepa-Tokens gekostet haben und sich ohne Abo nicht neu holen lassen.
Supabase pausiert Gratis-Projekte nach längerer Inaktivität; eine eigene
Kopie macht davon unabhängig.

Start: backup_db.bat doppelklicken. Die DATABASE_URL (Session Pooler, Port
5432 — derselbe Wert wie in Render) wird abgefragt, falls sie nicht in .env steht.
"""
import asyncio
import gzip
import os
import shutil
import ssl
import sys
from datetime import date
from pathlib import Path

import asyncpg
from dotenv import load_dotenv

load_dotenv()


async def main() -> int:
    url = os.getenv("BACKUP_DATABASE_URL") or ""
    if not url:
        print("DATABASE_URL von Supabase einfuegen (wie in Render, Port 5432)")
        print("und Enter druecken:")
        url = input("> ").strip()
    if not url.startswith("postgres"):
        print("Das sieht nicht nach einer Postgres-URL aus. Abbruch.")
        return 1

    # Wie database.py: Supabase verlangt SSL, Zertifikatspruefung aus.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    ziel = Path(__file__).parent / f"backup_{date.today().isoformat()}"
    ziel.mkdir(exist_ok=True)

    conn = await asyncpg.connect(url, ssl=ctx, timeout=30)
    try:
        tabellen = [r["table_name"] for r in await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1")]
        print(f"{len(tabellen)} Tabellen gefunden.\n")
        for t in tabellen:
            csv_pfad = ziel / f"{t}.csv"
            await conn.copy_from_table(t, output=str(csv_pfad), format="csv", header=True)
            with open(csv_pfad, "rb") as src, gzip.open(str(csv_pfad) + ".gz", "wb") as dst:
                shutil.copyfileobj(src, dst)
            csv_pfad.unlink()
            n = await conn.fetchval(f'SELECT COUNT(*) FROM "{t}"')
            print(f"  {t:<28} {n:>10,} Zeilen".replace(",", "'"))
    finally:
        await conn.close()

    print(f"\nFertig. Sicherung liegt in: {ziel}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
