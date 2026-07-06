# snagga.de — Nächste Aufgaben (Stand: 2026-07-05)

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
