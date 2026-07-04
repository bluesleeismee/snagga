const BASE = import.meta.env.VITE_API_URL || '/api'

async function get(path) {
  const res = await fetch(BASE + path)
  if (!res.ok) throw new Error(`API ${path}: ${res.status}`)
  return res.json()
}

export const api = {
  deals: (params = {}) => {
    const q = new URLSearchParams()
    if (params.category && params.category !== 'Alle') q.set('category', params.category)
    if (params.sort_by)  q.set('sort_by', params.sort_by)
    if (params.search)   q.set('search', params.search)
    if (params.limit)    q.set('limit', params.limit)
    return get(`/deals?${q}`)
  },
  product:    (asin) => get(`/product/${asin}`),
  // Detaildaten fürs Modal: Urteil, Preis-Eckdaten, Chart-SVG, Wunschpreis —
  // dieselbe Quelle wie die SSR-Preisseite /preis/{asin}.
  productDetail: (asin) => get(`/produkt/${asin}`),
  // Preisalarm aus dem Modal setzen (AJAX). Antwort: { ok, message }.
  setAlarm: (asin, email, targetPrice) => {
    const body = new URLSearchParams({ asin, email, target_price: targetPrice, ajax: '1' })
    return fetch(BASE + '/alarm/setzen', { method: 'POST', body })
      .then(async r => {
        const data = await r.json().catch(() => ({ ok: false, message: 'Unerwartete Antwort vom Server.' }))
        return { ok: r.ok && data.ok, message: data.message || 'Etwas ist schiefgelaufen.' }
      })
      .catch(() => ({ ok: false, message: 'Verbindung fehlgeschlagen. Bitte versuch es erneut.' }))
  },
  categories: ()     => get('/categories'),
  refresh:    ()     => fetch(BASE + '/refresh', { method: 'POST' }).then(r => r.json()),
}
