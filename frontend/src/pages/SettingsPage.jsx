import React, { useState } from 'react'
import { api } from '../api.js'

const ALL_CATS = ['Elektronik', 'Gaming', 'Haushalt', 'Kueche', 'Sport', 'Beauty']

export default function SettingsPage({ theme, onSetTheme, hiddenCats, onToggleCat, onShowLegal }) {
  const [refreshing, setRefreshing] = useState(false)
  const [refreshMsg, setRefreshMsg] = useState('')

  function handleRefresh() {
    setRefreshing(true)
    setRefreshMsg('')
    api.refresh()
      .then(r => setRefreshMsg(r.message || 'Fertig!'))
      .catch(() => setRefreshMsg('Fehler beim Refresh'))
      .finally(() => setRefreshing(false))
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div style={{ position: 'sticky', top: 0, zIndex: 6, background: 'var(--bg)', padding: '18px 16px 14px', borderBottom: '1px solid var(--border)' }}>
        <span style={{ fontFamily: 'Space Grotesk', fontWeight: 700, fontSize: 21, letterSpacing: '-.3px' }}>Einstellungen</span>
      </div>

      <div className="no-scroll" style={{ flex: 1, overflowY: 'auto', padding: '18px 16px 28px', display: 'flex', flexDirection: 'column', gap: 24 }}>

        <Section title="Darstellung">
          <div style={{ display: 'flex', gap: 8, background: 'var(--bg-elev2)', padding: 4, borderRadius: 11 }}>
            {[['dark', 'Dunkel'], ['light', 'Hell']].map(([val, label]) => (
              <button
                key={val}
                onClick={() => onSetTheme(val)}
                style={{
                  flex: 1, padding: 9, borderRadius: 8, border: 'none',
                  fontWeight: 700, fontSize: 13,
                  background: theme === val ? 'var(--bg-elev)' : 'transparent',
                  color: theme === val ? 'var(--text)' : 'var(--muted)',
                  boxShadow: theme === val ? '0 1px 3px var(--shadow)' : 'none',
                  transition: 'all .15s',
                }}
              >
                {val === 'dark' ? '🌙' : '☀️'} {label}
              </button>
            ))}
          </div>
        </Section>

        <Section title="Kategorien im Feed">
          <div style={{ background: 'var(--bg-elev)', border: '1px solid var(--border)', borderRadius: 14, overflow: 'hidden' }}>
            {ALL_CATS.map((cat, i) => {
              const enabled = !hiddenCats.has(cat)
              return (
                <div
                  key={cat}
                  style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '13px 15px', borderBottom: i < ALL_CATS.length - 1 ? '1px solid var(--border)' : 'none' }}
                >
                  <span style={{ fontSize: 14, color: 'var(--text)', fontWeight: 500 }}>{cat}</span>
                  <button
                    onClick={() => onToggleCat(cat)}
                    style={{
                      width: 44, height: 26, borderRadius: 99, border: 'none', padding: 0, position: 'relative',
                      background: enabled ? 'var(--red)' : 'var(--bg-elev2)',
                      transition: 'background .15s',
                    }}
                  >
                    <span style={{
                      position: 'absolute', top: 3, left: enabled ? 21 : 3,
                      width: 20, height: 20, borderRadius: '50%',
                      background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,.4)',
                      transition: 'left .15s',
                    }} />
                  </button>
                </div>
              )
            })}
          </div>
        </Section>

        <Section title="Daten">
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            style={{
              width: '100%', padding: '12px', borderRadius: 10,
              border: '1px solid var(--border)', background: 'var(--bg-elev)',
              color: refreshing ? 'var(--muted)' : 'var(--cyan)',
              fontWeight: 700, fontSize: 14,
            }}
          >
            {refreshing ? 'Aktualisiere...' : 'Deals jetzt aktualisieren'}
          </button>
          {refreshMsg && (
            <div style={{ fontSize: 13, color: 'var(--green)', textAlign: 'center', marginTop: 8 }}>
              {refreshMsg}
            </div>
          )}
          <div style={{ fontSize: 12, color: 'var(--muted)', textAlign: 'center', marginTop: 4 }}>
            Automatisch täglich um 03:00 Uhr
          </div>
        </Section>

        <Section title="Info">
          <div style={{ background: 'var(--bg-elev)', border: '1px solid var(--border)', borderRadius: 14, padding: '14px 15px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              ['Version', '1.0.0'],
              ['Datenquelle', 'CamelCamelCamel RSS'],
              ['Marktplatz', 'Amazon.de'],
              ['Affiliate', 'snagga-21'],
            ].map(([k, v]) => (
              <div key={k} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                <span style={{ color: 'var(--muted)' }}>{k}</span>
                <span style={{ color: 'var(--text)', fontWeight: 600 }}>{v}</span>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Rechtliches">
          <button
            onClick={onShowLegal}
            style={{
              width: '100%', padding: '12px 15px', borderRadius: 10,
              border: '1px solid var(--border)', background: 'var(--bg-elev)',
              color: 'var(--text)', fontWeight: 600, fontSize: 14,
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
            }}
          >
            <span>Impressum & Datenschutz</span>
            <span style={{ color: 'var(--muted)' }}>→</span>
          </button>
        </Section>

      </div>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <span style={{ fontSize: 11, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.7px', fontWeight: 700 }}>
        {title}
      </span>
      {children}
    </div>
  )
}
