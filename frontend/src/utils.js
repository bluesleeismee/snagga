/** Preis → "248 €" */
export function fmtPrice(p) {
  if (p == null) return '—'
  return p.toFixed(2).replace('.', ',') + ' €'
}

/** Preis kurz → "248€" (für Chart-Labels) */
export function fmtPriceShort(p) {
  if (p == null) return '—'
  if (p >= 1000) return (p / 1000).toFixed(1).replace('.', ',') + 'k€'
  return Math.round(p) + '€'
}

/** Rabatt in % */
export function discount(current, original) {
  if (!original || original <= current) return 0
  return Math.round((1 - current / original) * 100)
}

/** Score → Deal-Label { text, bg, color, border? } */
export function dealLabel(score) {
  if (score >= 90) return { text: 'Allzeit-Tief',        bg: '#111111', color: '#fff' }
  if (score >= 75) return { text: 'Seltene Gelegenheit', bg: '#E8500A', color: '#fff' }
  if (score >= 55) return { text: 'Sehr guter Deal',     bg: '#1E7A3C', color: '#fff' }
  if (score >= 30) return { text: 'Guter Deal',          bg: '#F0F0EB', color: '#555555', border: '1px solid #DDDDD8' }
  return null
}

/** Score → Chart-Status { text, color } */
export function chartStatus(prices, avgPrice, allTimeLow) {
  if (!prices || prices.length === 0) return null
  const current = prices[prices.length - 1]
  if (allTimeLow && current <= allTimeLow * 1.02) return { text: '▼ Günstigster je',  color: '#1E7A3C' }
  if (avgPrice && current < avgPrice * 0.85)        return { text: '▼ Selten so tief',  color: '#E8500A' }
  if (avgPrice && current < avgPrice * 0.95)        return { text: '▼ Deutlich unter Ø', color: '#1E7A3C' }
  return                                                   { text: '▼ Leicht unter Ø',  color: '#888888' }
}

/** Anzahl Reviews formatieren */
export function fmtReviews(n) {
  if (n >= 1000) return (n / 1000).toFixed(1).replace('.', ',') + 'k'
  return String(n)
}

/** Score → Farbe (legacy, für nicht-redesignte Pages) */
export function scoreColor(score) {
  if (score >= 85) return 'var(--orange)'
  if (score >= 60) return 'var(--yellow)'
  return 'var(--green)'
}

/** Anzahl Reviews formatieren (legacy alias) */
export function scoreBadge(score) {
  if (score >= 85) return '🔥 Allzeit-Tief'
  if (score >= 60) return '⚡ Sehr gut'
  return '✓ Gut'
}

/** stars (legacy) */
export function stars(rating) {
  return '★'.repeat(Math.round(rating)) + '☆'.repeat(5 - Math.round(rating))
}
