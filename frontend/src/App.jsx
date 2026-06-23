import React, { useState, useEffect, useCallback } from 'react'
import DealsPage from './pages/DealsPage.jsx'
import LegalPage from './pages/LegalPage.jsx'

function NotFoundPage() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', gap: 16, padding: 24, textAlign: 'center' }}>
      <span style={{ fontSize: 48 }}>🏷️</span>
      <div style={{ fontSize: 64, fontWeight: 800, color: 'var(--orange)', lineHeight: 1 }}>404</div>
      <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text)' }}>Diese Seite gibt's nicht</div>
      <div style={{ fontSize: 14, color: 'var(--muted)', maxWidth: 300 }}>
        Aber jede Menge Amazon-Deals schon.
      </div>
      <a href="/" style={{ marginTop: 8, padding: '10px 22px', borderRadius: 10, background: 'var(--orange)', color: '#fff', fontWeight: 600, fontSize: 14, textDecoration: 'none' }}>
        Zurück zu den Deals
      </a>
    </div>
  )
}

// ── localStorage helpers ─────────────────────────────────────────
const LS = {
  get: (k, fb) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : fb } catch { return fb } },
  set: (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)) } catch {} },
}

export default function App() {
  // Theme — light as default
  const [theme, setTheme] = useState(() => LS.get('dr_theme', 'light'))
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    LS.set('dr_theme', theme)
  }, [theme])

  // Watchlist (Set of ASINs)
  const [watchlist, setWatchlist] = useState(() => new Set(LS.get('dr_watch', [])))
  const toggleWatch = useCallback(asin => {
    setWatchlist(prev => {
      const next = new Set(prev)
      next.has(asin) ? next.delete(asin) : next.add(asin)
      LS.set('dr_watch', [...next])
      return next
    })
  }, [])

  const toggleTheme = () => setTheme(t => t === 'dark' ? 'light' : 'dark')

  const [showLegal, setShowLegal] = useState(false)
  const isNotFound = window.location.pathname !== '/'

  return (
    <div style={{
      height: '100%',
      background: 'var(--bg)',
      color: 'var(--text)',
    }}>
      {isNotFound ? (
        <NotFoundPage />
      ) : showLegal ? (
        <LegalPage onBack={() => setShowLegal(false)} />
      ) : (
        <DealsPage
          theme={theme}
          onToggleTheme={toggleTheme}
          watchlist={watchlist}
          onToggleWatch={toggleWatch}
          onShowLegal={() => setShowLegal(true)}
        />
      )}
    </div>
  )
}
