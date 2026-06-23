import React, { useState, useEffect, useCallback } from 'react'
import DealCard from '../components/DealCard.jsx'
import Sidebar from '../components/Sidebar.jsx'
import { api } from '../api.js'

const QUALITY_FILTERS = [
  { id: 'all',  label: 'Alle' },
  { id: 'atl',  label: 'Allzeit-Tief',        dot: '#111111', minScore: 90 },
  { id: 'rare', label: 'Seltene Gelegenheit',  dot: '#E8500A', minScore: 75 },
  { id: 'great',label: 'Sehr guter Deal',      dot: '#1E7A3C', minScore: 55 },
  { id: 'good', label: 'Guter Deal',           dot: '#888888', minScore: 30 },
]

const SORTS = [
  { id: 'score',    label: 'Bester Deal' },
  { id: 'discount', label: 'Grösster Rabatt' },
  { id: 'price_asc',label: 'Günstigste' },
]

export default function DealsPage({ theme, onToggleTheme, watchlist, onToggleWatch, onShowLegal }) {
  const [categories, setCategories] = useState(['Alle'])
  const [selectedCat, setSelectedCat] = useState('Alle')
  const [qualityFilter, setQualityFilter] = useState('all')
  const [sortBy, setSortBy] = useState('score')
  const [search, setSearch] = useState('')
  const [deals, setDeals] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [view, setView] = useState('grid')

  useEffect(() => {
    api.categories().then(setCategories).catch(() => {})
  }, [])

  const loadDeals = useCallback(() => {
    setLoading(true)
    setError(null)
    api.deals({ category: selectedCat, sort_by: sortBy, search: search || undefined, limit: 100 })
      .then(data => { setDeals(data); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [selectedCat, sortBy, search])

  useEffect(() => {
    const t = setTimeout(loadDeals, search ? 400 : 0)
    return () => clearTimeout(t)
  }, [loadDeals])

  // Qualitäts-Filter auf Client-Seite anwenden
  const filteredDeals = deals.filter(d => {
    const qf = QUALITY_FILTERS.find(f => f.id === qualityFilter)
    if (!qf || qf.id === 'all') return true
    // Find next filter to get upper bound
    const idx = QUALITY_FILTERS.indexOf(qf)
    const upper = idx > 0 ? QUALITY_FILTERS[idx - 1]?.minScore : 101
    return d.deal_score >= qf.minScore && d.deal_score < (upper ?? 101)
  })

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>

      {/* TOPBAR */}
      <div style={{
        background: 'var(--bg-elev)',
        borderBottom: '1px solid var(--border)',
        height: 58,
        display: 'flex',
        alignItems: 'center',
        padding: '0 24px',
        gap: 16,
        position: 'sticky',
        top: 0,
        zIndex: 100,
        flexShrink: 0,
      }}>
        {/* Logo — fixe Breite = Sidebar-Breite minus Topbar-Padding → Suchfeld bündig mit Grid */}
        <div style={{ flexShrink: 0, width: 208, marginRight: 0 }}>
          <span style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.5px', color: 'var(--text)', whiteSpace: 'nowrap' }}>
            snagga
          </span>
        </div>

        {/* Suchfeld */}
        <div style={{ flex: 1, maxWidth: 520, position: 'relative' }}>
          <span style={{
            position: 'absolute', left: 13, top: '50%', transform: 'translateY(-50%)',
            fontSize: 15, pointerEvents: 'none',
          }}>🔍</span>
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Produkt, Marke oder Kategorie suchen…"
            style={{
              width: '100%',
              padding: '9px 16px 9px 38px',
              borderRadius: 9,
              border: '1.5px solid var(--border)',
              background: 'var(--bg-elev2)',
              color: 'var(--text)',
              fontSize: 14,
              outline: 'none',
              transition: 'border-color 0.15s, background 0.15s',
            }}
            onFocus={e => { e.target.style.borderColor = '#E8500A'; e.target.style.background = 'var(--bg-elev)' }}
            onBlur={e => { e.target.style.borderColor = 'var(--border)'; e.target.style.background = 'var(--bg-elev2)' }}
          />
        </div>

        {/* Dark Mode Toggle */}
        <button
          onClick={onToggleTheme}
          style={{
            marginLeft: 'auto',
            width: 34, height: 34, borderRadius: 8,
            border: '1.5px solid var(--border)',
            background: 'var(--bg-elev2)',
            color: 'var(--text)', fontSize: 15,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          title={theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
        >
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>
      </div>

      {/* LAYOUT: Sidebar + Main */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Sidebar */}
        <Sidebar
          categories={categories}
          selectedCat={selectedCat}
          onSelectCat={setSelectedCat}
          deals={deals}
        />

        {/* Main Content */}
        <div className="no-scroll" style={{ flex: 1, overflowY: 'auto', minWidth: 0 }}>
          <div style={{ padding: '18px 22px 40px' }}>

            {/* Filter-Bar */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--muted)', marginRight: 2 }}>Filter</span>
              {QUALITY_FILTERS.map(f => {
                const active = f.id === qualityFilter
                return (
                  <button
                    key={f.id}
                    onClick={() => setQualityFilter(f.id)}
                    style={{
                      padding: '6px 13px',
                      borderRadius: 8,
                      border: `1.5px solid ${active ? 'var(--text)' : 'var(--border)'}`,
                      background: active ? 'var(--text)' : 'var(--bg-elev)',
                      color: active ? 'var(--bg-elev)' : 'var(--text)',
                      fontSize: 13, fontWeight: 500,
                      display: 'flex', alignItems: 'center', gap: 6,
                      whiteSpace: 'nowrap',
                      transition: 'all 0.12s',
                    }}
                  >
                    {f.dot && (
                      <div style={{ width: 7, height: 7, borderRadius: '50%', background: active ? 'var(--bg-elev)' : f.dot, flexShrink: 0 }} />
                    )}
                    {f.label}
                  </button>
                )
              })}

              <div style={{ width: 1, height: 22, background: 'var(--border)', margin: '0 4px' }} />

              <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--muted)', marginRight: 2 }}>Sortieren</span>
              {SORTS.map(s => {
                const active = s.id === sortBy
                return (
                  <button
                    key={s.id}
                    onClick={() => setSortBy(s.id)}
                    style={{
                      padding: '6px 13px',
                      borderRadius: 8,
                      border: `1.5px solid ${active ? 'var(--text)' : 'var(--border)'}`,
                      background: active ? 'var(--text)' : 'var(--bg-elev)',
                      color: active ? 'var(--bg-elev)' : 'var(--text)',
                      fontSize: 13, fontWeight: 500,
                      whiteSpace: 'nowrap',
                      transition: 'all 0.12s',
                    }}
                  >
                    {s.label}
                  </button>
                )
              })}
            </div>

            {/* Title row */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
              <div>
                <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)' }}>
                  {selectedCat === 'Alle' ? 'Alle Deals' : selectedCat}
                </span>
                <span style={{ fontSize: 13, color: 'var(--muted)', marginLeft: 8 }}>
                  {filteredDeals.length} Produkte
                </span>
              </div>
              {/* View Toggle */}
              <div style={{ display: 'flex', gap: 4 }}>
                {[{ id: 'grid', icon: '⊞' }, { id: 'list', icon: '☰' }].map(v => (
                  <button key={v.id} onClick={() => setView(v.id)} style={{ padding: '5px 11px', borderRadius: 7, border: `1.5px solid ${view === v.id ? 'var(--text)' : 'var(--border)'}`, background: view === v.id ? 'var(--text)' : 'var(--bg-elev)', color: view === v.id ? 'var(--bg-elev)' : 'var(--text)', fontSize: 13, fontWeight: 500, cursor: 'pointer' }}>
                    {v.icon}
                  </button>
                ))}
              </div>
            </div>

            {/* States */}
            {loading && (
              <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--muted)', fontSize: 14 }}>
                Deals laden…
              </div>
            )}
            {error && (
              <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--orange)', fontSize: 14 }}>
                Backend nicht erreichbar.<br />
                <span style={{ color: 'var(--muted)', fontSize: 12 }}>Läuft das Backend?</span>
              </div>
            )}
            {!loading && !error && filteredDeals.length === 0 && (
              <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--muted)', fontSize: 14 }}>
                Keine Deals gefunden.
              </div>
            )}

            {/* Grid / Liste */}
            {!loading && !error && filteredDeals.length > 0 && (
              <div style={view === 'grid' ? {
                display: 'grid',
                gridTemplateColumns: 'repeat(4, 1fr)',
                gap: 12,
              } : {
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}>
                {filteredDeals.map(deal => (
                  <DealCard
                    key={deal.asin}
                    deal={deal}
                    view={view}
                    saved={watchlist?.has(deal.asin)}
                    onSave={onToggleWatch}
                  />
                ))}
              </div>
            )}

            {/* Affiliate-Hinweis */}
            {!loading && filteredDeals.length > 0 && (
              <div style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'center', paddingTop: 24, lineHeight: 1.5 }}>
                * Als Amazon-Partner verdiene ich an qualifizierten Käufen.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
