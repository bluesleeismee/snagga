import React, { useRef } from 'react'
import { fmtPrice, discount, dealLabel } from '../utils.js'

const AFFILIATE_TAG = 'snagga-21'

export default function DealTicker({ deals }) {
  if (!deals || deals.length === 0) return null

  // Top 12 Deals nehmen, dann duplizieren für nahtlose Schleife
  const items = deals.slice(0, 12)
  const doubled = [...items, ...items]

  return (
    <div style={{
      background: 'var(--bg-elev)',
      borderBottom: '1px solid var(--border)',
      padding: '14px 0',
      overflow: 'hidden',
      position: 'relative',
    }}>
      {/* Fade-Masken links + rechts */}
      <div style={{
        position: 'absolute', left: 0, top: 0, bottom: 0, width: 60, zIndex: 2,
        background: 'linear-gradient(to right, var(--bg-elev), transparent)',
        pointerEvents: 'none',
      }} />
      <div style={{
        position: 'absolute', right: 0, top: 0, bottom: 0, width: 60, zIndex: 2,
        background: 'linear-gradient(to left, var(--bg-elev), transparent)',
        pointerEvents: 'none',
      }} />

      <style>{`
        @keyframes ticker {
          0%   { transform: translateX(0); }
          100% { transform: translateX(-50%); }
        }
        .ticker-track {
          display: flex;
          gap: 10px;
          width: max-content;
          animation: ticker ${items.length * 4}s linear infinite;
          padding: 0 24px;
        }
        .ticker-track:hover {
          animation-play-state: paused;
        }
        .ticker-card {
          display: flex;
          align-items: center;
          gap: 10px;
          background: var(--bg-card);
          border: 1.5px solid var(--border);
          border-radius: 10px;
          padding: 8px 12px 8px 8px;
          width: 260px;
          flex-shrink: 0;
          cursor: pointer;
          transition: border-color 0.15s, box-shadow 0.15s;
          text-decoration: none;
        }
        .ticker-card:hover {
          border-color: var(--border-hover);
          box-shadow: 0 4px 16px var(--shadow-hover);
        }
      `}</style>

      <div className="ticker-track">
        {doubled.map((deal, i) => {
          const disc = discount(deal.current_price, deal.original_price)
          const label = dealLabel(deal.deal_score)
          return (
            <a
              key={`${deal.asin}-${i}`}
              href={deal.affiliate_url}
              target="_blank"
              rel="noopener noreferrer"
              className="ticker-card"
              onClick={e => e.stopPropagation()}
            >
              {/* Bild */}
              <div style={{
                width: 44, height: 44, flexShrink: 0,
                background: 'var(--bg-elev2)', borderRadius: 7,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                overflow: 'hidden',
              }}>
                {deal.image_url
                  ? <img src={deal.image_url} alt="" style={{ width: '100%', height: '100%', objectFit: 'contain', padding: 3 }} />
                  : <span style={{ fontSize: 20 }}>📦</span>
                }
              </div>

              {/* Info */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 12, fontWeight: 500, color: 'var(--text)',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  marginBottom: 3,
                }}>
                  {deal.name}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ fontSize: 14, fontWeight: 800, color: 'var(--text)', letterSpacing: '-0.3px' }}>
                    {fmtPrice(deal.current_price)}
                  </span>
                  {disc > 0 && (
                    <span style={{
                      fontSize: 10.5, fontWeight: 700, color: 'var(--orange)',
                      background: 'var(--orange-soft)', padding: '1px 5px', borderRadius: 4,
                    }}>
                      –{disc}%
                    </span>
                  )}
                  {label && (
                    <span style={{
                      fontSize: 9.5, fontWeight: 700, padding: '1px 5px', borderRadius: 4,
                      background: label.bg, color: label.color, border: label.border || 'none',
                      whiteSpace: 'nowrap',
                    }}>
                      {label.text}
                    </span>
                  )}
                </div>
              </div>
            </a>
          )
        })}
      </div>
    </div>
  )
}
