import React, { useState, useEffect, useCallback } from 'react'
import DealCard from '../components/DealCard.jsx'
import Sidebar from '../components/Sidebar.jsx'
import ProductModal from '../components/ProductModal.jsx'
import DealTicker from '../components/DealTicker.jsx'
import { useBreakpoint } from '../hooks/useBreakpoint.js'
import { api } from '../api.js'

const QUALITY_FILTERS = [
  { id: 'atl',   label: 'Allzeit-Tief',       dot: '#111111', minScore: 90 },
  { id: 'rare',  label: 'Seltene Gelegenheit', dot: '#E8500A', minScore: 75 },
  { id: 'great', label: 'Sehr guter Deal',     dot: '#1E7A3C', minScore: 55 },
  { id: 'good',  label: 'Guter Deal',          dot: '#888888', minScore: 30 },
]

const SORTS = [
  { id: 'score',     label: 'Bester Deal' },
  { id: 'discount',  label: 'Grösster Rabatt' },
  { id: 'price_asc', label: 'Günstigste' },
]

// ── localStorage Cache Helpers ──────────────────────────────────────────────
const LS_DEALS = 'sng_deals_v1'
const LS_CATS  = 'sng_cats_v1'
const CACHE_TTL = 5 * 60 * 1000 // 5 Minuten

function lsGet(key) {
  try {
    const v = localStorage.getItem(key)
    if (!v) return null
    const { data, ts } = JSON.parse(v)
    if (Date.now() - ts > CACHE_TTL) return null
    return data
  } catch { return null }
}
function lsSet(key, data) {
  try { localStorage.setItem(key, JSON.stringify({ data, ts: Date.now() })) } catch {}
}

export default function DealsPage({ theme, onToggleTheme, watchlist, onToggleWatch, onShowLegal }) {
  const { isMobile, isTablet } = useBreakpoint()
  const [categories, setCategories]         = useState(() => lsGet(LS_CATS) || ['Alle'])
  const [selectedCat, setSelectedCat]       = useState('Alle')
  const [activeFilters, setActiveFilters]   = useState(new Set())
  const [sortBy, setSortBy]                 = useState('score')
  const [search, setSearch]                 = useState('')
  const [deals, setDeals]                   = useState(() => lsGet(LS_DEALS) || [])
  const [loading, setLoading]               = useState(deals.length === 0)
  const [error, setError]                   = useState(null)
  const [view, setView]                     = useState('grid')
  const [selectedDeal, setSelectedDeal]     = useState(null)
  const [sidebarOpen, setSidebarOpen]       = useState(false)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  useEffect(() => {
    api.categories().then(cats => { setCategories(cats); lsSet(LS_CATS, cats) }).catch(() => {})
  }, [])

  const loadDeals = useCallback(() => {
    // Nur Hauptansicht (kein Filter/Suche) cached
    const isDefault = selectedCat === 'Alle' && sortBy === 'score' && !search
    if (!isDefault) setLoading(true)
    setError(null)
    api.deals({ category: selectedCat, sort_by: sortBy, search: search || undefined, limit: 100 })
      .then(data => {
        setDeals(data)
        setLoading(false)
        if (isDefault) lsSet(LS_DEALS, data)
      })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [selectedCat, sortBy, search])

  useEffect(() => {
    const t = setTimeout(loadDeals, search ? 400 : 0)
    return () => clearTimeout(t)
  }, [loadDeals])

  /* ── Deep-Link: ?asin=... beim Seitenaufruf ── */
  useEffect(() => {
    const asin = new URLSearchParams(window.location.search).get('asin')
    if (!asin) return
    api.product(asin)
      .then(deal => {
        setSelectedDeal(deal)
        window.history.replaceState({ snagga: 'modal', asin: deal.asin }, '', `?asin=${asin}`)
      })
      .catch(() => {
        window.history.replaceState({}, '', '/')
      })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  /* ── History-basierte Modal-Navigation (Swipe-Back schliesst Modal) ── */
  const openDeal = useCallback((deal) => {
    setSelectedDeal(deal)
    window.history.pushState({ snagga: 'modal', asin: deal.asin }, '', `?asin=${deal.asin}`)
  }, [])

  const closeModal = useCallback(() => {
    const s = window.history.state?.snagga
    if (s === 'lightbox') {
      // Lightbox + Modal beide aus History entfernen, popstate setzt selectedDeal null
      window.history.go(-2)
    } else if (s === 'modal') {
      window.history.back()
    } else {
      // Kein History-Eintrag (z.B. direkter Deep-Link) — URL manuell bereinigen
      window.history.replaceState({}, '', '/')
      setSelectedDeal(null)
    }
  }, [])

  useEffect(() => {
    // Nur schliessen wenn wir zur Basis zurückkehren (nicht wenn Lightbox→Modal)
    const onPop = (e) => {
      const s = e.state?.snagga
      if (s !== 'modal' && s !== 'lightbox') setSelectedDeal(null)
    }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  function toggleFilter(id) {
    setActiveFilters(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const filteredDeals = deals.filter(d => {
    if (activeFilters.size === 0) return true
    return [...activeFilters].some(id => {
      const idx = QUALITY_FILTERS.findIndex(f => f.id === id)
      if (idx < 0) return false
      const qf    = QUALITY_FILTERS[idx]
      const upper = idx > 0 ? QUALITY_FILTERS[idx - 1].minScore : 101
      return d.deal_score >= qf.minScore && d.deal_score < upper
    })
  })

  const showBottomNav = isMobile || isTablet
  const isDesktop = !isMobile && !isTablet
  const gridCols = isMobile ? 'repeat(2, 1fr)' : isTablet ? 'repeat(3, 1fr)' : 'repeat(5, 1fr)'
  const pad      = showBottomNav ? (isMobile ? '12px 12px 96px' : '16px 22px 96px') : '16px 22px 40px'

  /* ── Filter chip ── */
  function FilterChip({ label, active, dot, onClick }) {
    return (
      <button onClick={onClick}
        style={{ padding: isMobile ? '5px 10px' : '6px 13px', borderRadius: 8, border: `1.5px solid ${active ? 'var(--text)' : 'var(--border)'}`, background: active ? 'var(--text)' : 'var(--bg-elev)', color: active ? 'var(--bg-elev)' : 'var(--text)', fontSize: isMobile ? 11.5 : 12.5, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 5, whiteSpace: 'nowrap', flexShrink: 0, transition: 'all 0.12s' }}
      >
        {dot && <div style={{ width: 6, height: 6, borderRadius: '50%', background: active ? 'var(--bg-elev)' : dot, flexShrink: 0 }} />}
        {label}
      </button>
    )
  }

  /* ── Row label (fixed width so chips align) ── */
  const RowLabel = ({ children }) => (
    <span style={{ fontSize: 10.5, fontWeight: 700, color: 'var(--muted)', flexShrink: 0,
      letterSpacing: 0.5, width: 48, minWidth: 48 }}>
      {children}
    </span>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {selectedDeal && (
        <ProductModal
          deal={selectedDeal}
          onClose={closeModal}
          saved={watchlist?.has(selectedDeal.asin)}
          onSave={onToggleWatch}
        />
      )}

      {/* Mobile Sidebar-Overlay */}
      {isMobile && sidebarOpen && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 200, display: 'flex' }}>
          <div onClick={() => setSidebarOpen(false)} style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.4)' }} />
          <div style={{ position: 'relative', zIndex: 1, width: 260, background: 'var(--bg-card)', borderRight: '1px solid var(--border)', overflowY: 'auto' }}>
            <div style={{ padding: '16px 20px 8px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontWeight: 700, fontSize: 15 }}>Kategorien</span>
              <button onClick={() => setSidebarOpen(false)} style={{ background: 'none', border: 'none', fontSize: 20, color: 'var(--muted)', lineHeight: 1 }}>×</button>
            </div>
            <Sidebar categories={categories} selectedCat={selectedCat}
              onSelectCat={cat => { setSelectedCat(cat); setSidebarOpen(false) }} deals={deals} />
          </div>
        </div>
      )}

      {/* TOPBAR */}
      <div style={{
        background: 'var(--bg-elev)', borderBottom: '1px solid var(--border)',
        height: 54, display: 'flex', alignItems: 'center',
        padding: isMobile ? '0 14px' : '0 24px 0 0',
        gap: isMobile ? 10 : 0,
        position: 'sticky', top: 0, zIndex: 100, flexShrink: 0,
      }}>
        {isMobile && (
          <button onClick={() => setSidebarOpen(true)} style={{ background: 'none', border: 'none', padding: 4, color: 'var(--text)', display: 'flex', alignItems: 'center', marginRight: 6 }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="3" y1="6"  x2="21" y2="6"/>
              <line x1="3" y1="12" x2="21" y2="12"/>
              <line x1="3" y1="18" x2="21" y2="18"/>
            </svg>
          </button>
        )}

        {/* Logo — nimmt exakt Sidebar-Breite ein (inkl. linkem Padding) */}
        <div style={{ flexShrink: 0, width: isMobile ? 'auto' : 208, paddingLeft: isMobile ? 0 : 24, display: 'flex', alignItems: 'center' }}>
          <span style={{ fontSize: isMobile ? 19 : 22, fontWeight: 800, letterSpacing: '-0.5px', color: 'var(--text)', whiteSpace: 'nowrap' }}>snagga</span>
        </div>

        {/* Suchfeld — linke Kante bündig mit Inhaltbereich */}
        <div style={{ flex: 1, position: 'relative', maxWidth: isMobile ? '100%' : 520, marginLeft: 0 }}>
          <span style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', fontSize: 14, pointerEvents: 'none' }}>🔍</span>
          <input
            value={search} onChange={e => setSearch(e.target.value)}
            placeholder={isMobile ? 'Suchen…' : 'Produkt, Marke oder Kategorie suchen…'}
            style={{ width: '100%', padding: '8px 12px 8px 34px', borderRadius: 9, border: '1.5px solid var(--border)', background: 'var(--bg-elev2)', color: 'var(--text)', fontSize: 14, outline: 'none' }}
            onFocus={e => { e.target.style.borderColor = '#E8500A'; e.target.style.background = 'var(--bg-elev)' }}
            onBlur={e  => { e.target.style.borderColor = 'var(--border)'; e.target.style.background = 'var(--bg-elev2)' }}
          />
        </div>

        {/* Dark Mode */}
        <button onClick={onToggleTheme}
          style={{ marginLeft: 'auto', width: 34, height: 34, borderRadius: 8, border: '1.5px solid var(--border)', background: 'var(--bg-elev2)', color: 'var(--text)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}
          title={theme === 'dark' ? 'Light Mode' : 'Dark Mode'}
        >
          {theme === 'dark' ? (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <circle cx="8" cy="8" r="3"/>
              <line x1="8" y1="1" x2="8" y2="2.5"/><line x1="8" y1="13.5" x2="8" y2="15"/>
              <line x1="1" y1="8" x2="2.5" y2="8"/><line x1="13.5" y1="8" x2="15" y2="8"/>
              <line x1="2.9" y1="2.9" x2="4" y2="4"/><line x1="12" y1="12" x2="13.1" y2="13.1"/>
              <line x1="13.1" y1="2.9" x2="12" y2="4"/><line x1="4" y1="12" x2="2.9" y2="13.1"/>
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M13 10A6 6 0 0 1 6 3a6 6 0 1 0 7 7z"/>
            </svg>
          )}
        </button>
      </div>

      {/* DEAL TICKER — nur Desktop */}
      {isDesktop && <DealTicker deals={deals} />}

      {/* LAYOUT */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>

        {/* Sidebar — Desktop/Tablet */}
        {!isMobile && (
          <>
            {!sidebarCollapsed ? (
              <Sidebar
                categories={categories}
                selectedCat={selectedCat}
                onSelectCat={setSelectedCat}
                deals={deals}
                onCollapse={() => setSidebarCollapsed(true)}
                onShowLegal={onShowLegal}
              />
            ) : (
              /* Schmaler Expand-Streifen */
              <div style={{
                width: 36, flexShrink: 0,
                background: 'var(--bg-elev)', borderRight: '1px solid var(--border)',
                position: 'sticky', top: 54, height: 'calc(100vh - 54px)',
                display: 'flex', flexDirection: 'column', alignItems: 'center', paddingTop: 14,
              }}>
                <button
                  onClick={() => setSidebarCollapsed(false)}
                  title="Kategorien einblenden"
                  style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', padding: 6, borderRadius: 6 }}
                  onMouseEnter={e => e.currentTarget.style.color = 'var(--text)'}
                  onMouseLeave={e => e.currentTarget.style.color = 'var(--muted)'}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="9,18 15,12 9,6"/>
                  </svg>
                </button>
              </div>
            )}
          </>
        )}

        {/* Main */}
        <div className="no-scroll" style={{ flex: 1, overflowY: 'auto', minWidth: 0 }}>

          {/* Sticky Filter-Bar */}
          <div style={{ position: 'sticky', top: 0, zIndex: 50, background: 'var(--bg)', borderBottom: '1px solid var(--border)', padding: (isMobile || isTablet) ? '9px 12px 7px' : '14px 22px 12px' }}>

            {(isMobile || isTablet) ? (
              <>
                {/* Zeile 1: Filter */}
                <div className="no-scroll" style={{ display: 'flex', alignItems: 'center', gap: 6, overflowX: 'auto', flexWrap: 'nowrap', paddingBottom: 1, marginBottom: 6 }}>
                  <RowLabel>FILTER</RowLabel>
                  {QUALITY_FILTERS.map(f => (
                    <FilterChip key={f.id} label={f.label} dot={f.dot} active={activeFilters.has(f.id)} onClick={() => toggleFilter(f.id)} />
                  ))}
                </div>
                {/* Zeile 2: Sort */}
                <div className="no-scroll" style={{ display: 'flex', alignItems: 'center', gap: 6, overflowX: 'auto', flexWrap: 'nowrap', paddingBottom: 1, marginBottom: 6 }}>
                  <RowLabel>SORT</RowLabel>
                  {SORTS.map(s => (
                    <FilterChip key={s.id} label={s.label} active={s.id === sortBy} onClick={() => setSortBy(s.id)} />
                  ))}
                </div>
              </>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--muted)', marginRight: 2, flexShrink: 0 }}>Filter</span>
                {QUALITY_FILTERS.map(f => (
                  <FilterChip key={f.id} label={f.label} dot={f.dot} active={activeFilters.has(f.id)} onClick={() => toggleFilter(f.id)} />
                ))}
                <div style={{ width: 1, height: 22, background: 'var(--border)', margin: '0 2px', flexShrink: 0 }} />
                <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--muted)', marginRight: 2, flexShrink: 0 }}>Sortieren</span>
                {SORTS.map(s => (
                  <FilterChip key={s.id} label={s.label} active={s.id === sortBy} onClick={() => setSortBy(s.id)} />
                ))}
              </div>
            )}

            {/* Anzahl + View Toggle */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                {selectedCat !== 'Alle' && (
                  <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)', marginRight: 7 }}>{selectedCat}</span>
                )}
                <span style={{ fontSize: 12, color: 'var(--muted)' }}>{filteredDeals.length} Produkte</span>
              </div>
              {!isMobile && (
                <div style={{ display: 'flex', gap: 4 }}>
                  {[{ id: 'grid', icon: '⊞' }, { id: 'list', icon: '☰' }].map(v => (
                    <button key={v.id} onClick={() => setView(v.id)}
                      style={{ padding: '5px 11px', borderRadius: 7, border: `1.5px solid ${view === v.id ? 'var(--text)' : 'var(--border)'}`, background: view === v.id ? 'var(--text)' : 'var(--bg-elev)', color: view === v.id ? 'var(--bg-elev)' : 'var(--text)', fontSize: 13, fontWeight: 500, cursor: 'pointer' }}>
                      {v.icon}
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Deals */}
          <div style={{ padding: pad }}>
            {loading && <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--muted)', fontSize: 14 }}>Deals laden…</div>}
            {error   && <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--orange)', fontSize: 14 }}>Backend nicht erreichbar.</div>}
            {!loading && !error && filteredDeals.length === 0 && <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--muted)', fontSize: 14 }}>Keine Deals gefunden.</div>}

            {!loading && !error && filteredDeals.length > 0 && (
              <div style={view === 'grid' || isMobile ? {
                display: 'grid', gridTemplateColumns: gridCols, gap: isMobile ? 10 : 12,
              } : { display: 'flex', flexDirection: 'column', gap: 8 }}>
                {filteredDeals.map(deal => (
                  <DealCard key={deal.asin} deal={deal}
                    view={isMobile ? 'grid' : view}
                    saved={watchlist?.has(deal.asin)}
                    onSave={onToggleWatch}
                    onClick={() => openDeal(deal)}
                  />
                ))}
              </div>
            )}

            {!loading && filteredDeals.length > 0 && (
              <div style={{ fontSize: 11, color: 'var(--muted)', textAlign: 'center', paddingTop: 24, lineHeight: 1.6 }}>
                Als Amazon-Partner verdiene ich an qualifizierten Käufen eine Provision — für dich entstehen keine Mehrkosten.{' '}
                <span style={{ cursor: 'pointer', color: 'var(--blue)', textDecoration: 'underline' }} onClick={onShowLegal}>Mehr erfahren</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Bottom Nav — Mobile + Tablet */}
      {showBottomNav && (
        <div style={{
          position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 150,
          height: 80,
          background: 'var(--bg-card)', borderTop: '1px solid var(--border)',
          display: 'flex', alignItems: 'stretch',
          paddingBottom: 'env(safe-area-inset-bottom)',
        }}>
          <MobileNavBtn icon="🏷️" label="Deals" active />
          <MobileNavBtn icon="☆" label="Watchlist" />
          <MobileNavBtn icon="⚙️" label="Einstellungen" onClick={onShowLegal} />
        </div>
      )}
    </div>
  )
}

function MobileNavBtn({ icon, label, active = false, onClick }) {
  return (
    <button onClick={onClick} style={{
      flex: 1,
      background: 'none', border: 'none',
      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
      gap: 4,
      color: active ? 'var(--orange)' : 'var(--muted)',
      fontSize: 11, fontWeight: active ? 700 : 400,
    }}>
      <span style={{ fontSize: 22, lineHeight: 1 }}>{icon}</span>
      {label}
    </button>
  )
}
