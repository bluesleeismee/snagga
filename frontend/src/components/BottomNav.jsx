import React from 'react'

const TABS = [
  { id: 'deals',     label: 'Deals',     icon: '📡' },
  { id: 'watchlist', label: 'Watchlist', icon: '⭐' },
  { id: 'alerts',    label: 'Alerts',    icon: '🔔' },
  { id: 'settings',  label: 'Settings',  icon: '⚙️' },
]

export default function BottomNav({ active, onSelect }) {
  return (
    <nav style={{
      position: 'sticky', bottom: 0, zIndex: 10,
      background: 'var(--bg-elev)',
      borderTop: '1px solid var(--border)',
      display: 'flex',
      paddingBottom: 'env(safe-area-inset-bottom, 0px)',
    }}>
      {TABS.map(t => {
        const isActive = t.id === active
        return (
          <button
            key={t.id}
            onClick={() => onSelect(t.id)}
            style={{
              flex: 1, border: 'none', background: 'none',
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              gap: 3, padding: '10px 0 8px',
              color: isActive ? 'var(--red)' : 'var(--muted)',
              transition: 'color .15s',
            }}
          >
            <span style={{ fontSize: 20, lineHeight: 1 }}>{t.icon}</span>
            <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '.4px' }}>{t.label}</span>
          </button>
        )
      })}
    </nav>
  )
}
