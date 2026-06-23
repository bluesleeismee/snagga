import React, { useState } from 'react'
import PriceChart from './PriceChart.jsx'
import { fmtPrice, discount, dealLabel } from '../utils.js'

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
      style={{
        background: 'var(--bg-card)', border: '1.5px solid var(--border)',
        borderRadius: 11, overflow: 'hidden',
        display: 'flex', flexDirection: 'column',
        transition: 'box-shadow 0.18s, border-color 0.18s', cursor: 'pointer',
      }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 3px 16px var(--shadow-hover)'; e.currentTarget.style.borderColor = 'var(--border-hover)' }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.borderColor = 'var(--border)' }}
    >
      {/* Bild */}
      <div style={{ width: '100%', aspectRatio: '4/3', background: 'var(--bg-elev2)', position: 'relative', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
        {deal.image_url && !imgError ? (
          <img src={deal.image_url} alt={deal.name} onError={() => setImgError(true)} style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 8 }} />
        ) : (
          <div style={{ fontSize: 40, color: 'var(--border)' }}>📦</div>
        )}
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

        {deal.prime && <span style={{ fontSize: 10.5, color: 'var(--blue)', fontWeight: 700, letterSpacing: 0.5, marginBottom: 7, display: 'block' }}>✦ Prime</span>}

        <CtaButton url={deal.affiliate_url} />
      </div>
    </div>
  )
}

/* ── List Card ─────────────────────────────────────────────────── */
function ListCard({ deal, saved, onSave, onClick, disc, label, imgError, setImgError }) {
  return (
    <div
      onClick={onClick}
      style={{
        background: 'var(--bg-card)', border: '1.5px solid var(--border)',
        borderRadius: 11, overflow: 'hidden',
        display: 'flex', flexDirection: 'row',
        transition: 'box-shadow 0.18s, border-color 0.18s', cursor: 'pointer',
        minHeight: 140,
      }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = '0 3px 16px var(--shadow-hover)'; e.currentTarget.style.borderColor = 'var(--border-hover)' }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.borderColor = 'var(--border)' }}
    >
      {/* Bild — links, feste Breite */}
      <div style={{ width: 160, flexShrink: 0, background: 'var(--bg-elev2)', position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' }}>
        {deal.image_url && !imgError ? (
          <img src={deal.image_url} alt={deal.name} onError={() => setImgError(true)} style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 10 }} />
        ) : (
          <div style={{ fontSize: 36, color: 'var(--border)' }}>📦</div>
        )}
        {label && <BadgeOverlay label={label} />}
      </div>

      {/* Info — Mitte */}
      <div style={{ flex: 1, padding: '12px 14px', display: 'flex', flexDirection: 'column', justifyContent: 'center', minWidth: 0, borderRight: '1px solid var(--border)' }}>
        <div style={{ fontSize: 11, color: 'var(--muted)', fontWeight: 500, marginBottom: 2 }}>{deal.brand}</div>
        <div style={{ fontSize: 14, color: 'var(--text)', fontWeight: 500, lineHeight: 1.4, marginBottom: 4, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
          {deal.name}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text)', marginBottom: 6 }}>{deal.category}</div>
        {deal.prime && <span style={{ fontSize: 10, color: 'var(--blue)', fontWeight: 700 }}>✦ Prime</span>}
      </div>

      {/* Chart — Mitte rechts */}
      <div style={{ width: 220, flexShrink: 0, padding: '12px 14px', display: 'flex', alignItems: 'center', borderRight: '1px solid var(--border)' }}>
        {deal.price_history?.length > 1 ? (
          <div style={{ width: '100%' }}>
            <PriceChart prices={deal.price_history} avgPrice={deal.avg_price} allTimeLow={deal.all_time_low} asin={deal.asin} />
          </div>
        ) : (
          <div style={{ color: 'var(--muted)', fontSize: 12 }}>—</div>
        )}
      </div>

      {/* Preis + CTA — rechts */}
      <div style={{ width: 160, flexShrink: 0, padding: '12px 14px', display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 10, alignItems: 'flex-start' }}>
        <SaveBtn saved={saved} onSave={e => { e.stopPropagation(); onSave?.(deal.asin) }} style={{ alignSelf: 'flex-end', position: 'relative', top: 'auto', right: 'auto' }} />
        <PriceRow current={deal.current_price} original={deal.original_price} disc={disc} vertical />
        <CtaButton url={deal.affiliate_url} />
      </div>
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
    <button
      onClick={onSave}
      style={{ position: 'absolute', top: 8, right: 8, width: 30, height: 30, borderRadius: 7, border: '1px solid var(--border)', background: 'var(--bg-card)', fontSize: 15, lineHeight: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: saved ? '#E8500A' : 'var(--muted)', transition: 'color 0.15s', ...style }}
    >
      {saved ? '★' : '☆'}
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

function CtaButton({ url }) {
  return (
    <a
      href={url} target="_blank" rel="noopener noreferrer"
      onClick={e => e.stopPropagation()}
      style={{ display: 'block', textAlign: 'center', background: 'var(--text)', color: 'var(--bg-card)', borderRadius: 8, padding: '8px', fontSize: 12.5, fontWeight: 600, marginTop: 'auto', transition: 'opacity 0.15s', width: '100%' }}
      onMouseEnter={e => e.currentTarget.style.opacity = '0.82'}
      onMouseLeave={e => e.currentTarget.style.opacity = '1'}
    >
      Zum Deal →
    </a>
  )
}
