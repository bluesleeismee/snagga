import React, { useState, useEffect, useCallback, useRef } from 'react'
import { fmtPrice, discount, fmtAge, AGE_COLORS } from '../utils.js'
import { useBreakpoint } from '../hooks/useBreakpoint.js'

function useProductImages(asin, primaryUrl) {
  const [images, setImages] = useState([])
  useEffect(() => {
    if (!asin) return
    const candidates = [1, 2, 3, 4, 5].map(
      n => `https://images-na.ssl-images-amazon.com/images/P/${asin}.0${n}.LZZZZZZZ.jpg`
    )
    const loaded = []
    let settled = 0
    candidates.forEach((url, i) => {
      const img = new Image()
      img.onload  = () => { loaded[i] = url; settled++; if (settled === candidates.length) setImages(loaded.filter(Boolean)) }
      img.onerror = () => { settled++;             if (settled === candidates.length) setImages(loaded.filter(Boolean)) }
      img.src = url
    })
  }, [asin])
  return images.length > 0 ? images : (primaryUrl ? [primaryUrl] : [])
}

export default function ProductModal({ deal, onClose }) {
  const [slide, setSlide] = useState(0)
  const [lightbox, setLightbox] = useState(false)
  const { isMobile, width } = useBreakpoint()
  const isStacked = width < 1100
  const images = useProductImages(deal?.asin, deal?.image_url)
  const touchStartX = useRef(null)
  const touchStartY = useRef(null)

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
          maxWidth: isStacked ? '100%' : 1280,
          height: isMobile ? '100dvh' : 'auto',
          maxHeight: isMobile ? '100dvh' : '95vh',
          display: isStacked ? 'flex' : 'grid',
          flexDirection: 'column',
          gridTemplateColumns: '1.2fr 0.8fr',
          overflowY: 'auto',
          position: 'relative',
          boxShadow: '0 30px 70px rgba(0,0,0,0.2)',
        }}
      >
        {/* Close */}
        <button
          onClick={onClose}
          style={{ position: 'absolute', top: 20, right: 20, zIndex: 20, background: 'none', border: 'none', fontSize: 28, color: 'var(--text)', lineHeight: 1, transition: 'color 0.15s' }}
          onMouseEnter={e => e.currentTarget.style.color = 'var(--accent)'}
          onMouseLeave={e => e.currentTarget.style.color = 'var(--text)'}
        >×</button>

        {/* ── LEFT: Gallery ── */}
        <div
          style={{
            background: 'var(--bg-img)',
            padding: isMobile ? '48px 24px 20px' : isStacked ? '40px 32px 20px' : '48px 48px 32px',
            display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
            borderRight: isStacked ? 'none' : '1px solid var(--border)',
            borderBottom: isStacked ? '1px solid var(--border)' : 'none',
          }}
        >
          <div
            onTouchStart={handleTouchStart}
            onTouchEnd={handleTouchEnd}
            style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative', minHeight: isMobile ? 220 : isStacked ? 280 : 360 }}
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
                style={{ maxWidth: '100%', maxHeight: isMobile ? 200 : 400, objectFit: 'contain', cursor: 'zoom-in' }}
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

        {/* ── RIGHT: Details ── */}
        <div
          onTouchStart={isStacked ? handleDetailTouchStart : undefined}
          onTouchEnd={isStacked ? handleDetailTouchEnd : undefined}
          style={{
            padding: isMobile ? '28px 24px 40px' : '48px 44px',
            display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
            overflowY: 'auto',
          }}
        >
          <div>
            {/* Brand */}
            <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: 1.5, color: 'var(--muted)', fontWeight: 600, marginBottom: 10 }}>
              {deal.brand || deal.category}
            </div>

            {/* Title */}
            <h2 style={{ fontSize: isMobile ? 22 : 28, fontWeight: 700, lineHeight: 1.3, color: 'var(--text)', paddingRight: isMobile ? 0 : 32 }}>
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
                <span style={{ fontSize: 16, textDecoration: 'line-through', color: 'var(--muted)' }}>
                  {fmtPrice(deal.original_price)}
                </span>
              )}
              {disc > 0 && (
                <div style={{ background: 'var(--accent)', color: '#fff', padding: '3px 9px', fontSize: 12, fontWeight: 600, letterSpacing: 0.5 }}>
                  –{disc}%
                </div>
              )}
            </div>

            {/* Stats */}
            {(deal.rating || deal.reviews || deal.prime || deal.last_updated) && (
              <div style={{ display: 'flex', gap: 24, marginBottom: 24, fontSize: 13, alignItems: 'flex-start' }}>
                {deal.rating && (
                  <a href={reviewUrl} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none' }}>
                    <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 600, letterSpacing: 0.5, marginBottom: 3 }}>BEWERTUNG</div>
                    <div style={{ fontWeight: 600, color: 'var(--text)' }}>★ {Number(deal.rating).toFixed(1)}</div>
                  </a>
                )}
                {deal.reviews && (
                  <a href={reviewUrl} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none' }}>
                    <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 600, letterSpacing: 0.5, marginBottom: 3 }}>REVIEWS</div>
                    <div style={{ fontWeight: 600, color: 'var(--text)' }}>{deal.reviews.toLocaleString('de')}</div>
                  </a>
                )}
                {deal.prime && (
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 600, letterSpacing: 0.5, marginBottom: 3 }}>VERSAND</div>
                    <div style={{ fontWeight: 600, color: '#00A8E0' }}>Prime</div>
                  </div>
                )}
                {deal.last_updated && (() => { const age = fmtAge(deal.last_updated); return age ? (
                  <div style={{ marginLeft: 'auto' }}>
                    <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 600, letterSpacing: 0.5, marginBottom: 3 }}>AKTUALISIERT</div>
                    <div style={{ fontWeight: 600, color: AGE_COLORS[age.level] }}>{age.text}</div>
                  </div>
                ) : null })()}
              </div>
            )}

            <a
              href={cartUrl}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
                background: 'var(--accent)', color: '#fff',
                padding: '16px 28px', fontSize: 14, fontWeight: 600,
                textDecoration: 'none', transition: 'filter 0.15s', marginBottom: 10,
              }}
              onMouseEnter={e => e.currentTarget.style.filter = 'brightness(0.9)'}
              onMouseLeave={e => e.currentTarget.style.filter = ''}
            >
              Zum Produkt
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12,5 19,12 12,19"/>
              </svg>
            </a>
            <p style={{ fontSize: 10.5, color: 'var(--muted)', textAlign: 'center', lineHeight: 1.4 }}>
              * Als Amazon-Partner verdienen wir an qualifizierten Käufen.
            </p>
          </div>
        </div>
      </div>
    </div>
    </>
  )
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
