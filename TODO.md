# snagga.de — Nächste Aufgaben (Stand: 2026-08-09)

## 2026-08-09: Doppelte Produkt-URLs in der Sitemap — ✅ UMGESETZT (noch nicht gepusht)

**Auslöser:** Google-Mail „Neue Gründe dafür, dass Seiten nicht indexiert
werden". Search Console meldete **97 indexiert gegen 2.880 nicht indexiert**,
davon 2.580 „Gefunden – zurzeit nicht indexiert" und 118 „Gecrawlt – zurzeit
nicht indexiert".

**Ursache:** Die Sitemap führte jedes Produkt **doppelt** — `/deal/{asin}` und
`/preis/{asin}`. Da `/deal` seinen Canonical auf `/preis` setzt (bewusst so,
gegen Duplicate Content zwischen zwei identisch aussehenden Seiten), war rund
die Hälfte aller angemeldeten URLs prinzipiell nicht indexierbar. Bei einer
jungen Domain mit knappem Crawl-Budget hat das die kanonischen `/preis`-Seiten
ausgebremst, bevor Google sie überhaupt erreicht hat. Verstärkt dadurch, dass
auch der komplette interne Linkgraph (Deal-Karten, Kategorie-JSON-LD, RSS) auf
`/deal` zeigte — Googlebot musste pro Produkt zweimal crawlen.

**Geändert in `backend/main.py`:**

| Stelle | Vorher | Nachher |
|---|---|---|
| `sitemap()` | `/deal` **und** `/preis` je Produkt | nur `/preis` — halbiert die Sitemap |
| `sitemap()` Priorität | alle `/preis` gleich (0.5, weekly) | aktive Deals 0.7/daily, ruhende Katalogseiten 0.4/weekly |
| `_deal_card_html()` | `href="/deal/{asin}"` | `href="/preis/{asin}"` |
| `category_page()` JSON-LD | `"url": "/deal/{asin}"` | `"url": "/preis/{asin}"` |
| `rss_feed()` | `<link>/deal/{asin}` | `<link>/preis/{asin}` (Deal-Titel bleibt im `<title>`) |

**Bewusst unangetastet:** `/deal/{asin}` bleibt vollständig funktionsfähig
inklusive der „Deal ist abgelaufen"-Seite mit ähnlichen Deals — kein 301,
damit Share-Titel (Preis + Rabatt) und die Sackgassen-Vermeidung erhalten
bleiben. Social-Poster nutzen ohnehin `/share/{asin}`. Preisalarm-Mails in
`alerts.py` behalten `/deal/` (E-Mails werden nicht gecrawlt).

**Regel ab jetzt:** `/preis/{asin}` ist die einzige kanonische Produkt-URL.
`/deal/` gehört nie in Sitemap, interne Links, strukturierte Daten oder Feeds.

**Nicht anfassen — die noindex-Fälle sind alle gewollt:** abgelaufene
`/deal`-Seiten, leere Kategorieseiten, `/preis` ohne `is_catalog_quality`
(Thin-Content-Schutz), `/preis-check`-Antwortseiten, 404-Seiten. Die 404-Seite
liefert bewusst echten 404-Status statt Redirect (Soft-404 wäre schlechter);
410 ist nicht nötig.

**Offen — nach dem Deploy zu prüfen:**

1. `https://www.snagga.de/sitemap.xml` aufrufen, verifizieren dass keine
   `/deal/`-Einträge mehr enthalten sind.
2. Sitemap in der Search Console neu einreichen (stößt Neubewertung an).
3. Über 4–8 Wochen beobachten. Der relevante Indikator ist **nicht** das Sinken
   der nicht-indexierten Seiten, sondern ob die **indexierten** über 97 steigen.
4. Bleibt die Zahl stehen, ist der Flaschenhals Domain-Autorität (Backlinks) —
   dann dort ansetzen, nicht weiter an der Technik.

---

## Offen (David, 2026-07-06 abends): Ad-hoc-Fetch — kurze Schon-Frist

Wenn ein Produkt ad hoc gesucht/geöffnet wurde (On-Demand-Fetch in price_page,
siehe fetch_and_store_history), soll es danach ~4h im Katalog "geschont" bleiben
(Preis + History nicht sofort wieder als veraltet gelten) — sonst muss bei
Hin-und-Herspringen zwischen Seiten jedes Mal neu geladen werden.

Vermutlich SCHON weitgehend erfüllt: last_checked wird nach dem Live-Fetch auf
"jetzt" gesetzt, und PRICE_FRESH_HOURS=24h verhindert einen erneuten Live-Fetch
für 24h (>4h, deckt den Fall also ab). Vor dem Bau neuer Logik zuerst live
verifizieren, ob das Hin-und-Herspringen wirklich neu lädt oder ob es (wie
vermutet) schon funktioniert — evtl. war das ein einmaliger Effekt der
zwei Bugs, die in Commit 943946f gefixt wurden.

---


Entstanden aus der Preis-Check-Utility (`/preis-check`, `/preis/{asin}`),
die am 2026-07-05 live ging. Sechs Punkte, sortiert nach Abhängigkeit.

**Update 2026-07-05 abends: ALLE 6 Punkte + Backfill UMGESETZT, committet
(ed7f214, 64940ea, d6b40d6, 6a165d1, 677b13f) und gepusht.** Header/Logo auf
`/preis/{asin}` und `/deal/{asin}` folgen jetzt 1:1 dem React-Header (Breite
1840px/98%). Preisseite: 90/1 Jahr/Gesamt-Tab-Umschalter (Default 90 Tage),
Zwei-Spalten-Layout (links Bild/Titel/CTA/Affiliate/Preisalarm, rechts Urteil/
Chart/Eckdaten, Zeilen exakt ausgerichtet, einheitliche 8px-Abstände).
Preis-Check-Lookup: echte Kategorie + kategoriebezogener Affiliate-Tag + Bild-
Fallback. Backfill der 3 On-the-fly-Testseiten (GoPro→Kamera & Foto, Sony→
Elektronik & Foto, instax→Sonstiges) direkt in Prod-DB erledigt.

---

## 1. Kategorie beim Preis-Check ermitteln — ✅ ERLEDIGT 2026-07-05 (Commit 677b13f)

`_parse_product()` liest jetzt `rootCategory` aus (als `root_cat` im Return-Dict).
Der Preis-Check-Endpoint nutzt `classify_category(title, root_cat)` statt hart
„Sonstiges" (bleibt Fallback, wenn keine Klassifikation greift).

## 2. Affiliate-Link passend zur Kategorie — ✅ ERLEDIGT 2026-07-05 (Commit 677b13f)

Preis-Check-Endpoint ruft jetzt `_affiliate_tag_for(category)` statt des harten
`AFFILIATE_TAG`. Kategoriespezifische Tags kommen aus Env `AMAZON_CATEGORY_TAGS`
(JSON); ohne Eintrag Fallback `snagga-21`.

## 3. Produktbild fehlt (Platzhalter statt echtem Bild) — ✅ ERLEDIGT 2026-07-05 (Commit 677b13f)

`_parse_product()` bekam denselben `P/{asin}`-Bild-Fallback wie `_parse_deal()`:
Ist `imagesCSV` leer, wird die generische ASIN-Bild-URL gesetzt statt einer
leeren URL (die zum Favicon-Platzhalter führte). Live-Diagnose der Ursache
(warum imagesCSV bei manchen On-the-fly-Lookups leer ist) steht aus — der
Fallback behebt aber das sichtbare Symptom robust. **Hinweis:** Der Live-Keepa-
Pfad ließ sich lokal nicht end-to-end testen (kein KEEPA_API_KEY im lokalen
`.env`, nur auf Render).

**Backfill: ✅ ERLEDIGT** — die 3 On-the-fly-Testseiten (leeres image_url)
wurden direkt in der Prod-DB nachgezogen (Kategorie aus Titel reklassifiziert,
P/{asin}-Bild + passender Affiliate-Link gesetzt), im Browser verifiziert.

## 4. Zeitraum-Umschalter am Preisverlauf-Chart (90 / 365 Tage / gesamt) — ✅ ERLEDIGT 2026-07-05

Text spricht von „90-Tage-Schnitt", Chart zeigt aber standardmäßig 365 Tage —
Inkonsistenz. **Neu:** 3 Buttons nebeneinander über dem Chart —
**90 Tage / 1 Jahr / Gesamt**, Default **90 Tage** (deckt sich mit dem
Ø90-Text). Ersetzt den bisherigen einzelnen „Gesamte Historie anzeigen"-Button
in `main.py::price_page` (aktuell nur 365↔gesamt).

## 5. Logo/Header der Preisseite an die Hauptseite anpassen — ✅ ERLEDIGT 2026-07-05

`/preis/{asin}` hat einen eigenen, schmaleren Header (`max-width:1360px`,
Logo klebt ohne inneren Wrapper am linken Rand) statt dem Standard-Header
der App (`maxWidth: 1840, width: 98%, margin: 0 auto`, Logo + Suchleiste +
Telegram + Theme-Toggle). Preisseite soll optisch wie „Teil der Seite"
wirken, nicht wie eine separate Mini-Site.

## 6. Preisseite zu tief — Zwei-Spalten-Layout — ✅ ERLEDIGT 2026-07-05

Aktuell läuft alles einspaltig untereinander (Bild → Urteil → Chart →
Eckdaten-Tabelle → CTA → Alarm-Formular → ähnliche Deals) → viel Scrollen.
**Neu, bei Standardbreite:** Chart **links**, Eckdaten (Urteil, Preis-Tabelle,
CTA) **rechts** in einer vertikalen Spalte daneben — soll ohne Scrollen
passen. Alarm-Formular + „Ähnliche Deals" bleiben darunter, volle Breite.

---

## Reihenfolge

1 → 2 (direkt abhängig) → 3 (parallel möglich) → Backfill (nach 1+3) → 4 → 5+6
(gemeinsam, da beides die HTML-Struktur von `price_page` betrifft)

## Entschieden

- Chart-Umschalter: 3 Buttons (90 / 365 / Gesamt), Default 90 Tage
- Bereits erzeugte Test-Seiten werden einmalig per Backfill korrigiert
- Redesign (#5, #6) wird direkt umgesetzt, kein Mockup vorab
