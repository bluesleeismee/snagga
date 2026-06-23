import React, { useState, useEffect, useCallback } from 'react'
import PriceChart from './PriceChart.jsx'
import { fmtPrice, discount, dealLabel } from '../utils.js'

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
  const [slide, setSlide] = useState(0)
  const images = useProductImages(deal?.asin, deal?.image_url)
  const disc = deal ? discount(deal.current_price, deal.original_price) : 0
  const label = deal ? dealLabel(deal.deal_score) : null

  const handleKey = useCallback(e => {
    if (e.key === 'Escape') onClose()
    if (e.key === 'ArrowRight') setSlide(s => (s + 1) % Math.max(images.length, 1))
    if (e.key === 'ArrowLeft')  setSlide(s => (s - 1 + Math.max(images.length, 1)) % Math.max(images.length, 1))
  }, [onClose, images.length])

  useEffect(() => {
    document.addEventListener('keydown', handleKey)
    return () => document.removeEventListener('keydown', handleKey)
  }, [handleKey])

  useEffect(() => { setSlide(0) }, [deal?.asin])

  if (!deal) return null

  const currentImg = images[slide] || null

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(0,0,0,0.55)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24,
        backdropFilter: 'blur(3px)',
      }}
    >
      {/* Wrapper für Modal + Close-Button */}
      <div style={{ position: 'relative', width: '100%', maxWidth: 1220 }} onClick={e => e.stopPropagation()}>

        {/* Close — Kreis, ausserhalb oben rechts */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute', top: -18, right: -18, zIndex: 20,
            width: 36, height: 36, borderRadius: '50%',
            border: '1.5px solid rgba(255,255,255,0.25)',
            background: 'rgba(30,30,30,0.85)',
            color: '#fff', fontSize: 20,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            lineHeight: 1,
            boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
          }}
        >×</button>

        {/* Modal */}
        <div
          style={{
            background: 'var(--bg-card)',
            border: '1.5px solid var(--border)',
            borderRadius: 14,
            width: '100%',
            maxHeight: '90vh',
            display: 'flex', flexDirection: 'row',
            overflow: 'hidden',
          }}
        >

        {/* Linke Seite: Bild + Slideshow */}
        <div style={{
          width: 600, flexShrink: 0,
          background: 'var(--bg-elev2)',
          display: 'flex', flexDirection: 'column',
          position: 'relative',
        }}>
          {/* Hauptbild */}
          <div style={{
            flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
            minHeight: 420, padding: 32, position: 'relative',
          }}>
            {currentImg ? (
              <img
                src={currentImg}
                alt={deal.name}
                style={{ maxWidth: '100%', maxHeight: 420, objectFit: 'contain' }}
              />
            ) : (
              <div style={{ fontSize: 56, color: 'var(--border)' }}>📦</div>
            )}

            {/* Pfeile */}
            {images.length > 1 && (
              <>
                <button onClick={() => setSlide(s => (s - 1 + images.length) % images.length)} style={arrowBtn('left')}>‹</button>
                <button onClick={() => setSlide(s => (s + 1) % images.length)} style={arrowBtn('right')}>›</button>
              </>
            )}
          </div>

          {/* Thumbnails */}
          {images.length > 1 && (
            <div style={{
              display: 'flex', gap: 6, padding: '0 16px 16px',
              justifyContent: 'center', flexWrap: 'wrap',
            }}>
              {images.map((url, i) => (
                <button
                  key={i}
                  onClick={() => setSlide(i)}
                  style={{
                    width: 46, height: 46, borderRadius: 6, padding: 3,
                    border: `2px solid ${i === slide ? 'var(--orange)' : 'var(--border)'}`,
                    background: 'var(--bg-card)',
                    overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    transition: 'border-color 0.15s',
                  }}
                >
                  <img src={url} alt="" style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }} />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Rechte Seite: Info */}
        <div style={{
          flex: 1, padding: '28px 28px 24px',
          display: 'flex', flexDirection: 'column',
          overflowY: 'auto',
        }}>
          {/* Brand */}
          <span style={{ fontSize: 12, color: 'var(--muted)', fontWeight: 500, marginBottom: 6, display: 'block' }}>
            {deal.brand || deal.category}
          </span>

          {/* Name + Save */}
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 6 }}>
            <h2 style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)', lineHeight: 1.4, margin: 0, flex: 1 }}>
              {deal.name}
            </h2>
            <button
              onClick={() => onSave?.(deal.asin)}
              style={{
                flexShrink: 0,
                width: 32, height: 32, borderRadius: 8,
                border: '1.5px solid var(--border)',
                background: 'var(--bg-elev)',
                fontSize: 16, color: saved ? 'var(--orange)' : 'var(--muted)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                marginTop: 2,
              }}
            >{saved ? '★' : '☆'}</button>
          </div>

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

          {deal.prime && (
            <span style={{ fontSize: 11, color: 'var(--blue)', fontWeight: 700, letterSpacing: 0.5, marginBottom: 14, display: 'block' }}>
              ✦ Prime
            </span>
          )}

          {/* Divider */}
          <div style={{ height: 1, background: 'var(--border)', margin: '4px 0 14px' }} />

          {/* Deal-Label + Chart */}
          {deal.price_history?.length > 1 && (
            <div style={{ marginBottom: 18 }}>
              {/* Label über dem Chart */}
              {label && (
                <div style={{
                  display: 'inline-block',
                  fontSize: 10.5, fontWeight: 700, padding: '3px 9px', borderRadius: 5,
                  background: label.bg, color: label.color, border: label.border || 'none',
                  marginBottom: 8,
                }}>
                  {label.text}
                </div>
              )}
              <PriceChart
                prices={deal.price_history}
                avgPrice={deal.avg_price}
                allTimeLow={deal.all_time_low}
                asin={deal.asin}
              />
            </div>
          )}

          {/* Kennzahlen */}
          <div style={{ display: 'flex', gap: 20, marginBottom: 24 }}>
            <Stat label="Allzeit-Tief" value={fmtPrice(deal.all_time_low)} />
            <Stat label="Ø Preis" value={fmtPrice(deal.avg_price)} />
            {deal.rating && <Stat label="Bewertung" value={`★ ${deal.rating}`} />}
            {deal.reviews && <Stat label="Reviews" value={deal.reviews.toLocaleString('de')} />}
          </div>

          {/* CTA */}
          <a
            href={deal.affiliate_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: 'block', textAlign: 'center',
              background: 'var(--text)', color: 'var(--bg-card)',
              borderRadius: 10, padding: '12px 20px',
              fontSize: 14, fontWeight: 700,
              marginTop: 'auto',
              transition: 'opacity 0.15s',
            }}
            onMouseEnter={e => e.currentTarget.style.opacity = '0.82'}
            onMouseLeave={e => e.currentTarget.style.opacity = '1'}
          >
            Zum Deal auf Amazon →
          </a>

          <p style={{ fontSize: 10.5, color: 'var(--muted)', textAlign: 'center', marginTop: 10, lineHeight: 1.4 }}>
            * Als Amazon-Partner verdiene ich an qualifizierten Käufen.
          </p>
        </div>
        </div>{/* Modal inner */}
      </div>{/* Wrapper */}
    </div>
  )
}

function Stat({ label, value }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--muted)', fontWeight: 500, marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 13, color: 'var(--text)', fontWeight: 600 }}>{value}</div>
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
