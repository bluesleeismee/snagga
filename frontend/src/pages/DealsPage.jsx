import React, { useState, useEffect, useCallback, useRef } from 'react'
import DealCard from '../components/DealCard.jsx'
import ProductModal from '../components/ProductModal.jsx'
import { useBreakpoint } from '../hooks/useBreakpoint.js'
import { api } from '../api.js'
import { fmtPrice, discount } from '../utils.js'

const SORTS = [
  { id: 'score',     label: 'Bester Deal' },
  { id: 'discount',  label: 'Grösster Rabatt' },
  { id: 'price_asc', label: 'Günstigste' },
  { id: 'newest',    label: 'Neu' },
]

const COUNTRIES = [
  { code: 'DE', src: '/flags/de.svg',  label: 'Deutschland' },
  { code: 'AT', src: '/flags/at.webp', label: 'Österreich' },
  { code: 'CH', src: '/flags/ch.avif', label: 'Schweiz' },
]

const LS_DEALS = 'sng_deals_v2'
const LS_CATS  = 'sng_cats_v2'
const LS_PICKS = 'sng_picks_v2'
const CACHE_TTL = 5 * 60 * 1000

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

/* ── Best Picks Slider ──────────────────────────────────────────── */
function BestPicksSlider({ deals, onOpen }) {
  const { isDesktop, width } = useBreakpoint()
  const topDeals = deals.filter(d => d.deal_score >= 75).slice(0, 8)
  if (topDeals.length === 0) return null

  const CARD_W = width < 500 ? width - 48 : 440
  const GAP    = 24
  const STEP   = CARD_W + GAP

  const trackRef  = useRef(null)
  const rafRef    = useRef(null)
  const pausedRef = useRef(false)
  const swipeX    = useRef(null)

  // RAF scroll loop — continuous, pausable via ref
  useEffect(() => {
    const track = trackRef.current
    if (!track) return
    const SPEED = 0.6
    const loop = () => {
      if (!pausedRef.current) {
        track.scrollLeft += SPEED
        const half = track.scrollWidth / 2
        if (track.scrollLeft >= half) track.scrollLeft -= half
      }
      rafRef.current = requestAnimationFrame(loop)
    }
    rafRef.current = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(rafRef.current)
  }, [])

  const setPaused = (val) => { pausedRef.current = val }

  const skip = (dir) => {
    const track = trackRef.current
    if (!track) return
    track.scrollLeft += dir * STEP
    const half = track.scrollWidth / 2
    if (track.scrollLeft >= half) track.scrollLeft -= half
    if (track.scrollLeft < 0)    track.scrollLeft += half
  }

  const onTouchStart = e => { swipeX.current = e.touches[0].clientX }
  const onTouchEnd   = e => {
    if (!swipeX.current) return
    const dx = e.changedTouches[0].clientX - swipeX.current
    if (Math.abs(dx) > 40) skip(dx < 0 ? 1 : -1)
    swipeX.current = null
  }

  const btnStyle = (side) => ({
    flexShrink: 0, width: 44, height: 44, borderRadius: '50%', alignSelf: 'center',
    background: 'var(--bg-card)', border: '1px solid var(--border)',
    color: 'var(--text)', fontSize: 22,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    cursor: 'pointer', transition: 'all 0.2s',
    marginLeft: side === 'right' ? 12 : 0,
    marginRight: side === 'left'  ? 12 : 0,
    boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
  })

  return (
    <section style={{ marginBottom: 28 }}>
      <h2 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', marginBottom: 22 }}>
        Die besten Picks des Tages
        <span style={{ fontSize: 14, fontWeight: 400, color: 'var(--muted)', marginLeft: 10 }}>
          ({topDeals.length})
        </span>
      </h2>

      <div style={{ display: 'flex', alignItems: 'stretch' }}>
        {isDesktop && (
          <button style={btnStyle('left')} onClick={() => skip(-1)}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent)'; e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = '#fff' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text)' }}
          >‹</button>
        )}

        <div
          ref={trackRef}
          className="no-scroll"
          style={{ flex: 1, overflowX: 'scroll', padding: '4px 0 12px' }}
          onMouseEnter={() => setPaused(true)}
          onMouseLeave={() => setPaused(false)}
          onTouchStart={onTouchStart}
          onTouchEnd={onTouchEnd}
        >
          <div style={{ display: 'flex', gap: GAP, width: 'max-content' }}>
            {[...topDeals, ...topDeals].map((deal, i) => {
              const disc = discount(deal.current_price, deal.original_price)
              return (
                <div
                  key={`${deal.asin}-${i}`}
                  onClick={() => onOpen(deal)}
                  style={{ flexShrink: 0, width: CARD_W, background: 'var(--bg-card)', border: '1px solid var(--border)', display: 'flex', cursor: 'pointer', transition: 'transform 0.3s cubic-bezier(0.16,1,0.3,1), box-shadow 0.3s' }}
                  onMouseEnter={e => { e.currentTarget.style.transform = 'translateY(-4px)'; e.currentTarget.style.boxShadow = '0 12px 30px rgba(31,30,29,0.06)' }}
                  onMouseLeave={e => { e.currentTarget.style.transform = ''; e.currentTarget.style.boxShadow = '' }}
                >
                  <div style={{ width: 170, flexShrink: 0, background: 'var(--bg-img)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20, position: 'relative' }}>
                    {disc > 0 && (
                      <div style={{ position: 'absolute', top: 12, left: 12, background: 'var(--accent)', color: '#fff', fontSize: 10, fontWeight: 600, padding: '2px 8px', letterSpacing: 0.5 }}>
                        –{disc}%
                      </div>
                    )}
                    {deal.image_url
                      ? <img src={deal.image_url} alt={deal.name} style={{ maxWidth: '100%', maxHeight: 130, objectFit: 'contain' }} />
                      : <div style={{ fontSize: 40, color: 'var(--border)' }}>📦</div>
                    }
                  </div>
                  <div style={{ flex: 1, padding: '20px 18px', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                    <div>
                      <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--muted)', fontWeight: 500, marginBottom: 6 }}>
                        {deal.brand || deal.category}
                      </div>
                      <h3 style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.4, marginBottom: 10, color: 'var(--text)' }}>
                        {deal.name}
                      </h3>
                    </div>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 17, fontWeight: 700 }}>{fmtPrice(deal.current_price)}</span>
                        {deal.original_price > deal.current_price && (
                          <span style={{ fontSize: 12, textDecoration: 'line-through', color: 'var(--muted)' }}>{fmtPrice(deal.original_price)}</span>
                        )}
                      </div>
                      <div style={{ fontSize: 11, color: 'var(--muted)' }}>
                        {deal.category}
                        {deal.prime && <span style={{ color: '#00A8E0', fontWeight: 600, marginLeft: 8 }}>Prime</span>}
                      </div>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {isDesktop && (
          <button style={btnStyle('right')} onClick={() => skip(1)}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent)'; e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = '#fff' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text)' }}
          >›</button>
        )}
      </div>
    </section>
  )
}


/* ── Main Page ──────────────────────────────────────────────────── */
export default function DealsPage() {
  const { isMobile, isDesktop, width } = useBreakpoint()
  const [categories,   setCategories]   = useState(() => lsGet(LS_CATS)  || ['Alle'])
  const [selectedCat,  setSelectedCat]  = useState('Alle')
  const [sortBy,       setSortBy]       = useState('score')
  const [selectedCountry, setSelectedCountry] = useState('DE')
  const [search,       setSearch]       = useState('')
  const [deals,        setDeals]        = useState(() => lsGet(LS_DEALS) || [])
  const [bestPicks,    setBestPicks]    = useState(() => lsGet(LS_PICKS) || [])
  const [loading,      setLoading]      = useState(deals.length === 0)
  const [theme,        setTheme]        = useState(() => localStorage.getItem('sng_theme') || 'light')

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('sng_theme', theme)
  }, [theme])

  const toggleTheme = () => setTheme(t => t === 'light' ? 'dark' : 'light')
  const [error,        setError]        = useState(null)
  const [selectedDeal, setSelectedDeal] = useState(null)

  /* Load best picks once — unaffected by filters */
  useEffect(() => {
    api.deals({ sort_by: 'score', limit: 20 })
      .then(data => { setBestPicks(data); lsSet(LS_PICKS, data) })
      .catch(() => {})
  }, [])

  useEffect(() => {
    api.categories()
      .then(cats => { setCategories(cats); lsSet(LS_CATS, cats) })
      .catch(() => {})
  }, [])

  const loadDeals = useCallback(() => {
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

  /* Deep link */
  useEffect(() => {
    const asin = new URLSearchParams(window.location.search).get('asin')
    if (!asin) return
    api.product(asin)
      .then(deal => {
        setSelectedDeal(deal)
        window.history.replaceState({ snagga: 'modal', asin: deal.asin }, '', `?asin=${asin}`)
      })
      .catch(() => window.history.replaceState({}, '', '/'))
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const openDeal = useCallback(deal => {
    setSelectedDeal(deal)
    window.history.pushState({ snagga: 'modal', asin: deal.asin }, '', `?asin=${deal.asin}`)
  }, [])

  const closeModal = useCallback(() => {
    if (window.history.state?.snagga === 'modal') window.history.back()
    else { window.history.replaceState({}, '', '/'); setSelectedDeal(null) }
  }, [])

  useEffect(() => {
    const onPop = e => { if (e.state?.snagga !== 'modal') setSelectedDeal(null) }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  // Swipe-left on main page → browser back
  const pageSwipeX = useRef(null)
  const handlePageTouchStart = useCallback(e => {
    pageSwipeX.current = e.touches[0].clientX
  }, [])
  const handlePageTouchEnd = useCallback(e => {
    if (pageSwipeX.current === null || selectedDeal) return
    const dx = e.changedTouches[0].clientX - pageSwipeX.current
    if (dx < -80) window.history.back()
    pageSwipeX.current = null
  }, [selectedDeal])

  const cols = width >= 1500 ? 5 : width >= 1100 ? 4 : width >= 768 ? 3 : 2

  return (
    <div
      style={{ minHeight: '100%', background: 'var(--bg)' }}
      onTouchStart={isMobile ? handlePageTouchStart : undefined}
      onTouchEnd={isMobile ? handlePageTouchEnd : undefined}
    >
      {selectedDeal && <ProductModal deal={selectedDeal} onClose={closeModal} />}

      {/* ── HEADER ── */}
      <header style={{
        background: '#153D68',
        position: 'sticky', top: 0, zIndex: 100,
        height: 'var(--header-h)',
      }}>
        <div style={{
          maxWidth: 1840, width: '98%', margin: '0 auto',
          height: '100%', display: 'flex', alignItems: 'center', gap: isMobile ? 12 : 36,
          paddingLeft: !isDesktop ? 14 : 0, paddingRight: !isDesktop ? 14 : 0,
        }}>
          <a href="/" style={{ fontSize: isMobile ? 22 : 28, fontWeight: 800, letterSpacing: '-0.5px', flexShrink: 0, color: '#EDE9E3' }}>
            snagga<span style={{ color: 'var(--accent)' }}>.de</span>
          </a>

          <div style={{ flex: 1, maxWidth: 560, position: 'relative' }}>
            <svg style={{ position: 'absolute', left: 13, top: '50%', transform: 'translateY(-50%)', color: '#999', pointerEvents: 'none' }} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
            </svg>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={isMobile ? 'Suchen…' : 'Marke, Kategorie oder Produkt suchen…'}
              style={{ width: '100%', padding: '10px 14px 10px 38px', border: '1px solid rgba(255,255,255,0.25)', background: '#fff', fontSize: 14, outline: 'none', borderRadius: 2, color: '#1F1E1D' }}
              onFocus={e  => { e.target.style.borderColor = '#fff'; e.target.style.boxShadow = '0 0 0 2px rgba(255,255,255,0.4)' }}
              onBlur={e   => { e.target.style.borderColor = 'rgba(255,255,255,0.25)'; e.target.style.boxShadow = '' }}
            />
          </div>

          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            title={theme === 'light' ? 'Dark Mode' : 'Light Mode'}
            style={{
              flexShrink: 0, marginLeft: 'auto', width: 38, height: 38, borderRadius: '50%',
              border: '1px solid rgba(255,255,255,0.25)', background: '#fff',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#153D68', transition: 'all 0.2s', lineHeight: 1,
            }}
            onMouseEnter={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.85)' }}
            onMouseLeave={e => { e.currentTarget.style.background = '#fff' }}
          >
            {theme === 'light' ? (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                <circle cx="12" cy="12" r="5"/>
                <line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/>
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                <line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/>
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
              </svg>
            )}
          </button>
        </div>
      </header>

      {/* ── FILTER BAR — full width, outside constrained main ── */}
      <div style={{
        background: '#153D68', border: '1px solid #1E5080', borderTop: 'none',
        position: 'sticky', top: 'calc(var(--header-h) - 1px)', zIndex: 90,
      }}>
        <div style={{
          maxWidth: 1840, width: '98%', margin: '0 auto',
          padding: isMobile ? '10px 14px' : '13px 0',
          display: 'flex',
          flexDirection: isMobile ? 'column' : 'row',
          justifyContent: 'space-between',
          alignItems: isMobile ? 'stretch' : 'center',
          gap: isMobile ? 8 : 0,
        }}>
        <div style={{ display: 'flex', alignItems: 'center', minWidth: 0, flex: 1, gap: 6 }}>
          {isDesktop && (
            <span style={{ fontSize: 13, color: '#fff', fontWeight: 600, flexShrink: 0 }}>
              Kategorien
            </span>
          )}
          {/* "Alle" — always visible, never scrolls away */}
          {['Alle'].map(cat => (
            <button
              key={cat}
              onClick={() => setSelectedCat(cat)}
              style={{
                padding: isMobile ? '6px 12px' : '7px 16px',
                fontSize: 13, flexShrink: 0, borderRadius: 2,
                border: '1px solid transparent',
                background: cat === selectedCat ? 'rgba(255,255,255,0.95)' : 'rgba(255,255,255,0.1)',
                color: cat === selectedCat ? '#153D68' : '#fff',
                fontWeight: cat === selectedCat ? 600 : 500,
                transition: 'all 0.15s',
              }}
              onMouseEnter={e => { if (cat !== selectedCat) { e.currentTarget.style.background = 'rgba(255,255,255,0.2)'; e.currentTarget.style.color = '#fff' } }}
              onMouseLeave={e => { if (cat !== selectedCat) { e.currentTarget.style.background = 'rgba(255,255,255,0.1)'; e.currentTarget.style.color = 'rgba(255,255,255,0.8)' } }}
            >
              {cat}
            </button>
          ))}
          <div style={{ width: 1, height: 18, background: 'rgba(255,255,255,0.2)', flexShrink: 0 }} />
          {/* Rest — scrollable */}
          <div className="no-scroll" style={{ display: 'flex', gap: 6, alignItems: 'center', overflowX: 'auto', flexWrap: 'nowrap', minWidth: 0 }}>
          {categories.filter(c => c !== 'Alle').map(cat => (
            <button
              key={cat}
              onClick={() => setSelectedCat(cat)}
              style={{
                padding: isMobile ? '6px 12px' : '7px 16px',
                fontSize: 13, flexShrink: 0, borderRadius: 2,
                border: '1px solid transparent',
                background: cat === selectedCat ? 'rgba(255,255,255,0.95)' : 'rgba(255,255,255,0.1)',
                color: cat === selectedCat ? '#153D68' : '#fff',
                fontWeight: cat === selectedCat ? 600 : 500,
                transition: 'all 0.15s',
              }}
              onMouseEnter={e => { if (cat !== selectedCat) { e.currentTarget.style.background = 'rgba(255,255,255,0.2)'; e.currentTarget.style.color = '#fff' } }}
              onMouseLeave={e => { if (cat !== selectedCat) { e.currentTarget.style.background = 'rgba(255,255,255,0.1)'; e.currentTarget.style.color = 'rgba(255,255,255,0.8)' } }}
            >
              {cat}
            </button>
          ))}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0, marginLeft: 12 }}>
          {/* Versandland */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            {COUNTRIES.map(c => {
              const active = selectedCountry === c.code
              return (
                <button
                  key={c.code}
                  onClick={() => setSelectedCountry(c.code)}
                  title={c.label}
                  style={{
                    padding: 0,
                    border: 'none',
                    background: 'none',
                    cursor: 'pointer',
                    display: 'flex',
                    transition: 'all 0.15s',
                    transform: active ? 'scale(1.18)' : 'scale(1)',
                    opacity: active ? 1 : 0.55,
                    filter: active ? 'none' : 'grayscale(30%)',
                  }}
                >
                  <img
                    src={c.src}
                    alt={c.label}
                    style={{ width: 28, height: 19, objectFit: 'cover', display: 'block', borderRadius: 2 }}
                  />
                </button>
              )
            })}
          </div>
          <div style={{ width: 1, height: 22, background: 'rgba(255,255,255,0.2)', flexShrink: 0 }} />
          {isDesktop && (
            <span style={{ fontSize: 13, color: '#fff', fontWeight: 600 }}>
              Sortieren
            </span>
          )}
          <select
            value={sortBy}
            onChange={e => setSortBy(e.target.value)}
            style={{ border: '1px solid var(--border)', background: 'var(--bg-card)', padding: '8px 14px', fontSize: 13, color: 'var(--text)', outline: 'none', borderRadius: 2, cursor: 'pointer', fontFamily: 'inherit' }}
          >
            {SORTS.map(s => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </div>
        </div>
      </div>

      {/* ── MAIN ── */}
      <main style={{ maxWidth: 1840, width: '98%', margin: '0 auto', padding: isMobile ? '12px 0 24px' : '20px 0 32px', minHeight: 'calc(100vh - var(--header-h))', display: 'flex', flexDirection: 'column' }}>

        {/* Best Picks — immer sichtbar, unabhängig vom Filter */}
        {!isMobile && bestPicks.length >= 3 && (
          <BestPicksSlider deals={bestPicks} onOpen={openDeal} />
        )}

        {/* Grid title */}
        <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 22, color: 'var(--text)' }}>
          {selectedCat !== 'Alle' ? `${selectedCat} Deals` : search ? `Suche: "${search}"` : 'Alle Picks'}
          {!loading && (
            <span style={{ fontSize: 14, fontWeight: 400, color: 'var(--muted)', marginLeft: 10 }}>
              ({deals.length})
            </span>
          )}
        </h2>

        {loading && <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--muted)', fontSize: 15 }}>Deals laden…</div>}
        {error   && <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--accent)', fontSize: 15 }}>Backend nicht erreichbar.</div>}
        {!loading && !error && deals.length === 0 && <div style={{ textAlign: 'center', padding: '80px 20px', color: 'var(--muted)', fontSize: 15 }}>Keine Deals gefunden.</div>}

        {/* ── GRID ── */}
        {!loading && !error && deals.length > 0 && (
          <div style={{ display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: isMobile ? 14 : 24 }}>
            {deals.map(deal => (
              <DealCard key={deal.asin} deal={deal} onClick={() => openDeal(deal)} />
            ))}
          </div>
        )}

        {!loading && deals.length > 0 && (
          <p style={{ fontSize: 12, color: 'var(--muted)', textAlign: 'center', marginTop: 'auto', paddingTop: 48, lineHeight: 1.6 }}>
            * Als Amazon-Partner verdienen wir an qualifizierten Käufen — für dich entstehen keine Mehrkosten.
          </p>
        )}
      </main>

      {/* ── FOOTER ── */}
      <footer style={{ background: '#153D68', borderTop: '1px solid #1E5080', padding: '36px 2%' }}>
        <div style={{ maxWidth: 1840, width: '98%', margin: '0 auto', display: 'flex', flexDirection: isMobile ? 'column' : 'row', justifyContent: 'space-between', alignItems: isMobile ? 'flex-start' : 'center', gap: 16 }}>
          <div>
            <a href="/" style={{ fontSize: 20, fontWeight: 800, color: '#EDE9E3', letterSpacing: '-0.5px' }}>
              snagga<span style={{ color: 'var(--accent)' }}>.de</span>
            </a>
            <p style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', marginTop: 6 }}>
              Täglich kuratierte Amazon-Bestpreise · Affiliate-Partner von Amazon
            </p>
          </div>
          <nav style={{ display: 'flex', gap: isMobile ? 16 : 28, flexWrap: 'wrap' }}>
            {[
              ['Impressum', '/legal#impressum'],
              ['Datenschutz', '/legal#datenschutz'],
              ['Affiliate-Hinweis', '/legal#affiliate'],
              ['Preisangaben', '/legal#preise'],
            ].map(([label, href]) => (
              <a key={label} href={href} style={{ fontSize: 13, color: 'rgba(255,255,255,0.65)', fontWeight: 500, transition: 'color 0.15s' }}
                onMouseEnter={e => e.currentTarget.style.color = '#fff'}
                onMouseLeave={e => e.currentTarget.style.color = 'rgba(255,255,255,0.65)'}
              >{label}</a>
            ))}
          </nav>
        </div>
        <div style={{ maxWidth: 1840, width: '98%', margin: '24px auto 0', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: 20 }}>
          <p style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)', textAlign: 'center' }}>
            © 2026 snagga.de · Preise ohne Gewähr · Stand Juni 2026
          </p>
        </div>
      </footer>
    </div>
  )
}
