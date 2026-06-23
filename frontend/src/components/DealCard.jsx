import React, { useState } from 'react'
import PriceChart from './PriceChart.jsx'
import { fmtPrice, discount, dealLabel } from '../utils.js'

const AFFILIATE_TAG = 'snagga-21'

function cartUrl(asin)   { return `https://www.amazon.de/gp/aws/cart/add.html?ASIN.1=${asin}&Quantity.1=1&tag=${AFFILIATE_TAG}` }
function reviewUrl(asin) { return `https://www.amazon.de/product-reviews/${asin}` }
function shareUrl(asin)  { return `https://snagga.de/?asin=${asin}` }

export default function DealCard({ deal, saved, onSave, onClick, view = 'grid' }) {
  const [imgError, setImgError] = useState(false)
  const disc = discount(deal.current_price, deal.original_price)
  const label = dealLabel(deal.deal_score)

  if (view === 'list') {
    return <ListCard deal={deal} saved={saved} onSave={onSave} onClick={onClick} disc={disc} label={label} imgError={imgError} setImgError={setImgError} />
  }
  return <GridCard deal={deal} saved={saved} onSave={onSave} onClick={onClick} disc={disc} label={label} imgError={imgError} setImgError={setImgError} />
}

/* ── Grid Card ─────────────────────────────────────────────────── */
function GridCard({ deal, saved, onSave, onClick, disc, label, imgError, setImgError }) {
  return (
    <div
      onClick={onClick}
      style={{ background: 'var(--bg-card)', border: '1.5px solid var(--border)', borderRadius: 11, overflow: 'hidden', display: 'flex', flexDirection: 'column', transition: 'box-shadow 0.18s, border-color 0.18s', cursor: 'pointer' }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 3px 16px var(--shadow-hover)'; e.currentTarget.style.borderColor = 'var(--border-hover)' }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.borderColor = 'var(--border)' }}
    >
      {/* Bild */}
      <div style={{ width: '100%', aspectRatio: '4/3', background: 'var(--bg-elev2)', position: 'relative', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        {deal.image_url && !imgError
          ? <img src={deal.image_url} alt={deal.name} onError={() => setImgError(true)} style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 8 }} />
          : <div style={{ fontSize: 40, color: 'var(--border)' }}>📦</div>}
        {label && <BadgeOverlay label={label} />}
        <SaveBtn saved={saved} onSave={e => { e.stopPropagation(); onSave?.(deal.asin) }} />
      </div>

      {/* Body */}
      <div style={{ padding: '11px 12px 13px', display: 'flex', flexDirection: 'column', flex: 1 }}>
        <div style={{ fontSize: 11.5, color: 'var(--muted)', fontWeight: 500, marginBottom: 2 }}>{deal.brand}</div>
        <div style={{ fontSize: 13.5, color: 'var(--text)', fontWeight: 500, lineHeight: 1.45, marginBottom: 3, display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical', overflow: 'hidden', height: 'calc(3 * 1.45 * 13.5px)' }}>
          {deal.name}
        </div>
        <div style={{ fontSize: 11.5, color: 'var(--text)', marginBottom: 9 }}>{deal.category}</div>

        <PriceRow current={deal.current_price} original={deal.original_price} disc={disc} />

        {deal.price_history?.length > 1 && (
          <PriceChart prices={deal.price_history} avgPrice={deal.avg_price} allTimeLow={deal.all_time_low} asin={deal.asin} />
        )}

        {/* Prime + Rating */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
          {deal.prime && <span style={{ fontSize: 10.5, color: 'var(--blue)', fontWeight: 700, letterSpacing: 0.5 }}>✦ Prime</span>}
          {deal.rating && (
            <a href={reviewUrl(deal.asin)} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}
              style={{ fontSize: 10.5, color: 'var(--muted)', textDecoration: 'none', marginLeft: 'auto' }}>
              ★ {Number(deal.rating).toFixed(1)} ({deal.reviews?.toLocaleString('de')})
            </a>
          )}
        </div>

        <ActionButtons deal={deal} />
      </div>
    </div>
  )
}

/* ── List Card ─────────────────────────────────────────────────── */
function ListCard({ deal, saved, onSave, onClick, disc, label, imgError, setImgError }) {
  return (
    <div
      onClick={onClick}
      style={{ background: 'var(--bg-card)', border: '1.5px solid var(--border)', borderRadius: 11, overflow: 'hidden', display: 'flex', flexDirection: 'row', transition: 'box-shadow 0.18s, border-color 0.18s', cursor: 'pointer', minHeight: 140 }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 3px 16px var(--shadow-hover)'; e.currentTarget.style.borderColor = 'var(--border-hover)' }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.borderColor = 'var(--border)' }}
    >
      {/* Bild */}
      <div style={{ width: 160, flexShrink: 0, background: 'var(--bg-elev2)', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
        {deal.image_url && !imgError
          ? <img src={deal.image_url} alt={deal.name} onError={() => setImgError(true)} style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 10 }} />
          : <div style={{ fontSize: 36, color: 'var(--border)' }}>📦</div>}
        {label && <BadgeOverlay label={label} />}
      </div>

      {/* Info */}
      <div style={{ flex: 1, padding: '12px 14px', display: 'flex', flexDirection: 'column', justifyContent: 'center', minWidth: 0, borderRight: '1px solid var(--border)' }}>
        <div style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 500, marginBottom: 2 }}>{deal.brand}</div>
        <div style={{ fontSize: 14, color: 'var(--text)', fontWeight: 500, lineHeight: 1.4, marginBottom: 4, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {deal.name}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text)', marginBottom: 4 }}>{deal.category}</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {deal.prime && <span style={{ fontSize: 10, color: 'var(--blue)', fontWeight: 700 }}>✦ Prime</span>}
          {deal.rating && (
            <a href={reviewUrl(deal.asin)} target="_blank" rel="noopener noreferrer" onClick={e => e.stopPropagation()}
              style={{ fontSize: 10, color: 'var(--muted)', textDecoration: 'none' }}>
              ★ {Number(deal.rating).toFixed(1)} ({deal.reviews?.toLocaleString('de')})
            </a>
          )}
        </div>
      </div>

      {/* Chart */}
      <div style={{ width: 220, flexShrink: 0, padding: '12px 14px', display: 'flex', alignItems: 'center', borderRight: '1px solid var(--border)' }}>
        {deal.price_history?.length > 1
          ? <div style={{ width: '100%' }}><PriceChart prices={deal.price_history} avgPrice={deal.avg_price} allTimeLow={deal.all_time_low} asin={deal.asin} /></div>
          : <div style={{ color: 'var(--muted)', fontSize: 12 }}>—</div>}
      </div>

      {/* Preis + Buttons */}
      <div style={{ width: 176, flexShrink: 0, padding: '12px 14px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
          <PriceRow current={deal.current_price} original={deal.original_price} disc={disc} vertical />
          <SaveBtn saved={saved} onSave={e => { e.stopPropagation(); onSave?.(deal.asin) }} style={{ position: 'relative', top: 'auto', right: 'auto', flexShrink: 0 }} />
        </div>
        <ActionButtons deal={deal} compact />
      </div>
    </div>
  )
}

/* ── Action Buttons (Warenkorb + Zum Deal + Teilen) ────────────── */
function ActionButtons({ deal, compact = false }) {
  const [copied, setCopied] = useState(false)

  function handleShare(e) {
    e.stopPropagation()
    const url = shareUrl(deal.asin)
    if (navigator.share) {
      navigator.share({ title: deal.name, url }).catch(() => {})
    } else {
      navigator.clipboard.writeText(url).then(() => {
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      })
    }
  }

  return (
    <div style={{ display: 'flex', gap: 5, marginTop: 'auto' }} onClick={e => e.stopPropagation()}>
      {/* Warenkorb */}
      <a href={cartUrl(deal.asin)} target="_blank" rel="noopener noreferrer"
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'var(--orange)', color: '#fff', borderRadius: 7, padding: compact ? '7px 8px' : '7px 10px', transition: 'opacity 0.15s', flexShrink: 0 }}
        title="In den Warenkorb"
        onMouseEnter={e => e.currentTarget.style.opacity = '0.85'}
        onMouseLeave={e => e.currentTarget.style.opacity = '1'}
      >
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="9" cy="21" r="1"/><circle cx="20" cy="21" r="1"/>
          <path d="M1 1h4l2.68 13.39a2 2 0 0 0 2 1.61h9.72a2 2 0 0 0 2-1.61L23 6H6"/>
        </svg>
      </a>

      {/* Zum Deal */}
      <a href={deal.affiliate_url} target="_blank" rel="noopener noreferrer"
        style={{ flex: 1, display: 'block', textAlign: 'center', background: 'var(--text)', color: 'var(--bg-card)', borderRadius: 7, padding: '7px 6px', fontSize: 12, fontWeight: 600, transition: 'opacity 0.15s' }}
        onMouseEnter={e => e.currentTarget.style.opacity = '0.82'}
        onMouseLeave={e => e.currentTarget.style.opacity = '1'}
      >
        Zum Deal →
      </a>

      {/* Teilen */}
      <button onClick={handleShare} title={copied ? 'Kopiert!' : 'Teilen'}
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, borderRadius: 7, padding: '7px 8px', border: '1.5px solid var(--border)', background: copied ? 'var(--orange-soft)' : 'var(--bg-elev2)', color: copied ? 'var(--orange)' : 'var(--muted)', transition: 'all 0.15s' }}
      >
        {copied
          ? <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20,6 9,17 4,12"/></svg>
          : <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/>
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/>
            </svg>
        }
      </button>
    </div>
  )
}

/* ── Shared sub-components ─────────────────────────────────────── */

function BadgeOverlay({ label }) {
  return (
    <div style={{ position: 'absolute', top: 8, left: 8, fontSize: 10, fontWeight: 700, padding: '3px 8px', borderRadius: 5, background: label.bg, color: label.color, border: label.border || 'none', letterSpacing: 0.1, lineHeight: 1.4 }}>
      {label.text}
    </div>
  )
}

function SaveBtn({ saved, onSave, style = {} }) {
  return (
    <button onClick={onSave}
      style={{ position: 'absolute', top: 8, right: 8, width: 30, height: 30, borderRadius: 7, border: `1px solid ${saved ? 'var(--star-saved)' : 'var(--border)'}`, background: saved ? 'var(--orange-soft)' : 'var(--bg-card)', display: 'flex', alignItems: 'center', justifyContent: 'center', transition: 'all 0.15s', ...style }}
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill={saved ? 'var(--star-saved)' : 'none'} stroke={saved ? 'var(--star-saved)' : 'var(--muted)'} strokeWidth="1.8" strokeLinejoin="round">
        <polygon points="12,2 15.09,8.26 22,9.27 17,14.14 18.18,21.02 12,17.77 5.82,21.02 7,14.14 2,9.27 8.91,8.26"/>
      </svg>
    </button>
  )
}

function PriceRow({ current, original, disc, vertical = false }) {
  return (
    <div style={{ display: 'flex', alignItems: vertical ? 'flex-start' : 'baseline', flexDirection: vertical ? 'column' : 'row', gap: vertical ? 2 : 7, flexWrap: 'wrap' }}>
      <span style={{ fontSize: 21, fontWeight: 800, color: 'var(--text)', letterSpacing: '-0.5px' }}>{fmtPrice(current)}</span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
        {original > current && <span style={{ fontSize: 13, color: 'var(--muted)', textDecoration: 'line-through' }}>{fmtPrice(original)}</span>}
        {disc > 0 && <span style={{ fontSize: 12, fontWeight: 700, color: 'var(--orange)', background: 'var(--orange-soft)', padding: '2px 6px', borderRadius: 4 }}>–{disc}%</span>}
      </div>
    </div>
  )
}
