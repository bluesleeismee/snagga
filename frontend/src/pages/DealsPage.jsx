import React, { useState, useEffect, useCallback } from 'react'
import DealCard from '../components/DealCard.jsx'
import { api } from '../api.js'

const SORTS = [
  { id: 'score',      label: 'Bester Deal' },
  { id: 'discount',   label: 'Rabatt' },
  { id: 'price_asc',  label: 'Günstigste' },
  { id: 'newest',     label: 'Neu' },
]

export default function DealsPage({ theme, onToggleTheme, watchlist, onToggleWatch }) {
  const [categories, setCategories] = useState(['Alle'])
  const [selectedCat, setSelectedCat] = useState('Alle')
  const [sortBy, setSortBy] = useState('score')
  const [search, setSearch] = useState('')
  const [deals, setDeals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Kategorien laden
  useEffect(() => {
    api.categories().then(setCategories).catch(() => {})
  }, [])

  // Deals laden
  const loadDeals = useCallback(() => {
    setLoading(true)
    setError(null)
    api.deals({ category: selectedCat, sort_by: sortBy, search: search || undefined })
      .then(data => { setDeals(data); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [selectedCat, sortBy, search])

  useEffect(() => {
    const t = setTimeout(loadDeals, search ? 400 : 0)
    return () => clearTimeout(t)
  }, [loadDeals])

  // Allzeit-Tief Zähler
  const allTimeLows = deals.filter(d => d.deal_score >= 85).length

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 6,
        background: 'var(--bg)', padding: '18px 16px 12px',
        borderBottom: '1px solid var(--border)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
            <div style={{ width: 11, height: 11, borderRadius: '50%', background: 'var(--red)', boxShadow: '0 0 0 4px var(--red-soft)' }} />
            <span style={{ fontFamily: 'Space Grotesk', fontWeight: 700, fontSize: 20, letterSpacing: '-.4px' }}>
              DEAL<span style={{ color: 'var(--red)' }}>RADAR</span>
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {allTimeLows > 0 && (
              <div style={{
                fontSize: 11, fontWeight: 600, color: 'var(--red)',
                background: 'var(--red-soft)', padding: '6px 9px',
                borderRadius: 8, display: 'flex', gap: 5, alignItems: 'center', whiteSpace: 'nowrap',
              }}>
                🔥 {allTimeLows} Allzeit-Tief{allTimeLows > 1 ? 's' : ''}
              </div>
            )}
            <button
              onClick={onToggleTheme}
              style={{
                width: 36, height: 36, borderRadius: 9,
                border: '1px solid var(--border)', background: 'var(--bg-elev2)',
                color: 'var(--text)', fontSize: 15,
                display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0,
              }}
            >
              {theme === 'dark' ? '☀️' : '🌙'}
            </button>
          </div>
        </div>

        {/* Suche */}
        <div style={{ marginTop: 13, position: 'relative' }}>
          <span style={{ position: 'absolute', left: 13, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted)', fontSize: 16, pointerEvents: 'none' }}>⌕</span>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Produkt oder Marke suchen…"
            style={{
              width: '100%', padding: '11px 12px 11px 36px',
              borderRadius: 11, border: '1px solid var(--border)',
              background: 'var(--bg-elev2)', color: 'var(--text)',
              fontSize: 14, outline: 'none',
            }}
          />
        </div>
      </div>

      {/* Kategorie-Chips */}
      <div className="no-scroll" style={{ display: 'flex', gap: 8, overflowX: 'auto', padding: '13px 16px 4px', flexShrink: 0 }}>
        {categories.map(cat => {
          const active = cat === selectedCat
          return (
            <button
              key={cat}
              onClick={() => setSelectedCat(cat)}
              style={{
                flexShrink: 0, padding: '8px 15px', borderRadius: 10,
                fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap',
                border: `1px solid ${active ? 'var(--red)' : 'var(--border)'}`,
                background: active ? 'var(--red-soft)' : 'var(--bg-elev2)',
                color: active ? 'var(--red)' : 'var(--muted)',
                transition: 'all .15s',
              }}
            >
              {cat}
            </button>
          )
        })}
      </div>

      {/* Sort-Buttons */}
      <div style={{ display: 'flex', gap: 8, padding: '10px 16px 4px', alignItems: 'center', flexShrink: 0 }}>
        <span style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.6px', fontWeight: 600 }}>Sortieren</span>
        {SORTS.map(s => {
          const active = s.id === sortBy
          return (
            <button
              key={s.id}
              onClick={() => setSortBy(s.id)}
              style={{
                padding: '6px 11px', borderRadius: 8, fontSize: 12, fontWeight: 600,
                border: `1px solid ${active ? 'var(--red)' : 'var(--border)'}`,
                background: active ? 'var(--red-soft)' : 'var(--bg-elev2)',
                color: active ? 'var(--red)' : 'var(--muted)',
                transition: 'all .15s',
              }}
            >
              {s.label}
            </button>
          )
        })}
      </div>

      {/* Feed */}
      <div className="no-scroll" style={{ flex: 1, overflowY: 'auto', padding: '16px 16px 28px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        {loading && (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--muted)', fontSize: 14 }}>
            Deals laden…
          </div>
        )}
        {error && (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--red)', fontSize: 14 }}>
            Verbindung zum Backend fehlgeschlagen.<br />
            <span style={{ color: 'var(--muted)', fontSize: 12 }}>Läuft das Backend? → python -m uvicorn main:app</span>
          </div>
        )}
        {!loading && !error && deals.length === 0 && (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: 'var(--muted)', fontSize: 14 }}>
            Keine Deals gefunden. Andere Kategorie oder Suche probieren.
          </div>
        )}
        {!loading && deals.map(deal => (
          <DealCard
            key={deal.asin}
            deal={deal}
            expanded
            saved={watchlist.has(deal.asin)}
            onSave={onToggleWatch}
          />
        ))}
      </div>
    </div>
  )
}
