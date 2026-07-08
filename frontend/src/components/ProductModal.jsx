import React, { useState, useEffect, useCallback, useRef } from 'react'
import { fmtPrice, discount, fmtAge, AGE_COLORS, fmtReviews, shareOrCopy } from '../utils.js'
import { useBreakpoint } from '../hooks/useBreakpoint.js'
import { api } from '../api.js'

// Chart-Fadenkreuz für den per dangerouslySetInnerHTML injizierten Chart-SVG.
// Spiegelt _CHART_HOVER_JS in backend/main.py (muss synchron bleiben) — die
// inline on*-Attribute des SVG rufen diese globalen Handler auf. <script>-Tags
// aus injiziertem HTML laufen nicht, inline-Handler + window-Funktion aber schon.
if (typeof window !== 'undefined' && !window.__chartHover) {
  window.__chartHover = function (evt, rect) {
    const svg = rect.ownerSVGElement; if (!svg) return
    const pts = svg.__pts || (svg.__pts = JSON.parse(svg.getAttribute('data-pts') || '[]'))
    if (!pts.length) return
    const pt = svg.createSVGPoint(); pt.x = evt.clientX; pt.y = evt.clientY
    const ctm = svg.getScreenCTM(); if (!ctm) return
    const loc = pt.matrixTransform(ctm.inverse())
    let best = pts[0], bd = 1e9
    for (let i = 0; i < pts.length; i++) { const d = Math.abs(pts[i][0] - loc.x); if (d < bd) { bd = d; best = pts[i] } }
    const line = svg.querySelector('.cx-line'), dot = svg.querySelector('.cx-dot'),
      tip = svg.querySelector('.cx-tip'), td = svg.querySelector('.cx-tip-d'), tp = svg.querySelector('.cx-tip-p')
    if (!line || !dot || !tip) return
    line.setAttribute('x1', best[0]); line.setAttribute('x2', best[0]); line.style.display = ''
    dot.setAttribute('cx', best[0]); dot.setAttribute('cy', best[1]); dot.style.display = ''
    td.textContent = best[2]; tp.textContent = best[3]
    let x = best[0] + 12; if (x + 118 > 746) x = best[0] - 118 - 12; if (x < 2) x = 2
    let y = best[1] - 48; if (y < 2) y = best[1] + 14
    tip.setAttribute('transform', `translate(${x},${y})`); tip.style.display = ''
  }
  window.__chartLeave = function (rect) {
    const svg = rect.ownerSVGElement; if (!svg) return
    ;['.cx-line', '.cx-dot', '.cx-tip'].forEach(s => { const e = svg.querySelector(s); if (e) e.style.display = 'none' })
  }
}

function useProductImages(asin, primaryUrl) {
  return primaryUrl ? [primaryUrl] : []
}

export default function ProductModal({ deal, onClose }) {
  const [slide, setSlide] = useState(0)
  const [lightbox, setLightbox] = useState(false)
  const [copied, setCopied] = useState(false)
  const { isMobile, width } = useBreakpoint()
  const isStacked = width < 1100
  const images = useProductImages(deal?.asin, deal?.image_url)
  const touchStartX = useRef(null)
  const touchStartY = useRef(null)

  // Detaildaten (Urteil, Chart-SVG, Preis-Eckdaten, Wunschpreis) — dieselbe
  // Quelle wie die SSR-Preisseite, damit das Modal exakt dasselbe zeigt.
  const [detail, setDetail]       = useState(null)
  const [detailErr, setDetailErr] = useState(false)
  // Zeitraum-Umschalter für den Chart (90 Tage / 1 Jahr / Gesamt) — identisch
  // zur SSR-Preisseite (/preis/{asin}), siehe main.py _chart_windows.
  const [chartWindow, setChartWindow] = useState('90')
  // Preisalarm-Formular direkt im Modal (kein Wegnavigieren).
  const [alarmEmail, setAlarmEmail] = useState('')
  const [alarmPrice, setAlarmPrice] = useState('')
  const [alarmState, setAlarmState] = useState('idle') // idle | sending | ok | error
  const [alarmMsg, setAlarmMsg]     = useState('')

  // Beim Öffnen eines Produkts Details laden und Formularzustand zurücksetzen.
  useEffect(() => {
    setAlarmState('idle'); setAlarmMsg(''); setAlarmEmail(''); setAlarmPrice(''); setChartWindow('90')
    if (!deal?.asin) return
    let cancelled = false
    setDetail(null); setDetailErr(false)
    api.productDetail(deal.asin)
      .then(d => { if (!cancelled) { setDetail(d); if (d?.suggested_target != null && d.suggested_target !== '') setAlarmPrice(String(d.suggested_target)) } })
      .catch(() => { if (!cancelled) setDetailErr(true) })
    return () => { cancelled = true }
  }, [deal?.asin])

  const submitAlarm = async e => {
    e.preventDefault()
    if (alarmState === 'sending') return
    setAlarmState('sending'); setAlarmMsg('')
    const res = await api.setAlarm(deal.asin, alarmEmail.trim(), alarmPrice)
    setAlarmState(res.ok ? 'ok' : 'error')
    setAlarmMsg(res.message)
  }

  // Swipe-down or swipe-left on details panel → close modal
  const handleDetailTouchStart = e => {
    touchStartX.current = e.touches[0].clientX
    touchStartY.current = e.touches[0].clientY
  }
  const handleDetailTouchEnd = e => {
    if (touchStartX.current === null) return
    const dx = e.changedTouches[0].clientX - touchStartX.current
    const dy = e.changedTouches[0].clientY - touchStartY.current
    if (dy > 60 || (dx < -60 && Math.abs(dy) < 40)) onClose()
    touchStartX.current = null
    touchStartY.current = null
  }

  // Lightbox swipe handlers
  const lbSwipeX = useRef(null)
  const lbSwipeY = useRef(null)
  const lbEdgeSwipe = useRef(false)
  const handleLbTouchStart = e => {
    lbSwipeX.current = e.touches[0].clientX
    lbSwipeY.current = e.touches[0].clientY
    lbEdgeSwipe.current = e.touches[0].clientX < 40  // left-edge back gesture
  }
  const handleLbTouchEnd = e => {
    if (lbSwipeX.current === null) return
    const dx = e.changedTouches[0].clientX - lbSwipeX.current
    const dy = e.changedTouches[0].clientY - lbSwipeY.current
    if (lbEdgeSwipe.current && dx > 40 && Math.abs(dy) < 60) { setLightbox(false) }  // edge swipe right → back to modal
    else if (dy > 60 || (Math.abs(dx) < 40 && dy > 30)) { setLightbox(false) }        // swipe down → close
    else if (dx < -40 && Math.abs(dy) < 40) setSlide(s => (s + 1) % images.length)   // swipe left → next
    else if (dx > 40  && Math.abs(dy) < 40) setSlide(s => (s - 1 + images.length) % images.length) // swipe right → prev
    lbSwipeX.current = null
    lbSwipeY.current = null
    lbEdgeSwipe.current = false
  }

  const disc    = deal ? discount(deal.current_price, deal.original_price) : 0
  const cartUrl = deal
    ? `https://www.amazon.de/gp/aws/cart/add.html?ASIN.1=${deal.asin}&Quantity.1=1&tag=snagga-21`
    : ''
  const reviewUrl = deal ? `https://www.amazon.de/product-reviews/${deal.asin}` : ''

  useEffect(() => { setSlide(0); setLightbox(false) }, [deal?.asin])

  const handleKey = useCallback(e => {
    if (e.key === 'Escape') { if (lightbox) setLightbox(false); else onClose() }
    if (e.key === 'ArrowRight') setSlide(s => (s + 1) % Math.max(images.length, 1))
    if (e.key === 'ArrowLeft')  setSlide(s => (s - 1 + Math.max(images.length, 1)) % Math.max(images.length, 1))
  }, [onClose, images.length, lightbox])

  useEffect(() => {
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [handleKey])

  const handleShare = async () => {
    const result = await shareOrCopy(deal)
    if (result === 'copied') {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleTouchStart = e => { touchStartX.current = e.touches[0].clientX }
  const handleTouchEnd   = e => {
    if (touchStartX.current === null || images.length <= 1) return
    const dx = e.changedTouches[0].clientX - touchStartX.current
    if (Math.abs(dx) > 40) {
      if (dx < 0) setSlide(s => (s + 1) % images.length)
      else        setSlide(s => (s - 1 + images.length) % images.length)
    }
    touchStartX.current = null
  }

  if (!deal) return null
  const currentImg = images[slide] || null

  return (
    <>
    {/* ── LIGHTBOX ── */}
    {lightbox && currentImg && (
      <div
        onClick={() => setLightbox(false)}
        onTouchStart={handleLbTouchStart}
        onTouchEnd={handleLbTouchEnd}
        style={{
          position: 'fixed', inset: 0, zIndex: 600,
          background: 'rgba(0,0,0,0.92)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        {images.length > 1 && (
          <button
            onClick={e => { e.stopPropagation(); setSlide(s => (s - 1 + images.length) % images.length) }}
            style={{ ...arrowStyle('left'), zIndex: 10, background: 'rgba(255,255,255,0.12)', borderColor: 'rgba(255,255,255,0.2)', color: '#fff', position: 'fixed', left: 16 }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent)'; e.currentTarget.style.borderColor = 'var(--accent)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.12)'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.2)' }}
          >‹</button>
        )}
        <img
          src={currentImg}
          alt={deal.name}
          onClick={e => e.stopPropagation()}
          style={{ maxWidth: '90vw', maxHeight: '90vh', objectFit: 'contain', userSelect: 'none' }}
          draggable={false}
        />
        {images.length > 1 && (
          <button
            onClick={e => { e.stopPropagation(); setSlide(s => (s + 1) % images.length) }}
            style={{ ...arrowStyle('right'), zIndex: 10, background: 'rgba(255,255,255,0.12)', borderColor: 'rgba(255,255,255,0.2)', color: '#fff', position: 'fixed', right: 16 }}
            onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent)'; e.currentTarget.style.borderColor = 'var(--accent)' }}
            onMouseLeave={e => { e.currentTarget.style.background = 'rgba(255,255,255,0.12)'; e.currentTarget.style.borderColor = 'rgba(255,255,255,0.2)' }}
          >›</button>
        )}
        <button
          onClick={() => setLightbox(false)}
          style={{ position: 'fixed', top: 20, right: 20, background: 'none', border: 'none', fontSize: 32, color: '#fff', cursor: 'pointer', lineHeight: 1, zIndex: 10 }}
        >×</button>
        {images.length > 1 && (
          <div style={{ position: 'fixed', bottom: 20, left: '50%', transform: 'translateX(-50%)', display: 'flex', gap: 8 }}>
            {images.map((_, i) => (
              <div key={i} onClick={e => { e.stopPropagation(); setSlide(i) }}
                style={{ width: 8, height: 8, borderRadius: '50%', background: i === slide ? '#fff' : 'rgba(255,255,255,0.35)', cursor: 'pointer', transition: 'background 0.2s' }} />
            ))}
          </div>
        )}
      </div>
    )}
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 500,
        background: 'rgba(31,30,29,0.48)', backdropFilter: 'blur(8px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: isMobile ? 0 : isStacked ? 16 : 24,
      }}
    >
      <div
        onClick={e => e.stopPropagation()}
        style={{
          background: 'var(--bg-card)',
          width: '100%',
          maxWidth: isStacked ? '100%' : 1600,
          height: isMobile ? '100dvh' : 'auto',
          maxHeight: isMobile ? '100dvh' : '95vh',
          display: isStacked ? 'flex' : 'grid',
          flexDirection: 'column',
          gridTemplateColumns: '1.2fr 0.8fr',
          gridTemplateRows: 'auto auto',
          overflowY: 'auto',
          position: 'relative',
          boxShadow: '0 30px 70px rgba(0,0,0,0.2)',
        }}
      >
        {/* Share */}
        <button
          onClick={handleShare}
          title={copied ? 'Link kopiert!' : 'Deal teilen'}
          style={{
            position: 'absolute', top: 18, right: 62, zIndex: 20,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 36, height: 36, borderRadius: '50%',
            background: 'none', border: 'none', cursor: 'pointer',
            color: copied ? 'var(--accent)' : 'var(--text)', transition: 'background 0.15s, color 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-img)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'none' }}
        >
          {copied ? (
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="20 6 9 17 4 12"/>
            </svg>
          ) : (
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
            </svg>
          )}
        </button>

        {/* Close */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute', top: 18, right: 20, zIndex: 20,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            width: 36, height: 36, borderRadius: '50%',
            background: 'none', border: 'none', cursor: 'pointer',
            color: 'var(--text)', transition: 'background 0.15s, color 0.15s',
          }}
          onMouseEnter={e => { e.currentTarget.style.background = 'var(--bg-img)'; e.currentTarget.style.color = 'var(--accent)' }}
          onMouseLeave={e => { e.currentTarget.style.background = 'none'; e.currentTarget.style.color = 'var(--text)' }}
        >
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/>
          </svg>
        </button>

        {/* ── LEFT TOP: Gallery ── */}
        <div
          style={{
            background: 'var(--bg-img)',
            padding: isMobile ? '48px 24px 20px' : isStacked ? '40px 32px 20px' : '19px 40px 19px',
            display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
            borderRight: isStacked ? 'none' : '1px solid var(--border)',
            borderBottom: isStacked ? '1px solid var(--border)' : 'none',
            gridColumn: isStacked ? 'auto' : '1', gridRow: isStacked ? 'auto' : '1',
          }}
        >
          <div
            onTouchStart={handleTouchStart}
            onTouchEnd={handleTouchEnd}
            style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', minHeight: isMobile ? 220 : isStacked ? 280 : 450 }}
          >
            {images.length > 1 && (
              <button
                onClick={() => setSlide(s => (s - 1 + images.length) % images.length)}
                style={arrowStyle('left')}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent)'; e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = '#fff' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text)' }}
              >‹</button>
            )}
            {currentImg ? (
              <img
                src={currentImg} alt={deal.name}
                onClick={() => setLightbox(true)}
                style={{ maxWidth: '100%', maxHeight: isMobile ? 200 : 450, objectFit: 'contain', cursor: 'zoom-in' }}
                draggable={false}
              />
            ) : (
              <div style={{ fontSize: 60, color: 'var(--border)' }}>📦</div>
            )}
            {images.length > 1 && (
              <button
                onClick={() => setSlide(s => (s + 1) % images.length)}
                style={arrowStyle('right')}
                onMouseEnter={e => { e.currentTarget.style.background = 'var(--accent)'; e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.color = '#fff' }}
                onMouseLeave={e => { e.currentTarget.style.background = 'var(--bg-card)'; e.currentTarget.style.borderColor = 'var(--border)'; e.currentTarget.style.color = 'var(--text)' }}
              >›</button>
            )}
          </div>

          {images.length > 1 && (
            <div className="no-scroll" style={{ display: 'flex', gap: 12, justifyContent: 'center', marginTop: 28, overflowX: 'auto' }}>
              {images.map((url, i) => (
                <button
                  key={i}
                  onClick={() => setSlide(i)}
                  style={{
                    width: 64, height: 64, background: 'var(--bg-card)', padding: 4, flexShrink: 0,
                    border: `1px solid ${i === slide ? 'var(--accent)' : 'var(--border)'}`,
                    boxShadow: i === slide ? '0 0 0 1px var(--accent)' : 'none',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    transition: 'all 0.15s', cursor: 'pointer',
                  }}
                >
                  <img src={url} alt="" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* ── RIGHT TOP: Titel · Preis · Stats · CTA ──
             Eigene Grid-Zelle (nur Zeile 1, nicht spannend) mit
             justifyContent:'space-between' — dadurch sitzt der CTA-Button IMMER
             an der Unterkante von Zeile 1, unabhängig von der Titellänge, weil
             Grid diese Zelle automatisch auf die Höhe der Bildspalte streckt.
             Das ersetzt fest verdrahtete Pixel-Werte, die nur für eine
             bestimmte Titellänge stimmten. */}
        <div
          onTouchStart={isStacked ? handleDetailTouchStart : undefined}
          onTouchEnd={isStacked ? handleDetailTouchEnd : undefined}
          style={{
            padding: isMobile ? '28px 24px 40px' : isStacked ? '28px 44px 40px' : '28px 44px 0px',
            display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
            // Auf Mobile/Tablet (gestapelt) KEIN eigener Scrollbereich → das ganze
            // Modal scrollt als Einheit (statt schmalem inneren Scroll).
            overflowY: isStacked ? 'visible' : 'auto',
            minWidth: 0,
            gridColumn: isStacked ? 'auto' : '2', gridRow: isStacked ? 'auto' : '1',
          }}
        >
          <div>
            {/* Brand */}
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 1.5, color: 'var(--muted)', fontWeight: 600, marginBottom: 10 }}>
              {deal.brand || deal.category}
            </div>

            {/* Title */}
            <h2 style={{ fontSize: isMobile ? 20 : 19, fontWeight: 700, lineHeight: 1.35, color: 'var(--text)', paddingRight: isMobile ? 0 : 32 }}>
              {deal.name}
            </h2>
          </div>

          {/* CTA + Prices + Stats */}
          <div>
            {/* Prices */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20, flexWrap: 'wrap', marginTop: 24 }}>
              <span style={{ fontSize: isMobile ? 28 : 34, fontWeight: 700, color: 'var(--text)' }}>
                {fmtPrice(deal.current_price)}
              </span>
              {deal.original_price > deal.current_price && (
                <span
                  title="Durchschnittspreis der letzten 6 Monate"
                  style={{ fontSize: 16, textDecoration: 'line-through', color: 'var(--muted)', cursor: 'help' }}
                >
                  {fmtPrice(deal.original_price)}
                </span>
              )}
              {disc > 0 && (
                <div
                  title={`–${disc}% verglichen mit dem Durchschnittspreis der letzten 6 Monate`}
                  style={{ background: 'var(--accent)', color: '#fff', padding: '3px 9px', fontSize: 12, fontWeight: 600, letterSpacing: 0.5, cursor: 'help' }}
                >
                  –{disc}%
                </div>
              )}
            </div>

            {/* Stats */}
            <div style={{ display: 'flex', gap: 24, marginBottom: 24, fontSize: 13, alignItems: 'flex-start', flexWrap: 'wrap' }}>
              {deal.prime && (
                <div>
                  <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 600, letterSpacing: 0.5, marginBottom: 3 }}>VERSAND</div>
                  <div style={{ fontWeight: 600, color: '#00A8E0' }}>Prime</div>
                </div>
              )}
              {deal.rating > 0 && (
                <div>
                  <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 600, letterSpacing: 0.5, marginBottom: 3 }}>BEWERTUNG</div>
                  <div style={{ fontWeight: 600, color: 'var(--text)' }}>
                    {deal.rating.toFixed(1)} <span style={{ color: '#F5A623' }}>★</span>
                  </div>
                </div>
              )}
              {fmtReviews(deal.reviews) && (
                <div>
                  <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 600, letterSpacing: 0.5, marginBottom: 3 }}>REVIEWS</div>
                  <div style={{ fontWeight: 600, color: 'var(--text)' }}>{fmtReviews(deal.reviews)}</div>
                </div>
              )}
              {detail?.last_checked && (() => { const age = fmtAge(detail.last_checked); return age ? (
                <div style={{ marginLeft: 'auto' }}>
                  <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 600, letterSpacing: 0.5, marginBottom: 3 }}>AKTUALISIERT</div>
                  <div style={{ fontWeight: 600, color: AGE_COLORS[age.level] }}>{age.text}</div>
                </div>
              ) : null })()}
            </div>

            <p style={{ fontSize: 12, color: 'var(--muted)', lineHeight: 1.5, marginBottom: 12 }}>
              * Affiliate-Hinweis: Als Amazon-Partner verdienen wir an qualifizierten Käufen —
              für dich entstehen keine Mehrkosten. Der angezeigte Preis kann abweichen;
              massgeblich ist der Preis bei Amazon zum Kaufzeitpunkt.
            </p>
            <a
              href={cartUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
                background: 'var(--accent)', color: '#fff',
                padding: '16px 28px', fontSize: 14, fontWeight: 600,
                textDecoration: 'none', transition: 'filter 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.filter = 'brightness(0.9)'}
              onMouseLeave={e => e.currentTarget.style.filter = ''}
            >
              Zum Angebot bei Amazon
            </a>
          </div>
        </div>

        {/* ── RIGHT BOTTOM: Preisalarm ──
             Eigene Grid-Zelle (Zeile 2, wie die Preisverlauf-Zelle links) —
             beide Zellen beginnen an derselben Zeilengrenze, dadurch stimmen
             ihre Oberkanten automatisch überein, ganz ohne Pixel-Tuning. */}
        <div style={{
          gridColumn: isStacked ? 'auto' : '2', gridRow: isStacked ? 'auto' : '2',
          padding: isMobile ? '0 24px 40px' : isStacked ? '0 44px 40px' : '18px 44px 24px',
        }}>
          {/* Unsichtbarer Platzhalter in exakt der Höhe von Label + Zeitraum-Tabs
              links, damit die Alarm-Box IMMER auf Höhe des Chart-Bilds beginnt
              (nicht auf Höhe von Label/Tabs) — durch Wiederverwendung derselben
              Komponenten bleibt das robust, auch wenn sich deren Höhe mal ändert. */}
          {!isStacked && (
            <div style={{ visibility: 'hidden' }} aria-hidden="true">
              <div style={sectionLabel}>Preisverlauf</div>
              {detail?.has_real_history && detail.chart_svg_90 && <ChartTabs value={chartWindow} onChange={() => {}} />}
            </div>
          )}
          <div style={{
            borderTop: '1px solid var(--border)', borderLeft: '4px solid var(--accent)',
            background: 'var(--bg-img)', padding: '14px 20px 14px 18px',
          }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)', marginBottom: 6 }}>🔔 Preisalarm setzen</div>
            {alarmState === 'ok' ? (
              <p style={{ fontSize: 14, color: '#1E7A3C', lineHeight: 1.5 }}>✅ {alarmMsg}</p>
            ) : (
              <form onSubmit={submitAlarm}>
                <p style={{ fontSize: 13, color: 'var(--text)', marginBottom: 14, lineHeight: 1.5 }}>
                  Wir schicken dir eine E-Mail, sobald der Preis auf deinen Wunschpreis fällt. Kostenlos, jederzeit abbestellbar.
                </p>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <input
                    type="email" required placeholder="deine@email.de" value={alarmEmail}
                    onChange={e => setAlarmEmail(e.target.value)} aria-label="E-Mail-Adresse"
                    style={{ ...alarmInput, width: '100%' }}
                  />
                  <div style={{ display: 'flex', gap: 10 }}>
                    <input
                      type="number" required min="1" step="0.01" placeholder="Wunschpreis €" value={alarmPrice}
                      onChange={e => setAlarmPrice(e.target.value)} aria-label="Wunschpreis in Euro"
                      style={{ ...alarmInput, flex: 1, minWidth: 0 }}
                    />
                    <button
                      type="submit" disabled={alarmState === 'sending'}
                      style={{
                        background: 'var(--accent)', color: '#fff', border: 'none', padding: '0 22px', height: 46,
                        fontSize: 14, fontWeight: 600, cursor: alarmState === 'sending' ? 'default' : 'pointer',
                        opacity: alarmState === 'sending' ? 0.7 : 1, flexShrink: 0,
                      }}
                    >
                      {alarmState === 'sending' ? 'Sende …' : 'Alarm aktivieren'}
                    </button>
                  </div>
                </div>
                {alarmState === 'error' && (
                  <p style={{ fontSize: 13, color: '#8b1a1a', marginTop: 10 }}>{alarmMsg}</p>
                )}
                <p style={{ fontSize: 11, color: 'var(--muted)', marginTop: 12, lineHeight: 1.5 }}>
                  Double-Opt-in: Du bekommst zuerst eine Bestätigungs-Mail. Deine Adresse nutzen wir ausschließlich für diesen Preisalarm.
                </p>
              </form>
            )}
          </div>
        </div>

        {/* ── LEFT BOTTOM: Preis-Eckdaten · Preisverlauf ── */}
        <div
          style={{
            gridColumn: isStacked ? 'auto' : '1', gridRow: isStacked ? 'auto' : '2',
            borderTop: '1px solid var(--border)',
            padding: isMobile ? '24px 24px 40px' : '18px 40px 24px',
            display: 'flex', flexDirection: 'column', gap: 14,
          }}
        >
          {/* Preis-Eckdaten (links, vertikal) + Preisverlauf (rechts) auf gleicher Ebene */}
          <div style={{ display: 'flex', gap: isStacked ? 20 : 36, flexDirection: isStacked ? 'column' : 'row', alignItems: isStacked ? 'stretch' : 'flex-start' }}>
            {/* Preis-Eckdaten */}
            {detail && (
              <div style={{
                display: 'flex', flexDirection: isStacked ? 'row' : 'column',
                flexWrap: 'wrap', gap: isStacked ? 20 : 18,
                minWidth: isStacked ? 'auto' : 150, flexShrink: 0,
              }}>
                {[['Aktueller Preis', detail.current_price], ['Allzeittief', detail.atl], ['Ø 90 Tage', detail.avg90], ['Ø 180 Tage', detail.avg180]]
                  .filter(([, v]) => v > 0)
                  .map(([label, v]) => (
                    <div key={label}>
                      <div style={{ ...sectionLabel, marginBottom: 4 }}>{label}</div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>{fmtPrice(v)}</div>
                    </div>
                  ))}
              </div>
            )}

            {/* Preisverlauf */}
            <div style={{ flex: 1, minWidth: 0, width: isStacked ? '100%' : 'auto' }}>
              <div style={sectionLabel}>Preisverlauf</div>
              {!detail && !detailErr && (
                <div style={{ height: 120, display: 'flex', alignItems: 'center', color: 'var(--muted)', fontSize: 13 }}>Lädt …</div>
              )}
              {detailErr && (
                <p style={{ fontSize: 13, color: 'var(--muted)' }}>Preisverlauf konnte gerade nicht geladen werden.</p>
              )}
              {detail && (detail.has_real_history && detail.chart_svg_90
                ? <div>
                    <ChartTabs value={chartWindow} onChange={setChartWindow} />
                    <div
                      style={{ background: '#fff', border: '1px solid var(--border)', padding: '14px 12px 8px', maxWidth: isStacked ? '100%' : 720 }}
                      dangerouslySetInnerHTML={{ __html: CHART_SVG_BY_WINDOW[chartWindow](detail) || detail.chart_svg_90 }}
                    />
                  </div>
                : <p style={{ fontSize: 13, color: 'var(--muted)' }}>Der geprüfte Preisverlauf für dieses Produkt wird gerade aufgebaut — schau bald wieder vorbei.</p>
              )}
            </div>
          </div>

          {/* Dauerhafte, teilbare Preisseite (SEO) */}
          <a
            href={`https://www.snagga.de/preis/${deal.asin}`}
            target="_blank" rel="noopener noreferrer"
            style={{ fontSize: 12, color: 'var(--muted)', textDecoration: 'underline', display: 'inline-flex', alignItems: 'center', gap: 5 }}
          >
            Dauerhafte Preisseite öffnen
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12,5 19,12 12,19"/>
            </svg>
          </a>
        </div>
      </div>
    </div>
    </>
  )
}

const sectionLabel = {
  fontSize: 11, textTransform: 'uppercase', letterSpacing: 1.5,
  color: 'var(--muted)', fontWeight: 600, marginBottom: 12,
}

// Zeitraum-Umschalter für den Preisverlauf-Chart — identisch zur SSR-Preisseite
// (main.py: _chart_windows / .chart-tab CSS), damit das Modal exakt dasselbe zeigt.
const CHART_WINDOWS = [['90', '90 Tage'], ['365', '1 Jahr'], ['full', 'Gesamt']]
const CHART_SVG_BY_WINDOW = {
  '90':  d => d.chart_svg_90,
  '365': d => d.chart_svg,
  'full': d => d.chart_svg_full,
}

function ChartTabs({ value, onChange }) {
  return (
    <div style={{ display: 'flex', gap: 8, marginBottom: 14 }}>
      {CHART_WINDOWS.map(([key, label]) => {
        const active = key === value
        return (
          <button
            key={key} type="button" onClick={() => onChange(key)}
            style={{
              background: active ? 'var(--accent)' : 'none',
              border: `1px solid ${active ? 'var(--accent)' : 'var(--border)'}`,
              color: active ? '#fff' : 'var(--accent)',
              padding: '7px 16px', fontSize: 13, fontFamily: 'inherit',
              fontWeight: active ? 600 : 400, cursor: 'pointer',
            }}
          >
            {label}
          </button>
        )
      })}
    </div>
  )
}

const alarmInput = {
  border: '1.5px solid color-mix(in srgb, var(--text) 32%, transparent)',
  background: 'var(--bg-card)', color: 'var(--text)',
  padding: '0 14px', height: 46, fontSize: 14, fontFamily: 'inherit',
}

function arrowStyle(side) {
  return {
    position: 'absolute', top: '50%', transform: 'translateY(-50%)',
    [side]: 8, width: 44, height: 44, borderRadius: '50%',
    background: 'var(--bg-card)', border: '1px solid var(--border)',
    color: 'var(--text)', fontSize: 22,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    boxShadow: '0 4px 12px rgba(0,0,0,0.05)', cursor: 'pointer', zIndex: 5,
    transition: 'all 0.2s',
  }
}
