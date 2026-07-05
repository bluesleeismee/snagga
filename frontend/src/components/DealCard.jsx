import React, { useState } from 'react'
import { fmtPrice, discount, fmtAge, AGE_COLORS, fmtReviews, shareOrCopy, catLabel } from '../utils.js'

const TAG_COLORS = {
  'Allzeittiefpreis':  { bg: '#1a1a1a', text: '#fff' },
  'Historisch günstig':{ bg: '#2d5a27', text: '#fff' },
  'Stark gefallen':    { bg: '#8b1a1a', text: '#fff' },
  'Preis gefallen':    { bg: 'var(--accent)', text: '#fff' },
}

// "Bester Preis seit X Monaten / über 1 Jahr" kommt mit variablem Text aus dem
// Backend (echtes Preishistorie-Urteil) → Präfix-Match statt exaktem Key.
export function tagStyleFor(tag) {
  if (!tag) return null
  if (tag.startsWith('Bester Preis seit')) return { bg: '#1E7A3C', text: '#fff' }
  return TAG_COLORS[tag] || null
}

export default function DealCard({ deal, onClick }) {
  const [imgError, setImgError] = useState(false)
  const [hovered,  setHovered]  = useState(false)
  const [copied,   setCopied]   = useState(false)
  const [shareHovered, setShareHovered] = useState(false)

  const disc = discount(deal.current_price, deal.original_price)
  const age  = fmtAge(deal.first_seen)
  const tag  = deal.tag || ''
  const tagStyle = tagStyleFor(tag)

  // Eyebrow-Label: Marke bevorzugt, sonst Bewertung. NIE die Kategorie — die
  // steht schon in der Fusszeile, sonst stuende sie zweimal auf der Kachel.
  // Fehlen Marke UND Bewertung, bleibt der Eyebrow leer (Hoehe wird per NBSP
  // gehalten, damit der Titel nicht nach oben rutscht).
  const ratingLabel = deal.rating > 0
    ? `${deal.rating.toFixed(1)} ★${fmtReviews(deal.reviews) ? ' · ' + fmtReviews(deal.reviews) : ''}`
    : null
  const eyebrow = deal.brand || ratingLabel || ''

  const imgSrc = deal.image_url || null

  const handleShare = async (e) => {
    e.preventDefault()
    e.stopPropagation()
    const result = await shareOrCopy(deal)
    if (result === 'copied') {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  // Echter Link auf die crawlbare Deal-Seite (SEO + Middle-Click/Ctrl-Click öffnen
  // sie in neuem Tab), normaler Linksklick öffnet weiterhin das schnelle Modal.
  const handleCardClick = (e) => {
    if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
    e.preventDefault()
    onClick?.(e)
  }

  return (
    <a
      href={`/deal/${deal.asin}`}
      onClick={handleCardClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        background: 'var(--bg-card)', border: '1px solid var(--border)',
        display: 'flex', flexDirection: 'column',
        cursor: 'pointer', position: 'relative', textDecoration: 'none', color: 'inherit',
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
          {eyebrow || ' '}
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
          <span>{catLabel(deal.category)}</span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {deal.prime && <span style={{ color: '#00A8E0', fontWeight: 600 }}>Prime</span>}
            {/* Share button — DSGVO-konform, kein Cookie, kein Tracker */}
            <button
              onClick={handleShare}
              title={copied ? 'Link kopiert!' : 'Deal teilen'}
              style={{
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                width: 26, height: 26, borderRadius: '50%',
                background: shareHovered ? 'var(--bg-img)' : 'none',
                border: 'none', cursor: 'pointer',
                color: copied ? 'var(--accent)' : shareHovered ? 'var(--text)' : 'var(--muted)',
                transition: 'background 0.15s, color 0.15s',
              }}
              onMouseEnter={() => setShareHovered(true)}
              onMouseLeave={() => setShareHovered(false)}
            >
              {copied ? (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12"/>
                </svg>
              ) : (
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
                  <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>
    </a>
  )
}
