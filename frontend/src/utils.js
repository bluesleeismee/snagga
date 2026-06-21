/** Preis → "€ 249,90" */
export function fmtPrice(p) {
  if (p == null) return '—'
  return '€ ' + p.toFixed(2).replace('.', ',')
}

/** Rabatt in % */
export function discount(current, original) {
  if (!original || original <= current) return 0
  return Math.round((1 - current / original) * 100)
}

/** Score → Farbe */
export function scoreColor(score) {
  if (score >= 85) return 'var(--red)'
  if (score >= 60) return 'var(--yellow)'
  return 'var(--green)'
}

/** Score → Badge-Text */
export function scoreBadge(score) {
  if (score >= 85) return '🔥 Allzeit-Tief'
  if (score >= 60) return '⚡ Sehr gut'
  return '✓ Gut'
}

/** SVG-Pfad aus Preisarray generieren (viewBox 0 0 300 54) */
export function miniChart(prices, W = 300, H = 54) {
  if (!prices || prices.length < 2) return { line: '', area: '' }
  const min = Math.min(...prices)
  const max = Math.max(...prices)
  const range = max - min || 1
  const pad = 4
  const pts = prices.map((p, i) => ({
    x: (i / (prices.length - 1)) * W,
    y: H - pad - ((p - min) / range) * (H - pad * 2),
  }))
  const line = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const area = `${line} L${W},${H} L0,${H} Z`
  return { line, area }
}

/** Sterne rendern */
export function stars(rating) {
  return '★'.repeat(Math.round(rating)) + '☆'.repeat(5 - Math.round(rating))
}

/** Anzahl Reviews formatieren */
export function fmtReviews(n) {
  if (n >= 1000) return (n / 1000).toFixed(1).replace('.', ',') + 'k'
  return String(n)
}
