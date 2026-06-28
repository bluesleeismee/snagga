# snagga.de — Deal-Strategie (Stand: Juni 2026)

## Grundprinzip

snagga.de ist keine Preis-Massenplattform, sondern eine kuratierte Deal-Seite mit Qualitätsanspruch.
Ziel: echte Preisvorteile sichtbar machen, Vertrauen aufbauen, hohe Klickwahrscheinlichkeit.

> **prüfen → bewerten → ranken → kuratieren → anzeigen**

---

## Markt & Scope

- Nur **amazon.de** (domain=3 in Keepa)
- Keine AT/CH-Domains (existieren nicht als eigene Amazon-Marketplaces)
- Affiliate-Tag: `snagga-21`

---

## Datenquellen

| Quelle | Zweck | Kosten |
|--------|-------|--------|
| Keepa `/deals` | ASIN-Discovery: welche Produkte sind gerade im Preis gefallen | wenige Tokens |
| Keepa `/product` | Deep-Sync: Preishistorie, ATL, Ø-Preis, Sales Rank, Rating | 1–2 Tokens/ASIN |
| Amazon-Produktseite (Scraping) | Stündlicher Live-Preis-Check der aktiven Deals | 0 Tokens |

**CamelCamelCamel: vollständig entfernt.**

### Token-Budget
- Plan: 20 Tokens/Minute = **28.800 Tokens/Tag**
- Geschätzter Verbrauch: ~6.000 Tokens/Tag
- Puffer: >22.000 Tokens/Tag

---

## Hard Filters — Qualifikation

Nur Produkte, die **alle** Kriterien erfüllen, kommen in die Datenbank:

| Kriterium | Bedingung |
|-----------|-----------|
| Rating | ≥ 4.0 ★ |
| Reviews | ≥ 50 |
| Preis | ≤ 85% des 90-Tage-Ø **oder** ≤ ATL × 1.05 |
| Verkäufer | csv[0] (Amazon direkt) **oder** csv[1] mit Buy-Box-Shipping = 0 (FBA-Proxy) |
| Sales Rank | ≤ Kategorie-Schwellwert (siehe unten) |

### Sales Rank Schwellwerte (anpassbar nach ersten echten Daten)

| Kategorie | Max. Sales Rank |
|-----------|----------------|
| Elektronik | 8.000 |
| Gaming | 5.000 |
| Haushalt | 20.000 |
| Küche | 20.000 |
| Sport | 25.000 |
| Beauty | 30.000 |
| Werkzeug | 25.000 |

Die Schwellwerte sind kategoriespezifisch — Nischenprodukte und saisonale Produkte sollen
nicht unnötig ausgeschlossen werden.

### FBA-Proxy
Keepa hat kein direktes `isFBA`-Feld. Proxy:
- Buy-Box-Shipping (csv[14]) = 0 → gilt als Prime/FBA-fähig
- Kombination mit csv[1] (Marketplace NEW) erlaubt, wenn Proxy erfüllt
- Schützt vor China-Dropshipping, lässt aber FBA-Markendeals (Anker, Philips etc.) durch

---

## Deal-Score (0–100)

```
Score = 40% × Abstand zu 90-Tage-Ø
      + 30% × Abstand zum All-Time-Low
      + 20% × Popularität
      + 10% × Stabilität
```

### Abstand zu 90-Tage-Ø
```
Faktor = (avg90 - current) / avg90   [0–1, negativ → 0]
```

### Abstand zum ATL
```
Faktor = (atl_distance) / avg90   [0–1]
atl_distance = max(0, current - atl)
Je näher am ATL, desto höher der Faktor.
```

### Popularität
```
Rank-Faktor = 1 - (sales_rank / max_kategorie_schwellwert)   [0–1]
Rating-Faktor = (rating - 4.0) / 1.0   [0–1, ab 4.0]
Review-Faktor = log10(reviews) / log10(10000)   [0–1]

Popularität = (Rank-Faktor × 0.5) + (Rating-Faktor × 0.3) + (Review-Faktor × 0.2)
```

Sales Rank wird **invertiert und normiert** — niedriger Rank = hoher Faktor (mathematisch korrekt).

### Stabilität
```
Faktor = 1.0   wenn Preis seit ≥ 24h stabil
Faktor = 0.3   wenn Preis < 24h auf diesem Niveau (Kurzzeit-Ausreisser)
```
Verhindert, dass kurzfristige Preisglitches künstlich hochgewertet werden.

### Score-Grenze
- Score ≥ 40 → aktiver Deal
- Score < 40 → deaktivieren / nicht anzeigen

---

## Tags (automatisch, datenbasiert, maximal 1 pro Deal)

Priorität absteigend (höchste Priorität gewinnt):

| Priorität | Tag | Bedingung |
|-----------|-----|-----------|
| 1 | **Allzeittiefpreis** | current ≤ ATL × 1.02 |
| 2 | **Historisch günstig** | current ≤ 80% des 180-Tage-Ø |
| 3 | **Stark gefallen** | current ≤ 70% des 90-Tage-Ø (≥30% Drop) |
| 4 | **Seltene Gelegenheit** | current ≤ ATL × 1.08 |
| 5 | **Preis gefallen** | current ≤ 85% des 90-Tage-Ø |

Kein Tag wenn keine Bedingung erfüllt (Deal kommt nur durch Hard Filter, Score aber < Tag-Schwelle).

---

## Volumen & Verteilung

| Pool | Anzahl | Sichtbar |
|------|--------|---------|
| Aktive Deals | 200 | ✓ |
| Backup-Deals | 100 | ✗ (rücken automatisch nach) |
| Top Picks | 10 | ✓ (Slider + Grid-Kategorie) |
| Top Pick Reserve | 5–10 | ✗ (sofort verfügbar bei Wegfall) |

Kategorien werden **nicht gleich gross** gehalten — mehr Deals in Kategorien mit mehr
verfügbarer Qualität (dynamisch nach verfügbaren qualifizierten Deals).

---

## Kategorien (7)

1. Elektronik
2. Gaming
3. Haushalt
4. Küche
5. Sport
6. Beauty
7. Werkzeug

---

## Top Picks

**Definition:** Die 10 Produkte mit dem höchsten Deal-Score aus dem aktiven Pool.

**Anzeige:**
- Slider oben auf der Seite (BestPicksSlider, bereits vorhanden)
- Eigene Filter-Kategorie "Top Picks" im unteren Grid

**Automatisch berechnet** — keine manuelle Auswahl.

---

## Update-Logik

### Stündlich (APScheduler)
1. Keepa `/deals` abrufen → neue ASIN-Kandidaten holen
2. Hard Filters anwenden (Rating, Reviews, Sales Rank, FBA-Proxy)
3. Score berechnen für Kandidaten
4. Aktive Deals: Preis via Amazon-Produktseite prüfen (0 Tokens)
5. Deals mit Score < 40 → `is_active = false`, Backup nachrücken
6. **Backup-Verifikation vor Go-Live:** Bevor Backup aktiv wird → Live-Preis prüfen.
   Stimmt Preis nicht mehr → nächstes Backup prüfen (keine Race Condition)
7. Top 10 nach Score → `is_top_pick = true`
8. Tags neu berechnen und setzen

### Nächtlich 03:00 Uhr (Deep-Sync)
- Keepa `/product` für alle 300 aktiven + Backup-Deals
- Aktualisiert: Sales Rank, 90-Tage-Ø, 180-Tage-Ø, ATL, Rating, Reviews, Preishistorie
- Scores und Tags neu berechnen
- Basis für Qualitätsentscheide des nächsten Tages

### Priorisierung
- Top Picks: alle 30 Minuten Preis-Check
- Reguläre aktive Deals: stündlich
- Backup-Deals: nur beim Deep-Sync (nachts)

---

## Datenbankschema (Erweiterungen)

Neue Spalten in `products`:

| Spalte | Typ | Bedeutung |
|--------|-----|-----------|
| `is_active` | BOOLEAN DEFAULT true | Wird gerade angezeigt |
| `is_top_pick` | BOOLEAN DEFAULT false | Unter den Top 10 |
| `is_backup` | BOOLEAN DEFAULT false | Im Backup-Pool, nicht sichtbar |
| `is_fba` | BOOLEAN DEFAULT false | FBA-Proxy erfüllt |
| `sales_rank` | INTEGER | Aktueller Sales Rank aus Keepa |
| `tag` | TEXT | Automatisch gesetzter Tag |
| `last_checked` | TIMESTAMP | Wann zuletzt Preis geprüft |
| `score_breakdown` | TEXT | JSON: Score-Komponenten für Debugging |

---

## Share-Button (Frontend)

- Button auf jeder Deal-Card
- Optionen: Link kopieren / WhatsApp / Telegram
- URL-Struktur: `snagga.de/?asin=XXXXXXXXXX`
- Kein Tracking, kein Cookie — DSGVO-konform

---

## Was bewusst weggelassen wurde

| Feature | Grund |
|---------|-------|
| Community-Deals | Für später vorgemerkt |
| Manuelle Kuratierung | Nicht geplant — alles datenbasiert |
| AT/CH-Filter | Nicht umsetzbar (kein eigener Marketplace) |
| "Redaktionell hervorgehoben" Tag | Würde manuellen Aufwand erfordern |
| Amazon PA API | Zugang erfordert 3 qualifizierende Verkäufe |
| Länderwahl DE/AT/CH aktiv | Vorerst nur DE |
| Sales Rank als UI-Filter | Intern — Oberfläche bleibt simpel |
