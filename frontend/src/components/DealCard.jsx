import React, { useState } from 'react'
import PriceChart from './PriceChart.jsx'
import { fmtPrice, discount, dealLabel } from '../utils.js'

export default function DealCard({ deal, saved, onSave }) {
  const [imgError, setImgError] = useState(false)
  const disc = discount(deal.current_price, deal.original_price)
  const label = dealLabel(deal.deal_score)

  return (
    <div style={{
      background: 'var(--bg-card)',
      border: '1.5px solid var(--border)',
      borderRadius: 11,
      overflow: 'hidden',
      display: 'flex',
      flexDirection: 'column',
      transition: 'box-shadow 0.18s, border-color 0.18s',
      cursor: 'pointer',
    }}
      onMouseEnter={e => {
        e.currentTarget.style.boxShadow = '0 3px 16px var(--shadow-hover)'
        e.currentTarget.style.borderColor = 'var(--border-hover)'
      }}
      onMouseLeave={e => {
        e.currentTarget.style.boxShadow = 'none'
        e.currentTarget.style.borderColor = 'var(--border)'
      }}
    >
      {/* Produktbild */}
      <div style={{
        width: '100%',
        aspectRatio: '4 / 3',
        background: 'var(--bg-elev2)',
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0,
      }}>
        {deal.image_url && !imgError ? (
          <img
            src={deal.image_url}
            alt={deal.name}
            onError={() => setImgError(true)}
            style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 8 }}
          />
        ) : (
          <div style={{ fontSize: 40, color: 'var(--border)' }}>📦</div>
        )}

        {/* Deal-Label Badge */}
        {label && (
          <div style={{
            position: 'absolute', top: 8, left: 8,
            fontSize: 10, fontWeight: 700,
            padding: '3px 8px', borderRadius: 5,
            background: label.bg, color: label.color,
            border: label.border || 'none',
            letterSpacing: 0.1,
            lineHeight: 1.4,
          }}>
            {label.text}
          </div>
        )}

        {/* Merken-Button */}
        <button
          onClick={e => { e.stopPropagation(); onSave?.(deal.asin) }}
          style={{
            position: 'absolute', top: 8, right: 8,
            width: 30, height: 30, borderRadius: 7,
            border: '1px solid var(--border)',
            background: 'var(--bg-card)',
            fontSize: 15, lineHeight: 1,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: saved ? '#E8500A' : 'var(--muted)',
            transition: 'color 0.15s',
          }}
        >
          {saved ? '★' : '☆'}
        </button>
      </div>

      {/* Card Body */}
      <div style={{
        padding: '11px 12px 13px',
        display: 'flex',
        flexDirection: 'column',
        flex: 1,
      }}>
        <div style={{ fontSize: 11.5, color: 'var(--muted)', fontWeight: 500, marginBottom: 2 }}>
          {deal.brand}
        </div>

        {/* Produktname — fixe 3 Zeilen */}
        <div style={{
          fontSize: 13.5,
          color: 'var(--text)',
          fontWeight: 500,
          lineHeight: 1.45,
          marginBottom: 3,
          display: '-webkit-box',
          WebkitLineClamp: 3,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
          height: 'calc(3 * 1.45 * 13.5px)',
        }}>
          {deal.name}
        </div>

        <div style={{ fontSize: 11.5, color: 'var(--text)', marginBottom: 9 }}>
          {deal.category}
        </div>

        {/* Preis */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 7, marginBottom: 10, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 21, fontWeight: 800, color: 'var(--text)', letterSpacing: '-0.5px' }}>
            {fmtPrice(deal.current_price)}
          </span>
          {deal.original_price > deal.current_price && (
            <span style={{ fontSize: 13, color: 'var(--muted)', textDecoration: 'line-through' }}>
              {fmtPrice(deal.original_price)}
            </span>
          )}
          {disc > 0 && (
            <span style={{
              fontSize: 12, fontWeight: 700,
              color: 'var(--orange)',
              background: 'var(--orange-soft)',
              padding: '2px 6px', borderRadius: 4,
            }}>
              –{disc}%
            </span>
          )}
        </div>

        {/* Preisgrafik */}
        {deal.price_history?.length > 1 && (
          <PriceChart
            prices={deal.price_history}
            avgPrice={deal.avg_price}
            allTimeLow={deal.all_time_low}
            asin={deal.asin}
          />
        )}

        {/* Prime */}
        {deal.prime && (
          <span style={{ fontSize: 10.5, color: 'var(--blue)', fontWeight: 700, letterSpacing: 0.5, marginBottom: 7, display: 'block' }}>
            ✦ Prime
          </span>
        )}

        {/* CTA — immer am Ende dank flex + marginTop auto */}
        <a
          href={deal.affiliate_url}
          target="_blank"
          rel="noopener noreferrer"
          onClick={e => e.stopPropagation()}
          style={{
            display: 'block',
            textAlign: 'center',
            background: 'var(--text)',
            color: 'var(--bg-card)',
            border: 'none',
            borderRadius: 8,
            padding: '8px',
            fontSize: 12.5,
            fontWeight: 600,
            marginTop: 'auto',
            transition: 'opacity 0.15s',
          }}
          onMouseEnter={e => e.currentTarget.style.opacity = '0.82'}
          onMouseLeave={e => e.currentTarget.style.opacity = '1'}
        >
          Zum Deal →
        </a>
      </div>
    </div>
  )
}
