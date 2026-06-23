import React, { useState, useEffect, useCallback, useRef } from 'react'
import PriceChart from './PriceChart.jsx'
import { fmtPrice, discount, dealLabel } from '../utils.js'
import { useBreakpoint } from '../hooks/useBreakpoint.js'

/* Versucht bis zu 5 Bilder pro ASIN zu laden (Amazon .01–.05) */
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
      img.onload = () => {
        loaded[i] = url
        settled++
        if (settled === candidates.length) setImages(loaded.filter(Boolean))
      }
      img.onerror = () => {
        settled++
        if (settled === candidates.length) setImages(loaded.filter(Boolean))
      }
      img.src = url
    })
  }, [asin])

  return images.length > 0 ? images : (primaryUrl ? [primaryUrl] : [])
}

export default function ProductModal({ deal, onClose, saved, onSave }) {
  const [slide, setSlide]           = useState(0)
  const [copied, setCopied]         = useState(false)
  const [lightboxOpen, setLightbox] = useState(false)

  const openLightbox = () => {
    setLightbox(true)
    window.history.pushState({ snagga: 'lightbox' }, '')
  }
  const closeLightbox = () => {
    if (window.history.state?.snagga === 'lightbox') window.history.back()
    else setLightbox(false)
  }
  const { isMobile, isTablet, isDesktop } = useBreakpoint()
  const isVertical = !isDesktop   // Mobile + Tablet: column-Layout
  const images     = useProductImages(deal?.asin, deal?.image_url)
  const imgAreaRef = useRef(null)
  const touchStartX = useRef(null)

  const shareUrl  = deal ? `https://snagga.de/?asin=${deal.asin}` : ''
  const cartUrl   = deal ? `https://www.amazon.de/gp/aws/cart/add.html?ASIN.1=${deal.asin}&Quantity.1=1&tag=snagga-21` : ''
  const reviewUrl = deal ? `https://www.amazon.de/product-reviews/${deal.asin}` : ''

  function handleShare() {
    if (navigator.share) {
      navigator.share({ title: deal.name, url: shareUrl }).catch(() => {})
    } else {
      navigator.clipboard.writeText(shareUrl).then(() => {
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      })
    }
  }

  /* Swipe */
  function handleTouchStart(e) { touchStartX.current = e.touches[0].clientX }
  function handleTouchEnd(e) {
    if (touchStartX.current === null || images.length <= 1) return
    const dx = e.changedTouches[0].clientX - touchStartX.current
    if (Math.abs(dx) > 40) {
      if (dx < 0) setSlide(s => (s + 1) % images.length)
      else         setSlide(s => (s - 1 + images.length) % images.length)
    }
    touchStartX.current = null
  }

  const disc  = deal ? discount(deal.current_price, deal.original_price) : 0
  const label = deal ? dealLabel(deal.deal_score) : null

  const handleKey = useCallback(e => {
    if (e.key === 'Escape') { if (lightboxOpen) closeLightbox(); else onClose() }
    if (e.key === 'ArrowRight') setSlide(s => (s + 1) % Math.max(images.length, 1))
    if (e.key === 'ArrowLeft')  setSlide(s => (s - 1 + Math.max(images.length, 1)) % Math.max(images.length, 1))
  }, [onClose, images.length, lightboxOpen])

  useEffect(() => {
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [handleKey])

  // Swipe-Back schliesst Lightbox zuerst, dann den Modal (über DealsPage-Handler)
  useEffect(() => {
    const onPop = () => { if (lightboxOpen) setLightbox(false) }
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [lightboxOpen])

  useEffect(() => { setSlide(0); setLightbox(false) }, [deal?.asin])

  if (!deal) return null

  const currentImg = images[slide] || null
  const imgHeight  = isMobile ? 320 : isTablet ? 500 : 'auto'

  /* ── Lightbox ── */
  const LightboxEl = lightboxOpen && (
    <div
      onClick={() => closeLightbox()}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      style={{ position: 'fixed', inset: 0, zIndex: 2000, background: 'rgba(0,0,0,0.96)',
        display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}
    >
      {/* Counter */}
      {images.length > 1 && (
        <div style={{ position: 'absolute', top: 20, left: '50%', transform: 'translateX(-50%)',
          color: 'rgba(255,255,255,0.55)', fontSize: 12, fontWeight: 500, whiteSpace: 'nowrap', pointerEvents: 'none' }}>
          {slide + 1} / {images.length}
        </div>
      )}
      {/* Close */}
      <button onClick={e => { e.stopPropagation(); closeLightbox() }}
        style={{ position: 'absolute', top: 16, right: 16, width: 36, height: 36, borderRadius: '50%',
          border: '1.5px solid rgba(255,255,255,0.2)', background: 'rgba(255,255,255,0.08)',
          color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg width="12" height="12" viewBox="0 0 10 10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
          <line x1="1" y1="1" x2="9" y2="9"/><line x1="9" y1="1" x2="1" y2="9"/>
        </svg>
      </button>
      {/* Main image */}
      {currentImg && (
        <img src={currentImg} alt={deal.name} onClick={e => e.stopPropagation()}
          style={{ maxWidth: '92%', maxHeight: '72vh', objectFit: 'contain', userSelect: 'none' }} />
      )}
      {/* Arrows */}
      {images.length > 1 && (
        <>
          <button onClick={e => { e.stopPropagation(); setSlide(s => (s - 1 + images.length) % images.length) }}
            style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)',
              width: 42, height: 42, borderRadius: 10, border: '1.5px solid rgba(255,255,255,0.2)',
              background: 'rgba(255,255,255,0.08)', color: '#fff', fontSize: 22,
              display: 'flex', alignItems: 'center', justifyContent: 'center' }}>‹</button>
          <button onClick={e => { e.stopPropagation(); setSlide(s => (s + 1) % images.length) }}
            style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)',
              width: 42, height: 42, borderRadius: 10, border: '1.5px solid rgba(255,255,255,0.2)',
              background: 'rgba(255,255,255,0.08)', color: '#fff', fontSize: 22,
              display: 'flex', alignItems: 'center', justifyContent: 'center' }}>›</button>
        </>
      )}
      {/* Thumbnails */}
      {images.length > 1 && (
        <div className="no-scroll" style={{ position: 'absolute', bottom: 20, left: 0, right: 0,
          display: 'flex', gap: 8, justifyContent: 'center', padding: '0 16px', overflowX: 'auto' }}>
          {images.map((url, i) => (
            <button key={i} onClick={e => { e.stopPropagation(); setSlide(i) }}
              style={{ width: 44, height: 44, borderRadius: 6, padding: 2, flexShrink: 0,
                border: `2px solid ${i === slide ? 'var(--orange)' : 'rgba(255,255,255,0.25)'}`,
                background: 'rgba(255,255,255,0.08)', overflow: 'hidden',
                display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <img src={url} alt="" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
            </button>
          ))}
        </div>
      )}
    </div>
  )

  return (
    <>
      {LightboxEl}

      <div
        onClick={onClose}
        style={{
          position: 'fixed', inset: 0, zIndex: 1000,
          background: isVertical ? 'var(--bg-card)' : 'rgba(0,0,0,0.55)',
          display: 'flex', alignItems: isVertical ? 'flex-start' : 'center', justifyContent: 'center',
          padding: isVertical ? 0 : 24,
          backdropFilter: isVertical ? 'none' : 'blur(3px)',
        }}
      >
        {/* Wrapper */}
        <div style={{ position: 'relative', width: '100%', maxWidth: isVertical ? '100%' : 1220 }}
          onClick={e => e.stopPropagation()}>

          {/* Close */}
          <button onClick={onClose} style={{
            position: 'absolute', top: isVertical ? 12 : -14, right: isVertical ? 12 : -14, zIndex: 20,
            width: 32, height: 32, borderRadius: '50%',
            border: '1.5px solid rgba(255,255,255,0.25)',
            background: 'rgba(30,30,30,0.85)',
            color: '#fff', padding: 0,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          }}>
            <svg width="10" height="10" viewBox="0 0 10 10" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
              <line x1="1" y1="1" x2="9" y2="9"/><line x1="9" y1="1" x2="1" y2="9"/>
            </svg>
          </button>

          {/* Modal */}
          <div style={{
            background: 'var(--bg-card)',
            border: isVertical ? 'none' : '1.5px solid var(--border)',
            borderRadius: isVertical ? 0 : 14,
            width: '100%',
            height: isVertical ? '100dvh' : 'auto',
            maxHeight: isVertical ? '100dvh' : '90vh',
            display: 'flex', flexDirection: isVertical ? 'column' : 'row',
            overflow: 'hidden',
          }}>

            {/* ── Bild-Panel ── */}
            <div style={{
              width: isVertical ? '100%' : 600,
              height: isVertical ? imgHeight : 'auto',
              flexShrink: 0,
              background: 'var(--bg-elev2)',
              display: 'flex', flexDirection: 'column',
              position: 'relative',
            }}>
              {/* Hauptbild — Klick öffnet Lightbox */}
              <div
                ref={imgAreaRef}
                onClick={() => currentImg && openLightbox()}
                onTouchStart={handleTouchStart}
                onTouchEnd={handleTouchEnd}
                style={{
                  flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  minHeight: isDesktop ? 420 : 0,
                  padding: isVertical ? 20 : 32,
                  position: 'relative',
                  cursor: currentImg ? 'zoom-in' : 'default',
                  userSelect: 'none',
                }}
              >
                {currentImg ? (
                  <img
                    src={currentImg}
                    alt={deal.name}
                    style={{ maxWidth: '100%', maxHeight: isVertical ? imgHeight - 88 : 420, objectFit: 'contain' }}
                    draggable={false}
                  />
                ) : (
                  <div style={{ fontSize: 56, color: 'var(--border)' }}>📦</div>
                )}

                {/* Pfeile */}
                {images.length > 1 && (
                  <>
                    <button onClick={e => { e.stopPropagation(); setSlide(s => (s - 1 + images.length) % images.length) }} style={arrowBtn('left')}>‹</button>
                    <button onClick={e => { e.stopPropagation(); setSlide(s => (s + 1) % images.length) }} style={arrowBtn('right')}>›</button>
                  </>
                )}
              </div>

              {/* Thumbnails */}
              {images.length > 1 && (
                <div className="no-scroll" style={{
                  display: 'flex', gap: 6, padding: '0 16px 16px',
                  justifyContent: 'center', flexWrap: 'nowrap', overflowX: 'auto',
                }}>
                  {images.map((url, i) => (
                    <button
                      key={i}
                      onClick={() => { setSlide(i); imgAreaRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }}
                      style={{
                        width: 46, height: 46, borderRadius: 6, padding: 3, flexShrink: 0,
                        border: `2px solid ${i === slide ? 'var(--orange)' : 'var(--border)'}`,
                        background: 'var(--bg-card)', overflow: 'hidden',
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        transition: 'border-color 0.15s',
                      }}
                    >
                      <img src={url} alt="" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* ── Info-Panel ── */}
            <div style={{
              flex: 1, padding: '28px 28px 24px',
              display: 'flex', flexDirection: 'column',
              overflowY: 'auto',
              position: 'relative',
            }}>
              {/* Favourite */}
              <button
                onClick={() => onSave?.(deal.asin)}
                style={{
                  position: 'absolute', top: 28, right: 28,
                  width: 34, height: 34, borderRadius: 8,
                  border: `1.5px solid ${saved ? 'var(--star-saved)' : 'var(--border)'}`,
                  background: saved ? 'var(--orange-soft)' : 'var(--bg-elev2)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  transition: 'all 0.15s',
                }}
              >
                <svg width="18" height="18" viewBox="0 0 24 24"
                  fill={saved ? 'var(--star-saved)' : 'none'}
                  stroke={saved ? 'var(--star-saved)' : 'var(--muted)'}
                  strokeWidth="1.8" strokeLinejoin="round">
                  <polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/>
                </svg>
              </button>

              <span style={{ fontSize: 12, color: 'var(--muted)', fontWeight: 500, marginBottom: 6, display: 'block', paddingRight: 44 }}>
                {deal.brand || deal.category}
              </span>
              <h2 style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)', lineHeight: 1.4, margin: '0 0 6px', paddingRight: 44 }}>
                {deal.name}
              </h2>
              <span style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 18, display: 'block' }}>{deal.category}</span>

              {/* Preis */}
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 6, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 30, fontWeight: 800, letterSpacing: '-1px', color: 'var(--text)' }}>
                  {fmtPrice(deal.current_price)}
                </span>
                {deal.original_price > deal.current_price && (
                  <span style={{ fontSize: 15, color: 'var(--muted)', textDecoration: 'line-through' }}>
                    {fmtPrice(deal.original_price)}
                  </span>
                )}
                {disc > 0 && (
                  <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--orange)', background: 'var(--orange-soft)', padding: '3px 8px', borderRadius: 5 }}>
                    –{disc}%
                  </span>
                )}
              </div>

              {/* Prime + Deal-Label */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, flexWrap: 'wrap' }}>
                {deal.prime && (
                  <span style={{ fontSize: 11, color: 'var(--blue)', fontWeight: 700, letterSpacing: 0.5 }}>✦ Prime</span>
                )}
                {label && (
                  <div style={{ fontSize: 10.5, fontWeight: 700, padding: '3px 9px', borderRadius: 5, background: label.bg, color: label.color, border: label.border || 'none' }}>
                    {label.text}
                  </div>
                )}
              </div>

              <div style={{ height: 1, background: 'var(--border)', margin: '0 0 14px' }} />

              {/* Chart */}
              {deal.price_history?.length > 1 && (
                <div style={{ marginBottom: 18 }}>
                  <PriceChart prices={deal.price_history} avgPrice={deal.avg_price} allTimeLow={deal.all_time_low} asin={deal.asin} />
                </div>
              )}

              {/* Kennzahlen */}
              <div style={{ display: 'flex', gap: 20, marginBottom: 24 }}>
                {deal.rating && (
                  <a href={reviewUrl} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none' }}>
                    <Stat label="Bewertung" value={`★ ${Number(deal.rating).toFixed(1)}`} clickable />
                  </a>
                )}
                {deal.reviews && (
                  <a href={reviewUrl} target="_blank" rel="noopener noreferrer" style={{ textDecoration: 'none' }}>
                    <Stat label="Reviews" value={deal.reviews.toLocaleString('de')} clickable />
                  </a>
                )}
              </div>

              {/* Buttons */}
              <div style={{ display: 'flex', gap: 8, marginTop: 'auto' }}>
                {/* Warenkorb */}
                <a href={cartUrl} target="_blank" rel="noopener noreferrer"
                  style={{
                    flex: isMobile ? '0 0 auto' : '1 1 0',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
                    background: 'var(--orange)', color: '#fff',
                    borderRadius: 10, padding: isMobile ? '12px 14px' : '12px 16px',
                    fontSize: 13.5, fontWeight: 700, transition: 'opacity 0.15s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.opacity = '0.85'}
                  onMouseLeave={e => e.currentTarget.style.opacity = '1'}
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/>
                    <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
                  </svg>
                  {!isMobile && 'In den Warenkorb'}
                </a>

                {/* Zum Produkt */}
                <a href={deal.affiliate_url} target="_blank" rel="noopener noreferrer"
                  style={{
                    flex: '1 1 0', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    background: 'var(--text)', color: 'var(--bg-card)',
                    borderRadius: 10, padding: '12px 16px',
                    fontSize: 13.5, fontWeight: 700, transition: 'opacity 0.15s',
                  }}
                  onMouseEnter={e => e.currentTarget.style.opacity = '0.82'}
                  onMouseLeave={e => e.currentTarget.style.opacity = '1'}
                >
                  Zum Produkt
                </a>

                {/* Teilen */}
                <button onClick={handleShare} title={copied ? 'Link kopiert!' : 'Deal teilen'}
                  style={{
                    width: 46, flexShrink: 0, borderRadius: 10, padding: '12px',
                    border: copied ? '1.5px solid var(--orange)' : 'none',
                    background: copied ? 'var(--orange-soft)' : 'var(--blue-soft)',
                    color: copied ? 'var(--orange)' : 'var(--blue)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    transition: 'all 0.15s',
                  }}
                >
                  {copied ? (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
                      <polyline points="20,6 9,17 4,12"/>
                    </svg>
                  ) : (
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
                      <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/>
                      <line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
                    </svg>
                  )}
                </button>
              </div>

              <p style={{ fontSize: 10.5, color: 'var(--muted)', textAlign: 'center', marginTop: 10, lineHeight: 1.4 }}>
                * Als Amazon-Partner verdiene ich an qualifizierten Käufen.
              </p>
            </div>
          </div>{/* Modal */}
        </div>{/* Wrapper */}
      </div>{/* Backdrop */}
    </>
  )
}

function Stat({ label, value, clickable = false }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 500, marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 13, color: clickable ? 'var(--orange)' : 'var(--text)', fontWeight: 600,
        textDecoration: clickable ? 'underline' : 'none', textDecorationColor: 'var(--orange-border)',
        cursor: clickable ? 'pointer' : 'default' }}>{value}</div>
    </div>
  )
}

function arrowBtn(side) {
  return {
    position: 'absolute', top: '50%', transform: 'translateY(-50%)',
    [side]: 8,
    width: 28, height: 28, borderRadius: 7,
    border: '1.5px solid var(--border)',
    background: 'var(--bg-card)',
    color: 'var(--text)', fontSize: 18, lineHeight: 1,
    display: 'flex', alignItems: 'center', justifyContent: 'center',
    zIndex: 5, transition: 'background 0.12s',
  }
}
