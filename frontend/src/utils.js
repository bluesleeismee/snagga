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

/** Score → Chart-Status { text, color } */
export function chartStatus(prices, avgPrice, allTimeLow) {
  if (!prices || prices.length === 0) return null
  const current = prices[prices.length - 1]
  if (allTimeLow && current <= allTimeLow * 1.02) return { text: '▼ Günstigster je',  color: '#1E7A3C' }
  if (avgPrice && current < avgPrice * 0.85)        return { text: '▼ Selten so tief',  color: '#E8500A' }
  if (avgPrice && current < avgPrice * 0.95)        return { text: '▼ Deutlich unter Ø', color: '#1E7A3C' }
  return                                                   { text: '▼ Leicht unter Ø',  color: '#888888' }
}

/** Zeitdifferenz seit last_updated → { text, level }
 *  level: 'fresh' (<6h) | 'ok' (6–24h) | 'stale' (>24h)
 */
export function fmtAge(lastUpdated) {
  if (!lastUpdated) return null
  const date = new Date(lastUpdated)
  if (isNaN(date.getTime())) return null
  const mins = Math.floor((Date.now() - date.getTime()) / 60000)
  if (mins < 1)   return { text: 'gerade eben', level: 'fresh' }
  if (mins < 60)  return { text: `vor ${mins}m`,            level: 'fresh' }
  const hrs = Math.floor(mins / 60)
  if (hrs < 6)    return { text: `vor ${hrs}h`,             level: 'fresh' }
  if (hrs < 24)   return { text: `vor ${hrs}h`,             level: 'ok'    }
  const days = Math.floor(hrs / 24)
  return           { text: `vor ${days} Tag${days > 1 ? 'en' : ''}`, level: 'stale' }
}

export const AGE_COLORS = {
  fresh: '#1E7A3C',
  ok:    '#E8500A',
  stale: '#888888',
}

/** Anzahl Bewertungen → "1.234" oder "12,3T" */
export function fmtReviews(n) {
  if (!n || n <= 0) return null
  if (n >= 1000) return (n / 1000).toFixed(1).replace('.', ',') + 'T'
  return n.toString()
}

