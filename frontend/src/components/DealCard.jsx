import React, { useState } from 'react'
import { fmtPrice, discount, fmtAge, AGE_COLORS } from '../utils.js'

const TAG_COLORS = {
  'Allzeittiefpreis':  { bg: '#1a1a1a', text: '#fff' },
  'Historisch günstig':{ bg: '#2d5a27', text: '#fff' },
  'Stark gefallen':    { bg: '#8b1a1a', text: '#fff' },
  'Seltene Gelegenheit':{ bg: '#1a3d6b', text: '#fff' },
  'Preis gefallen':    { bg: 'var(--accent)', text: '#fff' },
}

async function shareOrCopy(deal) {
  const url = `${window.location.origin}/share/${deal.asin}`
  const text = `${deal.name} jetzt für ${(deal.current_price).toFixed(2).replace('.',',')} € auf snagga.de 🔥`

  if (navigator.share) {
    try {
      await navigator.share({ title: deal.name, text, url })
      return
    } catch (_) {}
  }
  try {
    await navigator.clipboard.writeText(url)
    return 'copied'
  } catch (_) {}
  // Fallback: Textfeld
  const ta = document.createElement('textarea')
  ta.value = url
  document.body.appendChild(ta)
  ta.select()
  document.execCommand('copy')
  document.body.removeChild(ta)
  return 'copied'
}

export default function DealCard({ deal, onClick }) {
  const [imgError, setImgError] = useState(false)
  const [hovered,  setHovered]  = useState(false)
  const [copied,   setCopied]   = useState(false)

  const disc = discount(deal.current_price, deal.original_price)
  const age  = fmtAge(deal.last_updated)
  const tag  = deal.tag || ''
  const tagStyle = TAG_COLORS[tag] || null

  const imgSrc = deal.image_url || null

  const handleShare = async (e) => {
    e.stopPropagation()
    const result = await shareOrCopy(deal)
    if (result === 'copied') {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

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
        {/* Discount badge */}
        {disc > 0 && (
          <div
            title={`–${disc}% verglichen mit dem Durchschnittspreis der letzten 6 Monate`}
            style={{
              position: 'absolute', top: 14, left: 14, zIndex: 2,
              background: 'var(--accent)', color: '#fff',
              padding: '3px 8px', fontSize: 11, fontWeight: 600, letterSpacing: 0.5,
              cursor: 'help',
            }}
          >
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

      {/* Tag badge — immer gleiche Höhe, damit Body-Text auf allen Kacheln gleich beginnt */}
      <div style={{
        fontSize: 10, fontWeight: 600, letterSpacing: 0.6,
        padding: '4px 10px', textTransform: 'uppercase',
        background: (tag && tagStyle) ? tagStyle.bg : 'transparent',
        color:      (tag && tagStyle) ? tagStyle.text : 'transparent',
        visibility: (tag && tagStyle) ? 'visible' : 'hidden',
      }}>
        {(tag && tagStyle) ? tag : ' '}
      </div>

      {/* Card body */}
      <div style={{ padding: '16px 18px 16px', display: 'flex', flexDirection: 'column', flex: 1 }}>
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
        <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 8, marginBottom: 14 }}>
          <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
            <span style={{ fontSize: 17, fontWeight: 700, color: 'var(--text)' }}>
              {fmtPrice(deal.current_price)}
            </span>
            {deal.original_price > deal.current_price && (
              <span style={{ fontSize: 13, textDecoration: 'line-through', color: 'var(--muted)' }}>
                {fmtPrice(deal.original_price)}
              </span>
            )}
          </div>
          {age && (
            <span style={{ fontSize: 10, color: AGE_COLORS[age.level], flexShrink: 0, lineHeight: 1 }}>
              {age.text}
            </span>
          )}
        </div>

        {/* Footer */}
        <div style={{
          borderTop: '1px solid var(--border)', paddingTop: 11,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          fontSize: 11, color: 'var(--muted)', marginTop: 'auto',
        }}>
          <span>{deal.category}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {deal.prime && <span style={{ color: '#00A8E0', fontWeight: 600 }}>Prime</span>}
            {/* Share button — DSGVO-konform, kein Cookie, kein Tracker */}
            <button
              onClick={handleShare}
              title={copied ? 'Link kopiert!' : 'Deal teilen'}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: '2px 4px', color: copied ? 'var(--accent)' : 'var(--muted)',
                fontSize: 13, lineHeight: 1, transition: 'color 0.2s',
              }}
            >
              {copied ? '✓' : '↗'}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
