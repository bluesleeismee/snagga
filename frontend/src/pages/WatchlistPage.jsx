import React, { useState, useEffect } from 'react'
import DealCard from '../components/DealCard.jsx'
import { api } from '../api.js'

export default function WatchlistPage({ watchlist, onToggleWatch, onGoDeals, theme, onToggleTheme }) {
  const [deals, setDeals] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const asins = [...watchlist]
    if (asins.length === 0) { setDeals([]); return }
    setLoading(true)
    Promise.all(asins.map(asin => api.product(asin).catch(() => null)))
      .then(results => {
        setDeals(results.filter(Boolean))
        setLoading(false)
      })
  }, [watchlist])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <div style={{ position: 'sticky', top: 0, zIndex: 6, background: 'var(--bg)', padding: '18px 16px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontFamily: 'Space Grotesk', fontWeight: 700, fontSize: 21, letterSpacing: '-.3px' }}>Watchlist</span>
        <button onClick={onToggleTheme} style={{ width: 36, height: 36, borderRadius: 9, border: '1px solid var(--border)', background: 'var(--bg-elev2)', color: 'var(--text)', fontSize: 15, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}>
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>
      </div>

      <div className="no-scroll" style={{ flex: 1, overflowY: 'auto' }}>
        {watchlist.size === 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 14, padding: '90px 36px', textAlign: 'center' }}>
            <div style={{ width: 64, height: 64, borderRadius: 18, background: 'var(--bg-elev2)', border: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 28 }}>⭐</div>
            <div style={{ fontFamily: 'Space Grotesk', fontWeight: 600, fontSize: 17, color: 'var(--text)' }}>Noch nichts gespeichert</div>
            <div style={{ fontSize: 14, color: 'var(--muted)', lineHeight: 1.5 }}>Tippe auf das ☆ bei einem Deal, um ihn hier zu beobachten.</div>
            <button
              onClick={onGoDeals}
              style={{ marginTop: 4, background: 'var(--red)', color: '#fff', border: 'none', fontWeight: 700, fontSize: 14, padding: '11px 20px', borderRadius: 10 }}
            >
              Deals entdecken
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '16px 16px 28px' }}>
            {loading && <div style={{ textAlign: 'center', padding: 40, color: 'var(--muted)', fontSize: 14 }}>Laden…</div>}
            {deals.map(deal => (
              <DealCard
                key={deal.asin}
                deal={deal}
                expanded={false}
                saved
                onSave={onToggleWatch}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
