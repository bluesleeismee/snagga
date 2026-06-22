import React, { useState, useEffect, useCallback } from 'react'
import DealsPage from './pages/DealsPage.jsx'
import LegalPage from './pages/LegalPage.jsx'

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

  return (
    <div style={{
      height: '100%',
      background: 'var(--bg)',
      color: 'var(--text)',
    }}>
      {showLegal ? (
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
