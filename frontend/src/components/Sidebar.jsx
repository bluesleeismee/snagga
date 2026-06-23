import React from 'react'

export default function Sidebar({ categories, selectedCat, onSelectCat, deals, onCollapse }) {
  // Anzahl Deals pro Kategorie
  const counts = {}
  deals.forEach(d => {
    counts[d.category] = (counts[d.category] || 0) + 1
  })
  const totalCount = deals.length

  return (
    <div style={{
      width: 208,
      flexShrink: 0,
      background: 'var(--bg-elev)',
      borderRight: '1px solid var(--border)',
      padding: '18px 0 24px',
      position: 'sticky',
      top: 58,
      height: 'calc(100vh - 58px)',
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '4px 14px 8px 18px' }}>
        <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--muted)' }}>Kategorien</span>
        {onCollapse && (
          <button
            onClick={onCollapse}
            title="Einklappen"
            style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer', padding: '3px 5px', borderRadius: 5, display: 'flex', alignItems: 'center' }}
            onMouseEnter={e => e.currentTarget.style.color = 'var(--text)'}
            onMouseLeave={e => e.currentTarget.style.color = 'var(--muted)'}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15,18 9,12 15,6"/>
            </svg>
          </button>
        )}
      </div>

      {categories.map(cat => {
        const active = cat === selectedCat
        const count = cat === 'Alle' ? totalCount : (counts[cat] || 0)
        return (
          <div
            key={cat}
            onClick={() => onSelectCat(cat)}
            style={{
              padding: '9px 18px',
              fontSize: 14,
              color: active ? 'var(--orange)' : 'var(--text)',
              fontWeight: active ? 600 : 400,
              background: active ? 'var(--orange-soft)' : 'transparent',
              borderRight: active ? '2.5px solid var(--orange)' : '2.5px solid transparent',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              transition: 'background 0.1s',
              userSelect: 'none',
            }}
            onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--bg-elev2)' }}
            onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent' }}
          >
            <span>{cat}</span>
            <span style={{ fontSize: 12, color: active ? 'var(--orange)' : 'var(--muted)', fontWeight: 400, opacity: 0.8 }}>
              {count}
            </span>
          </div>
        )
      })}

      {/* Bottom links */}
      <div style={{ marginTop: 'auto', padding: '16px 18px 0', borderTop: '1px solid var(--border)' }}>
        <div style={{ fontSize: 12, color: 'var(--muted)', display: 'flex', flexDirection: 'column', gap: 8 }}>
          <span style={{ cursor: 'pointer' }} onClick={() => {}}>★ Watchlist</span>
          <span style={{ cursor: 'pointer' }} onClick={() => {}}>⚙ Einstellungen</span>
          <span style={{ cursor: 'pointer', fontSize: 11 }}>Impressum · Datenschutz</span>
        </div>
      </div>
    </div>
  )
}
