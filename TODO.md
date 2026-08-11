# snagga.de — Nächste Aufgaben (Stand: 2026-08-11)

## 2026-08-11 (abends): Erste echte Messwerte — zwei Annahmen widerlegt

**1. Der vermutete Engpass war nicht der Engpass.** Der Verdacht vom 09.08.
lautete, Quality Gate (a) (`QUALITY_DISCOUNT_FACTOR`) sei die Bremse. Gemessen
über drei Tage, 105.561 Kandidaten:

| Grund | Anteil |
|---|---|
| `preis_min` (< 20 €) | 34,2 % |
| `hard_filter:reviews` | 26,4 % |
| `kategorie_unbekannt` | 11,2 % |
| `hard_filter:sales_rank` | 11,1 % |
| `hard_filter:anti_spike` | 7,6 % |
| `preis_min_kategorie` | 6,0 % |
| `hard_filter:kein_vertrauenssignal` | 0,9 % |
| **`hard_filter:rabatt_zu_klein`** | **0,0 % (5 Zeilen)** |

`QUALITY_DISCOUNT_FACTOR` ist also **kein Regler** — daran zu drehen hätte
nichts gebracht. Die drei realen Hebel, in dieser Reihenfolge:
Preisuntergrenze (20 €), Review-Mindestzahl (100 / 500 bei Auto) und die
Kategorie-Zuordnung, die jeden neunten Kandidaten mangels Zuordnung verwirft.

**2. Der Hard-Filter ist gar nicht der Grund für nur 92 aktive Deals.**
Angenommen wurden 194 / 787 / 223 ASINs an den drei Tagen — ein Vielfaches der
92, die aktiv sind, bei `MAX_ACTIVE = 500`. Zwischen „qualifiziert" und „aktiv"
geht also der Grossteil verloren, und zwar **nach** dem Filter: Deaktivierung
älter 4 h, der stündliche Preis-Check oder das Überschreiben des Pools. Das ist
die Stelle, an der der nächste Schritt ansetzen muss — nicht an Schwellwerten.

**3. Aufbewahrung war zu knapp bemessen.** Gemessen ~35.000 Rohzeilen/Tag statt
der geschätzten 2.800, also ~10 MB/Tag. Bei 500 MB Supabase-Limit wäre die
Datenbank in ~7 Wochen voll gewesen; die zuerst gesetzten 120 Tage Rohdaten
wären über 1 GB geworden. Default deshalb auf **14 Tage** gesenkt — die
Verdichtung läuft ja vorher, die Langzeitreihe bleibt vollständig.

**4. Marken-Hubs: Datenlage besser als gedacht, aber die erste Messung war
irreführend.** Der Katalog hat **20.586 Produkte** (nicht ~1.450), `brand` ist
zu **79,6 %** gefüllt, über 300 Marken haben ≥ 5 Produkte. Aber: die Liste wird
von No-Name-Marktplatzmarken angeführt (Risareyi 287, WTHYGB 68, Home-Vision
113) — Hubs dafür wären genau die dünnen Seiten, die vermieden werden sollen.
`/debug/brand-coverage` zählt deshalb jetzt nur noch **crawlbare** Produkte
(aktiv oder `is_catalog_quality`) und markiert bekannte Marken. Erst diese Zahl
ist die Entscheidungsgrundlage. **Braucht einen weiteren Deploy.**

---

## 2026-08-11: Aufbewahrung, Messbarkeit, Positionierungs-Nachzug

**Gemessen (live, ohne Deploy):** `/deals` liefert aktuell **92 aktive Deals**
statt der 24 vom 09.08. Die Lockerung wirkt also, `MAX_ACTIVE = 500` ist aber
weiter weit weg. In diesen 92 ist `brand` bei **35 (38 %) leer** — das ist der
Backfill-Stand für die Marken-Hubs, aber nur die Stichprobe der aktiven Deals,
nicht der ~1.450 Produkte mit `/preis`-Seite.

**Gebaut:**

- `retention.py` — verdichtet `deal_observations` täglich um 04:30 nach
  `deal_observation_daily` (Tag × Kategorie × Ablehnungsgrund, mit Anzahl,
  Ø/Median-Preisvorteil gegen Ø90, Median-Preis, Rating, Reviews) und löscht
  erst danach Rohzeilen älter als `OBSERVATION_RETENTION_DAYS` (Default 120).
  **Reihenfolge ist die halbe Miete:** verdichten, prüfen, dann löschen — es
  wird nur gelöscht, was nachweislich eine Tageszeile hat. `0` = nie löschen.
  Damit fällt das Wachstum von ~2.800 auf ~100–200 Zeilen/Tag; die Langzeitreihe
  für die Datenstory bleibt vollständig, verloren geht nur die ASIN-Ebene.
- `/debug/observation-stats?token=…&days=7` — Ablehnungsgründe aus der DB statt
  aus dem Render-Log (das rotiert). Beantwortet „welcher Hard-Filter ist der
  Engpass?" über mehrere Tage statt nur für den letzten Lauf.
- `/debug/brand-coverage?token=…&min_products=5` — Entscheidungsgrundlage für
  die Marken-Hubs: wie viel Prozent der Produkte haben eine Marke, und wie viele
  Marken erreichen die Mindestanzahl. Gruppiert case-insensitiv und getrimmt,
  sonst würden „ANKER"/„Anker"/„anker " drei dünne Hubs ergeben.

**Positionierung nachgezogen** (offener Punkt vom 09.08.):
`MARKETING_STRATEGIE_2026.html` und `INDEX.html` beschreiben nicht mehr den
„Fake-Rabatt-Detektor", sondern den richtigen Kaufzeitpunkt; Tonalitätsregel und
die beiden methodischen Grenzen der Datenstory stehen jetzt im Dokument selbst.

**Nicht möglich ohne dich:**

- `/debug/*` verlangt `ADMIN_TOKEN` — die Zahlen kann nur jemand mit dem Token
  abrufen. Nach dem Deploy beide URLs einmal aufrufen (oder mir den Token geben).
- Render-Log und Supabase sind von hier aus nicht erreichbar, deshalb der Umweg
  über die Endpoints statt einer direkten Auswertung.
- Ungetestet gegen echtes Postgres: im Sandbox gibt es keine DB. Python
  kompiliert, das SQL ist Postgres-spezifisch (`PERCENTILE_CONT`, `FILTER`) und
  beim ersten Lauf zu beobachten. Fehler sind gekapselt — schlägt die Verdichtung
  fehl, wird nichts gelöscht und der Deal-Job läuft weiter.
- `frontend/dist/index.html` enthält noch den alten „Fake-Rabatte"-Text. Live ist
  der neue (geprüft), es ist nur ein veraltetes Build-Artefakt im Repo.

---

## Stand 2026-08-09

## Wachstumsplan — Reihenfolge (beschlossen 2026-08-09)

Ausgangslage: GSC meldet 97 indexierte gegen 2.880 nicht indexierte Seiten.
**Kernbefund: nicht die Seitenmenge ist das Problem, sondern fehlende
Domain-Autorität.** Es gibt bereits ~1.450 `/preis`-Seiten — noch mehr
Produktseiten zu bauen ändert daran nichts.

| # | Maßnahme | Status |
|---|---|---|
| 1 | Sitemap entdoppelt, interne Links kanonisch | ✅ 50226fd |
| 2 | Positionierung „richtiger Zeitpunkt" | ✅ 7bc81e2 |
| 3 | `deal_observations` — Datenerfassung für die Story | ✅ 8b2f993 |
| 4 | Deal-Nachschub: Hard-Filter messen und justieren | ⏳ läuft (c13cec3) |
| 5 | Marken-Hubs `/marke/{brand}` | ⬜ als Nächstes |
| 6 | Bestenlisten `/bestenliste/{kategorie}/{jahr-monat}` | ⬜ |
| 7 | Pinterest-Automatisierung | ⬜ |
| 8 | Datenstory + Presse-Pitches | ⬜ Oktober |

**Zu 5 (Marken-Hubs) — vor dem Bau klären:** Wie sauber ist die `brand`-Spalte
gefüllt? Laut Kommentar in `scoring.py` ist sie bei `/deal`-Daten oft leer
(Backfill läuft). Mindestanzahl Produkte pro Marke festlegen, sonst entstehen
genau die dünnen Seiten, die Google ohnehin nicht indexiert. Zweck der Hubs ist
eine zweite Navigationsebene — aktuell hängen ~1.450 Produktseiten an nur 11
Kategorieseiten, Googlebot kommt bei knappem Budget nicht in die Tiefe.

**Bewusst NICHT:** bezahlte Werbung (24h-Amazon-Cookies rechnen sich nie),
Reddit-/Foren-Posting (wird als Spam erkannt), gekaufte Backlinks.

**Erwartung:** Vor Oktober wirkt nichts davon. Der Indikator ist nicht das
Sinken der nicht-indexierten Seiten, sondern ob die **indexierten** über 97
steigen. Bleibt die Zahl stehen, ist der Engpass Autorität — dann dort ansetzen.

**Offener Nebenpunkt:** `deal_observations` wächst mit ~2.800 Zeilen/Tag
(doppelt so viel wie geschätzt) → ~1 Mio. Zeilen und 150–250 MB pro Jahr,
Supabase-Limit ist 500 MB. Aufbewahrungsregel einbauen, bevor es eng wird.

---

## 2026-08-09: Deal-Nachschub — Hard-Filter sichtbar gemacht

**Befund im Render-Log (15:05):** Von ~3.300 Kandidaten pro Lauf bleiben nur
**24 aktive Deals** übrig, bei `MAX_ACTIVE = 500`. Aufschlüsselung des Logs:
1.462 unter der 20-Euro-Grenze, 160 unbekannte Kategorie, **1.652 am Hard-Filter**,
0 am Score. Wenig Ware heisst wenig Klicks und wenig Affiliate-Umsatz.

Welche der acht Hard-Filter-Bedingungen der Engpass ist, sagte das Log nicht —
also erst messen, dann justieren.

**Gebaut:**

- `scoring.py::hard_filter_reason()` — gleiche Logik wie `passes_hard_filters()`,
  gibt aber den Ablehnungsgrund zurück (`zustand`, `rating`, `reviews`,
  `sales_rank`, `keine_referenz`, `anti_spike`, `avg365_anker`,
  `rabatt_zu_klein`, `kein_vertrauenssignal`). `passes_hard_filters()` ist jetzt
  ein dünner Wrapper darum — **Verhalten unverändert**, in 40.000 Zufallsfällen
  gegen den Wrapper geprüft.
- `scraper.py`: zählt die Gründe pro Lauf und loggt sie als Zeile
  `HardFilter im Detail: rabatt_zu_klein:812 · reviews:340 · …`. Zusätzlich
  landet der Grund feingranular in `deal_observations.reject_reason`
  (`hard_filter:rabatt_zu_klein` statt nur `hard_filter`).
- `scoring.py::QUALITY_DISCOUNT_FACTOR` — Quality Gate (a) ist jetzt über die
  Env-Variable `QUALITY_DISCOUNT_FACTOR` verstellbar (Default 0.80 = mind. 20 %
  unter Ø90). **Nachjustieren ohne Deploy**, nur Env in Render ändern.
  Höher (0.85) = mehr Deals bei schwächerem Preisvorteil.

**Verdacht (noch unbestätigt):** Keepa liefert Kandidaten ab −15 % gegenüber der
eigenen Referenz, Quality Gate (a) verlangt danach nochmals −20 % gegenüber Ø90.
Diese Kombination dürfte der Hauptengpass sein. Die neue Log-Zeile beweist es
oder widerlegt es.

**Nächster Schritt:** Nach dem Deploy die Zeile `HardFilter im Detail:` im
Render-Log ansehen und danach entscheiden — nicht vorher an Schwellwerten drehen.

---

## 2026-08-09: Positionierung — „richtiger Zeitpunkt" statt „Fake-Rabatte" (Commit 7bc81e2)

**Entscheidung David:** snagga positioniert sich künftig über den **richtigen
Kaufzeitpunkt**, nicht als Gegner von Amazon. Die Leitfrage ist „lohnt sich der
Kauf jetzt — oder lohnt sich Warten?". Begriffe wie „Fake-Rabatt", „Betrug",
„Verkaufstrick" oder „nie verlangt" kommen in Nutzertexten nicht mehr vor.

**Warum, über den Ton hinaus:** snagga verdient über Amazon PartnerNet. Eine
Marke, die sich gegen ihren eigenen Vertragspartner positioniert, ist
publizistisch und vertraglich angreifbar. Formulierungen deshalb immer aus
Nutzersicht, nie als Vorwurf an Amazon.

**Umgestellt:**

- `frontend/index.html` — Meta-Description, JSON-LD-Description, og:description,
  twitter:description, statischer Fallback-Text, Prime-Day-Linktext
- `backend/main.py::prime_day_page` — Title, Description, H1, Lead, Tipp-Block
  („So erkennst du einen wirklich guten Preis"), zwei FAQ-Antworten im JSON-LD
- Tonalitätsregel als Docstring in `prime_day_page` hinterlegt

**Noch offen:** `MARKETING_STRATEGIE_2026.html` beschreibt weiter die alte
Positionierung „Fake-Rabatt-Detektor" — beim nächsten Anfassen mitziehen.

---

## 2026-08-09: Presse-/Datenstory — Datenerfassung gebaut (Commit 8b2f993)

**Befund vor dem Bau gestoppt:** Der geplante Auswertungs-Report über beworbene
Rabatte lässt sich mit den aktuellen Daten **nicht** belegen.

`keepa.py` Zeile 412: `original_price = avg180_price` — der „Streichpreis" ist
der eigene 180-Tage-Durchschnitt (Fallback `max(history)` bzw. `current × 1.25`),
**nicht** Amazons beworbener Referenzpreis. Keepas `LIST_PRICE` (csv-Index 4)
wird nirgends ausgelesen, in den `IDX_*`-Konstanten fehlt er.

Eine Aussage über beworbene Rabatte wäre damit zirkulär: eigener Durchschnitt
gegen eigenen Durchschnitt. Zweites Problem: gespeichert werden nur Deals, die
die Filter **bestanden** haben — für eine Quote fehlt der Nenner.

**Positiv:** Snaggas eigene Rabattangaben sind dadurch sauber — verglichen wird
gegen den echten 180-Tage-Schnitt, nicht gegen einen aufgeblasenen UVP.

**Voraussetzung für den Report — ✅ GEBAUT 2026-08-09:**

1. Tabelle `deal_observations` (`database.py`): protokolliert bei jedem
   stündlichen Discovery-Lauf **jeden** Keepa-Kandidaten — auch die verworfenen,
   mit `accepted` und `reject_reason`. Damit existiert der Nenner.
   `UNIQUE (asin, observed_day)` + `ON CONFLICT DO NOTHING`: eine Zeile pro ASIN
   und Tag statt 24, hält die Tabelle bei ~450–1.500 Zeilen/Tag.
2. `LIST_PRICE` (Keepa csv-Index 4, neu `IDX_LIST`/`IDX_LIST_P` in `keepa.py`)
   wird mitgeschnitten. Nur protokolliert, **nicht angezeigt** — Amazon weist
   heute meist einen „typischen Preis" statt der UVP aus.
3. Schreibpfad in `scraper.py::fetch_and_update_deals`: `observe()` sammelt
   während der synchronen Filterschleife, ein gebündeltes `executemany` schreibt
   danach. Bewusst fehlertolerant (try/except mit Log) — die Statistik darf den
   Deal-Job nie blockieren.

Ab dem nächsten Deploy sammeln sich Daten. Für eine belastbare Aussage
~2 Monate rechnen, also **auswertbar ab etwa Mitte Oktober**.

**Beim Auswerten unbedingt beachten:**

- Grundgesamtheit ist „von Keepa als Rabatt gemeldete Angebote" (der /deal-
  Endpoint filtert bereits auf mind. −15 %, Elektronik-Zusatzabfrage −10 %),
  **nicht** „alle Amazon-Angebote". Jede Quote entsprechend formulieren.
- `avg365` in der Tabelle ist der Proxy aus dem /deal-Endpoint, **kein** belegtes
  Allzeittief (vgl. `resolve_atl`). Nicht als „Tiefstpreis" auswerten.
- Erst ab Deploy-Datum gefüllt; frühere Zeiträume gibt es nicht.

**Formulierung des Ergebnisses** muss zur neuen Positionierung passen: nicht
„X % der Rabatte sind Fake", sondern z. B. „Bei X % der Angebote war der Preis
in den letzten 90 Tagen schon einmal niedriger — ein Blick in die Historie
lohnt sich." Einschränkung, die in den Report gehört: Amazon zeigt heute meist
„typischer Preis" statt UVP, Keepas `LIST_PRICE` bildet das nur teilweise ab.

---

## 2026-08-09: Doppelte Produkt-URLs in der Sitemap — ✅ ERLEDIGT (Commit 50226fd, deployt)

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
