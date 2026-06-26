import React, { useState, useEffect } from 'react'
import { fmtPrice, discount } from '../utils.js'

export default function DealCard({ deal, onClick }) {
  const [imgError,    setImgError]    = useState(false)
  const [hovered,     setHovered]     = useState(false)
  const [secondImg,   setSecondImg]   = useState(null)
  const disc = discount(deal.current_price, deal.original_price)

  /* Preload second Amazon image variant */
  useEffect(() => {
    if (!deal.asin) return
    const url = `https://images-na.ssl-images-amazon.com/images/P/${deal.asin}.02.LZZZZZZZ.jpg`
    const img = new Image()
    img.onload  = () => setSecondImg(url)
    img.onerror = () => setSecondImg(null)
    img.src = url
  }, [deal.asin])

  const showSecond = hovered && secondImg
  const imgSrc     = showSecond ? secondImg : (deal.image_url || null)

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column',
        cursor: 'pointer', position: 'relative',
        transition: 'transform 0.3s cubic-bezier(0.16,1,0.3,1), box-shadow 0.3s',
        transform:  hovered ? 'translateY(-4px)' : '',
        boxShadow:  hovered ? '0 15px 35px rgba(31,30,29,0.06)' : '',
      }}
    >
      {/* Image area */}
      <div style={{
        background: hovered ? 'var(--bg-img)' : 'var(--bg-card)',
        height: 240,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 24, position: 'relative', overflow: 'hidden',
        transition: 'background 0.25s ease',
      }}>
        {disc > 0 && (
          <div style={{ position: 'absolute', top: 14, left: 14, zIndex: 2, background: 'var(--accent)', color: '#fff', padding: '3px 8px', fontSize: 11, fontWeight: 600, letterSpacing: 0.5 }}>
            –{disc}%
          </div>
        )}
        {imgSrc && !imgError ? (
          <img
            key={imgSrc}
            src={imgSrc}
            alt={deal.name}
            onError={() => setImgError(true)}
            style={{
              maxWidth: '100%', maxHeight: 190, objectFit: 'contain',
              transition: 'transform 0.4s ease, opacity 0.25s ease',
              transform: hovered ? 'scale(1.04)' : 'scale(1)',
            }}
          />
        ) : (
          <div style={{ fontSize: 42, color: 'var(--border)' }}>📦</div>
        )}
      </div>

      {/* Card body */}
      <div style={{ padding: '20px 18px 16px', display: 'flex', flexDirection: 'column', flex: 1 }}>
        <div style={{ fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 1, color: 'var(--muted)', fontWeight: 500, marginBottom: 7 }}>
          {deal.brand || deal.category}
        </div>
        <h3 style={{
          fontSize: 14, fontWeight: 500, lineHeight: 1.45, color: 'var(--text)', marginBottom: 14,
          display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden',
          height: '40px',
        }}>
          {deal.name}
        </h3>

        {/* Price row */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 14 }}>
          <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)' }}>
            {fmtPrice(deal.current_price)}
          </span>
          {deal.original_price > deal.current_price && (
            <span style={{ fontSize: 13, textDecoration: 'line-through', color: 'var(--muted)' }}>
              {fmtPrice(deal.original_price)}
            </span>
          )}
        </div>

        {/* Footer */}
        <div style={{ borderTop: '1px solid var(--border)', paddingTop: 11, display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11, color: 'var(--muted)', marginTop: 'auto' }}>
          <span>{deal.category}</span>
          {deal.prime && <span style={{ color: '#00A8E0', fontWeight: 600 }}>Prime</span>}
        </div>
      </div>
    </div>
  )
}
