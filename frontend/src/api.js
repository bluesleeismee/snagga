const BASE = '/api'

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
  categories: ()     => get('/categories'),
  refresh:    ()     => fetch(BASE + '/refresh', { method: 'POST' }).then(r => r.json()),
}
