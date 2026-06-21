import React from 'react'
import PriceChart from './PriceChart.jsx'
import { fmtPrice, discount, scoreColor, fmtReviews } from '../utils.js'

export default function DealCard({ deal, expanded = true, saved, onSave, onClick }) {
  const disc = discount(deal.current_price, deal.original_price)
  const sColor = scoreColor(deal.deal_score)
  const scorePct = `calc(${deal.deal_score}% - 7px)`
  const isLow = deal.deal_score >= 85

  return (
    <div
      onClick={onClick}
      style={{
        position: 'relative',
        background: 'var(--bg-elev)',
        border: '1px solid var(--border)',
        borderRadius: 16,
        padding: 14,
        display: 'flex',
        flexDirection: 'column',
        gap: 13,
        cursor: 'pointer',
        boxShadow: '0 1px 2px var(--shadow)',
        WebkitTapHighlightColor: 'transparent',
        userSelect: 'none',
      }}
    >
      {/* Allzeit-Tief Badge */}
      {isLow && (
        <div style={{
          position: 'absolute', top: 0, left: 16,
          transform: 'translateY(-50%)',
          background: 'var(--red)', color: '#fff',
          fontSize: 10, fontWeight: 700, letterSpacing: '.5px',
          padding: '3px 9px', borderRadius: 7,
          display: 'flex', alignItems: 'center', gap: 4,
          boxShadow: '0 3px 10px var(--red-glow)',
          pointerEvents: 'none',
        }}>
          🔥 ALLZEIT-TIEF
        </div>
      )}

      {/* Header: Bild + Info + Stern */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
        {/* Produktbild */}
        <div style={{
          flexShrink: 0, width: 84, height: 84,
          borderRadius: 10, border: '1px solid var(--border)',
          background: 'var(--bg-elev2)',
          overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <img
            src={deal.image_url}
            alt={deal.name}
            style={{ width: '100%', height: '100%', objectFit: 'contain' }}
            onError={e => {
              e.target.style.display = 'none'
              e.target.parentElement.style.background =
                'repeating-linear-gradient(135deg,var(--bg-elev2),var(--bg-elev2) 7px,transparent 7px,transparent 14px),var(--bg-elev2)'
            }}
          />
        </div>

        {/* Name + Brand + Rating */}
        <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 4 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
            {deal.brand && (
              <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '.8px', textTransform: 'uppercase', color: 'var(--muted)' }}>
                {deal.brand}
              </span>
            )}
            {deal.prime && (
              <span style={{ fontSize: 9, fontWeight: 700, color: 'var(--cyan)', background: 'var(--cyan-soft)', padding: '2px 6px', borderRadius: 5, letterSpacing: '.4px', textTransform: 'uppercase' }}>
                Prime
              </span>
            )}
          </div>
          <div style={{
            fontFamily: 'Space Grotesk, sans-serif',
            fontWeight: 600, fontSize: 14.5, lineHeight: 1.25,
            color: 'var(--text)',
            display: '-webkit-box',
            WebkitLineClamp: 2,
            WebkitBoxOrient: 'vertical',
            overflow: 'hidden',
          }}>
            {deal.name}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--muted)' }}>
            <span style={{ color: '#F5A623' }}>★</span>
            <span style={{ color: 'var(--text)', fontWeight: 600 }}>{deal.rating?.toFixed(1)}</span>
            <span>·</span>
            <span>{fmtReviews(deal.reviews)} Bewertungen</span>
          </div>
        </div>

        {/* Merken-Button */}
        <button
          onClick={e => { e.stopPropagation(); onSave?.(deal.asin) }}
          style={{
            flexShrink: 0, width: 34, height: 34,
            borderRadius: 9, border: '1px solid var(--border)',
            background: 'var(--bg-elev2)', fontSize: 17, lineHeight: 1,
            display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0,
          }}
        >
          {saved ? '★' : '☆'}
        </button>
      </div>

      {/* Preis */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <span style={{ fontFamily: 'Space Grotesk', fontWeight: 700, fontSize: 29, color: 'var(--text)', letterSpacing: '-.6px', lineHeight: 1 }}>
          {fmtPrice(deal.current_price)}
        </span>
        <span style={{ fontSize: 14, color: 'var(--muted)', textDecoration: 'line-through' }}>
          {fmtPrice(deal.original_price)}
        </span>
        {disc > 0 && (
          <span style={{ fontSize: 12, fontWeight: 700, color: '#fff', background: 'var(--red)', padding: '3px 8px', borderRadius: 7 }}>
            -{disc}%
          </span>
        )}
      </div>

      {/* Mini-Chart (nur expanded) */}
      {expanded && deal.price_history?.length > 1 && (
        <PriceChart
          prices={deal.price_history}
          avgPrice={deal.avg_price}
          allTimeLow={deal.all_time_low}
        />
      )}

      {/* Score-Leiste */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 11 }}>
          <span style={{ color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.7px', fontWeight: 600 }}>
            Preis-Score
          </span>
          <span style={{ fontFamily: 'Space Grotesk', fontWeight: 700, fontSize: 14, color: sColor }}>
            {deal.deal_score}
            <span style={{ color: 'var(--muted)', fontWeight: 500, fontSize: 11 }}>/100</span>
          </span>
        </div>
        <div style={{ position: 'relative', height: 7, borderRadius: 99, background: 'linear-gradient(90deg,#EF4444,#F59E0B 52%,#22C55E)' }}>
          <div style={{
            position: 'absolute', top: '50%', left: scorePct,
            width: 15, height: 15, borderRadius: '50%',
            background: '#fff', border: '2.5px solid var(--bg-elev)',
            boxShadow: '0 1px 4px rgba(0,0,0,.45)',
            transform: 'translate(-50%,-50%)',
          }} />
        </div>
      </div>

      {/* Amazon-Button (nur expanded) */}
      {expanded && (
        <a
          href={deal.affiliate_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={e => e.stopPropagation()}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
            textDecoration: 'none',
            background: 'var(--red)', color: '#fff',
            fontWeight: 700, fontSize: 14,
            padding: 12, borderRadius: 10,
            fontFamily: 'Inter',
          }}
        >
          Bei Amazon ansehen <span style={{ fontSize: 16 }}>→</span>
        </a>
      )}
    </div>
  )
}
