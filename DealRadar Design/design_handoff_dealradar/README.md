# Handoff: DealRadar — Mobile Deal-Discovery PWA (D-A-CH)

## Overview
DealRadar is a mobile-first PWA that surfaces Amazon products that are currently at a
historic price low, scored objectively from real price-history data (Keepa API in
production). Unlike community-vote deal sites, every deal carries a **Preis-Score (0–100)**
derived from how close the current price sits to its 180-day low. Monetisation is via
Amazon affiliate links (`amazon.de/dp/{ASIN}?tag=dealradar-21`).

Target users: 25–45, smartphone-savvy, bargain-conscious, German-speaking (DE/AT/CH).
All UI copy is in German.

This bundle contains a working interactive prototype of all six screens, in both dark and
light mode, with mock data.

## About the Design Files
The files in this bundle are **design references created in HTML** — a self-contained,
interactive prototype that demonstrates the intended look, layout, copy, and behavior.
They are **not production code to copy directly**.

The prototype is authored as "Design Components" (a streaming HTML component format:
`*.dc.html` + a small `support.js` runtime). **Do not port the `.dc.html` format or
`support.js` into your app.** Instead, recreate these designs in your target codebase using
its established framework and patterns:

- **React PWA** is the stated target (per the brief), with **Recharts** for charts. If you
  already have a component library / design system, build DealRadar with it.
- If no environment exists yet, scaffold a mobile-first React PWA (e.g. Vite + React +
  TypeScript), add a charting lib (Recharts is fine), and implement the screens below.

The logic inside the prototype (price-score formula, EUR formatting, filtering/sorting,
mock price-history generation) is plain, portable JavaScript — reuse it freely as a
reference; just re-home it into your own components/hooks.

## Fidelity
**High-fidelity (hifi).** Colors, typography, spacing, radii, and interactions are final and
intentional. Recreate the UI pixel-accurately, then wire it to real data. Treat the exact
hex values, font sizes, and spacing in the Design Tokens section as the source of truth.

---

## Screens / Views

The app is a single phone-framed surface (max-width **430px**, full-height column) with a
scrollable content area, a sticky per-screen header, and a fixed 4-item bottom navigation.
Four primary tabs + two bottom-sheet overlays.

### 1. Home / Deal Feed (`tab: deals`)
- **Purpose:** Browse current best deals; search, filter by category, sort.
- **Layout (top → bottom):**
  - **Sticky header** (`padding:18px 16px 12px`, `border-bottom:1px solid border`,
    `background:var(--bg)`, `z-index:6`):
    - Row: logo left + right cluster.
      - Logo: an 11×11 red dot (`border-radius:50%`, `box-shadow:0 0 0 4px red-soft`) +
        wordmark `DEAL` (text color) `RADAR` (red), Space Grotesk 700, 20px, `letter-spacing:-0.4px`.
      - Right: "🔥 N Allzeit-Tiefs" badge (`font-size:11px`, weight 600, color red,
        `background:red-soft`, `padding:6px 9px`, `border-radius:8px`) + 36×36 theme-toggle
        button (`border-radius:9px`, `border:1px solid border`, `background:bg-elev2`).
    - Search input (`margin-top:13px`): full-width, `padding:11px 12px 11px 36px`,
      `border-radius:11px`, `background:bg-elev2`, `border:1px solid border`, 14px Inter,
      with a `⌕` glyph absolutely positioned at left:13px. Placeholder "Produkt oder Marke suchen…".
  - **Category chips** (horizontal scroll, hidden scrollbar, `gap:8px`, `padding:13px 16px 4px`):
    each chip `padding:8px 15px`, `border-radius:10px`, 13px weight 600, `white-space:nowrap`.
    Active chip: `background:var(--text)`, `color:var(--bg)`, `border:1px solid var(--text)`.
    Inactive: `background:bg-elev2`, `color:muted`, `border:1px solid border`.
    Categories: **Alle, Elektronik, Haushalt, Küche, Gaming, Sport, Mode, Kind & Baby,
    Beauty, Garten, Auto**.
  - **Sort row** (`padding:12px 16px 4px`): label "Sortieren" (11px uppercase muted) +
    three pill buttons `padding:6px 11px`, `border-radius:8px`, 12px weight 600.
    Active: `color:red`, `background:red-soft`, `border:1px solid red`. Options:
    **Bester Deal** (`best`, by score desc), **% Rabatt** (`discount`, by discount desc),
    **Preis** (`price`, by price asc).
  - **Feed:** vertical list of Deal Cards, `gap:18px`, `padding:16px 16px 28px`. Empty
    state when no matches: centered muted text "Keine Treffer. Andere Kategorie oder Suche probieren."

### 2. Deal Card (core component — see `DealCard.dc.html`)
The repeated card used in the feed (expanded) and watchlist (compact). Container:
`background:bg-elev`, `border:1px solid border`, `border-radius:16px`, `padding:14px`,
`box-shadow:0 1px 2px shadow`, flex column `gap:13px`, `cursor:pointer` (tap opens detail modal).

- **All-time-low ribbon** (only if `isLow`): absolutely positioned straddling the top edge
  (`top:0; left:16px; transform:translateY(-50%)`), `background:red`, white, 10px weight 700,
  `letter-spacing:0.5px`, `padding:3px 9px`, `border-radius:7px`, text "🔥 ALLZEIT-TIEF",
  `box-shadow:0 3px 10px red-glow`.
- **Top row** (`gap:12px`, align-items flex-start):
  - **Image placeholder** 84×84, `border-radius:10px`, `border:1px solid border`, a
    diagonal striped fill (`repeating-linear-gradient(135deg, bg-elev2, bg-elev2 7px,
    transparent 7px, transparent 14px)` over `bg-elev2`). Centered: brand uppercase
    (Space Grotesk 700, 11px) + "PRODUKTFOTO" (mono, 7px, muted, `letter-spacing:1px`).
    *(Replace with real product image in production.)*
  - **Info column** (flex:1, min-width:0, `gap:4px`):
    - Brand line: brand (11px weight 600 uppercase muted, `letter-spacing:0.8px`) +
      optional **Prime** badge (9px weight 700, color cyan, `background:cyan-soft`,
      `padding:2px 6px`, `border-radius:5px`).
    - Name: Space Grotesk 600, 14.5px, `line-height:1.25`, clamped to 2 lines
      (`-webkit-line-clamp:2`).
    - Rating: `★` in #F5A623 + rating value (e.g. "4,6", comma decimal, weight 600 text) +
      `·` + review count (e.g. "18.420", dot thousands). 12px muted.
  - **Save button** (top-right): 34×34, `border-radius:9px`, `border:1px solid border`,
    `background:bg-elev2`. `★` (#F5A623) when saved, `☆` (muted) otherwise. Click
    **stops propagation** (does not open modal).
- **Price row** (align-items baseline, `gap:10px`, wrap):
  - Current price: **Space Grotesk 700, 29px**, color text, `letter-spacing:-0.6px` — the
    visual hero.
  - Original price: 14px muted, `line-through`.
  - Discount badge: e.g. "−38 %" (note the minus is U+2212), 12px weight 700, white on
    `background:red`, `padding:3px 8px`, `border-radius:7px`.
- **Mini chart** (expanded only): inline SVG, last 60 days, full width, height 50px.
  `viewBox="0 0 300 54"`, `preserveAspectRatio="none"`. Area fill `cyan-soft`; line
  `stroke:cyan`, `stroke-width:2`, `vector-effect:non-scaling-stroke`,
  round joins/caps.
- **Avg / low row** (expanded only): "Ø 60 T <value>" (value Space Grotesk weight 600 text)
  left; "Allzeit-Tief <value>" (value Space Grotesk weight 700 **cyan**) right. 12px,
  labels muted.
- **Price-score meter** (always): label "Preis-Score" (11px uppercase muted) +
  "{score}/100" (Space Grotesk 700, 14px, color = score color; "/100" muted). Below: a
  7px-tall track `border-radius:99px` with gradient
  `linear-gradient(90deg, #EF4444, #F59E0B 52%, #22C55E)` and a 15×15 white thumb
  (`border:2.5px solid bg-elev`, `box-shadow:0 1px 4px rgba(0,0,0,.45)`) positioned at
  `left:{score}%` (translate(-50%,-50%)). **Score color:** ≥80 `#22C55E`, 60–79 `#F59E0B`,
  <60 `#EF4444`.
- **CTA** (expanded only): full-width `<a>` to the Amazon affiliate URL, target _blank,
  click stops propagation. `background:red`, white, weight 700, 14px, `padding:12px`,
  `border-radius:10px`, text "Bei Amazon ansehen →".
- **Compact variant** (watchlist): hides mini chart, avg/low row, and CTA; keeps top row,
  price row, and score meter.

### 3. Detail Modal (bottom sheet)
- **Purpose:** Full deal detail; opens when a card is tapped.
- **Behavior:** overlay `position:absolute; inset:0; z-index:30;
  background:rgba(0,0,0,.55); backdrop-filter:blur(3px)`, content aligned to bottom.
  Clicking the overlay closes; clicking the sheet does not (stop propagation). Sheet:
  `background:bg`, `border-radius:26px 26px 0 0`, `border-top:1px solid border`,
  `padding:10px 18px 26px`, `max-height:93%`, scrollable. Entry animation `dr-sheet-up`
  (translateY 100%→0, 0.26s `cubic-bezier(.22,1,.36,1)`); overlay fades in (`dr-fade`, 0.18s).
- **Contents (top → bottom):**
  - Grabber bar: 42×5, `border-radius:99px`, `background:border`, centered.
  - Header row: brand (11px uppercase muted) + name (Space Grotesk 700, 18px) left; save
    + close (×) buttons right (38×38, `border-radius:10px`, `border:1px solid border`,
    `background:bg-elev2`).
  - Large image placeholder: full width, height 180px, `border-radius:16px`, same striped
    fill; brand label 22px + "PRODUKTFOTO" 9px. All-time-low badge top-left if applicable.
  - Price row: current price **Space Grotesk 700, 38px**, `letter-spacing:-1px`; original
    16px muted line-through; discount badge 13px white on red.
  - **Stats grid 2×2** (`gap:10px`): four cards (`background:bg-elev`, `border:1px solid
    border`, `border-radius:13px`, `padding:13px`). Label 10px uppercase muted; value
    Space Grotesk 700, 19px.
    - **Ersparnis** (savings, e.g. "−140,00 €") in `#22C55E`.
    - **Preis-Score** ("{score}/100") in score color.
    - **Allzeit-Tief** (low price) in cyan.
    - **Über Tief** (percent over the historic low, e.g. "+4,1 %") in text color.
  - **Price history chart** (180 days): heading "Preisverlauf" + "letzte 180 Tage".
    SVG `viewBox="0 0 360 150"`, `width:100%`. Area fill cyan-soft, line stroke cyan 2px.
    A cyan dot marks the all-time-low point. **Interactive tooltip:** on mouse/touch move
    over the SVG, a dashed vertical guide line, a white-filled cyan-ringed dot, and a label
    box (`fill:var(--text)`, rounded) showing the price (Space Grotesk) and relative day
    ("vor N T" / "heute") follow the pointer. Index = `round(pointerRatio × (n-1))`.
    Below: axis labels "vor 180 Tagen", "vor 90 Tagen", "heute".
  - **Primary CTA:** full-width `<a>` to Amazon, `background:red`, white, weight 700,
    15.5px, `padding:15px`, `border-radius:13px`, `box-shadow:0 8px 22px -6px red-glow`,
    text "🛒 Jetzt bei Amazon kaufen".
  - Affiliate note: centered 10.5px muted "Affiliate-Link · Preis kann bei Amazon abweichen".

### 4. Watchlist (`tab: watch`)
- **Purpose:** Saved products to monitor.
- **Layout:** sticky header "Watchlist" (Space Grotesk 700, 21px) + theme toggle.
  - When items exist: list of **compact** Deal Cards, `gap:14px`, `padding:16px 16px 28px`.
  - **Empty state** (default at first run): centered, `padding:90px 36px` — a 64×64 rounded
    tile (`background:bg-elev2`) with ⭐, heading "Noch nichts gespeichert" (Space Grotesk
    600, 17px), muted line "Tippe auf das ⭐ bei einem Deal, um ihn hier zu beobachten.",
    and a red "Deals entdecken" button that switches to the deals tab.

### 5. Alerts (`tab: alerts`)
- **Purpose:** Manage price alerts.
- **Layout:** sticky header "Preis-Alerts" + theme toggle. Below (`padding:16px 16px 28px`,
  `gap:12px`):
  - **"+ Neuer Alert"** button: full width, `border:1.5px dashed border`,
    `background:bg-elev`, color cyan, weight 700, 14px — opens the Add-Alert sheet.
  - **Alert rows** (`background:bg-elev`, `border:1px solid border`, `border-radius:14px`,
    `padding:14px`, flex `gap:12px`): product name (Space Grotesk 600, 14px, ellipsis);
    a line "Zielpreis <value cyan>" + "aktuell <value text>"; a status line (11px weight 700)
    — "Ziel erreicht ✓" in `#22C55E` when current ≤ target, else "aktiv · beobachtet" in muted.
    Right: an on/off **toggle switch** (44×26 track `border-radius:99px`; ON `background:cyan`,
    OFF `background:bg-elev2`; 20×20 white knob at left 3px↔21px, 0.15s transition) and a
    30×30 delete (×) button.
  - Empty state: centered muted "Keine aktiven Alerts. Lege oben einen an."

### 5b. Add-Alert sheet (overlay, `z-index:40`)
Same bottom-sheet chrome/animation as the detail modal. Title "Neuer Preis-Alert"
(Space Grotesk 700, 19px). Fields:
- **Produkt:** native `<select>` of all products (`brand · name`), styled like the search
  input. Changing the product resets the target to ~95% of its current price.
- **Zielpreis:** label + live value (Space Grotesk 700, 22px, cyan) + a range slider
  (`accent-color:cyan`), min = `round(low×0.8)`, max = `round(orig)`. Helper line shows the
  current price and "benachrichtigt sobald gleich oder günstiger."
- **"Alert anlegen"** primary button (red) — appends the alert and returns to the Alerts tab.

### 6. Settings (`tab: settings`)
- **Purpose:** Preferences. Sticky header "Einstellungen". Sections (`gap:24px`,
  `padding:18px 16px 28px`), each with an 11px uppercase muted label:
  - **Darstellung:** segmented control (Dunkel / Hell) — theme switch. Segmented container
    `background:bg-elev2`, `padding:4px`, `border-radius:11px`; active segment
    `background:var(--bg)`, `color:text`; inactive transparent/muted.
  - **Kategorien im Feed:** a grouped card with one row per category (all except "Alle"),
    each a label + toggle switch. Controls which categories appear when "Alle" is selected.
  - **Benachrichtigungen:** single row "Push bei Preis-Tiefs" + toggle.
  - **Region:** segmented control DE / AT / CH (values use Space Grotesk).
  - **Über die App:** info card — "DealRadar zeigt Amazon-Produkte mit objektivem
    Preis-Score auf Basis echter Preishistorie. Kein Community-Voting." + bold
    "Affiliate-Hinweis:" "Als Amazon-Partner verdienen wir an qualifizierten Käufen über
    die Links in dieser App."

### Bottom Navigation (persistent)
`display:grid; grid-template-columns:repeat(4,1fr)`, `border-top:1px solid border`,
`background:bg`, `padding:9px 6px max(10px, env(safe-area-inset-bottom))`. Each item: emoji
icon (19px) over 10px weight-600 label. Active item color = red and full-saturation icon;
inactive = muted with `filter:saturate(0)` (desaturated icon). Items:
**Deals 🔥 · Watchlist ⭐ · Alerts 🔔 · Einstellungen ⚙️**.

---

## Interactions & Behavior
- **Tab navigation:** bottom nav switches the active tab; content + sticky header swap.
- **Search:** filters deals by case-insensitive substring match against `name + brand`.
- **Category filter:** "Alle" shows all products in *enabled* categories (per Settings);
  any other chip shows only that category.
- **Sort:** Bester Deal = score desc; % Rabatt = discount desc; Preis = price asc.
- **Card tap → detail modal.** Save (★) and CTA on the card stop propagation so they don't
  open the modal.
- **Save / watchlist:** toggling ★ adds/removes from the watchlist; reflected live in the
  Watchlist tab and its empty state.
- **Detail chart tooltip:** pointer move sets a hover index; guide line, dot, and label
  update; mouse-leave clears it. Touch (`touchstart`/`touchmove`) supported;
  `touch-action:none` on the SVG.
- **Alerts:** toggle enables/disables; × removes; "+ Neuer Alert" opens the add sheet;
  submitting appends and returns to Alerts.
- **Theme:** dark ⇄ light, toggled from any screen header or Settings. Implemented via CSS
  custom properties on the root — swap the variable set; everything else reads `var(--…)`.
- **Animations:** sheets slide up `0.26s cubic-bezier(.22,1,.36,1)`; overlays fade `0.18s`;
  toggle knobs slide `0.15s`.
- **Responsive:** fixed 430px-wide phone column (`max-width:100%`). In production this is the
  full viewport of a mobile PWA; the surrounding device frame in the prototype is only for
  presentation and can be dropped.

## State Management
Single-screen app state (in the prototype, all in one component; in production, lift to a
store/context + hooks or URL where sensible):
- `tab`: `'deals' | 'watch' | 'alerts' | 'settings'`
- `theme`: `'dark' | 'light'`
- `search`: string
- `cat`: active category string (`'Alle'` or a category name)
- `sort`: `'best' | 'discount' | 'price'`
- `saved`: map of `asin → boolean` (watchlist membership)
- `openAsin`: `string | null` (which product's detail modal is open)
- `hoverIndex`: `number | null` (detail chart tooltip index)
- `addOpen`: boolean (add-alert sheet)
- `addAsin`, `addTarget`: add-alert form fields
- `notif`: boolean (push setting)
- `region`: `'DE' | 'AT' | 'CH'`
- `enabledCats`: map of `category → boolean` (feed category preferences)
- `alerts`: array of `{ id, asin, target, enabled }`

**Data fetching (production):** replace the mock product array + generated history with
Keepa API data. Each product needs: `asin, name, brand, category, rating, reviews, prime,
price, orig (list/reference), avg (window average), low (all-time/window low), history[]`
(daily price points). Derived fields (`discount`, `score`, `isLow`) are computed client-side.

### Key formulas (portable, reuse as-is)
- **Discount %:** `round((1 - price/orig) * 100)`
- **Preis-Score (0–100):** `clamp(round((avg - price) / (avg - low) * 100), 0, 100)`
  — price at avg → 0; price at low → 100.
- **isLow (🔥 all-time-low):** `price <= low * 1.05` (within 5% of the historic low).
- **Über Tief %:** `(price - low) / low * 100`.
- **EUR format (de-DE):** dot thousands, comma decimals, trailing `" €"` (e.g. `1.299,00 €`).
  Discount/savings minus sign is U+2212 (`−`), not a hyphen.

## Design Tokens

### Colors — Dark (default)
| Token | Value |
|---|---|
| `--page` (outside frame) | `#060608` |
| `--bg` (app background) | `#0B0B12` |
| `--bg-elev` (cards) | `#15151F` |
| `--bg-elev2` (chips/inputs) | `#1F1F2C` |
| `--border` | `rgba(255,255,255,0.08)` |
| `--text` | `#ECECF2` |
| `--muted` | `#8A8AA2` |
| `--shadow` | `rgba(0,0,0,0.4)` |

### Colors — Light
| Token | Value |
|---|---|
| `--page` | `#E6E6EC` |
| `--bg` | `#F5F5F8` |
| `--bg-elev` | `#FFFFFF` |
| `--bg-elev2` | `#ECECF1` |
| `--border` | `rgba(15,15,40,0.10)` |
| `--text` | `#17171F` |
| `--muted` | `#6C6C80` |
| `--shadow` | `rgba(20,20,50,0.07)` |

### Accents (both themes)
| Token | Value | Use |
|---|---|---|
| `--red` | `#FB4D3D` | deals, CTAs, badges, active nav |
| `--red-soft` | red @ 16% alpha (dark) / 10% (light) | badge/sort backgrounds |
| `--red-glow` | red @ 45% alpha | CTA shadow |
| `--cyan` | `#22D3EE` | charts, data values, active toggles |
| `--cyan-soft` | cyan @ 14% (dark) / 13% (light) | chart area fill, Prime badge bg |
| status green | `#22C55E` | savings, "Ziel erreicht", high score |
| status amber | `#F59E0B` | mid score |
| status red | `#EF4444` | low score |
| star gold | `#F5A623` | rating star, saved ★ |

The score-meter track gradient: `linear-gradient(90deg, #EF4444, #F59E0B 52%, #22C55E)`.
`--red` and `--cyan` are also exposed as tweakable props (`accentRed`, `accentCyan`) and
`--red-soft`/`--red-glow`/`--cyan-soft` are derived from them at runtime.

### Typography
- **Display / prices / headings:** **Space Grotesk** (500/600/700). The current price is
  always the largest, boldest element on its surface.
- **Body / UI:** **Inter** (400/500/600/700).
- Both via Google Fonts. Notable sizes: card price 29px/700, modal price 38px/700, screen
  titles 21px/700, stat values 19px/700, body 14px, labels 10–11px uppercase.

### Spacing / radius / misc
- Screen padding: 16px horizontal. Card padding 14px; modal/sheet padding `10px 18px 26px`.
- Gaps: feed 18px, watchlist 14px, alerts 12px, settings sections 24px.
- **Radii:** cards 16px; phone frame 40px; sheet top 26px; inputs/chips 10–11px; stat
  cards/alert cards 13–14px; small buttons 8–10px; toggles/pills 99px.
- **Shadows:** card `0 1px 2px var(--shadow)`; phone frame `0 40px 90px -20px rgba(0,0,0,.55)`;
  CTA `0 8px 22px -6px var(--red-glow)`.
- Hit targets ≥ 34px; toggles 44×26.

## Screenshots
See `screenshots/` for reference renders of every state:
- `01-deals-feed-dark.png` — Home feed (dark)
- `02-detail-modal-dark.png` — Detail bottom sheet (dark)
- `03-watchlist-empty-dark.png` — Watchlist empty state (dark)
- `04-alerts-dark.png` — Alerts list with toggles (dark)
- `05-add-alert-sheet-dark.png` — Add-alert bottom sheet (dark)
- `06-settings-dark.png` — Settings (dark)
- `07-settings-light.png` — Settings (light mode)
- `08-deals-feed-light.png` — Home feed (light mode)

## Assets
- **No raster assets.** Product images are intentional **striped SVG placeholders** with a
  monospace caption — replace with real Amazon product imagery in production.
- **Icons** are emoji (🔥 ⭐ 🔔 ⚙️ 🛒 ★ ☆ ⌕ ×). Swap for your icon set if you have one;
  keep meanings.
- **Fonts:** Google Fonts — Inter, Space Grotesk.

## Files
- `DealRadar.dc.html` — the full app (all 6 screens, theming, mock data + all logic).
  Read the `<script class="Component">` block for the exact formulas, mock product data,
  and handlers.
- `DealCard.dc.html` — the reusable deal-card component (template-only; renders from a
  precomputed `deal` object + `expanded` boolean).
- `support.js` — the prototype runtime **(reference only — do not ship)**.
- To preview the prototype: open `DealRadar.dc.html` in a browser (it loads `support.js`
  and the fonts).

> Note: the price-history data and ASINs in the mock are illustrative. Wire the real Keepa
> feed and verify affiliate tag/links before shipping.
