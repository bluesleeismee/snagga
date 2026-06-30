import React, { useState, useEffect, useCallback, useRef } from 'react'
import DealCard from '../components/DealCard.jsx'
import ProductModal from '../components/ProductModal.jsx'
import { useBreakpoint } from '../hooks/useBreakpoint.js'
import { api } from '../api.js'
import { fmtPrice, discount } from '../utils.js'

const SORTS = [
  { id: 'score',      label: 'Bester Deal' },
  { id: 'discount',   label: 'Grösster Rabatt' },
  { id: 'price_asc',  label: 'Günstigste' },
  { id: 'price_desc', label: 'Teuerste' },
  { id: 'newest',     label: 'Neueste' },
]

// Kurznamen nur für die Anzeige — interne Kategorie/DB bleibt unverändert.
// Flaggen (DE/AT/CH) entfernt: Keepa liefert nur amazon.de, AT/CH nicht
// unterscheidbar. Assets bleiben unter /public/flags/ archiviert für später.
const CAT_LABELS = {
  'Drogerie & Körperpflege':         'Körperpflege',
  'Küche, Haushalt & Wohnen':        'Küche & Haushalt',
  'Musikinstrumente & DJ-Equipment': 'Musik',
  'Elektro-Großgeräte':              'Grossgeräte',
  'Computer & Zubehör':              'Computer',
  'Elektronik & Foto':               'Elektronik',
  'Auto & Motorrad':                 'Auto',
  'Sport & Freizeit':                'Sport',
  'Kamera & Foto':                   'Kamera',
}
const catLabel = (c) => CAT_LABELS[c] || c

// Gewünschte Reihenfolge der Kategorie-Chips
const CAT_ORDER = [
  'Elektronik & Foto',
  'Computer & Zubehör',
  'Küche, Haushalt & Wohnen',
  'Games',
  'Auto & Motorrad',
  'Sport & Freizeit',
  'Drogerie & Körperpflege',
  'Baumarkt',
  'Musikinstrumente & DJ-Equipment',
  'Kamera & Foto',
  'Elektro-Großgeräte',
]
const sortCats = (cats) => {
  const known  = CAT_ORDER.filter(c => cats.includes(c))
  const others = cats.filter(c => !CAT_ORDER.includes(c) && c !== 'Alle' && c !== 'Top Picks')
  return [...known, ...others]
}

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
  const topDeals = deals.slice(0, 10)
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
    flexShrink: 0, width: 52, height: 52, borderRadius: '50%', alignSelf: 'center',
    background: 'var(--bg-card)', border: '1px solid var(--border)',
    color: 'var(--text)',
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    cursor: 'pointer', transition: 'all 0.2s',
    marginLeft: side === 'right' ? 12 : 0,
    marginRight: side === 'left'  ? 12 : 0,
    boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
  })
  const ArrowLeft  = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="15,18 9,12 15,6"/></svg>
  const ArrowRight = () => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="9,18 15,12 9,6"/></svg>

  return (
    <section style={{ marginBottom: 28 }}>
      <h2 style={{ fontSize: 22, fontWeight: 700, color: 'var(--text)', marginBottom: 22, display: 'flex', alignItems: 'center', gap: 12 }}>
        <span>Neueste Picks</span>
        <span style={{ fontSize: 11, fontWeight: 600, background: 'var(--accent)', color: '#fff', padding: '2px 8px', letterSpacing: 0.5, verticalAlign: 'middle' }}>
          NEU
        </span>
        <span style={{ fontSize: 14, fontWeight: 400, color: 'var(--muted)' }}>
          ({topDeals.length})
        </span>
      </h2>

      <div style={{ display: 'flex', alignItems: 'stretch' }}>
        {isDesktop && (
          <button style={btnStyle('left')} onClick={() => skip(-1)}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent)'; e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = '#fff' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text)' }}
          ><ArrowLeft /></button>
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
          ><ArrowRight /></button>
        )}
      </div>
    </section>
  )
}


/* ── Main Page ──────────────────────────────────────────────────── */
export default function DealsPage() {
  const { isMobile, isDesktop, width } = useBreakpoint()
  const [categories,   setCategories]   = useState(() => lsGet(LS_CATS)  || ['Alle'])
  const [selectedCats, setSelectedCats] = useState(new Set())   // leer = "Alle"
  const [sortBy,       setSortBy]       = useState('score')
  const [search,       setSearch]       = useState('')
  const [deals,        setDeals]        = useState(() => lsGet(LS_DEALS) || [])
  const [visibleCount, setVisibleCount] = useState(60)
  const [bestPicks,    setBestPicks]    = useState(() => lsGet(LS_PICKS) || [])
  const [loading,      setLoading]      = useState(deals.length === 0)
  const [theme,        setTheme]        = useState(() => localStorage.getItem('sng_theme') || 'light')
  const navRef    = useRef(null)
  const spacerRef = useRef(null)
  const lastScrollY = useRef(0)

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('sng_theme', theme)
  }, [theme])

  // Spacer height tracks nav height via ResizeObserver — no state, no re-render
  useEffect(() => {
    const nav    = navRef.current
    const spacer = spacerRef.current
    if (!nav || !spacer) return
    const update = () => { spacer.style.height = nav.offsetHeight + 'px' }
    update()
    const ro = new ResizeObserver(update)
    ro.observe(nav)
    return () => ro.disconnect()
  }, [])

  // Scroll-hide on mobile — direct DOM mutation, no React state, no re-render lag
  // Use document+capture so we catch scroll regardless of which element is the container
  useEffect(() => {
    const nav = navRef.current
    if (!nav) return
    nav.style.transform = 'translateY(0)'
    if (isDesktop) return
    const getY = () => window.scrollY ?? document.documentElement.scrollTop ?? document.body.scrollTop ?? 0
    let lastY = getY()
    const handleScroll = () => {
      const y = getY()
      if (y > lastY && y > 80) {
        nav.style.transform = 'translateY(-100%)'
      } else if (y < lastY) {
        nav.style.transform = 'translateY(0)'
      }
      lastY = y
    }
    document.addEventListener('scroll', handleScroll, { passive: true, capture: true })
    return () => document.removeEventListener('scroll', handleScroll, { capture: true })
  }, [isDesktop])

  const toggleTheme = () => setTheme(t => t === 'light' ? 'dark' : 'light')
  const [error,        setError]        = useState(null)
  const [selectedDeal, setSelectedDeal] = useState(null)

  /* Neueste Picks — frische Neuzugänge, unabhängig von Filtern */
  useEffect(() => {
    api.deals({ sort_by: 'newest', limit: 12 })
      .then(data => {
        setBestPicks(data)
        lsSet(LS_PICKS, data)
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    api.categories()
      .then(cats => { setCategories(cats); lsSet(LS_CATS, cats) })
      .catch(() => {})
  }, [])

  const loadDeals = useCallback(() => {
    const knownCats = sortCats(categories)
    const noFilter = selectedCats.size === 0 || selectedCats.size >= knownCats.length
    const isDefault = noFilter && sortBy === 'score' && !search
    if (!isDefault) setLoading(true)
    setError(null)
    // "Neueste"-Chip ohne Kategoriefilter: nur die 24 frischesten Deals
    const dealLimit = sortBy === 'newest' ? 24 : 500
    const categoryParam = noFilter ? undefined : [...selectedCats].join('|')
    api.deals({ category: categoryParam, sort_by: sortBy, search: search || undefined, limit: dealLimit })
      .then(data => {
        setDeals(data)
        setVisibleCount(60)
        setLoading(false)
        if (isDefault) lsSet(LS_DEALS, data)
      })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [selectedCats, sortBy, search, categories])

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


  const cols = width >= 1500 ? 5 : width >= 1100 ? 4 : width >= 768 ? 3 : 2

  return (
    <div
      style={{ minHeight: '100%', background: 'var(--bg)' }}
    >
      {selectedDeal && <ProductModal deal={selectedDeal} onClose={closeModal} />}

      {/* ── HEADER + FILTERBAR WRAPPER ── */}
      <div
        ref={navRef}
        style={{
          position: 'fixed', top: 0, left: 0, right: 0, zIndex: 100,
          transition: 'transform 0.3s ease',
          willChange: 'transform',
        }}
      >

      {/* ── HEADER ── */}
      <header style={{
        background: '#153D68',
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

          {/* Telegram button — ~3 button-widths left of theme toggle */}
          <a
            href="https://t.me/snagga_deals"
            target="_blank"
            rel="noopener noreferrer"
            title="Deals auf Telegram abonnieren"
            style={{
              marginLeft: 'auto', marginRight: 138, flexShrink: 0,
              width: 38, height: 38,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              textDecoration: 'none', transition: 'opacity 0.2s', opacity: 1,
            }}
            onMouseEnter={e => { e.currentTarget.style.opacity = '0.8' }}
            onMouseLeave={e => { e.currentTarget.style.opacity = '1' }}
          >
            <svg width="38" height="38" viewBox="0 0 240 240" xmlns="http://www.w3.org/2000/svg">
              <defs>
                <linearGradient id="tg-g" x1="120" y1="0" x2="120" y2="240" gradientUnits="userSpaceOnUse">
                  <stop offset="0" stopColor="#2AABEE"/>
                  <stop offset="1" stopColor="#229ED9"/>
                </linearGradient>
              </defs>
              <circle cx="120" cy="120" r="120" fill="url(#tg-g)"/>
              <path d="M81.229 128.772l14.237 39.406s1.78 3.687 3.686 3.687c1.906 0 30.255-29.493 30.255-29.493l31.485-60.32L81.229 128.772z" fill="#c8daea"/>
              <path d="M100.106 138.878l-2.733 29.046s-1.144 8.9 7.754 0l17.418-15.788-22.439-13.258z" fill="#a9c9dd"/>
              <path d="M81.486 130.178l-40.232-13.309s-4.806-1.948-3.268-6.364c.319-.913 1.955-2.152 5.805-4.298 18.032-10.009 135.01-50.899 135.01-50.899s4.406-1.485 7.006-.5c1.32.485 2.16 1.028 2.87 3.148.253.763.399 2.378.38 3.968-.018 1.149-.134 2.21-.27 3.574-1.378 13.85-42.524 117.178-42.524 117.178s-2.461 6.121-7.134 6.292c-2.008.073-4.444-.586-6.787-2.63-6.914-5.992-30.818-22.067-36.287-25.847-.126-.088-.229-.196-.32-.313-.34-.43-.546-1.065.24-1.788 0 0 41.795-37.276 42.966-41.369.087-.3-.232-.449-.667-.317-4.31 1.588-49.816 30.783-55.593 34.173z" fill="white"/>
            </svg>
          </a>
          {/* Theme toggle */}
          <button
            onClick={toggleTheme}
            title={theme === 'light' ? 'Dark Mode' : 'Light Mode'}
            style={{
              flexShrink: 0, width: 38, height: 38, borderRadius: '50%',
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

      {/* ── FILTER BAR ── */}
      <div style={{
        background: '#153D68', border: '1px solid #1E5080', borderTop: 'none',
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
          {(() => {
            const isActive = selectedCats.size === 0 && sortBy !== 'newest'
            return (
              <button
                key="alle"
                onClick={() => { setSelectedCats(new Set()); setSortBy('score') }}
                style={{
                  padding: isMobile ? '6px 12px' : '7px 16px',
                  fontSize: 13, flexShrink: 0, borderRadius: 2,
                  border: '1px solid transparent',
                  background: isActive ? 'rgba(255,255,255,0.95)' : 'rgba(255,255,255,0.1)',
                  color: isActive ? '#153D68' : '#fff',
                  fontWeight: isActive ? 600 : 500,
                  transition: 'all 0.15s',
                }}
                onMouseEnter={e => { if (!isActive) { e.currentTarget.style.background = 'rgba(255,255,255,0.2)'; e.currentTarget.style.color = '#fff' } }}
                onMouseLeave={e => { if (!isActive) { e.currentTarget.style.background = 'rgba(255,255,255,0.1)'; e.currentTarget.style.color = 'rgba(255,255,255,0.8)' } }}
              >
                Alle
              </button>
            )
          })()}
          <div style={{ width: 1, height: 18, background: 'rgba(255,255,255,0.2)', flexShrink: 0 }} />
          {/* Rest — Desktop: umbrechen (max. 2 Zeilen), Mobile: horizontaler Scroll */}
          <div className="no-scroll" style={{
            display: 'flex', gap: 6, alignItems: 'center', minWidth: 0,
            overflowX: isMobile ? 'auto' : 'visible',
            flexWrap: isMobile ? 'nowrap' : 'wrap',
            rowGap: 6, overscrollBehaviorX: 'contain',
          }}>
          {/* Neueste — Sortier-Shortcut */}
          {(() => {
            const isActive = sortBy === 'newest'
            return (
              <button
                key="neueste"
                onClick={() => { setSortBy('newest'); setSelectedCats(new Set()) }}
                style={{
                  padding: isMobile ? '6px 12px' : '7px 16px',
                  fontSize: 13, flexShrink: 0, borderRadius: 2,
                  border: '1px solid transparent',
                  background: isActive ? 'rgba(255,255,255,0.95)' : 'rgba(255,255,255,0.1)',
                  color: isActive ? '#153D68' : '#fff',
                  fontWeight: isActive ? 600 : 500,
                  transition: 'all 0.15s',
                  whiteSpace: 'nowrap',
                }}
                onMouseEnter={e => { if (!isActive) { e.currentTarget.style.background = 'rgba(255,255,255,0.2)' } }}
                onMouseLeave={e => { if (!isActive) { e.currentTarget.style.background = 'rgba(255,255,255,0.1)' } }}
              >
                Neueste
              </button>
            )
          })()}
          <div style={{ width: 1, height: 14, background: 'rgba(255,255,255,0.15)', flexShrink: 0 }} />
          {sortCats(categories).map(cat => {
            const isActive = selectedCats.has(cat)
            return (
              <button
                key={cat}
                onClick={() => {
                  setSelectedCats(prev => prev.has(cat) ? new Set() : new Set([cat]))
                  setSortBy('score')
                }}
                title={cat}
                style={{
                  padding: isMobile ? '6px 12px' : '7px 16px',
                  fontSize: 13, flexShrink: 0, borderRadius: 2,
                  border: '1px solid transparent',
                  background: isActive ? 'rgba(255,255,255,0.95)' : 'rgba(255,255,255,0.1)',
                  color: isActive ? '#153D68' : '#fff',
                  fontWeight: isActive ? 600 : 500,
                  transition: 'all 0.15s',
                  whiteSpace: 'nowrap',
                }}
                onMouseEnter={e => { if (!isActive) { e.currentTarget.style.background = 'rgba(255,255,255,0.2)' } }}
                onMouseLeave={e => { if (!isActive) { e.currentTarget.style.background = 'rgba(255,255,255,0.1)' } }}
              >
                {catLabel(cat)}
              </button>
            )
          })}
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexShrink: 0, marginLeft: 12 }}>
          {isDesktop && <div style={{ width: 1, height: 22, background: 'rgba(255,255,255,0.2)', flexShrink: 0 }} />}
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
      </div>{/* end fixed nav wrapper */}
      <div ref={spacerRef} />{/* spacer height set imperatively by ResizeObserver */}

      {/* ── MAIN ── */}
      <main style={{ maxWidth: 1840, width: '98%', margin: '0 auto', padding: isMobile ? '12px 0 24px' : '20px 0 32px', minHeight: 'calc(100vh - var(--header-h))', display: 'flex', flexDirection: 'column' }}>

        {/* Best Picks — immer sichtbar, unabhängig vom Filter */}
        {!isMobile && bestPicks.length >= 3 && (
          <BestPicksSlider deals={bestPicks} onOpen={openDeal} />
        )}

        {/* Grid title */}
        <h2 style={{ fontSize: 22, fontWeight: 700, marginBottom: 22, color: 'var(--text)' }}>
          {search
            ? `Suche: "${search}"`
            : selectedCats.size === 1
              ? `${catLabel([...selectedCats][0])} Deals`
              : selectedCats.size > 1
                ? [...selectedCats].map(catLabel).join(' + ')
                : sortBy === 'newest' ? 'Neueste Picks' : 'Alle Picks'
          }
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
            {deals.slice(0, visibleCount).map(deal => (
              <DealCard key={deal.asin} deal={deal} onClick={() => openDeal(deal)} />
            ))}
          </div>
        )}

        {/* ── Mehr anzeigen ── */}
        {!loading && !error && deals.length > visibleCount && (
          <div style={{ textAlign: 'center', marginTop: 32 }}>
            <button
              onClick={() => setVisibleCount(c => c + 60)}
              style={{
                padding: '12px 32px', fontSize: 14, fontWeight: 600,
                background: 'var(--accent)', color: '#fff', border: 'none',
                borderRadius: 2, cursor: 'pointer', transition: 'opacity 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.opacity = '0.88'}
              onMouseLeave={e => e.currentTarget.style.opacity = '1'}
            >
              Mehr anzeigen ({deals.length - visibleCount} weitere)
            </button>
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
            <p style={{ fontSize: 12, color: '#fff', marginTop: 6 }}>
              Täglich kuratierte Amazon-Deals · Affiliate-Partner von Amazon
            </p>
          </div>
          <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'flex-start' : 'center', gap: isMobile ? 12 : 28, flexWrap: 'wrap' }}>
            {[
              ['Impressum', '/legal#impressum'],
              ['Datenschutz', '/legal#datenschutz'],
              ['Nutzungsbedingungen', '/legal#nutzung'],
              ['Affiliate-Hinweis', '/legal#affiliate'],
              ['Preisangaben', '/legal#preise'],
            ].map(([label, href]) => (
              <a key={label} href={href} style={{ fontSize: 13, color: '#fff', fontWeight: 500, transition: 'opacity 0.15s' }}
                onMouseEnter={e => e.currentTarget.style.opacity = '0.7'}
                onMouseLeave={e => e.currentTarget.style.opacity = '1'}
              >{label}</a>
            ))}
            <span style={{ fontSize: 11, color: '#fff', marginLeft: isMobile ? 0 : 'auto' }}>
              © 2026 snagga.de · Preise ohne Gewähr
            </span>
          </div>
        </div>
      </footer>
    </div>
  )
}
